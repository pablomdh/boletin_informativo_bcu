"""
indicadores.py — Calcula todos los indicadores financieros derivados.

Carga serie_temporal.csv, computa ratios y guarda:
  data/processed/indicadores.csv   — todos los indicadores por inst/mes
  data/processed/plazos.csv        — distribución cartera por plazos (Anexo 1)

Indicadores calculados:
  Calidad cartera:  ratio_deterioro, cobertura, cartera_vigente_neta
  Rentabilidad:     roa_anual, roe_anual, margen_financiero_neto, ratio_eficiencia
  Fondeo/estructura:leverage, pasivos_estimados
  Market share:     ms_cartera_bruta, ms_activos
"""

import logging
import re
from pathlib import Path

import pandas as pd
import xlrd

from config.settings import FOCUS_COMPANY_CODE, FOCUS_COMPANY_NAME, SECTOR_CODE

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Plazos del Anexo 1 — sector no financiero, filas relativas al bloque
PLAZOS_LABELS = {
    20: "Vista",
    21: "Menor_30d",
    22: "Menor_91d",
    23: "Menor_181d",
    24: "Menor_367d",
    25: "Menor_3a",
    26: "Mayor_igual_3a",
}

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de anualización
# ─────────────────────────────────────────────────────────────────────────────

def meses_en_periodo(mes: int) -> int:
    """
    Retorna cuántos meses acumula el estado de resultados para un mes dado.
    El año fiscal del BCU va de octubre a septiembre.
    Oct=1, Nov=2, Dic=3, Ene=4, Feb=5, Mar=6, Abr=7, May=8, Jun=9, Jul=10, Ago=11, Sep=12
    """
    return (mes - 10) % 12 + 1


def factor_anualizacion(mes: int) -> float:
    return 12.0 / meses_en_periodo(mes)


# ─────────────────────────────────────────────────────────────────────────────
# Indicadores desde serie_temporal.csv
# ─────────────────────────────────────────────────────────────────────────────

def calcular_indicadores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["codigo"] = df["codigo"].astype(str)

    # Pasivos estimados = activos - patrimonio
    df["pasivos"] = df["activos_total"] - df["patrimonio"]

    # Market share vs sector (join con fila sector del mismo mes)
    sector = df[df["codigo"] == SECTOR_CODE][["fecha", "cartera_bruta", "activos_total"]].rename(
        columns={"cartera_bruta": "sect_cartera", "activos_total": "sect_activos"}
    )
    df = df.merge(sector, on="fecha", how="left")
    df["ms_cartera_bruta"] = df["cartera_bruta"] / df["sect_cartera"]
    df["ms_activos"] = df["activos_total"] / df["sect_activos"]

    # Calidad de cartera
    df["ratio_deterioro"] = df["deterioro_balance"].abs() / df["cartera_bruta"].replace(0, pd.NA)
    df["cartera_vigente_neta"] = df["cartera_vigente"] + df["deterioro_balance"]  # deterioro_balance es negativo

    # Cobertura: deterioro_balance / (cartera_bruta - cartera_vigente) = provisiones / cartera morosa
    df["cartera_morosa"] = df["cartera_bruta"] - df["cartera_vigente"]
    df["cobertura"] = df["deterioro_balance"].abs() / df["cartera_morosa"].replace(0, pd.NA)

    # Annualization factor
    df["factor_anual"] = df["fecha"].dt.month.map(factor_anualizacion)

    # Rentabilidad anualizada
    df["resultado_anualizado"] = df["resultado_operativo"] * df["factor_anual"]
    df["roa_anual"] = df["resultado_anualizado"] / df["activos_total"].replace(0, pd.NA)
    df["roe_anual"] = df["resultado_anualizado"] / df["patrimonio"].replace(0, pd.NA)

    # Margen financiero neto = (ingresos - gastos intereses - deterioro resultado) / cartera bruta
    df["margen_financiero_neto"] = (
        df["ingresos_intereses"] + df["gastos_intereses"] + df["deterioro_resultado"]
    ) / df["cartera_bruta"].replace(0, pd.NA)

    # Ratio de eficiencia = (gastos personal + gastos generales) / margen financiero bruto
    # Gastos son negativos en los datos, usamos abs
    df["gastos_totales"] = df["gastos_personal"].abs() + df["gastos_generales"].abs()
    df["ratio_eficiencia"] = df["gastos_totales"] / df["margen_financiero_bruto"].replace(0, pd.NA)

    # Leverage = pasivos / patrimonio
    df["leverage"] = df["pasivos"] / df["patrimonio"].replace(0, pd.NA)

    # Costo de fondeo estimado (sin pasivos detallados, usamos gastos intereses / pasivos)
    df["costo_fondeo"] = df["gastos_intereses"].abs() / df["pasivos"].replace(0, pd.NA) * df["factor_anual"]

    # Limpiar columnas auxiliares
    df = df.drop(columns=["sect_cartera", "sect_activos"], errors="ignore")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Parsing Anexo 1 — distribución cartera por plazos
