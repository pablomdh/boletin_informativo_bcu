"""
main.py — Orquestador del pipeline BCU Analysis

Pipeline:
  1. scraper.py       — descarga boletines .xls del BCU → data/raw/
  2. parser.py        — parsea los .xls → data/processed/serie_temporal.csv
  3. indicadores.py   — calcula ratios → data/processed/indicadores.csv + plazos.csv
  4. analysis.py      — gráficos matplotlib → output/0*.png
  5. dashboard_gen.py — dashboard Plotly → output/dashboards/dashboard_interactivo.html
  6. resumen_md_gen.py— resumen ejecutivo → output/reports/resumen_ejecutivo.md

Uso:
  python main.py              # pipeline completo
  python main.py --skip-dl    # saltar descarga (usar .xls ya descargados)
  python main.py --only-parse # solo parsear y calcular indicadores
  python main.py --force-dl   # re-descargar aunque ya existan
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Pipeline BCU Credit Analysis")
    parser.add_argument("--skip-dl", action="store_true", help="Omitir descarga de boletines")
    parser.add_argument("--only-parse", action="store_true", help="Solo parsear (sin análisis)")
    parser.add_argument("--force-dl", action="store_true", help="Re-descargar aunque ya existan")
    args = parser.parse_args()

    # ── 1. Descarga ──────────────────────────────────────────────────────────
    if not args.skip_dl:
        log.info("=" * 55)
        log.info("PASO 1/6 — Descarga de boletines BCU (grupo981)")
        log.info("=" * 55)
        try:
            from src.ingestion.scraper import descargar_todos
            resultados = descargar_todos(force=args.force_dl)
            total = len(resultados["ok"]) + len(resultados["skip"])
            if total == 0:
                log.error("No se descargó ningún archivo grupo981. Verificar conectividad.")
                sys.exit(1)
        except Exception as exc:
            log.error("Error en descarga grupo981: %s", exc)
            sys.exit(1)

        log.info("=" * 55)
        log.info("PASO 1b/6 — Descarga de boletines BCU (grupos bancarios)")
        log.info("=" * 55)
        try:
            from src.ingestion.scraper_bancos import descargar_todos as descargar_bancos
            resultados_b = descargar_bancos(force=args.force_dl)
            log.info("Bancos — ok: %d  skip: %d  fail: %d",
                     len(resultados_b["ok"]), len(resultados_b["skip"]), len(resultados_b["fail"]))
        except Exception as exc:
            log.error("Error en descarga bancos: %s", exc)
            sys.exit(1)
    else:
        log.info("[skip] Descarga omitida por --skip-dl")

    # ── 2. Parsing grupo981 ──────────────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 2/6 — Parsing grupo981 (administradoras)")
    log.info("=" * 55)
    try:
        from src.processing.parser import guardar, parse_todos
        df = parse_todos()
        if df.empty:
            log.error("El parser no produjo datos. Verificar archivos en data/raw/administratoras_de_credito/")
            sys.exit(1)
        csv_path = guardar(df)
        log.info("DataFrame: %d filas, %d meses", len(df), df["fecha"].nunique())
    except Exception as exc:
        log.error("Error en parsing grupo981: %s", exc)
        raise

    # ── 2b. Parsing grupos bancarios ─────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 2b/6 — Parsing grupos bancarios (99/996/997/998)")
    log.info("=" * 55)
    try:
        from src.processing.parser_bancos import parsear_todos as parsear_bancos
        df_bancos = parsear_bancos()
        if df_bancos.empty:
            log.warning("parser_bancos no produjo datos — verificar archivos en data/raw/")
        else:
            processed = BASE_DIR / "data" / "processed"
            df_bancos.to_csv(processed / "bancos_serie_temporal.csv", index=False, encoding="utf-8")
            log.info("Bancos: %d filas, %d meses, %d grupos",
                     len(df_bancos), df_bancos["fecha"].nunique(), df_bancos["grupo"].nunique())
    except Exception as exc:
        log.error("Error en parsing bancos: %s", exc)
        raise

    # ── 3. Indicadores ───────────────────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 3/6 — Cálculo de indicadores y Anexo 1")
    log.info("=" * 55)
    try:
        from src.processing.indicadores import calcular_indicadores, parse_todos_anexo1
        processed = BASE_DIR / "data" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        df_ind = calcular_indicadores(df)
        if df_ind.empty:
            raise ValueError(
                "calcular_indicadores() retornó DataFrame vacío — "
                "abortando para no sobrescribir datos válidos."
            )
        df_ind.to_csv(processed / "indicadores.csv", index=False, encoding="utf-8")
        log.info("Indicadores guardados: %d filas", len(df_ind))

        df_plazos = parse_todos_anexo1()
        if not df_plazos.empty:
            df_plazos.to_csv(processed / "plazos.csv", index=False, encoding="utf-8")
            log.info("Plazos (Anexo 1) guardados: %d filas", len(df_plazos))

        # Metadatos de fuente — usados por el dashboard y para auditoría en CI
        meta = {
            "fuente_url": "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF",
            "fuente_nombre": "BCU — Boletín SSF, Administradoras de Crédito > 150.000 UR",
            "fecha_descarga": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "filas_procesadas": len(df_ind),
            "meses_disponibles": int(df_ind["fecha"].nunique()),
            "ultimo_mes": df_ind["fecha"].max().strftime("%Y-%m"),
        }
        meta_path = processed / "ultima_actualizacion.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Metadatos guardados: %s", meta_path)
    except Exception as exc:
        log.error("Error en indicadores: %s", exc)
        raise

    if args.only_parse:
        log.info("[skip] Análisis omitido por --only-parse")
        return

    # ── 4. Gráficos matplotlib ────────────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 4/6 — Gráficos matplotlib")
    log.info("=" * 55)
    try:
        from src.analysis.analysis import analizar
        analizar()
    except Exception as exc:
        log.error("Error en análisis: %s", exc)
        raise

    # ── 5. Dashboard HTML ─────────────────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 5/6 — Dashboard HTML (Plotly)")
    log.info("=" * 55)
    try:
        from src.reporting.dashboard_gen import generate_dashboard
        generate_dashboard()
    except Exception as exc:
        log.error("Error en dashboard: %s", exc)
        raise

    # ── 6. Resumen ejecutivo MD ───────────────────────────────────────────────
    log.info("=" * 55)
    log.info("PASO 6/6 — Resumen ejecutivo Markdown")
    log.info("=" * 55)
    try:
        from src.reporting.resumen_md_gen import generate_resumen, main as resumen_main
        resumen_main()
    except Exception as exc:
        log.error("Error en resumen: %s", exc)
        raise

    log.info("=" * 55)
    log.info("Pipeline completado.")
    log.info("  serie_temporal.csv : %s", (BASE_DIR / "data" / "processed" / "serie_temporal.csv").resolve())
    log.info("  indicadores.csv    : %s", (BASE_DIR / "data" / "processed" / "indicadores.csv").resolve())
    log.info("  dashboard          : %s", (BASE_DIR / "output" / "dashboards" / "dashboard_interactivo.html").resolve())
    log.info("  resumen_ejecutivo  : %s", (BASE_DIR / "output" / "reports" / "resumen_ejecutivo.md").resolve())
    log.info("=" * 55)


if __name__ == "__main__":
    main()
