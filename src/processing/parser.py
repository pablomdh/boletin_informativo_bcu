"""
parser.py — Procesa archivos .xls del BCU (grupo981) y consolida en un DataFrame.

Estructura XLS verificada con abril 2026:
- Fila 8: header de instituciones (col 1-15 empresas, col 16 total sector 981)
- Celda [5,0]: fecha en texto, ej: "Datos al 30 de abril de 2026"
- Hoja Situación: activos_total ('1 - ACTIVOS'), patrimonio ('3 - PATRIMONIO')
- Hoja Resultados: ingresos/gastos intereses, márgenes, resultado operativo
- Hoja Anexo 2: cartera_bruta (fila 9), deterioro_balance (fila 10), cartera_vigente (fila 11)

Salida: data/processed/serie_temporal.csv
"""

import logging
import re
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw" / "administratoras_de_credito"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Métricas a buscar por substring en columna 0
# (hoja, substring_busqueda, nombre_columna, tipo_busqueda)
# tipo: 'startswith' | 'contains' | 'exact_row' (índice fijo en Anexo 2)
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

# En Anexo 2 las filas son fijas (verificado): 9=cartera_bruta, 10=deterioro, 11=vigentes
ANEXO2_FILAS = {
    9: "cartera_bruta",
    10: "deterioro_balance",
    11: "cartera_vigente",
}

log = logging.getLogger(__name__)


def _parse_fecha_texto(texto: str) -> pd.Timestamp | None:
    """Extrae fecha de texto como 'Datos al 30 de abril de 2026'."""
    texto = str(texto).lower()
    match = re.search(r"(\d{1,2}) de (\w+) de (\d{4})", texto)
    if not match:
        return None
    dia, mes_str, anio = match.groups()
    mes_num = MESES_ES.get(mes_str)
    if not mes_num:
        return None
    return pd.Timestamp(int(anio), mes_num, int(dia))


def _parse_fecha_filename(filepath: Path) -> pd.Timestamp | None:
    """Extrae fecha del nombre de archivo: grupo981_2026_Abril.xls."""
    m = re.search(r"grupo981_(\d{4})_(\w+)\.xls", filepath.name)
    if not m:
        return None
    anio, mes_str = m.groups()
    mes_num = MESES_ES.get(mes_str.lower())
    if not mes_num:
        return None
    # Usar último día del mes como convención
    return pd.Timestamp(int(anio), mes_num, 1) + pd.offsets.MonthEnd(0)


def _find_row(col0: pd.Series, substring: str) -> int | None:
    """Busca la primera fila donde col0 contiene el substring (case-insensitive)."""
    sub = substring.lower()
    for i, val in enumerate(col0):
        if pd.notna(val) and sub in str(val).lower():
            return i
    return None


def _get_instituciones(df: pd.DataFrame) -> dict[str, int]:
    """
    Retorna {codigo_nombre: col_index} desde la fila de headers (fila 8).
    Ej: {'4302 Nombre Inst.': 12, '981 ADMINISTRADORAS...': 16}
    """
    header_row = df.iloc[8, :]
    instituciones = {}
    for col_idx, val in enumerate(header_row):
        if pd.notna(val) and col_idx > 0:
            instituciones[str(val).strip()] = col_idx
    return instituciones


def _safe_float(val) -> float | None:
    """Convierte a float, retorna None si no es numérico."""
    try:
        f = float(val)
        return f if pd.notna(f) else None
    except (TypeError, ValueError):
        return None


