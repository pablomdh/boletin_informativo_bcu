"""
dashboard_gen.py — Genera output/dashboards/dashboard_interactivo.html (standalone, sin servidor).

Usa Plotly con include_plotlyjs='cdn'. Abrí el HTML directamente en el navegador.

Paneles:
  1. Market share cartera bruta — evolución mensual todas las instituciones
  2. Ratio de deterioro — empresa foco vs peers vs sector
  3. ROA y ROE de la empresa foco mes a mes (anualizados)
  4. Resultado operativo acumulado — empresa foco vs peers
  5. Distribución cartera por plazos — empresa foco vs sector (último mes)
  6. Ranking instituciones último mes — deterioro, resultado operativo, eficiencia
"""

import json
import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config.settings import (
    FOCUS_COMPANY_CODE, FOCUS_COMPANY_NAME, FOCUS_COMPANY_SHORT,
    FOCUS_COMPANY_COLOR, SECTOR_CODE,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "output"

MESES_ES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr",
    5: "may", 6: "jun", 7: "jul", 8: "ago",
    9: "set", 10: "oct", 11: "nov", 12: "dic",
}
MESES_ES_LARGO = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Setiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _fmt_mes(ts, largo: bool = False) -> str:
    """Formatea un Timestamp como 'abr 2026' o 'Abril 2026' en español."""
    nombre = MESES_ES_LARGO[ts.month] if largo else MESES_ES[ts.month]
    return f"{nombre} {ts.year}"

