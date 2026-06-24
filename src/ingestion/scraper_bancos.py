"""
scraper_bancos.py — Descarga boletines BCU para grupos del sistema bancario y financiero.

Grupos descargados:
  grupo99   — BANCOS OFICIALES (BROU, BHU)              → data/raw/bancos_oficiales/
  grupo997  — BANCOS PRIVADOS (Itaú, Santander, BBVA…)  → data/raw/bancos/
  grupo996  — COOPERATIVAS DE INTERMEDIACIÓN FINANCIERA  → data/raw/cooperativos_intermediacion_financiera/
  grupo998  — CASAS FINANCIERAS (Provincia)              → data/raw/casas_financieras/

Misma URL y estructura XLS que grupo981.

Ver decisiones.md para el detalle del SSL verify=False.
"""

import logging
import time
from datetime import date
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BASE_URL = "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF"

# Carpeta de destino por grupo
GRUPOS_DIRS = {
    "grupo99":  ROOT_DIR / "data" / "raw" / "bancos_oficiales",
    "grupo997": ROOT_DIR / "data" / "raw" / "bancos",
    "grupo996": ROOT_DIR / "data" / "raw" / "cooperativos_intermediacion_financiera",
    "grupo998": ROOT_DIR / "data" / "raw" / "casas_financieras",
}

_NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre",
]
_INICIO = (2024, 4)  # Abril 2024 — primer mes disponible en el BCU


def _generar_meses():
    """Genera la lista de (año, mes_nombre) desde el inicio hasta el mes anterior al actual."""
    hoy = date.today()
    if hoy.month == 1:
        hasta = (hoy.year - 1, 12)
    else:
        hasta = (hoy.year, hoy.month - 1)

    resultado = []
    año, mes = _INICIO
    while (año, mes) <= hasta:
        resultado.append((str(año), _NOMBRES_MESES[mes - 1]))
        mes += 1
        if mes > 12:
            mes = 1
            año += 1
    return resultado


MESES = _generar_meses()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/vnd.ms-excel,*/*",
    "Accept-Language": "es-UY,es;q=0.9",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def descargar_todos(force: bool = False) -> dict:
    for raw_dir in GRUPOS_DIRS.values():
        raw_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    resultados = {"ok": [], "skip": [], "fail": []}

    for grupo, raw_dir in GRUPOS_DIRS.items():
        for anio, mes in MESES:
            destino = raw_dir / f"{grupo}_{anio}_{mes}.xls"

            if destino.exists() and not force:
                log.info("[skip]  %s %s/%s", grupo, anio, mes)
                resultados["skip"].append((grupo, anio, mes))
                continue

            indice_url = f"{BASE_URL}/{anio}/{mes}/indice.htm"
            xls_url = f"{BASE_URL}/{anio}/{mes}/{grupo}.xls"

            try:
                session.get(indice_url, timeout=15, verify=False)
            except Exception:
                pass

            session.headers["Referer"] = indice_url
            log.info("[fetch] %s %s/%s ...", grupo, anio, mes)

            try:
                r = session.get(xls_url, timeout=30, verify=False)
                if r.status_code == 200 and len(r.content) > 5_000:
                    destino.write_bytes(r.content)
                    log.info("[ok]    %s %s/%s — %d KB", grupo, anio, mes, len(r.content) // 1024)
                    resultados["ok"].append((grupo, anio, mes))
                elif r.status_code == 404:
                    log.info("[404]   %s %s/%s — no publicado", grupo, anio, mes)
                    resultados["fail"].append((grupo, anio, mes))
                else:
                    log.warning("[err]   %s %s/%s — HTTP %d", grupo, anio, mes, r.status_code)
                    resultados["fail"].append((grupo, anio, mes))
            except Exception as exc:
                log.error("[exc]   %s %s/%s — %s", grupo, anio, mes, exc)
                resultados["fail"].append((grupo, anio, mes))

            time.sleep(0.3)

    log.info("─" * 50)
    log.info("Descargados:    %d", len(resultados["ok"]))
    log.info("Ya existían:    %d", len(resultados["skip"]))
    log.info("No disponibles: %d", len(resultados["fail"]))

    return resultados


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    descargar_todos(force=args.force)