def parse_file(filepath: Path) -> list[dict]:
    """
    Parsea un archivo .xls del BCU y retorna una lista de dicts,
    uno por institución, con todas las métricas clave.
    """
    filepath = Path(filepath)
    log.debug("Parseando: %s", filepath.name)

    try:
        df_sit = pd.read_excel(filepath, sheet_name="Situación", engine="xlrd", header=None)
        df_res = pd.read_excel(filepath, sheet_name="Resultados", engine="xlrd", header=None)
        df_an2 = pd.read_excel(filepath, sheet_name="Anexo 2", engine="xlrd", header=None)
    except Exception as exc:
        log.error("No se pudo abrir %s: %s", filepath.name, exc)
        return []

    # Fecha
    fecha = _parse_fecha_texto(df_sit.iloc[5, 0])
    if fecha is None:
        fecha = _parse_fecha_filename(filepath)
    if fecha is None:
        log.warning("No se pudo determinar fecha en %s", filepath.name)
        return []

    # Instituciones (todas comparten el mismo header en fila 8)
    instituciones = _get_instituciones(df_sit)
    if not instituciones:
        log.warning("No se encontraron instituciones en %s", filepath.name)
        return []

    # Índices de métricas en Situación
    col0_sit = df_sit.iloc[:, 0]
    idx_sit = {nombre: _find_row(col0_sit, sub) for sub, nombre in METRICAS_SITUACION}

    # Índices de métricas en Resultados
    col0_res = df_res.iloc[:, 0]
    idx_res = {nombre: _find_row(col0_res, sub) for sub, nombre in METRICAS_RESULTADOS}

    registros = []
    for inst_label, col_idx in instituciones.items():
        # Código numérico (primeros dígitos antes del espacio)
        codigo_match = re.match(r"^(\d+)", inst_label)
        codigo = codigo_match.group(1) if codigo_match else inst_label

        row = {
            "fecha": fecha,
            "institucion": inst_label,
            "codigo": codigo,
        }

        # Métricas de Situación
        for nombre, row_idx in idx_sit.items():
            row[nombre] = _safe_float(df_sit.iloc[row_idx, col_idx]) if row_idx is not None else None

        # Métricas de Resultados
        for nombre, row_idx in idx_res.items():
            row[nombre] = _safe_float(df_res.iloc[row_idx, col_idx]) if row_idx is not None else None

        # Métricas de Anexo 2 (filas fijas)
        for fila_idx, nombre in ANEXO2_FILAS.items():
            try:
                row[nombre] = _safe_float(df_an2.iloc[fila_idx, col_idx])
            except IndexError:
                row[nombre] = None

        registros.append(row)

    return registros


def parse_todos(raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """
    Parsea todos los .xls en raw_dir y retorna un DataFrame consolidado.
    """
    archivos = sorted(raw_dir.glob("grupo981_*.xls"))
    if not archivos:
        log.warning("No se encontraron archivos en %s", raw_dir)
        return pd.DataFrame()

    log.info("Parseando %d archivos...", len(archivos))
    todos = []
    for f in archivos:
        registros = parse_file(f)
        if registros:
            todos.extend(registros)
            log.info("  [ok] %s — %d registros", f.name, len(registros))
        else:
            log.warning("  [err] %s — sin datos", f.name)

    if not todos:
        return pd.DataFrame()

    df = pd.DataFrame(todos)
    df = df.sort_values(["fecha", "codigo"]).reset_index(drop=True)

    # Columnas en orden canónico
    cols_orden = [
        "fecha", "institucion", "codigo",
        "activos_total", "cartera_bruta", "cartera_vigente",
        "deterioro_balance", "patrimonio",
        "ingresos_intereses", "gastos_intereses", "margen_financiero_bruto",
        "deterioro_resultado", "resultado_operativo",
        "gastos_personal", "gastos_generales",
    ]
    cols_presentes = [c for c in cols_orden if c in df.columns]
    df = df[cols_presentes]

    return df


def guardar(df: pd.DataFrame, out_dir: Path = PROCESSED_DIR) -> Path:
    """Guarda el DataFrame en data/processed/serie_temporal.csv."""
    out_dir.mkdir(parents=True, exist_ok=True)
    destino = out_dir / "serie_temporal.csv"
    df.to_csv(destino, index=False, encoding="utf-8")
    log.info("Guardado: %s (%d filas)", destino, len(df))
    return destino


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )

    df = parse_todos()
    if df.empty:
        print("Sin datos para procesar. Correr primero: python scraper.py")
    else:
        destino = guardar(df)
        print(f"\nDataFrame shape: {df.shape}")
        print(f"Columnas: {df.columns.tolist()}")
        print(f"Fechas: {sorted(df['fecha'].unique())}")
        print(f"\nGuardado en: {destino}")