# ─────────────────────────────────────────────────────────────────────────────

def _parse_fecha_xls(filepath: Path) -> pd.Timestamp | None:
    m = re.search(r"grupo981_(\d{4})_(\w+)\.xls", filepath.name)
    if not m:
        return None
    anio, mes_str = m.groups()
    mes_num = MESES_ES.get(mes_str.lower())
    if not mes_num:
        return None
    return pd.Timestamp(int(anio), mes_num, 1) + pd.offsets.MonthEnd(0)


def parse_anexo1_file(filepath: Path) -> list[dict]:
    """
    Parsea el Anexo 1 de un archivo XLS y retorna distribución de cartera
    de créditos vigentes sector no financiero por plazo, por institución.
    """
    filepath = Path(filepath)
    fecha = _parse_fecha_xls(filepath)
    if fecha is None:
        return []

    try:
        wb = xlrd.open_workbook(str(filepath))
        ws = wb.sheet_by_name("Anexo 1")
    except Exception as exc:
        log.warning("No se pudo abrir Anexo 1 en %s: %s", filepath.name, exc)
        return []

    # Leer header de instituciones (fila 8, empieza en col 3)
    instituciones = {}
    if ws.nrows <= 8:
        return []
    for col_idx in range(ws.ncols):
        val = ws.cell_value(8, col_idx)
        if val and col_idx >= 3:
            m = re.match(r"^(\d+)", str(val))
            codigo = m.group(1) if m else str(val)
            instituciones[codigo] = col_idx

    if not instituciones:
        return []

    registros = []
    for fila_idx, plazo_label in PLAZOS_LABELS.items():
        if fila_idx >= ws.nrows:
            continue
        for codigo, col_idx in instituciones.items():
            if col_idx >= ws.ncols:
                continue
            val = ws.cell_value(fila_idx, col_idx)
            try:
                monto = float(val) if val else None
            except (TypeError, ValueError):
                monto = None
            registros.append({
                "fecha": fecha,
                "codigo": codigo,
                "plazo": plazo_label,
                "monto": monto,
            })

    return registros


def parse_todos_anexo1(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    archivos = sorted(raw_dir.glob("grupo981_*.xls"))
    todos = []
    for f in archivos:
        registros = parse_anexo1_file(f)
        todos.extend(registros)
    if not todos:
        return pd.DataFrame()
    df = pd.DataFrame(todos)
    df = df.sort_values(["fecha", "codigo", "plazo"]).reset_index(drop=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Indicadores
    csv_in = PROCESSED_DIR / "serie_temporal.csv"
    if not csv_in.exists():
        log.error("No se encontró serie_temporal.csv. Correr: python parser.py")
        return

    log.info("Calculando indicadores...")
    df = pd.read_csv(csv_in, parse_dates=["fecha"])
    df_ind = calcular_indicadores(df)
    out_ind = PROCESSED_DIR / "indicadores.csv"
    df_ind.to_csv(out_ind, index=False, encoding="utf-8")
    log.info("Guardado: %s (%d filas)", out_ind, len(df_ind))

    # Resumen empresa foco
    foco = df_ind[df_ind["codigo"].astype(str) == FOCUS_COMPANY_CODE].sort_values("fecha")
    log.info("\n=== %s — indicadores clave ===", FOCUS_COMPANY_NAME)
    cols_show = ["fecha", "ms_cartera_bruta", "ratio_deterioro", "roa_anual", "roe_anual",
                 "ratio_eficiencia", "leverage"]
    for _, row in foco[cols_show].iterrows():
        log.info(
            "%s | MS=%.1f%% | Det=%.1f%% | ROA=%.1f%% | ROE=%.1f%% | Efic=%.1f%% | Lev=%.1fx",
            row["fecha"].strftime("%Y-%m"),
            (row["ms_cartera_bruta"] or 0) * 100,
            (row["ratio_deterioro"] or 0) * 100,
            (row["roa_anual"] or 0) * 100,
            (row["roe_anual"] or 0) * 100,
            (row["ratio_eficiencia"] or 0) * 100,
            row["leverage"] or 0,
        )

    # Plazos (Anexo 1)
    log.info("\nParsando Anexo 1 (distribución por plazos)...")
    df_plazos = parse_todos_anexo1()
    if not df_plazos.empty:
        out_plazos = PROCESSED_DIR / "plazos.csv"
        df_plazos.to_csv(out_plazos, index=False, encoding="utf-8")
        log.info("Guardado: %s (%d filas)", out_plazos, len(df_plazos))
    else:
        log.warning("No se obtuvieron datos de Anexo 1")


if __name__ == "__main__":
    main()
