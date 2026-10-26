"""Job Hunter AI: capta ofertas, las filtra según tu perfil y guarda las nuevas en Notion.

Uso:
    python -m job_hunter.main             # ejecución normal
    python -m job_hunter.main --dry-run   # no escribe en Notion, solo muestra qué haría
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import os
from collections import Counter
from datetime import date
from pathlib import Path

from . import fuentes
from .notion import Notion
from .reglas import deduplicar, procesar

RAIZ = Path(__file__).resolve().parent.parent
REGISTRO = RAIZ / "data" / "capturas.csv"
EXCLUSIONES = RAIZ / "exclusiones.csv"
NOTION_DB_POR_DEFECTO = "3f4d42bb849381b2a3eeee254216409a"  # base Candidaturas

COLUMNAS_REGISTRO = ["fecha_captura", "canal", "empresa", "puesto", "ubicacion", "modalidad",
                     "estado", "motivo", "puntuacion", "fecha_publicacion", "resultado", "url_oferta"]

log = logging.getLogger("job_hunter")


def cargar_env_local() -> None:
    """Lee un .env local (solo para ejecutar en tu ordenador; en GitHub se usan Secrets)."""
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def cargar_exclusiones() -> list[tuple[str, str]]:
    """Candidaturas que gestionas fuera del sistema (CSV con columnas Empresa,Puesto)."""
    contenido = os.getenv("EXCLUSIONES_CSV") or (
        EXCLUSIONES.read_text(encoding="utf-8") if EXCLUSIONES.exists() else "")
    filas = csv.DictReader(io.StringIO(contenido))
    return [(f["Empresa"], f["Puesto"]) for f in filas if f.get("Empresa") and f.get("Puesto")]


def cargar_historico() -> list[dict]:
    """Ofertas que el sistema ya guardó alguna vez en Notion.

    Sirve de memoria: si borras una oferta en Notion porque no te interesa,
    no vuelve a entrar en la siguiente ejecución.
    """
    if not REGISTRO.exists():
        return []
    with REGISTRO.open(encoding="utf-8") as f:
        return [{"empresa": r["empresa"], "puesto": r["puesto"], "url": r["url_oferta"]}
                for r in csv.DictReader(f) if r.get("resultado") == "nueva"]


def guardar_registro(filas: list[dict]) -> None:
    """Histórico de TODO lo captado (también lo descartado): fuente para el dashboard."""
    REGISTRO.parent.mkdir(exist_ok=True)
    nuevo = not REGISTRO.exists()
    with REGISTRO.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_REGISTRO, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerows(filas)


def escribir_resumen(nuevas: list[dict], total: int, por_resultado: Counter, dry_run: bool) -> None:
    """Resumen en la página de la ejecución de GitHub Actions."""
    lineas = [
        f"## Job Hunter AI · {date.today():%d/%m/%Y}" + (" (simulación)" if dry_run else ""),
        f"Captadas: **{total}** · nuevas: **{por_resultado['nueva']}** · "
        f"ya conocidas: {por_resultado['repetida']} · descartadas: {por_resultado['descartada']}",
        "",
    ]
    if nuevas:
        lineas += ["| Puntos | Puesto | Empresa | Ubicación | Estado |", "|---|---|---|---|---|"]
        for o in nuevas:
            puesto = f"[{o['puesto']}]({o['url_oferta']})" if o["url_oferta"] else o["puesto"]
            lineas.append(f"| {o['puntuacion']} | {puesto} | {o['empresa']} | {o['ubicacion']} | {o['estado']} |")
    texto = "\n".join(lineas)
    print(texto)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="no escribe en Notion")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cargar_env_local()
    dry_run = args.dry_run or os.getenv("DRY_RUN", "").lower() == "true"

    # 1. Captar
    brutas = (fuentes.adzuna(os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY"))
              + fuentes.himalayas()
              + fuentes.jsearch(os.getenv("RAPIDAPI_KEY"))
              + fuentes.infojobs(os.getenv("INFOJOBS_CLIENT_ID"), os.getenv("INFOJOBS_CLIENT_SECRET")))
    log.info("Captadas %d ofertas: %s", len(brutas), dict(Counter(o["canal"].split(" ·")[0] for o in brutas)))

    # 2. Filtrar y puntuar
    evaluadas = procesar(brutas)
    validas = [o for o in evaluadas if o["estado"] != "descartar"]

    # 3. Deduplicar contra Notion y la lista de exclusiones
    token = os.getenv("NOTION_TOKEN")
    notion = Notion(token, os.getenv("NOTION_DATABASE_ID") or NOTION_DB_POR_DEFECTO) if token else None
    if notion is None and not dry_run:
        log.error("Falta NOTION_TOKEN: no se puede deduplicar ni guardar. Usa --dry-run para probar sin Notion.")
        return 1
    en_notion = notion.leer_candidaturas() if notion else []
    historico = cargar_historico()
    log.info("Candidaturas en Notion: %d · ya guardadas alguna vez: %d", len(en_notion), len(historico))
    existentes = en_notion + historico
    nuevas, repetidas = deduplicar(validas, existentes, cargar_exclusiones())

    # 4. Guardar
    if not dry_run:
        for o in nuevas:
            notion.crear_candidatura(o)
    ids_nuevas, ids_repetidas = {id(o) for o in nuevas}, {id(o) for o in repetidas}
    for o in evaluadas:
        o["resultado"] = ("nueva" if id(o) in ids_nuevas else
                          "repetida" if id(o) in ids_repetidas else "descartada")
    if not dry_run:
        guardar_registro(evaluadas)

    escribir_resumen(nuevas, len(evaluadas), Counter(o["resultado"] for o in evaluadas), dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
