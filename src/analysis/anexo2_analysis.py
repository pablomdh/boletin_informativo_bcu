"""
anexo2_analysis.py — Análisis de segmentación de créditos por calidad de cobro (Anexo 2).

Para el último mes disponible genera:
  output/anexo2_segmentos.html — dashboard HTML standalone con:
    1. Distribución de cartera bruta por segmento (vigentes / col.vencida / en gestión / morosos)
       — stacked bar horizontal, % por institución
    2. Volumen de mercado en cada segmento (quién tiene qué)
    3. Tasas de cobertura (provisión / saldo) por segmento y por institución
    4. Composición sectorial de créditos vigentes (fin / no-fin privado / no-fin público)
    5. Comparativa empresa foco vs sector: distribución y cobertura

Segmentos de calidad de cobro (Anexo 2):
  Nivel 1 — VIGENTES          (fila 11): probabilidad de cobro alta
    1.2  Sector financiero     (fila 14)
    1.3  Sector no-fin privado (fila 28): el principal para crédito al consumo
    1.4  Sector no-fin público (fila 30)
  Nivel 2 — VENCIDOS          (fila 34): incumplimiento
    2.2.1 Colocación vencida   (fila 40): < 60 días, aún recuperable
    2.2.2 Créditos en gestión  (fila 42): 60-180 días, en proceso de cobro
    2.2.3 Créditos morosos     (fila 44): > 180 días, provisión ~100%
"""

import logging
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
import xlrd

from config.settings import FOCUS_COMPANY_CODE, FOCUS_COMPANY_NAME, FOCUS_COMPANY_SHORT, SECTOR_CODE

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
OUTPUT_DIR = ROOT_DIR / "output"

log = logging.getLogger(__name__)

MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MESES_FULL = {v: k.capitalize() for k, v in MESES_ES.items() if k != "septiembre"}

