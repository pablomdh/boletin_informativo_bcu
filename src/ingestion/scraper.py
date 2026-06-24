"""
scraper.py — Descarga boletines BCU grupo981.xls

Fuente: https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin SSF/{AÑO}/{Mes}/grupo981.xls
Rango: Abril 2024 → mes anterior al actual (generado dinámicamente)

Guarda los archivos en data/raw/grupo981_{AÑO}_{Mes}.xls
"""

import logging
import time
from datetime import date
from pathlib import Path

import requests
import urllib3

# El BCU usa una cadena de certificados que Python/macOS no verifica por defecto.
# Se deshabilita la verificación SSL para este dominio público.
# Ver contexto/decisiones.md para detalle.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw" / "administratoras_de_credito"

BASE_URL = "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF"

_NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre",
]
_INICIO = (2024, 4)  # Abril 2024 — primer mes disponible en el BCU


def _generar_meses():
    """Genera la lista de (año, mes_nombre) desde el inicio hasta el mes anterior al actual."""
    hoy = date.today()
    # Mes anterior: si estamos en enero, retrocede al diciembre del año anterior
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
    """
    Descarga todos los boletines disponibles.

    Args:
        force: Si True, re-descarga aunque el archivo ya exista.

    Returns:
        dict con listas 'ok', 'skip', 'fail'
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)

    resultados = {"ok": [], "skip": [], "fail": []}

    for anio, mes in MESES:
        destino = RAW_DIR / f"grupo981_{anio}_{mes}.xls"

        if destino.exists() and not force:
            log.info("[skip]  %s/%s — ya existe", anio, mes)
            resultados["skip"].append((anio, mes))
            continue

        indice_url = f"{BASE_URL}/{anio}/{mes}/indice.htm"
        xls_url = f"{BASE_URL}/{anio}/{mes}/grupo981.xls"

        # Visitar el índice para obtener cookies de sesión
        try:
            session.get(indice_url, timeout=15, verify=False)
        except Exception:
            pass  # El índice puede no existir; seguimos igual

        session.headers["Referer"] = indice_url
        log.info("[fetch] %s/%s ...", anio, mes)

        try:
            r = session.get(xls_url, timeout=30, verify=False)
            if r.status_code == 200 and len(r.content) > 5_000:
                destino.write_bytes(r.content)
                log.info("[ok]    %s/%s — %d KB", anio, mes, len(r.content) // 1024)
                resultados["ok"].append((anio, mes))
            elif r.status_code == 404:
                log.info("[404]   %s/%s — no publicado aún", anio, mes)
                resultados["fail"].append((anio, mes))
            else:
                log.warning("[err]   %s/%s — HTTP %d", anio, mes, r.status_code)
                resultados["fail"].append((anio, mes))
        except Exception as exc:
            log.error("[exc]   %s/%s — %s", anio, mes, exc)
            resultados["fail"].append((anio, mes))

        time.sleep(0.5)

    log.info("─" * 50)
    log.info("Descargados:    %d", len(resultados["ok"]))
    log.info("Ya existían:    %d", len(resultados["skip"]))
    log.info("No disponibles: %d", len(resultados["fail"]))
    log.info("Archivos en:    %s", RAW_DIR.resolve())

    return resultados


if __name__ == "__main__":
    descargar_todos()
