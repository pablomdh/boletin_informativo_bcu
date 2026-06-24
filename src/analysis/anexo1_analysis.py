"""
anexo1_analysis.py — Análisis de distribución de cartera y fondeo por plazos (Anexo 1).

Para el último mes disponible genera output/anexo1_plazos.html con:
  1. Distribución de créditos vigentes por plazo — stacked bar % por institución
  2. Volumen de mercado en cada tramo de plazo (quién financia a qué plazo)
  3. Distribución de pasivos financieros por plazo (fondeo)
  4. Análisis de descalce activo/pasivo para empresa foco vs sector
  5. Evolución temporal de la composición de plazos de la empresa foco (serie histórica)

Estructura Anexo 1 (verificada abril 2026):
  Activos — créditos vigentes (fila 10):
    Sector financiero  (f11): plazos f12-f18
    Sector no-fin      (f19): plazos f20-f26  ← principal para crédito consumo
      Vista | <30d | <91d | <181d | <367d | <3a | ≥3a

  Pasivos — a costo amortizado (fila 27):
    BCU (f28-35) | Dep.fin (f36-43) | Dep.no-fin (f44-51) |
    Débitos neg. (f52-59) | Otros (f60-67)  ← fideicomisos/obligaciones suelen reportarse aquí

  Nota: en Anexo 1 las instituciones empiezan en col 3 (no col 1 como las otras hojas).
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
RAW_DIR  = ROOT_DIR / "data" / "raw"
OUTPUT_DIR = ROOT_DIR / "output"

log = logging.getLogger(__name__)

MESES_ES = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"setiembre":9,"septiembre":9,
    "octubre":10,"noviembre":11,"diciembre":12,
}
MESES_FULL = {1:"Enero",2:"Febrero",3:"Marzo",4:"Abril",5:"Mayo",6:"Junio",
              7:"Julio",8:"Agosto",9:"Setiembre",10:"Octubre",11:"Noviembre",12:"Diciembre"}

INST_NAMES = {
    "803":"DIRECTOS","804":"SOCUR","805":"ANDA","815":"OCA SA",
    "816":"PROMOTORA","817":"RETOP","846":"DEL ESTE","852":"VERENDY",
    "853":"E.de Valor","854":"PASS CARD","858":"BAUTZEN","860":"FUCAC",
    "7884":"MICROFdURU","7886":"RMSA",
    "7890":"Floder","7894":"Sol.Integ.","981":"SECTOR TOTAL",
}
INST_NAMES[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_NAME

# Plazos ordenados de corto a largo
PLAZOS = ["Vista","<30d","<91d","<181d","<367d","<3a","≥3a"]
PLAZOS_COLORES = ["#1A237E","#283593","#3949AB","#5C6BC0","#7986CB","#9FA8DA","#C5CAE9"]

# Filas activos (sector no financiero — el relevante para crédito al consumo)
ACT_ROWS = {
    "total_vigentes": 10,   # créditos vigentes totales
    "sf_total":       11,   # sector financiero total
    "nf_total":       19,   # sector no financiero total
    "nf_Vista":       20,
    "nf_<30d":        21,
    "nf_<91d":        22,
    "nf_<181d":       23,
    "nf_<367d":       24,
    "nf_<3a":         25,
    "nf_≥3a":         26,
}

# Filas pasivos (subtotales por tramo de plazo — "Otros" incluye fideicomisos/obligaciones)
PAS_ROWS = {
    "pas_total":      27,
    "pas_otros_total":60,
    "pas_otros_Vista":    61,
    "pas_otros_<30d":     62,
    "pas_otros_<91d":     63,
    "pas_otros_<181d":    64,
    "pas_otros_<367d":    65,
    "pas_otros_<3a":      66,
    "pas_otros_≥3a":      67,
}


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def _fecha_de_nombre(p: Path) -> pd.Timestamp:
    m = re.search(r"grupo981_(\d{4})_(\w+)\.xls", p.name)
    if not m:
        return pd.Timestamp.min
    anio, mes_str = m.groups()
    mes_num = MESES_ES.get(mes_str.lower(), 0)
    return pd.Timestamp(int(anio), mes_num or 1, 1)


def parse_anexo1_file(filepath: Path) -> pd.DataFrame | None:
    try:
        wb = xlrd.open_workbook(str(filepath))
        ws = wb.sheet_by_name("Anexo 1")
    except Exception as e:
        log.warning("No se pudo abrir Anexo 1 en %s: %s", filepath.name, e)
        return None

    # Header instituciones en fila 8 — empieza en col 3
    instituciones = {}
    for col in range(ws.ncols):
        v = ws.cell_value(8, col)
        if v and col >= 3:
            m = re.match(r"^(\d+)", str(v))
            if m:
                instituciones[m.group(1)] = col

    if not instituciones:
        return None

    fecha = _fecha_de_nombre(filepath) + pd.offsets.MonthEnd(0)

    todos = {**ACT_ROWS, **PAS_ROWS}
    rows = []
    for codigo, col in instituciones.items():
        rec = {"fecha": fecha, "codigo": codigo}
        for campo, fila in todos.items():
            try:
                v = ws.cell_value(fila, col)
                rec[campo] = float(v) if (v != "" and v is not None) else 0.0
            except (IndexError, ValueError):
                rec[campo] = 0.0
        rows.append(rec)

    return pd.DataFrame(rows)


def get_serie_historica() -> pd.DataFrame:
    """Parsea Anexo 1 de todos los archivos disponibles."""
    archivos = sorted(RAW_DIR.glob("grupo981_*.xls"), key=_fecha_de_nombre)
    frames = []
    for f in archivos:
        df = parse_anexo1_file(f)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        raise FileNotFoundError("No hay datos de Anexo 1")
    return pd.concat(frames, ignore_index=True).sort_values(["fecha","codigo"])


def get_ultimo_mes(serie: pd.DataFrame) -> pd.DataFrame:
    return serie[serie["fecha"] == serie["fecha"].max()].copy()


# ─────────────────────────────────────────────────────────────────────────────
# Figuras — último mes
# ─────────────────────────────────────────────────────────────────────────────

def fig_stacked_activos(df: pd.DataFrame) -> go.Figure:
    """Stacked 100% horizontal — % de cada plazo en créditos vigentes sector no-fin."""
    d = df[(df["codigo"] != SECTOR_CODE)].copy()
    d["nombre"] = d["codigo"].map(lambda c: INST_NAMES.get(c, c))
    # Calcular total no-fin para normalizar
    d["total_nf"] = d["nf_total"].replace(0, pd.NA)
    campos = [f"nf_{p}" for p in PLAZOS]
    for c in campos:
        d[f"pct_{c}"] = d[c] / d["total_nf"] * 100

    # Solo instituciones con cartera no-financiero > 0
    d = d[d["total_nf"].notna() & (d["total_nf"] > 100)].copy()
    # Ordenar por peso en plazo largo (<3a + ≥3a)
    d["largo"] = d["pct_nf_<3a"].fillna(0) + d["pct_nf_≥3a"].fillna(0)
    d = d.sort_values("largo", ascending=True)

    fig = go.Figure()
    for plazo, color in zip(PLAZOS, PLAZOS_COLORES):
        campo = f"pct_nf_{plazo}"
        vals = d[campo].fillna(0).round(1)
        fig.add_trace(go.Bar(
            y=d["nombre"],
            x=vals,
            name=plazo,
            orientation="h",
            marker_color=color,
            marker_line=dict(color="white", width=0.5),
            hovertemplate=f"<b>%{{y}}</b><br>{plazo}: %{{x:.1f}}%<extra></extra>",
            text=vals.apply(lambda v: f"{v:.0f}%" if v > 5 else ""),
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=10, color="white"),
        ))

    # Marcar empresa foco
    foco_row = d[d["codigo"] == FOCUS_COMPANY_CODE]
    if not foco_row.empty:
        fig.add_annotation(
            y=foco_row["nombre"].iloc[0], x=103,
            text=f"◄ {FOCUS_COMPANY_SHORT}", showarrow=False,
            font=dict(color="#1565C0", size=11), xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="Distribución de Créditos Vigentes por Plazo — Sector No Financiero<br>"
                 "<sup>Ordenado por concentración en plazos largos (azul oscuro = corto, celeste = largo)</sup>",
            font=dict(size=15),
        ),
        xaxis=dict(title="% sobre créditos vigentes no-fin.", ticksuffix="%", range=[0,112]),
        yaxis=dict(title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        height=500,
        margin=dict(l=110, r=80, t=90, b=80),
        paper_bgcolor="white", plot_bgcolor="#fafafa",
    )
    return fig


def fig_mercado_por_plazo(df: pd.DataFrame) -> go.Figure:
    """4 subplots: volumen (B$) de mercado en cada tramo de plazo."""
    d = df[df["codigo"] != SECTOR_CODE].copy()
    d["nombre"] = d["codigo"].map(lambda c: INST_NAMES.get(c, c))
    d = d[d["nf_total"] > 100]

    # Agrupar plazos en 4 bloques para visibilidad
    bloques = [
        ("Corto plazo\n(Vista + <30d + <91d)",
         ["nf_Vista","nf_<30d","nf_<91d"], "#1565C0"),
        ("Mediano plazo\n(<181d + <367d)",
         ["nf_<181d","nf_<367d"], "#5C6BC0"),
        ("Largo plazo\n(<3a)",
         ["nf_<3a"], "#9FA8DA"),
        ("Muy largo plazo\n(≥3a)",
         ["nf_≥3a"], "#C5CAE9"),
    ]

    fig = make_subplots(rows=2, cols=2,
                        subplot_titles=[b[0] for b in bloques],
                        vertical_spacing=0.18, horizontal_spacing=0.12)

    pos = [(1,1),(1,2),(2,1),(2,2)]
    for (titulo, campos, color), (row, col) in zip(bloques, pos):
        d_b = d.copy()
        d_b["valor"] = d_b[campos].sum(axis=1)
        d_b = d_b[d_b["valor"] > 0].sort_values("valor", ascending=True)
        colors = ["#E53935" if c == FOCUS_COMPANY_CODE else color for c in d_b["codigo"]]
        fig.add_trace(go.Bar(
            y=d_b["nombre"], x=(d_b["valor"]/1e6).round(2),
            orientation="h", marker_color=colors,
            marker_line=dict(
                color=["#1565C0" if c == FOCUS_COMPANY_CODE else "white" for c in d_b["codigo"]],
                width=[2 if c == FOCUS_COMPANY_CODE else 0.5 for c in d_b["codigo"]],
            ),
            showlegend=False,
            hovertemplate="<b>%{y}</b><br>$%{x:.2f}B<extra></extra>",
        ), row=row, col=col)
        fig.update_xaxes(tickprefix="$", ticksuffix="B", row=row, col=col)

    fig.update_layout(
        title=dict(
            text="Volumen de Mercado por Tramo de Plazo (créditos vigentes no-fin.)<br>"
                 f"<sup>Rojo con borde azul = {FOCUS_COMPANY_NAME}</sup>",
            font=dict(size=15),
        ),
        height=560, paper_bgcolor="white", plot_bgcolor="#fafafa",
        margin=dict(l=100, r=40, t=90, b=40),
    )
    return fig


def fig_descalce_foco(df: pd.DataFrame) -> go.Figure:
    """
    Descalce activo/pasivo de la empresa foco y del sector.
    Barras hacia arriba = activos (usos), hacia abajo = pasivos (fuentes).
    Gap = porción de activos no cubierta por pasivos → fondeo residual implícito.
    """
    foco = df[df["codigo"] == FOCUS_COMPANY_CODE]
    sect = df[df["codigo"] == SECTOR_CODE]
    if foco.empty:
        return go.Figure().add_annotation(text=f"Sin datos {FOCUS_COMPANY_SHORT}", showarrow=False)
    c = foco.iloc[0]
    s = sect.iloc[0] if not sect.empty else None

    act_campos = [f"nf_{p}" for p in PLAZOS]
    pas_campos = [f"pas_otros_{p}" for p in PLAZOS]

    fig = make_subplots(rows=1, cols=2,
                        subplot_titles=[FOCUS_COMPANY_NAME, "Sector total"],
                        horizontal_spacing=0.12)

    for col_idx, (entidad, titulo) in enumerate([(c, FOCUS_COMPANY_NAME), (s, "Sector")], 1):
        if entidad is None:
            continue
        act_vals = [entidad.get(f, 0) / 1e6 for f in act_campos]
        pas_vals = [-entidad.get(f, 0) / 1e6 for f in pas_campos]

        fig.add_trace(go.Bar(
            name="Activos (créditos)", x=PLAZOS, y=act_vals,
            marker_color=PLAZOS_COLORES,
            hovertemplate="%{x}<br>Activos: $%{y:.2f}B<extra></extra>",
            legendgroup="act", showlegend=(col_idx==1),
        ), row=1, col=col_idx)

        fig.add_trace(go.Bar(
            name="Pasivos (fondeo)", x=PLAZOS, y=pas_vals,
            marker_color=["rgba(229,57,53,0.7)" for _ in PLAZOS],
            hovertemplate="%{x}<br>Pasivos: $%{y:.2f}B<extra></extra>",
            legendgroup="pas", showlegend=(col_idx==1),
        ), row=1, col=col_idx)

        fig.update_yaxes(title_text="$ B pesos" if col_idx==1 else "", tickprefix="$", ticksuffix="B",
                         row=1, col=col_idx)

    fig.add_hline(y=0, line_color="black", line_width=1, opacity=0.4)
    fig.update_layout(
        barmode="overlay",
        title=dict(
            text="Descalce Activo/Pasivo por Plazo — Créditos vs Fondeo<br>"
                 "<sup>Barras azules ↑ = activos colocados | Barras rojas ↓ = pasivos contratados | "
                 "Gap = fondeo implícito no contractual (patrimonio, cuentas por pagar, etc.)</sup>",
            font=dict(size=14),
        ),
        height=430,
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        paper_bgcolor="white", plot_bgcolor="#fafafa",
        margin=dict(l=60, r=40, t=100, b=80),
    )
    return fig


def fig_pasivos_por_plazo(df: pd.DataFrame) -> go.Figure:
    """Estructura de pasivos financieros por plazo — quién financia a qué plazo."""
    d = df[df["codigo"] != SECTOR_CODE].copy()
    d["nombre"] = d["codigo"].map(lambda c: INST_NAMES.get(c, c))
    d["pas_total_calc"] = d[[f"pas_otros_{p}" for p in PLAZOS]].sum(axis=1)
    d = d[d["pas_total_calc"] > 10].copy()

    # Normalizar como % del total de pasivos con plazo conocido
    for p in PLAZOS:
        d[f"pct_pas_{p}"] = d[f"pas_otros_{p}"] / d["pas_total_calc"].replace(0, pd.NA) * 100

    d = d.sort_values("pct_pas_<3a", ascending=True)

    fig = go.Figure()
    for plazo, color in zip(PLAZOS, PLAZOS_COLORES):
        vals = d[f"pct_pas_{plazo}"].fillna(0).round(1)
        fig.add_trace(go.Bar(
            y=d["nombre"], x=vals, name=plazo, orientation="h",
            marker_color=color,
            marker_line=dict(color="white", width=0.5),
            hovertemplate=f"<b>%{{y}}</b><br>{plazo}: %{{x:.1f}}%<extra></extra>",
            text=vals.apply(lambda v: f"{v:.0f}%" if v > 6 else ""),
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=10, color="white"),
        ))

    foco_row = d[d["codigo"] == FOCUS_COMPANY_CODE]
    if not foco_row.empty:
        fig.add_annotation(
            y=foco_row["nombre"].iloc[0], x=103, text=f"◄ {FOCUS_COMPANY_SHORT}",
            showarrow=False, font=dict(color="#1565C0", size=11), xanchor="left",
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text="Distribución de Pasivos Financieros por Plazo (\"Otros\" — fideicomisos/obligaciones)<br>"
                 "<sup>Solo instituciones con pasivos a plazo reportados en esta categoría</sup>",
            font=dict(size=15),
        ),
        xaxis=dict(title="% sobre pasivos a plazo", ticksuffix="%", range=[0,112]),
        yaxis=dict(title="", tickfont=dict(size=11)),
        legend=dict(orientation="h", y=-0.12, x=0.5, xanchor="center"),
        height=440,
        margin=dict(l=110, r=80, t=90, b=80),
        paper_bgcolor="white", plot_bgcolor="#fafafa",
    )
    return fig


def fig_evolucion_foco(serie: pd.DataFrame) -> go.Figure:
    """Evolución temporal de la composición de plazos de la empresa foco."""
    foco = serie[serie["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    if foco.empty:
        return go.Figure().add_annotation(text=f"Sin datos {FOCUS_COMPANY_SHORT} en serie histórica", showarrow=False)

    foco = foco[foco["nf_total"] > 0].copy()
    for p in PLAZOS:
        foco[f"pct_{p}"] = foco[f"nf_{p}"] / foco["nf_total"] * 100

    fig = go.Figure()
    for plazo, color in zip(PLAZOS, PLAZOS_COLORES):
        fig.add_trace(go.Scatter(
            x=foco["fecha"], y=foco[f"pct_{plazo}"].round(1),
            name=plazo, mode="lines+markers",
            line=dict(color=color, width=2),
            marker=dict(size=5),
            stackgroup="one",
            hovertemplate=f"{plazo}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        title=dict(
            text=f"{FOCUS_COMPANY_NAME} — Evolución de la Distribución de Plazos (créditos vigentes no-fin.)",
            font=dict(size=15),
        ),
        yaxis=dict(title="% sobre cartera vigente no-fin.", ticksuffix="%", range=[0,100]),
        xaxis=dict(title=""),
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center"),
        hovermode="x unified",
        height=400,
        paper_bgcolor="white", plot_bgcolor="#fafafa",
        margin=dict(l=60, r=40, t=70, b=80),
    )
    return fig


def fig_foco_vs_sector_radar(df: pd.DataFrame) -> go.Figure:
    """
    Comparativa directa empresa foco vs sector y peers en distribución de plazos.
    Grouped bar lado a lado para los plazos clave.
    """
    peers_show = [FOCUS_COMPANY_CODE, "815", "805", "804", "817", SECTOR_CODE]
    peer_colors = {
        FOCUS_COMPANY_CODE: "#E53935",
        "815": "#FF9800",
        "805": "#4CAF50",
        "804": "#2196F3",
        "817": "#9C27B0",
        SECTOR_CODE: "#90A4AE",
    }
    peer_names = {FOCUS_COMPANY_CODE: FOCUS_COMPANY_NAME, "815":"OCA SA","805":"ANDA",
                  "804":"SOCUR","817":"RETOP",SECTOR_CODE:"SECTOR"}

    fig = go.Figure()
    for codigo in peers_show:
        row = df[df["codigo"] == codigo]
        if row.empty:
            continue
        r = row.iloc[0]
        total = r["nf_total"]
        if total <= 0:
            continue
        pcts = [r.get(f"nf_{p}", 0) / total * 100 for p in PLAZOS]
        fig.add_trace(go.Bar(
            name=peer_names.get(codigo, codigo),
            x=PLAZOS, y=[round(v, 1) for v in pcts],
            marker_color=peer_colors.get(codigo, "#78909C"),
            marker_line=dict(
                color="#1565C0" if codigo == FOCUS_COMPANY_CODE else "white",
                width=2 if codigo == FOCUS_COMPANY_CODE else 0.5,
            ),
            hovertemplate=f"<b>{peer_names.get(codigo,codigo)}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        barmode="group",
        title=dict(
            text=f"Comparativa de Plazos — {FOCUS_COMPANY_SHORT} vs Peers y Sector",
            font=dict(size=15),
        ),
        yaxis=dict(title="% cartera vigente no-fin.", ticksuffix="%"),
        xaxis=dict(title="Tramo de plazo"),
        legend=dict(orientation="h", y=-0.18, x=0.5, xanchor="center"),
        hovermode="x unified",
        height=420,
        paper_bgcolor="white", plot_bgcolor="#fafafa",
        margin=dict(l=60, r=40, t=70, b=80),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Tabla de datos empresa foco
# ─────────────────────────────────────────────────────────────────────────────

def build_summary_stats(df: pd.DataFrame, serie: pd.DataFrame) -> str:
    foco = df[df["codigo"] == FOCUS_COMPANY_CODE]
    sect = df[df["codigo"] == SECTOR_CODE]
    if foco.empty:
        return ""
    c = foco.iloc[0]
    s = sect.iloc[0] if not sect.empty else None

    total_act = c["nf_total"]
    total_pas = c.get("pas_otros_total", 0)
    if total_pas == 0:
        total_pas = sum(c.get(f"pas_otros_{p}", 0) for p in PLAZOS)

    # Concentración en largo plazo
    largo = c.get("nf_<3a", 0) + c.get("nf_≥3a", 0)
    pct_largo = largo / total_act * 100 if total_act > 0 else 0

    # Concentración en corto (sector)
    corto_s = (s.get("nf_Vista",0) + s.get("nf_<30d",0) + s.get("nf_<91d",0)) if s is not None else 0
    pct_corto_s = corto_s / s["nf_total"] * 100 if s is not None and s["nf_total"] > 0 else 0

    stats = [
        (f"Créditos vigentes {FOCUS_COMPANY_SHORT}", f"${total_act/1e6:.2f}B", "sector no financiero"),
        ("Concentración en <3 años", f"{pct_largo:.0f}%",
         f"{FOCUS_COMPANY_SHORT} vs sector {100 - pct_corto_s:.0f}%"),
        (f"Pasivos a plazo {FOCUS_COMPANY_SHORT}", f"${total_pas/1e6:.2f}B", "fideicomisos / obligaciones"),
        ("Descalce estimado", f"${(total_act - total_pas)/1e6:.2f}B",
         "activos no cubiertos por pasivos contractuales"),
    ]

    html = ""
    for label, value, sub in stats:
        color = "#E53935" if "Descalce" in label else "#1565C0"
        html += (f'<div class="stat">'
                 f'<div class="label">{label}</div>'
                 f'<div class="value" style="color:{color}">{value}</div>'
                 f'<div class="sub">{sub}</div>'
                 f'</div>\n')
    return html


# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Distribución por Plazos — Anexo 1 BCU</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f7fa;color:#1a1a2e}}
  .header{{background:linear-gradient(135deg,#0d47a1 0%,#1565c0 50%,#1976d2 100%);
           color:white;padding:24px 40px}}
  .header h1{{font-size:22px;font-weight:700}}
  .header p{{font-size:13px;opacity:0.75;margin-top:5px}}
  .kpi-bar{{display:flex;gap:16px;padding:16px 40px;background:white;
             border-bottom:1px solid #eee;flex-wrap:wrap}}
  .stat{{background:#f8f9fa;border-radius:8px;padding:12px 18px;min-width:180px}}
  .label{{font-size:11px;text-transform:uppercase;color:#888;letter-spacing:.5px;font-weight:600}}
  .value{{font-size:20px;font-weight:700;margin-top:3px}}
  .sub{{font-size:11px;color:#aaa;margin-top:1px}}
  .legend-box{{background:white;border-radius:8px;padding:12px 24px;margin:12px 40px 4px;
               display:flex;gap:20px;flex-wrap:wrap;border:1px solid #eee;font-size:12px}}
  .leg-item{{display:flex;align-items:center;gap:6px}}
  .leg-dot{{width:14px;height:14px;border-radius:3px;flex-shrink:0}}
  .grid1{{display:grid;grid-template-columns:1fr;gap:20px;padding:16px 40px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:0 40px 16px}}
  .card{{background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);
         padding:16px;border:1px solid #eee}}
  .section{{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#888;
            padding:12px 40px 0;font-weight:600}}
  footer{{text-align:center;padding:20px;font-size:12px;color:#aaa;
          border-top:1px solid #eee;background:white;margin-top:16px}}
</style>
</head>
<body>
<div class="header">
  <h1>Distribución de Cartera y Fondeo por Plazos — Anexo 1 BCU</h1>
  <p>Fuente: BCU Boletín SSF &nbsp;|&nbsp; {fecha_label} &nbsp;|&nbsp; Cifras en miles de pesos uruguayos</p>
</div>
<div class="kpi-bar">{stats}</div>
<div class="legend-box">
  <strong style="margin-right:6px">Plazos:</strong>
  {leyenda}
</div>
<p class="section">Distribución por institución — activos</p>
<div class="grid1"><div class="card" id="c_stacked"></div></div>
<p class="section">Comparativa peers y volumen</p>
<div class="grid2">
  <div class="card" id="c_peers"></div>
  <div class="card" id="c_mercado"></div>
</div>
<p class="section">Fondeo y descalce</p>
<div class="grid2">
  <div class="card" id="c_pasivos"></div>
  <div class="card" id="c_descalce"></div>
</div>
<p class="section">Evolución temporal — {focus_company_name}</p>
<div class="grid1"><div class="card" id="c_evolucion"></div></div>
<footer>Generado por BCU Analysis pipeline &nbsp;|&nbsp; Datos: BCU Boletín SSF &nbsp;|&nbsp; {fecha_label}</footer>
<script>{scripts}</script>
</body>
</html>"""