INST_NAMES = {
    "803": "DIRECTOS", "804": "SOCUR", "805": "ANDA", "815": "OCA SA",
    "816": "PROMOTORA", "817": "RETOP", "846": "DEL ESTE", "852": "VERENDY",
    "853": "E.de Valor", "854": "PASS CARD", "858": "BAUTZEN", "860": "FUCAC",
    "7884": "MICROFdURU", "7886": "RMSA",
    "7890": "Floder", "7894": "Sol.Integ.", "981": "SECTOR TOTAL",
}
INST_NAMES[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_NAME

# Colores de calidad de crédito (verde→rojo según riesgo)
COLOR_VIGENTES   = "#43A047"   # verde
COLOR_COL_VEN    = "#FDD835"   # amarillo
COLOR_GESTION    = "#FB8C00"   # naranja
COLOR_MOROSOS    = "#E53935"   # rojo
COLOR_FOCO       = "#1565C0"   # azul oscuro para destacar empresa foco

# Filas fijas en Anexo 2 (verificadas en abril 2026)
ROWS_ANEXO2 = {
    # saldo
    "cartera_bruta":       9,
    "vigentes":           11,
    "vig_sf":             14,   # sector financiero
    "vig_nfp":            28,   # no financiero privado
    "vig_nfpub":          30,   # no financiero público
    "vencidos":           34,
    "col_vencida":        40,
    "en_gestion":         42,
    "morosos":            44,
    # deterioro (provisiones)
    "det_total":          10,
    "det_vigentes":       12,
    "det_vencidos":       35,
    "det_col_vencida":    41,
    "det_en_gestion":     43,
    "det_morosos":        45,
}


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def parse_anexo2_file(filepath: Path) -> pd.DataFrame | None:
    """Parsea el Anexo 2 de un XLS, retorna DataFrame con una fila por institución."""
    try:
        wb = xlrd.open_workbook(str(filepath))
        ws = wb.sheet_by_name("Anexo 2")
    except Exception as e:
        log.warning("No se pudo abrir Anexo 2 en %s: %s", filepath.name, e)
        return None

    # Header instituciones en fila 8
    instituciones = {}
    for col in range(ws.ncols):
        v = ws.cell_value(8, col)
        if v and col > 0:
            m = re.match(r"^(\d+)", str(v))
            if m:
                instituciones[m.group(1)] = col

    if not instituciones:
        return None

    # Fecha desde nombre de archivo
    m = re.search(r"grupo981_(\d{4})_(\w+)\.xls", filepath.name)
    if not m:
        return None
    anio, mes_str = m.groups()
    mes_num = MESES_ES.get(mes_str.lower())
    if not mes_num:
        return None
    fecha = pd.Timestamp(int(anio), mes_num, 1) + pd.offsets.MonthEnd(0)

    rows = []
    for codigo, col in instituciones.items():
        rec = {"fecha": fecha, "codigo": codigo, "nombre": INST_NAMES.get(codigo, codigo)}
        for campo, fila in ROWS_ANEXO2.items():
            try:
                v = ws.cell_value(fila, col)
                rec[campo] = float(v) if v != "" and v is not None else 0.0
            except (IndexError, ValueError):
                rec[campo] = 0.0
        rows.append(rec)

    return pd.DataFrame(rows)


def get_ultimo_mes_anexo2() -> pd.DataFrame:
    """Carga el Anexo 2 del último mes disponible (ordenado por fecha desc)."""
    archivos = sorted(RAW_DIR.glob("grupo981_*.xls"))
    if not archivos:
        raise FileNotFoundError("No hay archivos en data/raw/")

    # Ordenar por fecha extraída del nombre (no alfabético)
    def _fecha_de_nombre(p: Path):
        m = re.search(r"grupo981_(\d{4})_(\w+)\.xls", p.name)
        if not m:
            return pd.Timestamp.min
        anio, mes_str = m.groups()
        mes_num = MESES_ES.get(mes_str.lower(), 0)
        return pd.Timestamp(int(anio), mes_num or 1, 1)

    archivos_sorted = sorted(archivos, key=_fecha_de_nombre, reverse=True)

    for f in archivos_sorted:
        df = parse_anexo2_file(f)
        if df is not None and not df.empty:
            log.info("Usando archivo: %s", f.name)
            return df
    raise ValueError("No se pudo parsear ningún Anexo 2")


# ─────────────────────────────────────────────────────────────────────────────
# Figuras
# ─────────────────────────────────────────────────────────────────────────────

def _nombre(codigo: str) -> str:
    return INST_NAMES.get(str(codigo), str(codigo))


def fig_stacked_segmentos(df: pd.DataFrame) -> go.Figure:
    """
    Stacked bar horizontal: % de cada segmento sobre cartera bruta por institución.
    Solo instituciones con cartera > 0, sin el SECTOR TOTAL.
    """
    d = df[(df["codigo"] != SECTOR_CODE) & (df["cartera_bruta"] > 0)].copy()
    d["pct_vigentes"]    = d["vigentes"]    / d["cartera_bruta"] * 100
    d["pct_col_vencida"] = d["col_vencida"] / d["cartera_bruta"] * 100
    d["pct_en_gestion"]  = d["en_gestion"]  / d["cartera_bruta"] * 100
    d["pct_morosos"]     = d["morosos"]     / d["cartera_bruta"] * 100
    d = d.sort_values("pct_morosos", ascending=True)  # peor mora abajo

    # Destacar empresa foco con borde
    marker_line = [dict(color="#1565C0", width=2.5) if c == FOCUS_COMPANY_CODE
                   else dict(color="white", width=0.5) for c in d["codigo"]]

    fig = go.Figure()
    for col, color, label in [
        ("pct_vigentes",    COLOR_VIGENTES,  "Vigentes"),
        ("pct_col_vencida", COLOR_COL_VEN,   "Colocación vencida"),
        ("pct_en_gestion",  COLOR_GESTION,   "En gestión"),
        ("pct_morosos",     COLOR_MOROSOS,   "Morosos"),
    ]:
        fig.add_trace(go.Bar(
            y=d["nombre"],
            x=d[col].round(1),
            name=label,
            orientation="h",
            marker_color=color,
            marker_line=dict(color="white", width=0.5),
            hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x:.1f}}%<extra></extra>",
            text=d[col].apply(lambda v: f"{v:.1f}%" if v > 4 else ""),
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=10, color="white"),
        ))

    # Anotación empresa foco
    foco_row = d[d["codigo"] == FOCUS_COMPANY_CODE]
    if not foco_row.empty:
        fig.add_annotation(
            y=foco_row["nombre"].iloc[0],
            x=102,
            text=f"◄ {FOCUS_COMPANY_SHORT}",
            showarrow=False,
            font=dict(color=COLOR_FOCO, size=11, family="monospace"),
            xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="Distribución de Cartera Bruta por Segmento de Calidad<br>"
                 "<sup>Vigentes | Colocación vencida | En gestión | Morosos</sup>",
            font=dict(size=15),
        ),
        xaxis=dict(title="% sobre cartera bruta", ticksuffix="%", range=[0, 112]),
        yaxis=dict(title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        height=480,
        margin=dict(l=100, r=80, t=80, b=80),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    return fig


def fig_mercado_por_segmento(df: pd.DataFrame) -> go.Figure:
    """
    4 subplots: volumen de mercado (M$) en cada segmento — quién tiene qué parte.
    """
    d = df[(df["codigo"] != SECTOR_CODE) & (df["cartera_bruta"] > 0)].copy()
    d["nombre"] = d["codigo"].map(_nombre)

    segmentos = [
        ("vigentes",    COLOR_VIGENTES,  "Créditos Vigentes"),
        ("col_vencida", COLOR_COL_VEN,   "Colocación Vencida"),
        ("en_gestion",  COLOR_GESTION,   "Créditos en Gestión"),
        ("morosos",     COLOR_MOROSOS,   "Créditos Morosos"),
    ]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[s[2] for s in segmentos],
        vertical_spacing=0.18,
        horizontal_spacing=0.12,
    )

    pos = [(1,1),(1,2),(2,1),(2,2)]
    for (campo, color, titulo), (row, col) in zip(segmentos, pos):
        d_seg = d[d[campo].abs() > 0].sort_values(campo, ascending=True)
        bar_colors = [COLOR_FOCO if c == FOCUS_COMPANY_CODE else color for c in d_seg["codigo"]]

        fig.add_trace(go.Bar(
            y=d_seg["nombre"],
            x=(d_seg[campo] / 1000).round(0),
            name=titulo,
            orientation="h",
            marker_color=bar_colors,
            marker_line=dict(
                color=[COLOR_FOCO if c == FOCUS_COMPANY_CODE else "white" for c in d_seg["codigo"]],
                width=[2 if c == FOCUS_COMPANY_CODE else 0.5 for c in d_seg["codigo"]],
            ),
            showlegend=False,
            hovertemplate=f"<b>%{{y}}</b><br>%{{x:,.0f}} M$<extra></extra>",
        ), row=row, col=col)

        fig.update_xaxes(tickprefix="$", ticksuffix="M", row=row, col=col)

    fig.update_layout(
        title=dict(
            text="Mercado por Segmento de Calidad de Crédito (millones $)<br>"
                 f"<sup>Azul = {FOCUS_COMPANY_NAME}</sup>",
            font=dict(size=15),
        ),
        height=600,
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        margin=dict(l=100, r=40, t=100, b=40),
    )
    return fig


