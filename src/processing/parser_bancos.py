"""
parser_bancos.py — Parsea boletines XLS de grupos bancarios y financieros.

Lee:
  data/raw/bancos_oficiales/grupo99_*.xls
  data/raw/bancos/grupo997_*.xls
  data/raw/cooperativos_intermediacion_financiera/grupo996_*.xls
  data/raw/casas_financieras/grupo998_*.xls
Genera data/processed/bancos_serie_temporal.csv

Columnas de salida:
  fecha, grupo, codigo, institucion,
  activos_total, patrimonio,
  ingresos_intereses, gastos_intereses, margen_financiero_bruto,
  deterioro_resultado, gastos_personal, gastos_generales, resultado_operativo,
  cartera_bruta, deterioro_balance, vigentes, col_vencida, en_gestion, morosos,
  roe_anual, roa_anual, morosidad_a4, eficiencia_a4

Notas:
  - Estructura XLS idéntica a grupo981 (Situación, Resultados, Anexo 2, Anexo 4).
  - Instituciones en fila 8, col 1..N-1 (última col = total grupo).
  - Métricas buscadas por substring en col 0 (nunca hardcodear índice de fila).
  - Anexo 4 tiene indicadores pre-calculados por el BCU (ROE, ROA, morosidad).
  - Resultados son acumulados desde inicio del ejercicio BCU (oct-sep).
    No se anualizan aquí: se guardan brutos para que el análisis decida.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT_DIR / "data" / "processed"

RAW_DIRS = {
    "grupo99":  ROOT_DIR / "data" / "raw" / "bancos_oficiales",
    "grupo997": ROOT_DIR / "data" / "raw" / "bancos",
    "grupo996": ROOT_DIR / "data" / "raw" / "cooperativos_intermediacion_financiera",
    "grupo998": ROOT_DIR / "data" / "raw" / "casas_financieras",
}

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Métricas por substring en col 0
METRICAS_SITUACION = [
    ("1 - ACTIVOS", "activos_total"),
    ("3 - PATRIMONIO", "patrimonio"),
]

METRICAS_RESULTADOS = [
    ("4 - Ingresos por intereses", "ingresos_intereses"),
    ("5 - Gastos por intereses", "gastos_intereses"),
    ("Margen financiero bruto", "margen_financiero_bruto"),
    ("7 - Deterioro de activos", "deterioro_resultado"),
    ("16 - Gastos de personal", "gastos_personal"),
    ("17 - Gastos generales", "gastos_generales"),
    ("Resultado operativo", "resultado_operativo"),
]

# Filas fijas en Anexo 2 (verificadas contra grupo997 y grupo99 abril 2026)
ANEXO2_FILAS = {
    9: "cartera_bruta",
    10: "deterioro_balance",
    11: "vigentes",
    40: "col_vencida",
    42: "en_gestion",
    44: "morosos",
}

# Filas fijas en Anexo 4
ANEXO4_FILAS = {
    27: "roe_anual",
    28: "roa_anual",
    30: "morosidad_a4",
    36: "eficiencia_a4",
}


def _fecha_de_nombre(path: Path) -> pd.Timestamp:
    m = re.search(r"grupo\w+_(\d{4})_(\w+)\.xls", path.name)
    if not m:
        return pd.Timestamp.min
    anio, mes_str = m.groups()
    mes_num = MESES_ES.get(mes_str.lower(), 0)
    return pd.Timestamp(int(anio), mes_num or 1, 1)


def _safe_float(val) -> float:
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s in ("N/C", "N/A", "-", ""):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def _buscar_metrica(df: pd.DataFrame, substring: str) -> int | None:
    """Devuelve el índice de la primera fila cuya col 0 contiene substring (case-insensitive)."""
    substr_lower = substring.lower()
    for i in range(len(df)):
        val = df.iloc[i, 0]
        if pd.notna(val) and substr_lower in str(val).lower():
            return i
    return None


def _parse_hoja(df: pd.DataFrame, metricas: list, columnas: list) -> dict:
    """Extrae métricas por búsqueda de substring para cada columna de institución."""
    resultado = {col: {nombre: np.nan for _, nombre in metricas} for col in columnas}
    for substring, nombre in metricas:
        fila = _buscar_metrica(df, substring)
        if fila is None:
            continue
        for col_idx in columnas:
            resultado[col_idx][nombre] = _safe_float(df.iloc[fila, col_idx])
    return resultado


def _parse_anexo_filas_fijas(df: pd.DataFrame, filas: dict, columnas: list) -> dict:
    """Extrae métricas por índice de fila fijo para cada columna de institución."""
    resultado = {col: {} for col in columnas}
    for fila_idx, nombre in filas.items():
        if fila_idx >= len(df):
            continue
        for col_idx in columnas:
            if col_idx >= df.shape[1]:
                resultado[col_idx][nombre] = np.nan
                continue
            resultado[col_idx][nombre] = _safe_float(df.iloc[fila_idx, col_idx])
    return resultado


def parsear_archivo(path: Path) -> list[dict]:
    """Parsea un XLS de grupo bancario. Devuelve lista de dicts (uno por institución)."""
    fecha = _fecha_de_nombre(path)
    m = re.search(r"(grupo\w+)_(\d{4})_(\w+)\.xls", path.name)
    if not m:
        return []
    grupo = m.group(1)

    try:
        xl = pd.ExcelFile(path, engine="xlrd")
    except Exception:
        return []

    # Leer hojas
    sheets = {name: pd.read_excel(path, sheet_name=name, header=None, engine="xlrd")
              for name in xl.sheet_names}

    sit = sheets.get("Situación")
    if sit is None:
        return []

    # Descubrir instituciones desde fila 8
    fila_header = sit.iloc[8]
    instituciones = {}  # col_idx → nombre
    for c in range(1, len(fila_header)):
        val = fila_header[c]
        if pd.notna(val) and str(val).strip():
            instituciones[c] = str(val).strip()
    if not instituciones:
        return []

    columnas = list(instituciones.keys())

    # Parsear Situación
    sit_data = _parse_hoja(sit, METRICAS_SITUACION, columnas)

    # Parsear Resultados
    res = sheets.get("Resultados")
    res_data = _parse_hoja(res, METRICAS_RESULTADOS, columnas) if res is not None else {c: {} for c in columnas}

    # Parsear Anexo 2
    an2 = sheets.get("Anexo 2")
    an2_data = _parse_anexo_filas_fijas(an2, ANEXO2_FILAS, columnas) if an2 is not None else {c: {} for c in columnas}

    # Parsear Anexo 4
    an4 = sheets.get("Anexo 4")
    an4_data = _parse_anexo_filas_fijas(an4, ANEXO4_FILAS, columnas) if an4 is not None else {c: {} for c in columnas}

    rows = []
    for col_idx, nombre_inst in instituciones.items():
        # Extraer código numérico del nombre (ej: "997 BANCOS PRIVADOS" → 997)
        codigo_m = re.match(r"(\d+)", nombre_inst)
        codigo = int(codigo_m.group(1)) if codigo_m else 0

        row = {
            "fecha": fecha,
            "grupo": grupo,
            "codigo": codigo,
            "institucion": nombre_inst,
        }
        row.update(sit_data[col_idx])
        row.update(res_data[col_idx])
        row.update(an2_data[col_idx])
        row.update(an4_data[col_idx])
        rows.append(row)

    return rows


def parsear_todos() -> pd.DataFrame:
    archivos = sorted(
        [f for raw_dir in RAW_DIRS.values() for f in raw_dir.glob("grupo*.xls")],
        key=_fecha_de_nombre,
    )
    if not archivos:
        raise FileNotFoundError(f"No hay archivos en ninguna carpeta de {list(RAW_DIRS.values())}")

    todas = []
    for f in archivos:
        filas = parsear_archivo(f)
        todas.extend(filas)
        print(f"  {f.name}: {len(filas)} instituciones")

    df = pd.DataFrame(todas)
    df = df.sort_values(["fecha", "grupo", "codigo"]).reset_index(drop=True)
    return df


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Parseando boletines bancarios...")
    df = parsear_todos()
    out = OUT_DIR / "bancos_serie_temporal.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"\nGuardado: {out}")
    print(f"Filas: {len(df)}  |  Meses: {df['fecha'].nunique()}  |  Grupos: {df['grupo'].nunique()}")
    print(f"\nGrupos disponibles:")
    for g, cnt in df.groupby("grupo")["fecha"].nunique().items():
        instituciones = df[df["grupo"] == g]["institucion"].unique()
        print(f"  {g}: {cnt} meses — {list(instituciones)}")
