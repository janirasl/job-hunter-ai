"""Lectura y escritura en la base Candidaturas de Notion (API REST oficial)."""
from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _texto(prop: dict | None) -> str:
    """Extrae el texto plano de una propiedad de Notion, sea del tipo que sea."""
    if not prop:
        return ""
    tipo = prop.get("type")
    valor = prop.get(tipo)
    if tipo in ("title", "rich_text"):
        return "".join(t.get("plain_text", "") for t in valor or [])
    if tipo == "select":
        return (valor or {}).get("name", "")
    if tipo in ("url", "email", "phone_number"):
        return valor or ""
    return ""


class Notion:
    def __init__(self, token: str, database_id: str):
        self.database_id = database_id
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "Notion-Version": VERSION,
            "Content-Type": "application/json",
        })

    def _post(self, ruta: str, cuerpo: dict) -> dict:
        for intento in range(3):
            r = self.s.post(f"{API}{ruta}", json=cuerpo, timeout=30)
            if r.status_code == 429:  # límite de Notion: ~3 peticiones/segundo
                time.sleep(float(r.headers.get("Retry-After", 1)) * (intento + 1))
                continue
            if not r.ok:
                raise RuntimeError(f"Notion {r.status_code}: {r.text[:300]}")
            return r.json()
        raise RuntimeError("Notion: demasiadas peticiones seguidas")

    def leer_candidaturas(self) -> list[dict]:
        """Devuelve TODAS las páginas (paginando de 100 en 100) como {empresa, puesto, url}."""
        paginas, cursor = [], None
        while True:
            cuerpo = {"page_size": 100}
            if cursor:
                cuerpo["start_cursor"] = cursor
            datos = self._post(f"/databases/{self.database_id}/query", cuerpo)
            for p in datos.get("results", []):
                props = p.get("properties", {})
                paginas.append({
                    "empresa": _texto(props.get("Empresa")),
                    "puesto": _texto(props.get("Puesto")),
                    "url": _texto(props.get("url oferta")),
                })
            if not datos.get("has_more"):
                return paginas
            cursor = datos.get("next_cursor")

    def crear_candidatura(self, o: dict) -> None:
        def texto(v):
            return {"rich_text": [{"text": {"content": str(v)[:2000]}}]}

        props = {
            "Empresa": {"title": [{"text": {"content": o["empresa"][:2000]}}]},
            "Puesto": texto(o["puesto"]),
            "Ubicación": texto(o["ubicacion"]),
            "Canal": texto(o["canal"]),
            "Estado": texto(o["estado"]),
            "Notas": texto(o["notas"]),
            "Modalidad": {"select": {"name": o["modalidad"]}},
            "Puntuación": {"number": o["puntuacion"]},
            "Fecha captura": {"date": {"start": o["fecha_captura"]}},
            "Fecha publicación": {"date": {"start": o["fecha_publicacion"]}},
        }
        if o.get("url_oferta"):
            props["url oferta"] = {"url": o["url_oferta"]}
        self._post("/pages", {"parent": {"database_id": self.database_id}, "properties": props})
        time.sleep(0.35)  # margen para el límite de Notion