def fig_cobertura_por_segmento(df: pd.DataFrame) -> go.Figure:
    """
    Tasa de cobertura (provisión/saldo) por segmento para cada institución.
    Heatmap + barras agrupadas.
    """
    d = df[(df["codigo"] != SECTOR_CODE) & (df["cartera_bruta"] > 0)].copy()

    # Calcular coberturas
    def safe_cov(det, saldo):
        return (abs(det) / saldo * 100).where(saldo > 0, 0)

    d["cob_vigentes"]    = safe_cov(d["det_vigentes"],    d["vigentes"])
    d["cob_col_vencida"] = safe_cov(d["det_col_vencida"], d["col_vencida"])
    d["cob_en_gestion"]  = safe_cov(d["det_en_gestion"],  d["en_gestion"])
    d["cob_morosos"]     = safe_cov(d["det_morosos"],     d["morosos"])
    d = d.sort_values("cob_morosos", ascending=False)
    d["nombre"] = d["codigo"].map(_nombre)

    fig = go.Figure()
    coberturas = [
        ("cob_vigentes",    COLOR_VIGENTES,  "Vigentes"),
        ("cob_col_vencida", COLOR_COL_VEN,   "Col. vencida"),
        ("cob_en_gestion",  COLOR_GESTION,   "En gestión"),
        ("cob_morosos",     COLOR_MOROSOS,   "Morosos"),
    ]

    for campo, color, label in coberturas:
        vals = d[campo].clip(0, 110).round(1)
        fig.add_trace(go.Bar(
            name=label,
            x=d["nombre"],
            y=vals,
            marker_color=color,
            marker_line=dict(
                color=[COLOR_FOCO if c == FOCUS_COMPANY_CODE else "white" for c in d["codigo"]],
                width=[2.5 if c == FOCUS_COMPANY_CODE else 0.5 for c in d["codigo"]],
            ),
            hovertemplate=f"<b>%{{x}}</b><br>Cobertura {label}: %{{y:.1f}}%<extra></extra>",
        ))

    # Líneas de referencia
    fig.add_hline(y=100, line_dash="dot", line_color="red", opacity=0.3,
                  annotation_text="100% cobertura", annotation_position="top right")

    fig.update_layout(
        barmode="group",
        title=dict(
            text="Tasa de Cobertura por Segmento (Provisión / Saldo)<br>"
                 f"<sup>Marco azul = {FOCUS_COMPANY_NAME} — Morosos con cobertura ~100% es lo esperado</sup>",
            font=dict(size=15),
        ),
        yaxis=dict(title="Cobertura (%)", ticksuffix="%", range=[0, 115]),
        xaxis=dict(title="", tickangle=-30),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        height=480,
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        margin=dict(l=60, r=40, t=90, b=100),
    )
    return fig


