"""Reglas de perfil: normalización, filtro de nivel y zona, modalidad y puntuación.

Todo el criterio de "qué oferta me interesa" vive aquí, separado de las APIs,
para poder probarlo con tests sin llamar a ningún servicio.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone

DIAS_MAX = 30  # se descartan ofertas publicadas hace más días

ZONA_LOCAL = re.compile(r"\b(alicante|alacant|san vicente|sant vicent)\b")
ZONA_MADRID = re.compile(r"\bmadrid\b")

SENIOR = re.compile(r"\b(senior|sr|lead(?!\s+gen)|principal|director|directora|head of|jefe|jefa|vp)\b")
NIVEL_ALTO_FUENTE = re.compile(r"senior|lead|manager|director|executive|mid", re.I)
NUCLEO = re.compile(r"\b(data|datos|bi|business intelligence|analytics|analitica|reporting|insights?|power bi|tableau|dashboards?)\b")
ANALISTA = re.compile(r"\b(analyst|analista|trainee|becario|becaria|beca|intern|internship|practicas)\b")
HERRAMIENTAS = re.compile(r"\b(sql|power bi|powerbi|tableau|python|looker|dashboards?)\b")
TECNICO = re.compile(r"\b(engineer|ingeniero|ingeniera|scientist|developer|desarrollador|desarrolladora|architect|arquitecto|programmer|programador)\b")
EXPERIENCIA_ALTA = re.compile(r"\b([3-9]|1[0-9])\s*\+?\s*(anos|years)\b")
OBJETIVO = re.compile(
    r"\b(data analyst|analista de datos|bi analyst|business intelligence|reporting analyst|"
    r"insights analyst|data reporting|hr analytics|analista de rrhh)\b|\bpeople\b.*\banalytics\b"
)
ENTRADA = re.compile(r"\b(junior|jr|trainee|becario|becaria|beca|intern|internship|practicas|entry|graduate)\b")
HABILIDADES = [
    (re.compile(r"\bsql\b"), 10), (re.compile(r"\bpower ?bi\b"), 10), (re.compile(r"\bpython\b"), 10),
    (re.compile(r"\btableau\b"), 5), (re.compile(r"\bexcel\b"), 5), (re.compile(r"\b(pandas|numpy)\b"), 5),
    (re.compile(r"\b(people|rrhh|recursos humanos|hr)\b"), 5),
    (re.compile(r"\b(marketing|e ?commerce|ecommerce)\b"), 5),
]


# ---------------------------------------------------------------- utilidades
def quitar_acentos(s) -> str:
    texto = unicodedata.normalize("NFD", "" if s is None else str(s))
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def limpiar(s) -> str:
    x = quitar_acentos(s).lower()
    x = re.sub(r"<[^>]*>", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def norm_puesto(s) -> str:
    x = re.sub(r"[^a-z0-9+ ]", " ", limpiar(s))
    return re.sub(r"\s+", " ", x).strip()


def norm_empresa(s) -> str:
    x = re.sub(r"[^a-z0-9 ]", " ", limpiar(s))
    x = re.sub(r"\b(s ?l ?u?|s ?a ?u?|inc|llc|ltd|limited|gmbh|corp|co|group|grupo|spain|espana|iberia)\b", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def norm_url(u) -> str:
    x = str(u or "").split("?")[0].split("#")[0]
    return x.rstrip("/").lower()


def a_fecha(v) -> str:
    """Convierte timestamps (s o ms) o textos ISO en 'AAAA-MM-DD'. Devuelve '' si no se puede."""
    if v is None or v == "":
        return ""
    try:
        if isinstance(v, (int, float)):
            seg = v / 1000 if v >= 1e12 else v
            return datetime.fromtimestamp(seg, tz=timezone.utc).date().isoformat()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ""


_UNIDADES = {"minuto": 1 / 1440, "minute": 1 / 1440, "hora": 1 / 24, "hour": 1 / 24,
             "dia": 1, "day": 1, "semana": 7, "week": 7, "mes": 30, "month": 30}


def fecha_relativa(s, hoy: date) -> str:
    """'hace 6 días' / '3 hours ago' -> 'AAAA-MM-DD'."""
    x = re.sub(r"\b(un|una|a|an)\b", "1", limpiar(s))
    m = re.search(r"(\d+)\+?\s*(minuto|hora|dia|semana|mes|minute|hour|day|week|month)", x)
    if not m:
        return ""
    return (hoy - timedelta(days=int(m.group(1)) * _UNIDADES[m.group(2)])).isoformat()


def modalidad_desde_texto(texto) -> str:
    x = limpiar(texto)
    if re.search(r"\b(hibrido|hibrida|hybrid)\b", x):
        return "Híbrido"
    if re.search(r"\b(remoto|remota|teletrabajo|remote)\b", x):
        return "Remoto"
    if re.search(r"\bpresencial\b", x):
        return "Presencial"
    return "No especificada"


# ---------------------------------------------------------------- criterio
def clasificar(o: dict) -> tuple[str, str]:
    """Devuelve (estado, motivo): 'pendiente', 'revisar' o 'descartar'."""
    t = norm_puesto(o.get("puesto"))
    d = limpiar(o.get("descripcion"))
    sen = str(o.get("seniority_fuente") or "")
    if SENIOR.search(t):
        return "descartar", "título sénior"
    if NIVEL_ALTO_FUENTE.search(sen):
        return "descartar", f"nivel de la fuente: {sen}"
    nucleo = bool(NUCLEO.search(t))
    if not nucleo and not (ANALISTA.search(t) and HERRAMIENTAS.search(d)):
        return "descartar", "puesto sin relación con datos"
    motivos = []
    if not nucleo:
        motivos.append("título poco claro")
    if TECNICO.search(t) and not re.search(r"\b(analyst|analista)\b", t):
        motivos.append("perfil más técnico")
    if re.search(r"\b(programmer|programador|developer|desarrollador)\b", t):
        motivos.append("perfil de desarrollo")
    if re.search(r"\bmanager\b", t):
        motivos.append("puesto de manager")
    if EXPERIENCIA_ALTA.search(d):
        motivos.append("pide 3 o más años")
    if re.search(r"\bsenior\b", d):
        motivos.append("la descripción menciona senior")
    return ("revisar", ", ".join(motivos)) if motivos else ("pendiente", "")


def aplicar_zona(o: dict, estado: str, motivo: str) -> tuple[str, str]:
    """Alicante/San Vicente: cualquier modalidad. Madrid: remoto o híbrido. Resto: solo remoto."""
    if estado == "descartar" or o.get("modalidad") == "Remoto":
        return estado, motivo
    u = limpiar(o.get("ubicacion"))
    if ZONA_LOCAL.search(u):
        return estado, motivo
    if ZONA_MADRID.search(u):
        if o.get("modalidad") == "Híbrido":
            return estado, motivo
        if o.get("modalidad") == "No especificada":
            return "revisar", ", ".join(filter(None, [motivo, "Madrid: modalidad sin confirmar"]))
        return "descartar", "Madrid presencial"
    return "descartar", "fuera de zona y no remota"


def puntuar(o: dict, estado: str) -> int:
    """Encaje 0-100: puesto objetivo, nivel de entrada, herramientas y zona."""
    t = norm_puesto(o.get("puesto"))
    d = limpiar(o.get("descripcion"))
    p = 0
    if OBJETIVO.search(t):
        p += 30
    elif NUCLEO.search(t):
        p += 15
    if ENTRADA.search(f"{t} {limpiar(o.get('seniority_fuente'))}"):
        p += 15
    for patron, valor in HABILIDADES:
        if patron.search(t) or patron.search(d):
            p += valor
    if ZONA_LOCAL.search(limpiar(o.get("ubicacion"))):
        p += 10
    elif o.get("modalidad") == "Remoto":
        p += 5
    if estado == "revisar":
        p -= 15
    return max(0, min(100, p))


def procesar(brutas: list[dict], hoy: date | None = None) -> list[dict]:
    """Normaliza y evalúa todas las ofertas. Devuelve también las descartadas (para el registro)."""
    hoy = hoy or date.today()
    salida = []
    for o in brutas:
        if not o.get("puesto") or not o.get("empresa"):
            continue
        fecha_pub = a_fecha(o.get("fecha"))
        if fecha_pub and (hoy - date.fromisoformat(fecha_pub)).days > DIAS_MAX:
            estado, motivo = "descartar", f"publicada hace más de {DIAS_MAX} días"
        else:
            estado, motivo = aplicar_zona(o, *clasificar(o))
        notas = " · ".join(filter(None, [
            f"Revisar: {motivo}" if estado == "revisar" else "",
            "" if fecha_pub else "Fecha de publicación no disponible: se usa la de captura",
        ]))
        salida.append({
            "empresa": str(o["empresa"]).strip(),
            "puesto": str(o["puesto"]).strip(),
            "ubicacion": str(o.get("ubicacion") or "").strip(),
            "modalidad": o.get("modalidad") or "No especificada",
            "canal": o.get("canal", ""),
            "estado": estado,
            "motivo": motivo,
            "puntuacion": puntuar(o, estado) if estado != "descartar" else 0,
            "notas": notas,
            "url_oferta": o.get("url") or "",
            "url_normalizada": norm_url(o.get("url")),
            "clave": f"{norm_empresa(o['empresa'])}|{norm_puesto(o['puesto'])}",
            "fecha_publicacion": fecha_pub or hoy.isoformat(),
            "fecha_captura": hoy.isoformat(),
        })
    salida.sort(key=lambda x: x["puntuacion"], reverse=True)
    return salida


def deduplicar(ofertas: list[dict], existentes: list[dict], exclusiones: list[tuple[str, str]]):
    """Separa las ofertas nuevas de las ya conocidas.

    Una oferta se considera conocida si coincide su URL (sin parámetros) o la pareja
    empresa + puesto con una candidatura de Notion, con la lista de exclusiones o con
    otra oferta de la misma ejecución.
    """
    urls = {norm_url(p.get("url")) for p in existentes if p.get("url")}
    claves = {f"{norm_empresa(e)}|{norm_puesto(t)}" for e, t in exclusiones}
    claves |= {f"{norm_empresa(p.get('empresa'))}|{norm_puesto(p.get('puesto'))}"
               for p in existentes if p.get("empresa") and p.get("puesto")}
    nuevas, repetidas = [], []
    for o in ofertas:
        if (o["url_normalizada"] and o["url_normalizada"] in urls) or o["clave"] in claves:
            repetidas.append(o)
            continue
        if o["url_normalizada"]:
            urls.add(o["url_normalizada"])
        claves.add(o["clave"])
        nuevas.append(o)
    return nuevas, repetidas