PEER_COLORS = {
    "804": "#2196F3",    # SOCUR — azul
    "805": "#4CAF50",    # ANDA — verde
    "815": "#FF9800",    # OCA SA — naranja
    "817": "#9C27B0",    # RETOP — violeta
    "860": "#00BCD4",    # FUCAC — cyan
    "981": "#90A4AE",    # SECTOR — gris
}
PEER_COLORS[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_COLOR

INST_NAMES = {
    "803": "DIRECTOS", "804": "SOCUR", "805": "ANDA", "815": "OCA SA",
    "816": "PROMOTORA", "817": "RETOP", "846": "DEL ESTE", "852": "VERENDY",
    "853": "E.de Valor", "854": "PASS CARD", "858": "BAUTZEN", "860": "FUCAC",
    "7884": "MICROFdURU", "7886": "RMSA",
    "7890": "Floder", "7894": "Sol.Integrales", "981": "SECTOR",
}
INST_NAMES[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_NAME

log = logging.getLogger(__name__)

BCU_BOLETIN_URL = "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF"


def _load_meta() -> dict:
    """Lee ultima_actualizacion.json; retorna defaults si no existe."""
    meta_path = PROCESSED_DIR / "ultima_actualizacion.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "fuente_url": BCU_BOLETIN_URL,
        "fecha_descarga": "—",
        "ultimo_mes": "—",
    }


def _fmt_fecha(ts) -> str:
    if hasattr(ts, 'month'):
        return f"{MESES_ES.get(ts.month, str(ts.month))}-{ts.year}"
    return str(ts)


def _nombre(codigo: str) -> str:
    return INST_NAMES.get(str(codigo), str(codigo))


def _color(codigo: str) -> str:
    return PEER_COLORS.get(str(codigo), "#78909C")


def load_data():
    df = pd.read_csv(PROCESSED_DIR / "serie_temporal.csv", parse_dates=["fecha"])
    df["codigo"] = df["codigo"].astype(str)
    ind = pd.read_csv(PROCESSED_DIR / "indicadores.csv", parse_dates=["fecha"])
    ind["codigo"] = ind["codigo"].astype(str)
    plazos_path = PROCESSED_DIR / "plazos.csv"
    plazos = pd.read_csv(plazos_path, parse_dates=["fecha"]) if plazos_path.exists() else pd.DataFrame()
    if not plazos.empty:
        plazos["codigo"] = plazos["codigo"].astype(str)
    return df, ind, plazos


# ─── Panel 1: Market Share — todas las instituciones ────────────────────────

def fig_market_share(ind: pd.DataFrame) -> go.Figure:
    sector = ind[ind["codigo"] == SECTOR_CODE][["fecha", "cartera_bruta"]].copy()
    empresas = ind[ind["codigo"] != SECTOR_CODE].copy()
    empresas = empresas.merge(
        sector.rename(columns={"cartera_bruta": "sector_total"}), on="fecha"
    )
    empresas["ms"] = empresas["cartera_bruta"] / empresas["sector_total"] * 100
    empresas = empresas.sort_values("fecha")

    # Solo instituciones con > 1% de share en algún mes
    max_ms = empresas.groupby("codigo")["ms"].max()
    codigos_relevantes = max_ms[max_ms >= 1.0].index.tolist()
    # Siempre incluir empresa foco aunque sea pequeña
    if FOCUS_COMPANY_CODE not in codigos_relevantes:
        codigos_relevantes.append(FOCUS_COMPANY_CODE)

    fig = go.Figure()
    for codigo in sorted(codigos_relevantes, key=lambda c: -empresas[empresas["codigo"]==c]["ms"].max()):
        data = empresas[empresas["codigo"] == codigo].sort_values("fecha")
        if data.empty:
            continue
        nombre = _nombre(codigo)
        color = _color(codigo)
        lw = 3 if codigo == FOCUS_COMPANY_CODE else 1.5
        dash = "solid" if codigo == FOCUS_COMPANY_CODE else "solid"
        fig.add_trace(go.Scatter(
            x=data["fecha"],
            y=data["ms"].round(2),
            name=nombre,
            mode="lines+markers",
            line=dict(color=color, width=lw, dash=dash),
            marker=dict(size=5 if codigo == FOCUS_COMPANY_CODE else 3),
            hovertemplate=f"<b>{nombre}</b><br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Market Share — Cartera Bruta (% del sector)", font=dict(size=16)),
        yaxis=dict(title="Share (%)", tickformat=".1f", ticksuffix="%"),
        xaxis=dict(title=""),
        legend=dict(orientation="v", x=1.01, y=1),
        hovermode="x unified",
        height=450,
        margin=dict(r=150),
    )
    return fig


# ─── Panel 2: Ratio Deterioro — empresa foco vs peers vs sector ──────────────

def fig_ratio_deterioro(ind: pd.DataFrame) -> go.Figure:
    codigos = [FOCUS_COMPANY_CODE, "817", "805", "804", "815", SECTOR_CODE]
    fig = go.Figure()
    for codigo in codigos:
        data = ind[ind["codigo"] == codigo].sort_values("fecha")
        if data.empty:
            continue
        nombre = _nombre(codigo)
        color = _color(codigo)
        lw = 3 if codigo == FOCUS_COMPANY_CODE else 1.5
        dash = "dot" if codigo == SECTOR_CODE else "solid"
        fig.add_trace(go.Scatter(
            x=data["fecha"],
            y=(data["ratio_deterioro"] * 100).round(2),
            name=nombre,
            mode="lines+markers",
            line=dict(color=color, width=lw, dash=dash),
            marker=dict(size=5 if codigo == FOCUS_COMPANY_CODE else 3),
            hovertemplate=f"<b>{nombre}</b><br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
        ))

    # Línea de alerta en 35%
    fig.add_hline(y=35, line_dash="dash", line_color="red", opacity=0.4,
                  annotation_text="Alerta: 35%", annotation_position="bottom right")

    fig.update_layout(
        title=dict(text="Ratio de Deterioro — Provisiones / Cartera Bruta", font=dict(size=16)),
        yaxis=dict(title="Ratio (%)", tickformat=".1f", ticksuffix="%"),
        xaxis=dict(title=""),
        hovermode="x unified",
        height=450,
        legend=dict(orientation="v", x=1.01, y=1),
        margin=dict(r=150),
    )
    return fig


# ─── Panel 3: ROA y ROE de la empresa foco ───────────────────────────────────

def fig_roa_roe(ind: pd.DataFrame) -> go.Figure:
    foco = ind[ind["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    if foco.empty:
        return go.Figure()

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Bar(
        x=foco["fecha"],
        y=(foco["roa_anual"] * 100).round(2),
        name="ROA anualizado",
        marker_color=["#E63946" if v < 0 else "#4CAF50" for v in foco["roa_anual"]],
        hovertemplate="ROA: %{y:.1f}%<extra></extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=foco["fecha"],
        y=(foco["roe_anual"] * 100).round(2),
        name="ROE anualizado",
        mode="lines+markers",
        line=dict(color="#2196F3", width=2.5),
        marker=dict(size=6),
        hovertemplate="ROE: %{y:.1f}%<extra></extra>",
    ), secondary_y=True)

    fig.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.3)

    fig.update_layout(
        title=dict(text=f"{FOCUS_COMPANY_NAME} — ROA y ROE Anualizados", font=dict(size=16)),
        hovermode="x unified",
        height=400,
        legend=dict(orientation="h", y=-0.2),
        barmode="group",
    )
    fig.update_yaxes(title_text="ROA (%)", ticksuffix="%", secondary_y=False)
    fig.update_yaxes(title_text="ROE (%)", ticksuffix="%", secondary_y=True)
    return fig


# ─── Panel 4: Resultado Operativo Acumulado ───────────────────────────────────

def fig_resultado_operativo(df: pd.DataFrame) -> go.Figure:
    codigos = [FOCUS_COMPANY_CODE, "817", "805", "804", "815", "860"]
    fig = go.Figure()
    for codigo in codigos:
        data = df[df["codigo"] == codigo].sort_values("fecha")
        if data.empty:
            continue
        nombre = _nombre(codigo)
        color = _color(codigo)
        lw = 3 if codigo == FOCUS_COMPANY_CODE else 1.5
        fig.add_trace(go.Scatter(
            x=data["fecha"],
            y=(data["resultado_operativo"] / 1000).round(1),
            name=nombre,
            mode="lines+markers",
            line=dict(color=color, width=lw),
            marker=dict(size=5 if codigo == FOCUS_COMPANY_CODE else 3),
            hovertemplate=f"<b>{nombre}</b><br>%{{x|%b %Y}}: $%{{y:.0f}}M<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="solid", line_color="black", opacity=0.3)
    fig.update_layout(
        title=dict(text="Resultado Operativo Acumulado (millones de pesos)", font=dict(size=16)),
        yaxis=dict(title="Resultado Op. (M$)", tickprefix="$", ticksuffix="M"),
        xaxis=dict(title=""),
        hovermode="x unified",
        height=450,
        legend=dict(orientation="v", x=1.01, y=1),
        margin=dict(r=150),
    )
    return fig


# ─── Panel 5: Distribución cartera por plazos ────────────────────────────────

def fig_plazos(plazos: pd.DataFrame) -> go.Figure:
    if plazos.empty:
        return go.Figure().add_annotation(text="Sin datos de Anexo 1", showarrow=False)

    ultimo_mes = plazos["fecha"].max()
    orden_plazos = ["Vista", "Menor_30d", "Menor_91d", "Menor_181d",
                    "Menor_367d", "Menor_3a", "Mayor_igual_3a"]
    labels_plazos = {
        "Vista": "Vista", "Menor_30d": "<30 días", "Menor_91d": "<91 días",
        "Menor_181d": "<181 días", "Menor_367d": "<367 días",
        "Menor_3a": "<3 años", "Mayor_igual_3a": "≥3 años",
    }
    colors_plazos = ["#1A237E", "#283593", "#3949AB", "#5C6BC0",
                     "#7986CB", "#9FA8DA", "#C5CAE9"]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[
            f"{FOCUS_COMPANY_NAME} ({_fmt_mes(ultimo_mes)})",
            f"Sector ({_fmt_mes(ultimo_mes)})"
        ],
        specs=[[{"type": "pie"}, {"type": "pie"}]]
    )

    for col_idx, codigo in enumerate([FOCUS_COMPANY_CODE, SECTOR_CODE], 1):
        data = plazos[(plazos["fecha"] == ultimo_mes) & (plazos["codigo"] == codigo)]
        data = data.set_index("plazo").reindex(orden_plazos)
        data = data[data["monto"].notna() & (data["monto"] > 0)]

        fig.add_trace(go.Pie(
            labels=[labels_plazos.get(p, p) for p in data.index],
            values=data["monto"].round(0),
            name=FOCUS_COMPANY_SHORT if codigo == FOCUS_COMPANY_CODE else "Sector",
            hole=0.4,
            marker_colors=colors_plazos[:len(data)],
            textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>$%{value:,.0f}k<br>%{percent}<extra></extra>",
        ), row=1, col=col_idx)

    fig.update_layout(
        title=dict(text="Distribución Cartera Vigente por Plazo (sector no financiero)", font=dict(size=16)),
        height=450,
        showlegend=True,
    )
    return fig


# ─── Panel 6: Ranking último mes ─────────────────────────────────────────────

def fig_ranking_ultimo_mes(ind: pd.DataFrame) -> go.Figure:
    ultimo_mes = ind["fecha"].max()
    ult = ind[(ind["fecha"] == ultimo_mes) & (ind["codigo"] != SECTOR_CODE)].copy()
    ult = ult[ult["cartera_bruta"].notna() & (ult["cartera_bruta"] > 0)].copy()
    ult["nombre"] = ult["codigo"].map(_nombre)

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=[
            "Ratio Deterioro (menor = mejor)",
            "Resultado Operativo (M$)",
            "Ratio Eficiencia (menor = mejor)",
        ],
        horizontal_spacing=0.12,
    )

    def bar_colors(series, codigo_col, reverse=False):
        max_v = series.max()
        min_v = series.min()
        colors = []
        for i, (_, row) in enumerate(series.items()):
            if ult.iloc[i][codigo_col] == FOCUS_COMPANY_CODE:
                colors.append("#E63946")
            elif reverse:
                norm = (max_v - row) / (max_v - min_v + 1e-9)
                g = int(80 + norm * 100)
                colors.append(f"rgb(70,{g},180)")
            else:
                norm = (row - min_v) / (max_v - min_v + 1e-9)
                g = int(80 + norm * 100)
                colors.append(f"rgb(70,{g},180)")
        return colors

    # Panel A: deterioro
    df_det = ult[["nombre", "codigo", "ratio_deterioro"]].dropna().sort_values("ratio_deterioro")
    colors_det = ["#E63946" if c == FOCUS_COMPANY_CODE else "#5C6BC0" for c in df_det["codigo"]]
    fig.add_trace(go.Bar(
        x=(df_det["ratio_deterioro"] * 100).round(1),
        y=df_det["nombre"],
        orientation="h",
        marker_color=colors_det,
        text=(df_det["ratio_deterioro"] * 100).round(1).astype(str) + "%",
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>",
        showlegend=False,
    ), row=1, col=1)
    fig.update_xaxes(ticksuffix="%", row=1, col=1)

    # Panel B: resultado operativo
    df_res = ult[["nombre", "codigo", "resultado_operativo"]].dropna().sort_values("resultado_operativo")
    colors_res = ["#E63946" if c == FOCUS_COMPANY_CODE else ("#4CAF50" if v >= 0 else "#F44336")
                  for c, v in zip(df_res["codigo"], df_res["resultado_operativo"])]
    fig.add_trace(go.Bar(
        x=(df_res["resultado_operativo"] / 1000).round(0),
        y=df_res["nombre"],
        orientation="h",
        marker_color=colors_res,
        text=("$" + (df_res["resultado_operativo"] / 1000).round(0).astype(int).astype(str) + "M"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>$%{x:.0f}M<extra></extra>",
        showlegend=False,
    ), row=1, col=2)
    fig.update_xaxes(tickprefix="$", ticksuffix="M", row=1, col=2)

    # Panel C: eficiencia
    df_efi = ult[["nombre", "codigo", "ratio_eficiencia"]].dropna()
    df_efi = df_efi[df_efi["ratio_eficiencia"] < 5]  # filtrar outliers con MFB ~0
    df_efi = df_efi.sort_values("ratio_eficiencia")
    colors_efi = ["#E63946" if c == FOCUS_COMPANY_CODE else "#5C6BC0" for c in df_efi["codigo"]]
    fig.add_trace(go.Bar(
        x=(df_efi["ratio_eficiencia"] * 100).round(1),
        y=df_efi["nombre"],
        orientation="h",
        marker_color=colors_efi,
        text=(df_efi["ratio_eficiencia"] * 100).round(1).astype(str) + "%",
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>",
        showlegend=False,
    ), row=1, col=3)
    fig.update_xaxes(ticksuffix="%", row=1, col=3)

    fig.update_layout(
        title=dict(
            text=f"Ranking Instituciones — {_fmt_mes(ultimo_mes, largo=True)}  (rojo = {FOCUS_COMPANY_NAME})",
            font=dict(size=16)
        ),
        height=500,
        margin=dict(l=120, r=80, t=80, b=40),
    )
    return fig


# ─── HTML Dashboard ───────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BCU Analysis — {focus_company_name} Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f5f7fa; color: #1a1a2e; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
             color: white; padding: 28px 40px; }}
  .header h1 {{ font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }}
  .header p {{ font-size: 14px; opacity: 0.7; margin-top: 6px; }}
  .kpi-bar {{ display: flex; gap: 16px; padding: 20px 40px;
              background: white; border-bottom: 1px solid #e0e0e0;
              flex-wrap: wrap; }}
  .kpi {{ background: #f8f9fa; border-radius: 10px; padding: 14px 20px;
          min-width: 160px; border-left: 4px solid #ccc; }}
  .kpi.red {{ border-left-color: #E63946; }}
  .kpi.green {{ border-left-color: #4CAF50; }}
  .kpi.amber {{ border-left-color: #FF9800; }}
  .kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
                color: #666; font-weight: 600; }}
  .kpi-value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .kpi-sub {{ font-size: 11px; color: #999; margin-top: 2px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr;
           gap: 20px; padding: 24px 40px; }}
  .grid.full {{ grid-template-columns: 1fr; }}
  .card {{ background: white; border-radius: 12px;
           box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 20px;
           border: 1px solid #eee; overflow: hidden; }}
  .section-title {{ font-size: 13px; text-transform: uppercase;
                    letter-spacing: 1px; color: #666; padding: 8px 40px 0;
                    font-weight: 600; }}
  .alert-box {{ margin: 12px 40px; padding: 12px 20px;
                background: #fff3cd; border-left: 4px solid #ff9800;
                border-radius: 6px; font-size: 13px; }}
  .alert-box.danger {{ background: #ffeaea; border-left-color: #E63946; }}
  footer {{ text-align: center; padding: 24px; font-size: 12px; color: #aaa;
            border-top: 1px solid #eee; background: white; margin-top: 20px; }}
  footer a {{ color: #457B9D; text-decoration: none; }}
  footer a:hover {{ text-decoration: underline; }}
  footer small {{ display: block; margin-top: 6px; font-size: 11px; color: #bbb; }}

  @media (max-width: 768px) {{
    .header {{ padding: 16px 16px; }}
    .header h1 {{ font-size: 16px; }}
    .header p {{ font-size: 12px; }}
    .kpi-bar {{ padding: 12px 16px; gap: 10px; }}
    .kpi {{ min-width: calc(50% - 5px); padding: 10px 14px; }}
    .kpi-value {{ font-size: 18px; }}
    .grid {{ grid-template-columns: 1fr; padding: 12px 16px; gap: 12px; }}
    .grid.full {{ padding: 12px 16px; }}
    .section-title {{ padding: 8px 16px 0; }}
    .alert-box {{ margin: 8px 16px; }}
    .card {{ min-height: 320px; }}
    footer {{ padding: 16px; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>BCU Analysis — {focus_company_name} &amp; Sector de Crédito al Consumo Uruguay</h1>
  <p>Fuente: Banco Central del Uruguay — Boletín SSF &nbsp;|&nbsp; {periodo} &nbsp;|&nbsp; Cifras en miles de pesos uruguayos</p>
</div>

{kpi_bar}
{alerts}

<p class="section-title">Evolución del sector</p>
<div class="grid">
  <div class="card" id="chart_ms"></div>
  <div class="card" id="chart_det"></div>
</div>

<p class="section-title">Rentabilidad y resultado</p>
<div class="grid">
  <div class="card" id="chart_roa"></div>
  <div class="card" id="chart_res"></div>
</div>

<p class="section-title">Cartera y ranking</p>
<div class="grid">
  <div class="card" id="chart_plazos"></div>
  <div class="card" id="chart_rank_top"></div>
</div>

<div class="grid full">
  <div class="card" id="chart_rank_full"></div>
</div>

<footer>
  Fuente: <a href="{fuente_url}" target="_blank" rel="noopener">Banco Central del Uruguay — Boletín SSF</a>
  &nbsp;|&nbsp; Empresa foco: {focus_company_name}
  &nbsp;|&nbsp; Datos al {ultimo_mes}
  &nbsp;|&nbsp; Actualizado: {fecha_actualizacion}
  <small>Este sitio no tiene afiliación oficial con el Banco Central del Uruguay ni con las instituciones analizadas. Los datos son de fuente pública.</small>
</footer>

<script>
// Locale español para ejes de fechas en Plotly
Plotly.register({{
  moduleType: 'locale', name: 'es', dictionary: {{}},
  format: {{
    months: ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Setiembre','Octubre','Noviembre','Diciembre'],
    shortMonths: ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Set','Oct','Nov','Dic'],
    days: ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'],
    shortDays: ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'],
    decimal: ',', thousands: '.'
  }}
}});
Plotly.setPlotConfig({{locale: 'es'}});

{plotly_scripts}

// Ajustes para mobile: márgenes compactos y leyenda horizontal
(function() {{
  if (window.innerWidth > 768) return;
  var ids = ['chart_ms','chart_det','chart_roa','chart_res','chart_plazos','chart_rank_top','chart_rank_full'];
  var mobileLayout = {{
    height: 320,
    margin: {{l: 38, r: 8, t: 36, b: 28}},
    font: {{size: 9}},
    legend: {{orientation: 'h', y: -0.22, x: 0, font: {{size: 8}}}}
  }};
  ids.forEach(function(id) {{
    var el = document.getElementById(id);
    if (el && el.data) Plotly.relayout(id, mobileLayout);
  }});
}})();
</script>
</body>
</html>"""


def build_kpi_bar(ind: pd.DataFrame) -> str:
    foco = ind[ind["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    if foco.empty:
        return f'<div class="kpi-bar"><div class="kpi"><span class="kpi-label">Sin datos {FOCUS_COMPANY_SHORT}</span></div></div>'

    last = foco.iloc[-1]
    prev = foco.iloc[-2] if len(foco) > 1 else last

    ms = last["ms_cartera_bruta"] * 100
    det = last["ratio_deterioro"] * 100
    roa = last["roa_anual"] * 100
    roe = last["roe_anual"] * 100
    efic = last["ratio_eficiencia"] * 100
    lev = last["leverage"]
    res_op = last["resultado_operativo"] / 1_000_000

    ms_class = "green" if ms >= 10 else "amber"
    det_class = "red" if det > 35 else ("amber" if det > 25 else "green")
    roa_class = "green" if roa > 0 else "red"
    roe_class = "green" if roe > 0 else "red"
    efic_class = "green" if efic < 45 else ("amber" if efic < 55 else "red")

    delta_det = det - (prev["ratio_deterioro"] * 100)
    delta_roa = roa - (prev["roa_anual"] * 100)

    return f"""<div class="kpi-bar">
  <div class="kpi {ms_class}">
    <div class="kpi-label">Market Share</div>
    <div class="kpi-value">{ms:.1f}%</div>
    <div class="kpi-sub">cartera bruta vs sector</div>
  </div>
  <div class="kpi {det_class}">
    <div class="kpi-label">Ratio Deterioro</div>
    <div class="kpi-value">{det:.1f}%</div>
    <div class="kpi-sub">{'▲' if delta_det > 0 else '▼'}{abs(delta_det):.1f}pp vs mes anterior</div>
  </div>
  <div class="kpi {roa_class}">
    <div class="kpi-label">ROA Anualizado</div>
    <div class="kpi-value">{roa:.1f}%</div>
    <div class="kpi-sub">{'▲' if delta_roa > 0 else '▼'}{abs(delta_roa):.1f}pp vs mes anterior</div>
  </div>
  <div class="kpi {roe_class}">
    <div class="kpi-label">ROE Anualizado</div>
    <div class="kpi-value">{roe:.1f}%</div>
    <div class="kpi-sub">resultado op / patrimonio</div>
  </div>
  <div class="kpi {efic_class}">
    <div class="kpi-label">Ratio Eficiencia</div>
    <div class="kpi-value">{efic:.1f}%</div>
    <div class="kpi-sub">gastos / margen financiero bruto</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Resultado Op.</div>
    <div class="kpi-value" style="color:{'#E63946' if res_op < 0 else '#4CAF50'}">${res_op:+.0f}B</div>
    <div class="kpi-sub">acumulado período fiscal</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Leverage</div>
    <div class="kpi-value">{lev:.1f}x</div>
    <div class="kpi-sub">pasivos / patrimonio</div>
  </div>
</div>"""


def build_alerts(ind: pd.DataFrame) -> str:
    foco = ind[ind["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    if foco.empty:
        return ""
    last = foco.iloc[-1]
    alerts = []

    det = last["ratio_deterioro"] * 100
    roa = last["roa_anual"] * 100
    efic = last["ratio_eficiencia"] * 100

    if det > 35:
        alerts.append(("danger", f"⚠ Ratio de deterioro en {det:.1f}% — supera umbral crítico del 35%"))
    if roa < 0:
        alerts.append(("danger", f"⚠ ROA negativo ({roa:.1f}%) — la empresa está destruyendo valor en base anualizada"))
    if efic > 50:
        alerts.append(("danger", f"⚠ Ratio de eficiencia en {efic:.1f}% — por encima del 50%, los gastos consumen más de la mitad del margen"))

    # Tendencia deterioro — últimos 3 meses
    if len(foco) >= 3:
        det_series = foco["ratio_deterioro"].tail(3) * 100
        if all(det_series.diff().dropna() > 0):
            alerts.append(("amber", f"⚡ Deterioro en tendencia ascendente por 3 meses consecutivos ({det_series.iloc[0]:.1f}% → {det_series.iloc[-1]:.1f}%)"))

    html = ""
    for cls, msg in alerts:
        html += f'<div class="alert-box {cls}">{msg}</div>\n'
    return html


def generate_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Cargando datos...")
    df, ind, plazos = load_data()

    ultimo_mes = df["fecha"].max()
    primer_mes = df["fecha"].min()
    periodo = f"{_fmt_mes(primer_mes)} → {_fmt_mes(ultimo_mes)}"

    log.info("Generando figuras...")
    figs = {
        "ms": fig_market_share(ind),
        "det": fig_ratio_deterioro(ind),
        "roa": fig_roa_roe(ind),
        "res": fig_resultado_operativo(df),
        "plazos": fig_plazos(plazos),
    }

    # Ranking — top 8 por resultado para card mediana
    ultimo_mes = ind["fecha"].max()
    ult = ind[(ind["fecha"] == ultimo_mes) & (ind["codigo"] != SECTOR_CODE)].copy()
    ult = ult[ult["cartera_bruta"].notna() & (ult["cartera_bruta"] > 0)].copy()

    fig_rank = fig_ranking_ultimo_mes(ind)

    # Construir scripts Plotly
    import plotly.io as pio
    scripts = ""
    for chart_id, fig in figs.items():
        fig.update_layout(
            paper_bgcolor="white",
            plot_bgcolor="#fafafa",
            font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size=11),
        )
        div_js = pio.to_json(fig)
        scripts += f"\nPlotly.newPlot('chart_{chart_id}', {div_js}.data, {div_js}.layout, {{responsive:true, displayModeBar:'hover'}});\n"

    fig_rank.update_layout(
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        font=dict(family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size=11),
    )
    rank_js = pio.to_json(fig_rank)
    scripts += f"\nPlotly.newPlot('chart_rank_full', {rank_js}.data, {rank_js}.layout, {{responsive:true, displayModeBar:'hover'}});\n"
    # Empty top-right card
    scripts += "\nPlotly.newPlot('chart_rank_top', [{type:'scatter',x:[],y:[]}], {title:{text:'Ver ranking completo abajo'},height:400,paper_bgcolor:'white'}, {responsive:true});\n"

    kpi_bar = build_kpi_bar(ind)
    alerts_html = build_alerts(ind)

    meta = _load_meta()
    html = HTML_TEMPLATE.format(
        periodo=periodo,
        kpi_bar=kpi_bar,
        alerts=alerts_html,
        plotly_scripts=scripts,
        focus_company_name=FOCUS_COMPANY_NAME,
        focus_company_code=FOCUS_COMPANY_CODE,
        fuente_url=meta["fuente_url"],
        ultimo_mes=meta.get("ultimo_mes", "—"),
        fecha_actualizacion=meta.get("fecha_descarga", "—"),
    )

    dest = OUTPUT_DIR / "dashboard_interactivo.html"
    dest.write_text(html, encoding="utf-8")
    log.info("Dashboard guardado: %s (%d KB)", dest, len(html.encode()) // 1024)
    return dest


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    generate_dashboard()