def fig_composicion_sectorial_vigentes(df: pd.DataFrame) -> go.Figure:
    """
    Composición sectorial de créditos vigentes:
    sector financiero / no-financiero privado / no-financiero público
    Stacked bars 100%, ordenadas por % no-fin privado.
    """
    d = df[(df["codigo"] != SECTOR_CODE) & (df["vigentes"] > 100)].copy()
    d["pct_sf"]   = d["vig_sf"]    / d["vigentes"] * 100
    d["pct_nfp"]  = d["vig_nfp"]   / d["vigentes"] * 100
    d["pct_nfpub"]= d["vig_nfpub"] / d["vigentes"] * 100
    # "otros vigentes" = diferencia (BCU, etc.)
    d["pct_otros"]= (100 - d["pct_sf"] - d["pct_nfp"] - d["pct_nfpub"]).clip(0)
    d = d.sort_values("pct_nfp", ascending=False)
    d["nombre"] = d["codigo"].map(_nombre)

    PALETA = ["#1565C0", "#1E88E5", "#42A5F5", "#90CAF9"]
    segmentos_sect = [
        ("pct_nfp",   PALETA[0], "No-fin. privado"),
        ("pct_sf",    PALETA[1], "Sector financiero"),
        ("pct_nfpub", PALETA[2], "No-fin. público"),
        ("pct_otros", PALETA[3], "BCU / Otros"),
    ]

    fig = go.Figure()
    for campo, color, label in segmentos_sect:
        fig.add_trace(go.Bar(
            y=d["nombre"],
            x=d[campo].round(1),
            name=label,
            orientation="h",
            marker_color=color,
            marker_line=dict(color="white", width=0.5),
            hovertemplate=f"<b>%{{y}}</b><br>{label}: %{{x:.1f}}%<extra></extra>",
            text=d[campo].apply(lambda v: f"{v:.0f}%" if v > 6 else ""),
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=10, color="white"),
        ))

    # Marcar empresa foco
    foco_row = d[d["codigo"] == FOCUS_COMPANY_CODE]
    if not foco_row.empty:
        fig.add_annotation(
            y=foco_row["nombre"].iloc[0],
            x=102,
            text=f"◄ {FOCUS_COMPANY_SHORT}",
            showarrow=False,
            font=dict(color=COLOR_FOCO, size=11),
            xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="Composición Sectorial de Créditos Vigentes<br>"
                 "<sup>No-fin. privado = crédito al consumo | Sector financiero = préstamos interempresa</sup>",
            font=dict(size=15),
        ),
        xaxis=dict(title="% sobre cartera vigente", ticksuffix="%", range=[0, 112]),
        yaxis=dict(title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        height=460,
        margin=dict(l=100, r=80, t=80, b=80),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
    )
    return fig


