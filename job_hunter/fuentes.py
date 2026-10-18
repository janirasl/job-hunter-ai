"""Conectores a las APIs de empleo.

Cada función devuelve una lista de ofertas "en bruto" con el mismo formato:
canal, empresa, puesto, descripcion, ubicacion, url, fecha, modalidad, seniority_fuente.
Si una fuente falla (sin clave, cupo agotado, caída), se registra el aviso y se
devuelve una lista vacía: el resto de fuentes sigue funcionando.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import requests

from .reglas import fecha_relativa, limpiar, modalidad_desde_texto

log = logging.getLogger(__name__)
TIMEOUT = 30

# ------------------------------------------------------------- búsquedas
BUSQUEDAS_ADZUNA = [
    ("analista de datos", "Alicante"),
    ("data analyst", "Alicante"),
    ("business intelligence", "Alicante"),
    ("data analyst", "Madrid"),  # solo pasarán las remotas o híbridas
]

# JSearch (plan gratuito: 200 peticiones/mes). 4 búsquedas x 22 días laborables = ~88.
# "via linkedin" hace que Google for Jobs priorice ofertas publicadas en LinkedIn.
BUSQUEDAS_JSEARCH = [
    ("data analyst Alicante", False),
    ("business intelligence analyst Alicante via linkedin", False),
    ("data analyst Madrid via linkedin", False),
    ("junior data analyst España via linkedin", True),
]

BUSQUEDAS_INFOJOBS = [
    ("analista de datos", "alicante"),
    ("data analyst", "alicante"),
    ("business intelligence", "alicante"),
    ("people analytics", None),
    ("analista de datos teletrabajo", None),
]


def _get(url, **kwargs) -> dict:
    r = requests.get(url, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ Adzuna
def adzuna(app_id: str | None, app_key: str | None) -> list[dict]:
    if not (app_id and app_key):
        log.warning("Adzuna: faltan ADZUNA_APP_ID / ADZUNA_APP_KEY, se omite")
        return []
    ofertas = []
    for what, where in BUSQUEDAS_ADZUNA:
        try:
            datos = _get("https://api.adzuna.com/v1/api/jobs/es/search/1", params={
                "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                "what": what, "where": where, "distance": 20, "max_days_old": 30, "sort_by": "date",
            })
        except requests.RequestException as e:
            log.warning("Adzuna '%s' en %s falló: %s", what, where, e)
            continue
        for j in datos.get("results", []):
            ofertas.append({
                "canal": "adzuna",
                "empresa": (j.get("company") or {}).get("display_name"),
                "puesto": j.get("title"),
                "descripcion": j.get("description"),
                "ubicacion": (j.get("location") or {}).get("display_name"),
                "url": j.get("redirect_url"),
                "fecha": j.get("created"),
                "modalidad": modalidad_desde_texto(f"{j.get('title', '')} {j.get('description', '')}"),
            })
    return ofertas


# --------------------------------------------------------------- Himalayas
def himalayas() -> list[dict]:
    """Solo ofertas remotas. Sin clave."""
    try:
        datos = _get("https://himalayas.app/jobs/api/search",
                     params={"q": "data analyst", "country": "Spain", "sort": "recent"})
    except requests.RequestException as e:
        log.warning("Himalayas falló: %s", e)
        return []
    ofertas = []
    for j in datos.get("jobs", []):
        zonas = j.get("locationRestrictions") or []
        sen = j.get("seniority")
        ofertas.append({
            "canal": "himalayas",
            "empresa": j.get("companyName"),
            "puesto": j.get("title"),
            "descripcion": f"{j.get('excerpt') or ''} {j.get('description') or ''}",
            "ubicacion": f"Remoto ({', '.join(zonas)})" if zonas else "Remoto (sin restricción)",
            "url": j.get("applicationLink") or j.get("guid"),
            "fecha": j.get("pubDate"),
            "modalidad": "Remoto",
            "seniority_fuente": ", ".join(sen) if isinstance(sen, list) else sen,
        })
    return ofertas


# ----------------------------------------------------------------- JSearch
def jsearch(rapidapi_key: str | None, hoy: date | None = None) -> list[dict]:
    """Google for Jobs (LinkedIn, Indeed, Glassdoor…). Cada búsqueda gasta 1 petición."""
    if not rapidapi_key:
        log.warning("JSearch: falta RAPIDAPI_KEY, se omite")
        return []
    hoy = hoy or date.today()
    ofertas = []
    for i, (query, remoto) in enumerate(BUSQUEDAS_JSEARCH):
        if i:
            time.sleep(2)  # sin pausa, la API responde 429 a las peticiones simultáneas
        try:
            datos = _get("https://jsearch.p.rapidapi.com/search-v2",
                         headers={"x-rapidapi-key": rapidapi_key, "x-rapidapi-host": "jsearch.p.rapidapi.com"},
                         params={"query": query, "country": "es", "date_posted": "week",
                                 "num_pages": 1, "work_from_home": str(remoto).lower()})
        except requests.RequestException as e:
            log.warning("JSearch '%s' falló: %s", query, e)
            continue
        data = datos.get("data")
        lista = data if isinstance(data, list) else (data or {}).get("jobs", [])
        for j in lista:
            # job_location llega como "Alicante  •  a través de Jooble"
            lugar = (", ".join(filter(None, [j.get("job_city"), j.get("job_state")]))
                     or str(j.get("job_location") or "").split("•")[0]
                     or j.get("job_country") or "").strip()
            publisher = j.get("job_publisher")
            ofertas.append({
                "canal": f"jsearch · {publisher}" if publisher else "jsearch",
                "empresa": j.get("employer_name"),
                "puesto": j.get("job_title"),
                "descripcion": j.get("job_description"),
                "ubicacion": lugar,
                "url": j.get("job_apply_link") or j.get("job_google_link"),
                "fecha": (j.get("job_posted_at_datetime_utc") or j.get("job_posted_at_timestamp")
                          or fecha_relativa(j.get("job_posted_at"), hoy)),
                "modalidad": "Remoto" if j.get("job_is_remote")
                else modalidad_desde_texto(f"{j.get('job_title', '')} {j.get('job_description', '')}"),
            })
    return ofertas


# ---------------------------------------------------------------- InfoJobs
def _modalidad_infojobs(valor) -> str:
    x = limpiar(valor)
    if "hibrid" in x:
        return "Híbrido"
    if "teletrabajo" in x or "remot" in x:
        return "Remoto"
    if "presencial" in x:
        return "Presencial"
    return "No especificada"


def infojobs(client_id: str | None, client_secret: str | None) -> list[dict]:
    """API oficial de InfoJobs (autenticación de aplicación, sin login de usuario).

    Pendiente de verificar con credenciales reales: los nombres exactos de algunos
    campos (teleworking, experienceMin) pueden variar según la versión de la API.
    """
    if not (client_id and client_secret):
        log.warning("InfoJobs: faltan INFOJOBS_CLIENT_ID / INFOJOBS_CLIENT_SECRET, se omite")
        return []
    ofertas = []
    for q, provincia in BUSQUEDAS_INFOJOBS:
        params = {"q": q, "maxResults": 50, "sinceDate": "_7_DAYS", "order": "updated-desc"}
        if provincia:
            params["province"] = provincia
        try:
            datos = _get("https://api.infojobs.net/api/9/offer", params=params,
                         auth=(client_id, client_secret))
        except requests.RequestException as e:
            log.warning("InfoJobs '%s' falló: %s", q, e)
            continue
        for j in datos.get("offers", []):
            provincia_txt = (j.get("province") or {}).get("value", "")
            experiencia = (j.get("experienceMin") or {}).get("value", "")
            tele = (j.get("teleworking") or {}).get("value", "")
            ofertas.append({
                "canal": "infojobs",
                "empresa": (j.get("author") or {}).get("name"),
                "puesto": j.get("title"),
                # la experiencia mínima va a la descripción para que la regla "3 o más años" la detecte
                "descripcion": f"{j.get('requirementMin') or ''} Experiencia: {experiencia}",
                "ubicacion": ", ".join(filter(None, [j.get("city"), provincia_txt])),
                "url": j.get("link"),
                "fecha": j.get("published") or j.get("updated"),
                "modalidad": _modalidad_infojobs(tele) if tele
                else modalidad_desde_texto(f"{j.get('title', '')} {j.get('requirementMin') or ''}"),
            })
    return ofertas