def generate(output_dir: Path = OUTPUT_DIR):
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("Cargando serie histórica Anexo 1...")
    serie = get_serie_historica()
    ult = get_ultimo_mes(serie)
    fecha_ts = ult["fecha"].iloc[0]
    fecha_label = f"{MESES_FULL.get(fecha_ts.month, str(fecha_ts.month))} {fecha_ts.year}"
    log.info("Último mes: %s | %d instituciones", fecha_label, len(ult))

    # Log resumen empresa foco
    foco_row = ult[ult["codigo"] == FOCUS_COMPANY_CODE]
    if not foco_row.empty:
        c = foco_row.iloc[0]
        total = c["nf_total"]
        log.info("%s distribución plazos (no-fin):", FOCUS_COMPANY_SHORT)
        for p in PLAZOS:
            v = c.get(f"nf_{p}", 0)
            pct = v/total*100 if total > 0 else 0
            log.info("  %-8s $%.2fB  %.1f%%", p, v/1e6, pct)

    log.info("Generando gráficos...")
    figs = {
        "stacked":   fig_stacked_activos(ult),
        "peers":     fig_foco_vs_sector_radar(ult),
        "mercado":   fig_mercado_por_plazo(ult),
        "pasivos":   fig_pasivos_por_plazo(ult),
        "descalce":  fig_descalce_foco(ult),
        "evolucion": fig_evolucion_foco(serie),
    }

    scripts = ""
    for chart_id, fig in figs.items():
        fig.update_layout(font=dict(family="-apple-system,sans-serif", size=11))
        js = pio.to_json(fig)
        scripts += f"Plotly.newPlot('c_{chart_id}',{js}.data,{js}.layout,{{responsive:true}});\n"

    leyenda_html = "".join(
        f'<div class="leg-item"><div class="leg-dot" style="background:{c}"></div>{p}</div>'
        for p, c in zip(PLAZOS, PLAZOS_COLORES)
    )

    html = HTML_TEMPLATE.format(
        fecha_label=fecha_label,
        stats=build_summary_stats(ult, serie),
        leyenda=leyenda_html,
        scripts=scripts,
        focus_company_name=FOCUS_COMPANY_NAME,
    )
    dest = output_dir / "anexo1_plazos.html"
    dest.write_text(html, encoding="utf-8")
    log.info("Guardado: %s (%d KB)", dest, len(html.encode())//1024)
    return dest


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-7s  %(message)s",
                        datefmt="%H:%M:%S")
    generate()