def fig_foco_zoom(df: pd.DataFrame) -> go.Figure:
    """
    Zoom en empresa foco vs promedio del sector:
    waterfall de cartera: bruta → vigentes → vencidos (col.vencida / gestión / morosos)
    + cobertura por segmento lado a lado.
    """
    foco = df[df["codigo"] == FOCUS_COMPANY_CODE].iloc[0] if not df[df["codigo"] == FOCUS_COMPANY_CODE].empty else None
    sect = df[df["codigo"] == SECTOR_CODE].iloc[0] if not df[df["codigo"] == SECTOR_CODE].empty else None

    if foco is None:
        return go.Figure().add_annotation(text=f"Sin datos {FOCUS_COMPANY_SHORT}", showarrow=False)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[f"Estructura de Cartera — {FOCUS_COMPANY_SHORT} vs Sector", f"Cobertura por Segmento — {FOCUS_COMPANY_SHORT} vs Sector"],
        horizontal_spacing=0.14,
    )

    # Panel izquierdo: composición % cartera bruta
    segm_labels = ["Vigentes", "Col. vencida", "En gestión", "Morosos"]
    segm_campos = ["vigentes", "col_vencida", "en_gestion", "morosos"]
    segm_colors = [COLOR_VIGENTES, COLOR_COL_VEN, COLOR_GESTION, COLOR_MOROSOS]

    def _dim_colors(colors, factor=0.55):
        """Convierte hex #RRGGBB a rgba con opacidad reducida."""
        result = []
        for c in colors:
            r = int(c[1:3], 16)
            g = int(c[3:5], 16)
            b = int(c[5:7], 16)
            result.append(f"rgba({r},{g},{b},{factor})")
        return result

    for entidad, nombre, show_leg in [
        (foco, FOCUS_COMPANY_NAME, True),
        (sect, "Sector",    True),
    ]:
        if entidad is None:
            continue
        pcts = [entidad[c] / entidad["cartera_bruta"] * 100 for c in segm_campos]
        colors = segm_colors if nombre == FOCUS_COMPANY_NAME else _dim_colors(segm_colors)
        fig.add_trace(go.Bar(
            name=nombre,
            x=segm_labels,
            y=[round(p, 1) for p in pcts],
            marker_color=colors,
            marker_pattern_shape="" if nombre == FOCUS_COMPANY_NAME else "/",
            legendgroup=nombre,
            showlegend=show_leg,
            hovertemplate=f"<b>{nombre}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ), row=1, col=1)

    fig.update_yaxes(title_text="% cartera bruta", ticksuffix="%", row=1, col=1)

    # Panel derecho: cobertura por segmento
    cob_labels = ["Vigentes", "Col. vencida", "En gestión", "Morosos"]
    det_campos  = ["det_vigentes", "det_col_vencida", "det_en_gestion", "det_morosos"]
    sal_campos  = ["vigentes",     "col_vencida",      "en_gestion",     "morosos"]

    for entidad, nombre, show_leg in [
        (foco, FOCUS_COMPANY_NAME, False),
        (sect, "Sector",    False),
    ]:
        if entidad is None:
            continue
        covs = [abs(entidad[d]) / entidad[s] * 100 if entidad[s] > 0 else 0
                for d, s in zip(det_campos, sal_campos)]
        colors = segm_colors if nombre == FOCUS_COMPANY_NAME else _dim_colors(segm_colors)
        fig.add_trace(go.Bar(
            name=nombre,
            x=cob_labels,
            y=[round(c, 1) for c in covs],
            marker_color=colors,
            marker_pattern_shape="" if nombre == FOCUS_COMPANY_NAME else "/",
            legendgroup=nombre,
            showlegend=show_leg,
            hovertemplate=f"<b>{nombre}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ), row=1, col=2)

    fig.add_hline(y=100, line_dash="dot", line_color="red", opacity=0.3, row=1, col=2)
    fig.update_yaxes(title_text="Cobertura (%)", ticksuffix="%", row=1, col=2)

    fig.update_layout(
        barmode="group",
        title=dict(
            text=f"{FOCUS_COMPANY_NAME} vs Sector — Estructura de Cartera y Cobertura",
            font=dict(size=15),
        ),
        height=420,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        margin=dict(l=60, r=40, t=80, b=80),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# HTML builder
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Segmentación de Créditos — Anexo 2 BCU</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f7fa; color: #1a1a2e; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
             color: white; padding: 24px 40px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; }}
  .header p  {{ font-size: 13px; opacity: 0.7; margin-top: 5px; }}
  .summary-bar {{ display: flex; gap: 16px; padding: 18px 40px;
                  background: white; border-bottom: 1px solid #eee; flex-wrap: wrap; }}
  .stat {{ background: #f8f9fa; border-radius: 8px; padding: 12px 18px;
           min-width: 150px; }}
  .stat .label {{ font-size: 11px; text-transform: uppercase; color: #888;
                  letter-spacing: 0.5px; font-weight: 600; }}
  .stat .value {{ font-size: 20px; font-weight: 700; margin-top: 3px; }}
  .stat .sub   {{ font-size: 11px; color: #aaa; margin-top: 1px; }}
  .grid1 {{ display: grid; grid-template-columns: 1fr; gap: 20px;
            padding: 20px 40px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
            padding: 0 40px 20px; }}
  .card {{ background: white; border-radius: 12px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.08);
           padding: 16px; border: 1px solid #eee; }}
  .section {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1px;
              color: #888; padding: 16px 40px 0; font-weight: 600; }}
  .legend-box {{ background: white; border-radius: 8px; padding: 14px 24px;
                 margin: 0 40px 8px; display: flex; gap: 24px; flex-wrap: wrap;
                 border: 1px solid #eee; font-size: 12px; }}
  .leg-item {{ display: flex; align-items: center; gap: 6px; }}
  .leg-dot {{ width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }}
  footer {{ text-align: center; padding: 20px; font-size: 12px; color: #aaa;
            border-top: 1px solid #eee; background: white; margin-top: 16px; }}
</style>
</head>
<body>

<div class="header">
  <h1>Segmentación de Créditos por Calidad de Cobro — Anexo 2 BCU</h1>
  <p>Fuente: BCU Boletín SSF &nbsp;|&nbsp; {fecha_label} &nbsp;|&nbsp; Cifras en miles de pesos uruguayos</p>
</div>

<div class="summary-bar">
{summary_stats}
</div>

<div class="legend-box">
  <strong style="margin-right:8px">Segmentos:</strong>
  <div class="leg-item"><div class="leg-dot" style="background:#43A047"></div> <b>Vigentes</b> — probabilidad de cobro alta</div>
  <div class="leg-item"><div class="leg-dot" style="background:#FDD835"></div> <b>Colocación vencida</b> — incumplimiento reciente (&lt;60d)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#FB8C00"></div> <b>En gestión</b> — en proceso de cobro (60-180d)</div>
  <div class="leg-item"><div class="leg-dot" style="background:#E53935"></div> <b>Morosos</b> — &gt;180 días, provisión ~100%</div>
  <div class="leg-item"><div class="leg-dot" style="background:#1565C0; border:2px solid #1565C0"></div> <b>Marco azul</b> = {focus_company_name}</div>
</div>

<p class="section">Distribución por institución</p>
<div class="grid1">
  <div class="card" id="chart_stacked"></div>
</div>

<p class="section">Volumen de mercado en cada segmento</p>
<div class="grid1">
  <div class="card" id="chart_mercado"></div>
</div>

<p class="section">{focus_company_name} en detalle</p>
<div class="grid1">
  <div class="card" id="chart_foco_zoom"></div>
</div>

<p class="section">Tasa de cobertura y composición sectorial</p>
<div class="grid2">
  <div class="card" id="chart_cobertura"></div>
  <div class="card" id="chart_sectorial"></div>
</div>

<footer>
  Generado por BCU Analysis pipeline &nbsp;|&nbsp; Datos: BCU Boletín SSF &nbsp;|&nbsp;
  Empresa foco: {focus_company_name} &nbsp;|&nbsp; {fecha_label}
</footer>

<script>
{scripts}
</script>
</body>
</html>"""


def build_summary_stats(df: pd.DataFrame) -> str:
    foco = df[df["codigo"] == FOCUS_COMPANY_CODE]
    sect = df[df["codigo"] == SECTOR_CODE]
    if foco.empty:
        return ""
    c = foco.iloc[0]
    s = sect.iloc[0] if not sect.empty else None

    pct_venc_foco = c["vencidos"] / c["cartera_bruta"] * 100
    pct_mor_foco  = c["morosos"]  / c["cartera_bruta"] * 100
    cob_total     = abs(c["det_total"]) / c["cartera_bruta"] * 100

    pct_venc_sect = s["vencidos"] / s["cartera_bruta"] * 100 if s is not None else 0
    pct_mor_sect  = s["morosos"]  / s["cartera_bruta"] * 100 if s is not None else 0

    stats = [
        (f"Cartera bruta {FOCUS_COMPANY_SHORT}", f"${c['cartera_bruta']/1e6:,.0f}M", "miles de pesos"),
        (f"Vigentes {FOCUS_COMPANY_SHORT}", f"{c['vigentes']/c['cartera_bruta']*100:.1f}%", f"${c['vigentes']/1e6:,.0f}M"),
        (f"Vencidos {FOCUS_COMPANY_SHORT}", f"{pct_venc_foco:.1f}%", f"vs sector {pct_venc_sect:.1f}%"),
        ("   — Morosos", f"{pct_mor_foco:.1f}%", f"vs sector {pct_mor_sect:.1f}%"),
        ("Cobertura total", f"{cob_total:.1f}%", "provisión / cartera bruta"),
        (f"Cartera morosa {FOCUS_COMPANY_SHORT}", f"${c['morosos']/1e6:,.0f}M", "provisionada al 100%"),
    ]

    html = ""
    for label, value, sub in stats:
        color = "#E53935" if ("Vencido" in label or "Moroso" in label or "morosa" in label) else "#1565C0" if FOCUS_COMPANY_SHORT in label else "#333"
        html += f"""<div class="stat">
  <div class="label">{label}</div>
  <div class="value" style="color:{color}">{value}</div>
  <div class="sub">{sub}</div>
</div>\n"""
    return html


def generate(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Cargando Anexo 2 del último mes...")
    df = get_ultimo_mes_anexo2()
    fecha_ts = df["fecha"].iloc[0]
    fecha_label = f"{MESES_FULL.get(fecha_ts.month, str(fecha_ts.month))} {fecha_ts.year}"
    log.info("Fecha: %s | %d instituciones", fecha_label, len(df))

    # Mostrar tabla empresa foco vs sector en log
    for codigo in [FOCUS_COMPANY_CODE, SECTOR_CODE]:
        row = df[df["codigo"] == codigo]
        if row.empty:
            continue
        r = row.iloc[0]
        log.info(
            "[%s] Bruta=%d  Vigentes=%d  Vencidos=%d  (Morosos=%d)",
            r["nombre"], r["cartera_bruta"], r["vigentes"], r["vencidos"], r["morosos"]
        )

    log.info("Generando gráficos...")
    figs = {
        "stacked":   fig_stacked_segmentos(df),
        "mercado":   fig_mercado_por_segmento(df),
        "foco_zoom": fig_foco_zoom(df),
        "cobertura": fig_cobertura_por_segmento(df),
        "sectorial": fig_composicion_sectorial_vigentes(df),
    }

    scripts = ""
    for chart_id, fig in figs.items():
        fig.update_layout(font=dict(family="-apple-system, sans-serif", size=11))
        js = pio.to_json(fig)
        scripts += f"Plotly.newPlot('chart_{chart_id}', {js}.data, {js}.layout, {{responsive:true}});\n"

    html = HTML_TEMPLATE.format(
        fecha_label=fecha_label,
        summary_stats=build_summary_stats(df),
        scripts=scripts,
        focus_company_name=FOCUS_COMPANY_NAME,
    )

    dest = output_dir / "anexo2_segmentos.html"
    dest.write_text(html, encoding="utf-8")
    log.info("Guardado: %s (%d KB)", dest, len(html.encode()) // 1024)
    return dest


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    generate()
