from datetime import date

from job_hunter.reglas import a_fecha, deduplicar, fecha_relativa, modalidad_desde_texto, norm_empresa, procesar

HOY = date(2026, 10, 18)


def oferta(**kw):
    base = {"canal": "test", "empresa": "Acme", "puesto": "Data Analyst", "descripcion": "",
            "ubicacion": "Alicante", "url": "https://x.com/1", "fecha": "2026-10-15", "modalidad": "Presencial"}
    return {**base, **kw}


def uno(**kw):
    return procesar([oferta(**kw)], HOY)[0]


def test_senior_en_titulo_se_descarta_aunque_lleve_tilde():
    assert uno(puesto="Senior Data Analyst")["estado"] == "descartar"
    assert uno(puesto="Analista de Datos Sénior")["estado"] == "descartar"


def test_lead_generation_no_es_lead():
    assert uno(puesto="Lead Generation Data Analyst")["estado"] != "descartar"


def test_nivel_mid_de_la_fuente_se_descarta():
    assert uno(seniority_fuente="Mid-level", modalidad="Remoto")["estado"] == "descartar"


def test_puesto_sin_datos_se_descarta():
    assert uno(puesto="Camarero/a")["estado"] == "descartar"
    assert uno(puesto="Remote analyst", descripcion="financial modeling")["estado"] == "descartar"


def test_analista_sin_datos_en_titulo_pasa_si_pide_herramientas():
    o = uno(puesto="Analista junior", descripcion="SQL y Power BI")
    assert o["estado"] == "revisar" and "título poco claro" in o["motivo"]


def test_experiencia_alta_se_descarta():
    assert uno(descripcion="Se requieren 3 años de experiencia")["estado"] == "descartar"
    assert uno(descripcion="5+ years of experience")["estado"] == "descartar"
    assert uno(descripcion="De 0 a 2 años de experiencia")["estado"] == "pendiente"


def test_nivel_numerado_se_descarta():
    assert uno(puesto="Data Analyst III (Remote)", modalidad="Remoto")["estado"] == "descartar"
    assert uno(puesto="Data Analyst II - Regulatory Reporting")["estado"] == "descartar"
    assert uno(puesto="Data Analyst Intern")["estado"] == "pendiente"


def test_perfil_tecnico_sin_analista_se_descarta():
    assert uno(puesto="Data Scientist - Analytics")["estado"] == "descartar"
    assert uno(puesto="Ingeniero de Datos")["estado"] == "descartar"
    assert uno(puesto="BI Developer / Data Analyst")["estado"] == "revisar"


def test_zonas():
    assert uno(ubicacion="San Vicente del Raspeig", modalidad="Presencial")["estado"] == "pendiente"
    assert uno(ubicacion="Madrid", modalidad="Presencial")["estado"] == "descartar"
    assert uno(ubicacion="Madrid", modalidad="Híbrido")["estado"] == "pendiente"
    assert uno(ubicacion="Madrid", modalidad="No especificada")["estado"] == "descartar"
    assert uno(ubicacion="Valencia", modalidad="Presencial")["estado"] == "descartar"
    assert uno(ubicacion="Sevilla", modalidad="Remoto")["estado"] == "pendiente"


def test_ofertas_antiguas_se_descartan():
    o = uno(fecha="2026-08-01")
    assert o["estado"] == "descartar" and "30 días" in o["motivo"]


def test_puntuacion_premia_encaje():
    buena = uno(puesto="Analista de Datos Junior", descripcion="SQL, Power BI y Python")
    floja = uno(puesto="Data Analyst", descripcion="Spark")
    assert buena["puntuacion"] == 85
    assert buena["puntuacion"] > floja["puntuacion"]
    assert uno(puesto="People Rewards Analytics Specialist")["puntuacion"] >= 30


def test_modalidad_y_fechas():
    assert modalidad_desde_texto("Modalidad híbrida, 2 días") == "Híbrido"
    assert modalidad_desde_texto("Oficina en el centro") == "No especificada"
    assert modalidad_desde_texto("Data Analyst - Madrid Homebased") == "Remoto"
    assert fecha_relativa("hace 6 días", HOY) == "2026-10-12"
    assert fecha_relativa("hace un día", HOY) == "2026-10-17"
    assert a_fecha(1792154947) == "2026-10-16"       # segundos
    assert a_fecha(1792154947000) == "2026-10-16"    # milisegundos
    assert a_fecha("2026-10-13T09:00:00.000Z") == "2026-10-13"
    assert a_fecha("basura") == ""


def test_norm_empresa_ignora_forma_juridica():
    assert norm_empresa("Acme S.L.") == norm_empresa("Acme Inc") == norm_empresa("ACME, SL") == "acme"


def test_deduplicar_por_url_clave_exclusiones_y_misma_ejecucion():
    ofertas = procesar([
        oferta(empresa="Talan", url="https://himalayas.app/talan?utm=1"),      # misma URL que Notion
        oferta(empresa="Excelia", puesto="Junior Data Analyst", url="https://y/1"),  # misma empresa+puesto
        oferta(empresa="PrimeIT", puesto="Junior Data Analyst", url="https://y/2"),  # en exclusiones
        oferta(empresa="Acme S.L.", url="https://a/1"),                        # nueva
        oferta(empresa="Acme Inc", url="https://b/1"),                         # repetida en la ejecución
    ], HOY)
    existentes = [{"empresa": "Otra", "puesto": "X", "url": "https://himalayas.app/talan"},
                  {"empresa": "Excelia", "puesto": "Junior Data Analyst", "url": ""}]
    nuevas, repetidas = deduplicar(ofertas, existentes, [("PrimeIT", "Junior Data Analyst")])
    assert [o["empresa"] for o in nuevas] == ["Acme S.L."]
    assert len(repetidas) == 4


def test_deduplicar_con_notion_vacio():
    nuevas, repetidas = deduplicar(procesar([oferta()], HOY), [], [])
    assert len(nuevas) == 1 and not repetidas
