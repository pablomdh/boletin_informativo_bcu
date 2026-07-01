"""
dashboard_gen.py — Genera output/dashboards/dashboard_interactivo.html

Dashboard interactivo con:
  - Selector de categoría (Admins, Bancos Privados, Bancos Oficiales, Cooperativas, Casas Financieras)
  - Selector de institución dinámico
  - 4 pestañas: Acerca del Dashboard | Análisis General | Calidad Tomadores | Distribución Plazos
  - KPIs dinámicos por institución
  - Datos embebidos como JSON; renderizado client-side con Plotly
  - Responsive mobile
"""

import json
import logging
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from config.settings import (
    FOCUS_COMPANY_CODE,
    FOCUS_COMPANY_NAME,
    FOCUS_COMPANY_COLOR,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "output" / "dashboards"

log = logging.getLogger(__name__)

BCU_URL = "https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF"

# ── Nombres y colores ─────────────────────────────────────────────────────────

ADMIN_NAMES = {
    "803": "DIRECTOS",
    "804": "SOCUR",
    "805": "ANDA",
    "815": "OCA SA",
    "816": "PROMOTORA",
    "817": "RETOP",
    "846": "DEL ESTE",
    "852": "VERENDY",
    "853": "E.de Valor",
    "854": "PASS CARD",
    "858": "BAUTZEN",
    "860": "FUCAC",
    "7884": "Repúb.Micro",
    "7886": "RMSA",
    "7890": "Floder",
    "7894": "Sol.Int.",
    "981": "Sector Admin",
}
ADMIN_NAMES[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_NAME

ADMIN_COLORS = {
    "804": "#2196F3",
    "805": "#4CAF50",
    "815": "#FF9800",
    "817": "#9C27B0",
    "860": "#00BCD4",
    "981": "#90A4AE",
    "803": "#607D8B",
    "816": "#795548",
    "846": "#009688",
    "852": "#FF5722",
    "853": "#3F51B5",
    "854": "#E91E63",
    "858": "#FFC107",
    "7884": "#1B5E20",
    "7886": "#4E342E",
    "7890": "#006064",
    "7894": "#1A237E",
}
ADMIN_COLORS[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_COLOR

BANK_COLORS = {
    "113": "#1565C0",
    "137": "#C62828",
    "128": "#E65100",
    "153": "#2E7D32",
    "1": "#1A237E",
    "91": "#4527A0",
    "607": "#00695C",
    "361": "#4E342E",
    "110": "#37474F",
    "205": "#0277BD",
    "157": "#880E4F",
    "162": "#558B2F",
    "246": "#F57F17",
}

CAT_LABELS = {
    "admin": "Administradoras de Crédito",
    "bp": "Bancos Privados",
    "bo": "Bancos Oficiales",
    "coop": "Cooperativas",
    "casas": "Casas Financieras",
}

GRUPO_TO_CAT = {
    "grupo997": "bp",
    "grupo99": "bo",
    "grupo996": "coop",
    "grupo998": "casas",
}

CAT_SECTOR_COD = {
    "admin": "981",
    "bp": "997",
    "bo": "99",
    "coop": "996",
    "casas": "998",
}

# Plazos: nombre CSV → clave JS
PLZ_MAP = {
    "Vista": "vista",
    "Menor_30d": "lt30",
    "Menor_91d": "lt91",
    "Menor_181d": "lt181",
    "Menor_367d": "lt367",
    "Menor_3a": "lt3a",
    "Mayor_igual_3a": "geq3a",
}

MONTHS_EN = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _iso(ts) -> str:
    return ts.strftime("%Y-%m-%d")


def _fmt_kpi_fecha(ts) -> str:
    return f"{MONTHS_EN[ts.month]} {ts.year}"


def _safe(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
    except TypeError:
        pass
    return v


def _sl(series) -> list:
    """Convierte una pandas Series a lista con None en lugar de NaN."""
    return [_safe(v) for v in series.tolist()]


def _strip_cod(name_cod: str) -> str:
    """'113 Itaú' → 'Itaú'"""
    parts = str(name_cod).strip().split(" ", 1)
    return (
        parts[1].strip()
        if len(parts) > 1 and parts[0].isdigit()
        else str(name_cod).strip()
    )


# ── Carga de datos ────────────────────────────────────────────────────────────


def load_all():
    ind = pd.read_csv(PROCESSED / "indicadores.csv", parse_dates=["fecha"])
    ind["codigo"] = ind["codigo"].astype(str)

    anx2 = pd.read_csv(PROCESSED / "admin_anx2_detail.csv", parse_dates=["fecha"])
    anx2["codigo"] = anx2["codigo"].astype(str)

    plazos = pd.read_csv(PROCESSED / "plazos.csv", parse_dates=["fecha"])
    plazos["codigo"] = plazos["codigo"].astype(str)

    bancos = pd.read_csv(PROCESSED / "bancos_serie_temporal.csv", parse_dates=["fecha"])
    bancos["codigo"] = bancos["codigo"].astype(str)

    bp_path = PROCESSED / "bancos_plazos.csv"
    bancos_plazos = (
        pd.read_csv(bp_path, parse_dates=["fecha"])
        if bp_path.exists()
        else pd.DataFrame()
    )
    if not bancos_plazos.empty:
        bancos_plazos["codigo"] = bancos_plazos["codigo"].astype(str)

    tasas = pd.read_csv(PROCESSED / "tasas.csv", parse_dates=["fecha"])

    meta_path = PROCESSED / "ultima_actualizacion.json"
    meta = (
        json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    )

    return ind, anx2, plazos, bancos, bancos_plazos, tasas, meta


# ── Construcción INST para administradoras ────────────────────────────────────


def _anx2_admin(anx2_df, ind_df, cod):
    a = anx2_df[anx2_df["codigo"] == cod].sort_values("fecha")
    i = ind_df[ind_df["codigo"] == cod][["fecha", "cartera_bruta"]].sort_values("fecha")
    if a.empty or i.empty:
        return {}
    m = a.merge(i, on="fecha", how="left")
    tot = m["cartera_bruta"].replace(0, float("nan"))

    def pct(col):
        return _sl((m[col].fillna(0) / tot * 100).round(3))

    vig = _sl(
        (
            (
                tot
                - m["col_vencida"].fillna(0)
                - m["en_gestion"].fillna(0)
                - m["morosos"].fillna(0)
            )
            / tot
            * 100
        ).round(3)
    )
    return {
        "fechas": [_iso(f) for f in m["fecha"]],
        "vigentes_pct": vig,
        "col_vencida_pct": pct("col_vencida"),
        "en_gestion_pct": pct("en_gestion"),
        "morosos_pct": pct("morosos"),
    }


def _plazos_admin(plazos_df, cod):
    p = plazos_df[plazos_df["codigo"] == cod].sort_values("fecha")
    if p.empty:
        return {}
    fechas = sorted(p["fecha"].unique())
    out = {"fechas": [_iso(f) for f in fechas]}
    for csv_col, key in PLZ_MAP.items():
        vals = []
        for f in fechas:
            row = p[(p["fecha"] == f) & (p["plazo"] == csv_col)]
            vals.append(
                _safe(float(row["monto"].values[0]) / 1_000 if not row.empty else None)
            )
        out[key] = vals
    return out


def build_admin_inst(ind, anx2, plazos) -> dict:
    result = {}
    for cod in ind["codigo"].unique():
        df = ind[ind["codigo"] == cod].sort_values("fecha")
        if df.empty:
            continue

        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        det = _safe(last.get("ratio_deterioro"))
        det_p = _safe(prev.get("ratio_deterioro"))
        roa = _safe(last.get("roa_anual"))
        roa_p = _safe(prev.get("roa_anual"))
        roe = _safe(last.get("roe_anual"))
        efic = _safe(last.get("ratio_eficiencia"))
        ms = _safe(last.get("ms_cartera_bruta"))
        lev = _safe(last.get("leverage"))
        cb = _safe(last.get("cartera_bruta"))
        res = _safe(last.get("resultado_operativo"))

        kpis = {
            "fecha": _fmt_kpi_fecha(last["fecha"]),
            "n_meses": len(df),
            "deterioro": round(det * 100, 3) if det is not None else None,
            "delta_deterioro": round((det - det_p) * 100, 3) if det and det_p else None,
            "roa": round(roa * 100, 4) if roa is not None else None,
            "delta_roa": round((roa - roa_p) * 100, 4) if roa and roa_p else None,
            "roe": round(roe * 100, 4) if roe is not None else None,
            "eficiencia": round(efic * 100, 4) if efic is not None else None,
            "ms": round(ms * 100, 4) if ms is not None else None,
            "leverage": round(lev, 4) if lev is not None else None,
            "cartera_b": round(cb / 1_000_000, 4) if cb is not None else None,
            "resultado_op": round(res / 1_000, 4) if res is not None else None,
        }

        det_series = _sl((df["ratio_deterioro"] * 100).round(3))
        det_max = max((v for v in det_series if v is not None), default=60)

        series = {
            "fechas": [_iso(f) for f in df["fecha"]],
            "ms": _sl((df["ms_cartera_bruta"] * 100).round(4)),
            "deterioro": det_series,
            "roa": _sl((df["roa_anual"] * 100).round(4)),
            "roe": _sl((df["roe_anual"] * 100).round(4)),
            "eficiencia": _sl((df["ratio_eficiencia"] * 100).round(4)),
            "resultado_op": _sl((df["resultado_operativo"] / 1_000).round(4)),
            "cartera_b": _sl((df["cartera_bruta"] / 1_000_000).round(4)),
            "vigentes_pct": _sl((100 - df["ratio_deterioro"] * 100).round(3)),
        }

        result[cod] = {
            "_cod": cod,
            "name": ADMIN_NAMES.get(cod, cod),
            "color": ADMIN_COLORS.get(cod, "#78909C"),
            "category": "admin",
            "sector_cod": "981",
            "det_label": "Deterioro / Cartera Bruta",
            "det_range": [0, min(100, round(det_max * 1.3, 0))],
            "kpis": kpis,
            "series": series,
            "anx2": _anx2_admin(anx2, ind, cod),
            "plazos": _plazos_admin(plazos, cod),
        }
    return result


# ── Construcción INST para bancos ─────────────────────────────────────────────


def _anx2_bank(df_i):
    if df_i.empty:
        return {}
    df = df_i.sort_values("fecha")
    tot = (
        df["vigentes"].fillna(0)
        + df["col_vencida"].fillna(0)
        + df["en_gestion"].fillna(0)
        + df["morosos"].fillna(0)
    ).replace(0, float("nan"))

    def pct(col):
        return _sl((df[col].fillna(0) / tot * 100).round(3))

    return {
        "fechas": [_iso(f) for f in df["fecha"]],
        "vigentes_pct": pct("vigentes"),
        "col_vencida_pct": pct("col_vencida"),
        "en_gestion_pct": pct("en_gestion"),
        "morosos_pct": pct("morosos"),
    }


def _plazos_bank(bancos_plazos, cod):
    if bancos_plazos.empty:
        return {}
    p = bancos_plazos[bancos_plazos["codigo"] == cod].sort_values("fecha")
    if p.empty:
        return {}
    fechas = sorted(p["fecha"].unique())
    out = {"fechas": [_iso(f) for f in fechas]}
    # bancos_plazos.csv usa formato ancho: columnas vista, lt30, lt91, lt181, lt367, lt3a, geq3a
    for key in ["vista", "lt30", "lt91", "lt181", "lt367", "lt3a", "geq3a"]:
        if key not in p.columns:
            out[key] = [None] * len(fechas)
            continue
        vals = []
        for f in fechas:
            row = p[p["fecha"] == f]
            vals.append(
                _safe(float(row[key].values[0]) / 1_000) if not row.empty else None
            )
        out[key] = vals
    return out


def build_bank_inst(bancos, bancos_plazos) -> dict:
    result = {}
    for grupo, cat in GRUPO_TO_CAT.items():
        df_g = bancos[bancos["grupo"] == grupo].copy()
        if df_g.empty:
            continue
        sector_cod = CAT_SECTOR_COD[cat]
        sect_cb = df_g[df_g["codigo"] == sector_cod].set_index("fecha")["cartera_bruta"]

        for cod in df_g["codigo"].unique():
            df_i = df_g[df_g["codigo"] == cod].sort_values("fecha")
            if df_i.empty:
                continue

            ms_list = []
            for _, row in df_i.iterrows():
                tot = sect_cb.get(row["fecha"])
                ms_list.append(
                    round(row["cartera_bruta"] / tot * 100, 4)
                    if tot and tot > 0
                    else None
                )

            last, prev = df_i.iloc[-1], (
                df_i.iloc[-2] if len(df_i) > 1 else df_i.iloc[-1]
            )

            det = _safe(last.get("morosidad_a4"))
            detp = _safe(prev.get("morosidad_a4"))
            roa = _safe(last.get("roa_anual"))
            roap = _safe(prev.get("roa_anual"))
            roe = _safe(last.get("roe_anual"))
            efic = _safe(last.get("eficiencia_a4"))
            cb = _safe(last.get("cartera_bruta"))
            res = _safe(last.get("resultado_operativo"))

            kpis = {
                "fecha": _fmt_kpi_fecha(last["fecha"]),
                "n_meses": len(df_i),
                "deterioro": round(det, 3) if det is not None else None,
                "delta_deterioro": round(det - detp, 3) if det and detp else None,
                "roa": round(roa, 4) if roa is not None else None,
                "delta_roa": round(roa - roap, 4) if roa and roap else None,
                "roe": round(roe, 4) if roe is not None else None,
                "eficiencia": round(efic, 4) if efic is not None else None,
                "ms": (
                    round(ms_list[-1], 4)
                    if ms_list and ms_list[-1] is not None
                    else None
                ),
                "leverage": None,
                "cartera_b": round(cb / 1_000_000, 4) if cb is not None else None,
                "resultado_op": round(res / 1_000, 4) if res is not None else None,
            }

            det_series = _sl(df_i["morosidad_a4"])
            tot_col = (
                df_i["vigentes"].fillna(0)
                + df_i["col_vencida"].fillna(0)
                + df_i["en_gestion"].fillna(0)
                + df_i["morosos"].fillna(0)
            ).replace(0, float("nan"))

            series = {
                "fechas": [_iso(f) for f in df_i["fecha"]],
                "ms": _sl(pd.Series(ms_list)),
                "deterioro": det_series,
                "roa": _sl(df_i["roa_anual"]),
                "roe": _sl(df_i["roe_anual"]),
                "eficiencia": _sl(df_i["eficiencia_a4"]),
                "resultado_op": _sl((df_i["resultado_operativo"] / 1_000).round(4)),
                "cartera_b": _sl((df_i["cartera_bruta"] / 1_000_000).round(4)),
                "vigentes_pct": _sl(
                    (df_i["vigentes"].fillna(0) / tot_col * 100).round(3)
                ),
            }

            name = _strip_cod(str(last.get("institucion", cod)))
            color = BANK_COLORS.get(str(cod), "#607D8B")

            result[str(cod)] = {
                "_cod": str(cod),
                "name": name,
                "color": color,
                "category": cat,
                "sector_cod": sector_cod,
                "det_label": "Morosidad NPL (Anx.4)",
                "det_range": [0, 10],
                "kpis": kpis,
                "series": series,
                "anx2": _anx2_bank(df_i),
                "plazos": _plazos_bank(bancos_plazos, str(cod)),
            }
    return result


# ── RANKING ───────────────────────────────────────────────────────────────────


def build_ranking(inst_all: dict) -> dict:
    """Ranking del último mes disponible por categoría."""
    ranking = {}
    for cat, sector_cod in CAT_SECTOR_COD.items():
        insts = [
            d
            for d in inst_all.values()
            if d["category"] == cat and d["_cod"] != sector_cod
        ]
        if not insts:
            continue
        is_bank = cat != "admin"
        ranking[cat] = {
            "codigos": [d["_cod"] for d in insts],
            "nombres": [d["name"] for d in insts],
            "deterioro": [d["kpis"].get("deterioro") for d in insts],
            "roa": [d["kpis"].get("roa") for d in insts],
            "ms": [d["kpis"].get("ms") for d in insts],
            "det_label": "Morosidad NPL" if is_bank else "Ratio Deterioro",
        }
    return ranking


# ── CAT_INST y CAT_PEERS ──────────────────────────────────────────────────────


def build_cat_inst(inst_all: dict, ind: pd.DataFrame, bancos: pd.DataFrame) -> dict:
    cat_inst = {}
    last_date_ind = ind["fecha"].max()
    last_date_bancos = bancos["fecha"].max() if not bancos.empty else None

    for cat, sector_cod in CAT_SECTOR_COD.items():
        insts = [
            (d["_cod"], d["name"])
            for d in inst_all.values()
            if d["category"] == cat
            and d["_cod"] != sector_cod
            and d["series"]["fechas"]
        ]

        if cat == "admin":
            last_cb = ind[ind["fecha"] == last_date_ind][
                ["codigo", "cartera_bruta"]
            ].set_index("codigo")

            def _sort_a(item):
                try:
                    return -float(last_cb.loc[item[0], "cartera_bruta"])
                except:
                    return 0

            insts.sort(key=_sort_a)
        elif last_date_bancos is not None:
            grupo = next((g for g, c in GRUPO_TO_CAT.items() if c == cat), None)
            if grupo:
                last_cb_b = bancos[
                    (bancos["grupo"] == grupo) & (bancos["fecha"] == last_date_bancos)
                ][["codigo", "cartera_bruta"]].set_index("codigo")

                def _sort_b(item, lcb=last_cb_b):
                    try:
                        return -float(lcb.loc[item[0], "cartera_bruta"])
                    except:
                        return 0

                insts.sort(key=_sort_b)

        cat_inst[cat] = [[cod, name] for cod, name in insts]
    return cat_inst


def build_cat_peers(inst_all: dict) -> dict:
    peers = {
        "admin": [
            c
            for c in ["804", "817", "805", "815", "860"]
            if c in inst_all and c != FOCUS_COMPANY_CODE
        ]
    }
    for cat, sector_cod in CAT_SECTOR_COD.items():
        if cat == "admin":
            continue
        peers[cat] = [
            d["_cod"]
            for d in inst_all.values()
            if d["category"] == cat and d["_cod"] != sector_cod
        ]
    return peers


# ── Gráficos estáticos globales ───────────────────────────────────────────────


def build_fig_mercado(ind: pd.DataFrame) -> dict:
    sector = ind[ind["codigo"] == "981"][["fecha", "cartera_bruta"]].copy()
    emp = ind[ind["codigo"] != "981"].merge(
        sector.rename(columns={"cartera_bruta": "tot"}), on="fecha"
    )
    emp["ms"] = (emp["cartera_bruta"] / emp["tot"] * 100).round(2)
    max_ms = emp.groupby("codigo")["ms"].max()
    top = max_ms[max_ms >= 1.0].index.tolist()
    if FOCUS_COMPANY_CODE not in top:
        top.append(FOCUS_COMPANY_CODE)

    fig = go.Figure()
    for cod in sorted(top, key=lambda c: -max_ms.get(c, 0)):
        df_c = emp[emp["codigo"] == cod].sort_values("fecha")
        if df_c.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=df_c["fecha"],
                y=df_c["ms"],
                name=ADMIN_NAMES.get(cod, cod),
                mode="lines+markers",
                line=dict(
                    color=ADMIN_COLORS.get(cod, "#78909C"),
                    width=3 if cod == FOCUS_COMPANY_CODE else 1.5,
                ),
                marker=dict(size=4),
                hovertemplate=f"<b>{ADMIN_NAMES.get(cod, cod)}</b><br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
            )
        )
    fig.update_layout(
        title=dict(text="Market Share — Cartera Bruta (Admins)", font=dict(size=13)),
        yaxis=dict(title="Share (%)", ticksuffix="%"),
        hovermode="x unified",
        height=320,
        legend=dict(orientation="h", y=-0.32),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        font=dict(
            family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", size=11
        ),
        margin=dict(t=50, b=90, l=50, r=20),
    )
    return json.loads(pio.to_json(fig))


def build_fig_tasas(tasas: pd.DataFrame) -> dict:
    df = tasas.sort_values("fecha")
    fig = go.Figure()
    for col, name, color in [
        ("tasa_consumo_total", "Consumo total", "#1565C0"),
        ("tasa_tarjeta_credito", "Tarjeta crédito", "#E63946"),
        ("tasa_depositos_promedio", "Depósitos prom.", "#4CAF50"),
        ("tasa_consumo_sin_autorizacion", "Sin autorización", "#FF9800"),
    ]:
        if col not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["fecha"],
                y=df[col].round(2),
                name=name,
                mode="lines+markers",
                line=dict(color=color, width=2),
                marker=dict(size=4),
                hovertemplate=f"<b>{name}</b><br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
            )
        )
    fig.update_layout(
        title=dict(text="Tasas de Interés (BCU)", font=dict(size=13)),
        yaxis=dict(title="Tasa (%)", ticksuffix="%"),
        hovermode="x unified",
        height=320,
        legend=dict(orientation="h", y=-0.32),
        paper_bgcolor="white",
        plot_bgcolor="#fafafa",
        font=dict(
            family="-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif", size=11
        ),
        margin=dict(t=50, b=90, l=50, r=20),
    )
    return json.loads(pio.to_json(fig))


# ── Generación HTML ───────────────────────────────────────────────────────────


def generate_html(
    inst_all, cat_inst, cat_peers, ranking, fig_mercado, fig_tasas, meta
) -> str:
    ultimo_mes = meta.get("ultimo_mes", "—")
    fecha_desc = meta.get("fecha_descarga", "—")
    n_meses = meta.get("meses_disponibles", "—")
    fuente_url = meta.get("fuente_url", BCU_URL)

    cat_options = "\n".join(
        f'<option value="{cat}">{label}</option>'
        for cat, label in CAT_LABELS.items()
        if cat in cat_inst and cat_inst[cat]
    )

    j = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    html = HTML_TEMPLATE
    html = html.replace("__INST__", j(inst_all))
    html = html.replace("__CAT_INST__", j(cat_inst))
    html = html.replace("__CAT_PEERS__", j(cat_peers))
    html = html.replace("__CAT_LABELS__", j(CAT_LABELS))
    html = html.replace("__RANKING__", j(ranking))
    html = html.replace("__FIG_MERCADO__", j(fig_mercado))
    html = html.replace("__FIG_TASAS__", j(fig_tasas))
    html = html.replace("__ULTIMO_MES__", str(ultimo_mes))
    html = html.replace("__N_MESES__", str(n_meses))
    html = html.replace("__FECHA_DESC__", str(fecha_desc))
    html = html.replace("__FUENTE_URL__", fuente_url)
    html = html.replace("__CAT_OPTIONS__", cat_options)
    return html


# ── Orquestador ───────────────────────────────────────────────────────────────


def generate_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Cargando datos...")
    ind, anx2, plazos, bancos, bancos_plazos, tasas, meta = load_all()

    log.info("Construyendo INST (administradoras)...")
    inst_admin = build_admin_inst(ind, anx2, plazos)

    log.info("Construyendo INST (bancos)...")
    inst_bank = build_bank_inst(bancos, bancos_plazos)

    inst_all = {**inst_admin, **inst_bank}

    log.info("Construyendo estructuras auxiliares...")
    cat_inst = build_cat_inst(inst_all, ind, bancos)
    cat_peers = build_cat_peers(inst_all)
    ranking = build_ranking(inst_all)

    log.info("Generando gráficos estáticos...")
    fig_mercado = build_fig_mercado(ind)
    fig_tasas = build_fig_tasas(tasas)

    log.info("Generando HTML...")
    html = generate_html(
        inst_all, cat_inst, cat_peers, ranking, fig_mercado, fig_tasas, meta
    )

    dest = OUTPUT_DIR / "dashboard.html"
    dest.write_text(html, encoding="utf-8")
    log.info("Dashboard guardado: %s (%d KB)", dest, len(html.encode()) // 1024)
    return dest


# ── HTML Template ─────────────────────────────────────────────────────────────
# Usa __VARNAME__ como placeholders (no f-string, para no escapar braces JS)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sistema Financiero Uruguay — Dashboard Interactivo</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#1a1a2e}
  .header{background:linear-gradient(135deg,#0d1b2a 0%,#1b263b 60%,#415a77 100%);color:white;padding:20px 36px}
  .header h1{font-size:19px;font-weight:700}
  .header p{font-size:12px;opacity:.65;margin-top:4px}

  .selector-bar{background:white;border-bottom:2px solid #e0e0e0;padding:12px 36px;
                display:flex;align-items:center;gap:20px;flex-wrap:wrap}
  .sel-group{display:flex;flex-direction:column;gap:4px}
  .sel-group label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:#777}
  select.sel-cat{font-size:13px;font-weight:600;padding:7px 12px;border:2px solid #607D8B;
                  border-radius:7px;color:#37474F;background:white;cursor:pointer;min-width:200px}
  select.sel-inst{font-size:14px;font-weight:700;padding:7px 14px;border:2px solid #1565C0;
                   border-radius:7px;color:#1565C0;background:white;cursor:pointer;min-width:220px}
  select:focus{outline:none;box-shadow:0 0 0 3px rgba(21,101,192,.15)}
  .sel-meta{font-size:12px;color:#aaa;margin-left:auto;align-self:center}

  .tab-nav{background:white;border-bottom:3px solid #e0e0e0;padding:0 36px;display:flex;gap:0}
  .tab-btn{background:none;border:none;padding:12px 22px;font-size:13px;font-weight:600;
            color:#777;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-3px;
            transition:all .2s;letter-spacing:.2px}
  .tab-btn.active{color:#1565C0;border-bottom-color:#1565C0}
  .tab-btn:hover:not(.active){color:#1565C0;background:#f8f9fa}
  .tab-pane{display:none}.tab-pane.active{display:block}
  .tab-info{font-size:11px;color:#666;padding:9px 36px;background:#f8f9fa;
             border-bottom:1px solid #eee;line-height:1.6}

  .kpi-bar{display:flex;gap:11px;padding:12px 36px;background:white;
            border-bottom:1px solid #e8e8e8;flex-wrap:wrap}
  .kpi{background:#f8f9fa;border-radius:9px;padding:11px 15px;min-width:130px;flex:1;
        border-left:4px solid #ddd;transition:all .2s}
  .kpi.red{border-left-color:#E63946}.kpi.green{border-left-color:#4CAF50}.kpi.amber{border-left-color:#FF9800}
  .kpi-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.6px;color:#777;font-weight:700}
  .kpi-value{font-size:19px;font-weight:700;margin-top:3px;line-height:1}
  .kpi-sub{font-size:10.5px;color:#aaa;margin-top:2px}

  .section{padding:14px 36px 3px}
  .section h2{font-size:10.5px;text-transform:uppercase;letter-spacing:1.2px;color:#999;
               font-weight:700;border-bottom:2px solid #e8e8e8;padding-bottom:5px}
  .grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:12px 36px}
  .grid-1{display:grid;grid-template-columns:1fr;gap:16px;padding:12px 36px}
  .card{background:white;border-radius:11px;box-shadow:0 2px 10px rgba(0,0,0,.06);
         padding:16px;border:1px solid #ebebeb;min-height:340px}
  .no-data{padding:40px 20px;color:#aaa;text-align:center;font-size:13px}

  /* ── Pestaña Acerca de ── */
  .about-wrap{max-width:1100px;margin:0 auto;padding:28px 36px;display:grid;grid-template-columns:1fr 1fr;gap:20px}
  .about-card{background:white;border-radius:11px;box-shadow:0 2px 10px rgba(0,0,0,.06);padding:24px 28px;border:1px solid #ebebeb}
  .about-card.full{grid-column:1/-1}
  .about-card h2{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:#0d1b2a;border-bottom:2px solid #e8f0fe;padding-bottom:8px;margin-bottom:14px}
  .about-card p{font-size:13px;line-height:1.7;color:#333;margin-bottom:8px}
  .about-card ul{margin:6px 0 8px 16px}
  .about-card li{font-size:13px;line-height:1.7;color:#333;margin-bottom:3px}
  .about-card a{color:#1565C0;text-decoration:none}
  .about-card a:hover{text-decoration:underline}
  .law-item{background:#f8f9fa;border-left:4px solid #1565C0;border-radius:4px;padding:9px 13px;margin-bottom:9px}
  .law-name{font-size:12px;font-weight:700;color:#1565C0}
  .law-desc{font-size:12px;color:#555;margin-top:2px;line-height:1.5}
  .disclaimer-box{background:#fff8e1;border:1px solid #ffe082;border-radius:7px;padding:14px 18px;margin-top:14px;font-size:12px;color:#5d4037;line-height:1.6}

  footer{text-align:center;padding:18px;font-size:11px;color:#bbb;
          border-top:1px solid #eee;background:white;margin-top:18px}
  footer a{color:#1565C0;text-decoration:none}

  @media(max-width:900px){
    .grid-2{grid-template-columns:1fr}
    .grid-2,.grid-1,.section,.kpi-bar,.selector-bar,.tab-nav{padding-left:14px;padding-right:14px}
    .kpi{min-width:120px}
    .tab-btn{padding:10px 14px;font-size:12px}
    .about-wrap{grid-template-columns:1fr;padding:14px}
    .about-card.full{grid-column:1}
    .header{padding:14px}
    .header h1{font-size:15px}
  }
</style>
</head>
<body>

<div class="header">
  <h1>Sistema Financiero Uruguay — Dashboard Comparativo</h1>
  <p>Fuente: BCU Boletín SSF &nbsp;|&nbsp; __N_MESES__ meses (hasta __ULTIMO_MES__) &nbsp;|&nbsp; Cifras en miles de pesos uruguayos</p>
</div>

<div class="tab-nav">
  <button class="tab-btn active" data-tab="about"     onclick="switchTab('about')">ℹ Acerca del Dashboard</button>
  <button class="tab-btn"        data-tab="general"   onclick="switchTab('general')">📊 Análisis General</button>
  <button class="tab-btn"        data-tab="tomadores" onclick="switchTab('tomadores')">👥 Calidad Tomadores</button>
  <button class="tab-btn"        data-tab="plazos"    onclick="switchTab('plazos')">⏱ Distribución Plazos</button>
</div>

<div class="selector-bar" id="selectorBar">
  <div class="sel-group">
    <label>Categoría</label>
    <select class="sel-cat" id="catSelector" onchange="onCatChange(this.value)">
      __CAT_OPTIONS__
    </select>
  </div>
  <div class="sel-group">
    <label>Institución</label>
    <select class="sel-inst" id="instSelector" onchange="updateDashboard(this.value)"></select>
  </div>
  <span class="sel-meta" id="metaInfo"></span>
</div>

<div class="kpi-bar" id="kpiBar"></div>

<!-- ══════════════════ TAB 0: ACERCA ══════════════════ -->
<div id="tab-about" class="tab-pane active">
<div class="about-wrap">

  <div class="about-card">
    <h2>Objetivo del Dashboard</h2>
    <p>Herramienta de <strong>inteligencia competitiva</strong> del mercado financiero uruguayo, basada en los boletines estadísticos mensuales del Banco Central del Uruguay (BCU). Permite analizar cualquier institución frente al sector seleccionado.</p>
    <p>Métricas disponibles:</p>
    <ul>
      <li><strong>Market share</strong> de cartera bruta por institución</li>
      <li><strong>Calidad de cartera</strong> — deterioro, composición por segmento (Anexo 2)</li>
      <li><strong>Rentabilidad</strong> — ROA y ROE anualizados</li>
      <li><strong>Resultado operativo</strong> acumulado vs. competidores</li>
      <li><strong>Distribución de cartera por plazos</strong> (Anexo 1 BCU)</li>
    </ul>
  </div>

  <div class="about-card">
    <h2>Fuente de Datos</h2>
    <p><strong>Banco Central del Uruguay (BCU)</strong><br>
    Superintendencia de Servicios Financieros (SSF)<br>
    Boletines Estadísticos Mensuales:</p>
    <ul>
      <li>Grupo 981 — Administradoras de Crédito al Consumo</li>
      <li>Grupos 99, 996, 997, 998 — Instituciones bancarias</li>
    </ul>
    <p>Los datos son descargados directamente desde el servidor del BCU sin modificaciones. Cifras en miles de pesos uruguayos (UYU).</p>
    <p style="margin-top:10px"><a href="__FUENTE_URL__" target="_blank" rel="noopener">Ver boletines en bcu.gub.uy →</a></p>
  </div>

  <div class="about-card full">
    <h2>Marco Legal y Uso de los Datos</h2>
    <p>Los datos utilizados provienen exclusivamente de <strong>publicaciones oficiales del BCU</strong>, disponibles de forma libre y gratuita en el sitio institucional. El BCU genera estos boletines con el fin expreso de informar al mercado y al público sobre la situación del sistema financiero uruguayo.</p>
    <div class="law-item">
      <div class="law-name">Ley N° 18.381 — Derecho de Acceso a la Información Pública (2008)</div>
      <div class="law-desc">Toda persona tiene derecho a acceder a la información pública sin necesidad de justificar las razones que la motivan. Los organismos del Estado están obligados a publicar de oficio la información de relevancia pública que generen.</div>
    </div>
    <div class="law-item">
      <div class="law-name">Decreto N° 232/010 — Reglamentación Ley 18.381</div>
      <div class="law-desc">Define procedimientos de acceso, plazos de respuesta y obligaciones de los organismos públicos en materia de transparencia y difusión de información.</div>
    </div>
    <div class="law-item">
      <div class="law-name">Carta Orgánica del BCU — Ley N° 16.696, art. 3 lit. i</div>
      <div class="law-desc">Establece entre los cometidos del BCU la publicación de estadísticas e informes sobre el sistema financiero, con el objetivo de informar al público y promover la transparencia del mercado.</div>
    </div>
    <div class="disclaimer-box">
      <strong>Aviso:</strong> Este dashboard es una herramienta de análisis independiente, sin afiliación oficial con el BCU ni con las instituciones analizadas. Los datos reproducen fielmente la fuente pública oficial. Los análisis e interpretaciones son de carácter informativo y no constituyen asesoramiento financiero, legal ni regulatorio.
    </div>
  </div>

  <div class="about-card">
    <h2>Metodología</h2>
    <ul>
      <li><strong>ROA</strong> = Resultado operativo / Activo total (anualizado)</li>
      <li><strong>ROE</strong> = Resultado operativo / Patrimonio (anualizado)</li>
      <li><strong>Ratio deterioro</strong> = Deterioro / Cartera bruta (admins)</li>
      <li><strong>Morosidad NPL</strong> = Cartera vencida / Cartera bruta (bancos, Anx.4)</li>
      <li><strong>Eficiencia</strong> = Gastos operativos / Margen financiero bruto</li>
    </ul>
    <p style="font-size:12px;color:#888;margin-top:8px">Nota: la cartera bruta puede superar el activo total del balance — es esperado, ya que el balance descuenta provisiones mientras el Anexo 2 reporta valores brutos.</p>
  </div>

  <div class="about-card">
    <h2>Cobertura</h2>
    <p><strong>Administradoras de Crédito</strong> — Grupo 981</p>
    <p style="margin-bottom:10px">Directos · SOCUR (Creditel) · ANDA · OCA SA · RETOP · Del Este · Verendy · E. de Valor · Pass Card · Bautzen · FUCAC · CASH S.A. · RMSA · Floder · Sol. Integrales</p>
    <p><strong>Sector Bancario</strong></p>
    <p>Bancos Privados (Itaú, Santander, Scotiabank, BBVA…) · Bancos Oficiales (BROU, BHU) · Cooperativas (FUCEREP) · Casas Financieras</p>
  </div>

</div>
</div><!-- /tab-about -->

<!-- ══════════════════ TAB 1: GENERAL ══════════════════ -->
<div id="tab-general" class="tab-pane">

<div class="section"><h2>Posición en el Mercado</h2></div>
<div class="grid-2">
  <div class="card" id="chart_ms"></div>
  <div class="card" id="chart_deterioro"></div>
</div>

<div class="section"><h2>Rentabilidad</h2></div>
<div class="grid-2">
  <div class="card" id="chart_roa"></div>
  <div class="card" id="chart_resultado"></div>
</div>

<div class="section"><h2>Calidad de Cartera y Eficiencia</h2></div>
<div class="grid-2">
  <div class="card" id="chart_cartera"></div>
  <div class="card" id="chart_eficiencia"></div>
</div>

<div class="section"><h2 id="rankTitle">Ranking de la Categoría — Último Mes</h2></div>
<div class="grid-1">
  <div class="card" id="chart_ranking"></div>
</div>

<div class="section"><h2>Contexto del Mercado Total</h2></div>
<div class="grid-2">
  <div class="card" id="chart_mercado"></div>
  <div class="card" id="chart_tasas"></div>
</div>

</div><!-- /tab-general -->

<!-- ══════════════════ TAB 2: CALIDAD TOMADORES ══════════════════ -->
<div id="tab-tomadores" class="tab-pane">

<div class="tab-info">
  <b>Apertura por calidad de cobro.</b> &nbsp;
  <b>Vigentes:</b> sin atrasos. &nbsp;
  <b>Col. Vencida:</b> 1–30 días mora. &nbsp;
  <b>En Gestión:</b> 31–180 días. &nbsp;
  <b>Morosos:</b> más de 180 días.
</div>

<div class="section"><h2>Composición de Cartera por Calidad de Cobro — Evolución Histórica</h2></div>
<div class="grid-2">
  <div class="card" id="chart_anx2_comp"></div>
  <div class="card" id="chart_anx2_evol"></div>
</div>

<div class="section"><h2>Último Mes — Comparativa vs Sector y Peers</h2></div>
<div class="grid-1">
  <div class="card" id="chart_anx2_latest"></div>
</div>

</div><!-- /tab-tomadores -->

<!-- ══════════════════ TAB 3: PLAZOS ══════════════════ -->
<div id="tab-plazos" class="tab-pane">

<div class="tab-info">
  <b>Apertura por plazo contractual (Sector No Financiero).</b> &nbsp;
  Refleja el perfil de maduración de la cartera vigente.
</div>

<div class="section"><h2>Distribución de Cartera por Plazo — Evolución Histórica</h2></div>
<div class="grid-2">
  <div class="card" id="chart_plazos_evol"></div>
  <div class="card" id="chart_plazos_comp"></div>
</div>

</div><!-- /tab-plazos -->

<footer>
  Fuente: <a href="__FUENTE_URL__" target="_blank" rel="noopener">Banco Central del Uruguay — Boletín SSF</a>
  &nbsp;|&nbsp; Datos al __ULTIMO_MES__
  &nbsp;|&nbsp; Descargado: __FECHA_DESC__
  <br><small style="display:block;margin-top:5px;color:#ccc">
    Análisis independiente — sin afiliación oficial con el BCU. Datos de fuente pública.
  </small>
</footer>

<script>
// ── Constantes de datos (inyectadas por Python) ───────────────────────────────
const INST        = __INST__;
const CAT_INST    = __CAT_INST__;
const CAT_PEERS   = __CAT_PEERS__;
const CATEGORIAS  = __CAT_LABELS__;
const RANKING     = __RANKING__;
const FIG_MERCADO = __FIG_MERCADO__;
const FIG_TASAS   = __FIG_TASAS__;

// ── Layout base Plotly ────────────────────────────────────────────────────────
const LAYOUT = {
  paper_bgcolor:"white", plot_bgcolor:"#fafafa",
  font:{family:"-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",size:11},
  margin:{t:70,b:55,l:60,r:45},
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt      = (v, d=1, s="%") => v===null||v===undefined ? "—" : v.toFixed(d)+s;
const fmtDelta = v => {
  if(v===null||v===undefined) return "";
  return (v>0?"▲":"▼")+Math.abs(v).toFixed(2)+"pp vs mes anterior";
};
const semaforo = (v, redAbove, greenBelow) => {
  if(v===null) return "";
  if(v>redAbove)   return "red";
  if(v<greenBelow) return "green";
  return "amber";
};
const noData = id => {
  const el = document.getElementById(id);
  if(el) el.innerHTML='<div class="no-data">Sin datos disponibles para esta institución</div>';
};

// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  document.querySelector('[data-tab="'+tab+'"]').classList.add('active');
  const isAbout = tab === 'about';
  document.getElementById('selectorBar').style.display = isAbout ? 'none' : '';
  document.getElementById('kpiBar').style.display      = isAbout ? 'none' : '';
  setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
}

// ── KPI bar ───────────────────────────────────────────────────────────────────
function renderKPIs(inst) {
  const k = inst.kpis;
  if(!k||!k.fecha) { document.getElementById("kpiBar").innerHTML=""; return; }
  const isBank   = inst.category !== "admin";
  const detLabel = isBank ? "Morosidad NPL" : "Ratio Deterioro";
  const detCls   = isBank ? semaforo(k.deterioro,4,1) : semaforo(k.deterioro,35,15);
  const roaCls   = k.roa>=0 ? "green" : "red";
  const eficCls  = semaforo(k.eficiencia,50,35);
  const resColor = (k.resultado_op||0)>=0?"#4CAF50":"#E63946";

  document.getElementById("kpiBar").innerHTML = `
    <div class="kpi ${detCls}">
      <div class="kpi-label">${detLabel}</div>
      <div class="kpi-value">${fmt(k.deterioro, isBank?2:1)}</div>
      <div class="kpi-sub">${fmtDelta(k.delta_deterioro)}</div>
    </div>
    <div class="kpi ${roaCls}">
      <div class="kpi-label">ROA${isBank?" (Anx.4 últ.12m)":" Anualizado"}</div>
      <div class="kpi-value">${fmt(k.roa,2)}</div>
      <div class="kpi-sub">${fmtDelta(k.delta_roa)}</div>
    </div>
    <div class="kpi ${roaCls}">
      <div class="kpi-label">ROE${isBank?" (Anx.4 últ.12m)":""}</div>
      <div class="kpi-value">${fmt(k.roe,1)}</div>
      <div class="kpi-sub">resultado / patrimonio</div>
    </div>
    <div class="kpi ${eficCls}">
      <div class="kpi-label">Eficiencia${isBank?" (Anx.4)":""}</div>
      <div class="kpi-value">${fmt(k.eficiencia,1)}</div>
      <div class="kpi-sub">gastos / margen financiero</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Market Share (sub-grupo)</div>
      <div class="kpi-value">${fmt(k.ms,1)}</div>
      <div class="kpi-sub">% cartera del sector</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Cartera Bruta</div>
      <div class="kpi-value">$${fmt(k.cartera_b,1,"B")}</div>
      <div class="kpi-sub">miles mill. UYU — ${k.fecha}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Resultado Op.</div>
      <div class="kpi-value" style="color:${resColor}">$${fmt(k.resultado_op,0,"M")}</div>
      <div class="kpi-sub">acumulado período fiscal</div>
    </div>
  `;
}

// ── Tab 1: charts ─────────────────────────────────────────────────────────────
function renderMS(inst) {
  const s     = inst.series;
  const peers = (CAT_PEERS[inst.category]||[]).filter(p=>p!==inst._cod && INST[p]);
  const traces = peers.map(p => ({
    x:INST[p].series.fechas, y:INST[p].series.ms, name:INST[p].name, mode:"lines",
    line:{color:"#BDBDBD",width:1},
    hovertemplate:`<b>${INST[p].name}</b><br>%{x|%b %Y}: %{y:.1f}%<extra></extra>`,
  }));
  traces.push({
    x:s.fechas, y:s.ms, name:inst.name, mode:"lines+markers",
    line:{color:inst.color,width:3}, marker:{size:7},
    hovertemplate:`<b>${inst.name}</b><br>%{x|%b %Y}: %{y:.1f}%<extra></extra>`,
  });
  Plotly.react("chart_ms", traces, {
    ...LAYOUT,
    title:{text:"Market Share en Sub-Grupo — Cartera Bruta",font:{size:13}},
    yaxis:{title:"Share (%)",ticksuffix:"%"},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
  },{responsive:true});
}

function renderDeterio(inst) {
  const s    = inst.series;
  const sect = INST[inst.sector_cod]?.series || {};
  const peers = (CAT_PEERS[inst.category]||[]).filter(p=>p!==inst._cod && INST[p]);
  const traces = peers.map(p => ({
    x:INST[p].series.fechas, y:INST[p].series.deterioro, name:INST[p].name, mode:"lines",
    line:{color:"#BDBDBD",width:1},
    hovertemplate:`<b>${INST[p].name}</b><br>%{x|%b %Y}: %{y:.2f}%<extra></extra>`,
  }));
  if(sect.fechas) traces.push({
    x:sect.fechas, y:sect.deterioro, name:"Sector",
    mode:"lines", line:{color:"#90A4AE",width:1.5,dash:"dot"},
    hovertemplate:"<b>Sector</b><br>%{x|%b %Y}: %{y:.2f}%<extra></extra>",
  });
  traces.push({
    x:s.fechas, y:s.deterioro, name:inst.name,
    mode:"lines+markers", line:{color:inst.color,width:3}, marker:{size:7},
    hovertemplate:`<b>${inst.name}</b><br>%{x|%b %Y}: %{y:.2f}%<extra></extra>`,
  });
  const umbral = inst.category==="admin" ? 35 : null;
  const shapes = umbral ? [{type:"line",x0:0,x1:1,xref:"paper",y0:umbral,y1:umbral,
    line:{color:"red",dash:"dash",width:1.5}}] : [];
  const annotations = umbral ? [{xref:"paper",x:1,y:umbral,text:"Umbral 35%",
    showarrow:false,font:{color:"red",size:10},xanchor:"right"}] : [];
  Plotly.react("chart_deterioro", traces, {
    ...LAYOUT, title:{text:inst.det_label,font:{size:13}},
    yaxis:{title:"(%)",ticksuffix:"%",range:inst.det_range||[0,55]},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
    shapes, annotations,
  },{responsive:true});
}

function renderRoaRoe(inst) {
  const s = inst.series;
  const barColors = s.roa.map(v=>v===null?"#ccc":(v>=0?"#4CAF50":"#E63946"));
  Plotly.react("chart_roa",[
    {type:"bar",x:s.fechas,y:s.roa,name:"ROA",marker:{color:barColors},yaxis:"y",
      hovertemplate:"ROA: %{y:.2f}%<extra></extra>"},
    {type:"scatter",x:s.fechas,y:s.roe,name:"ROE",
      mode:"lines+markers",line:{color:"#1565C0",width:2.5},marker:{size:6},yaxis:"y2",
      hovertemplate:"ROE: %{y:.1f}%<extra></extra>"},
  ],{
    ...LAYOUT, title:{text:`${inst.name} — ROA y ROE`,font:{size:13}},
    yaxis:{title:"ROA (%)",ticksuffix:"%",side:"left"},
    yaxis2:{title:"ROE (%)",ticksuffix:"%",overlaying:"y",side:"right"},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
    shapes:[{type:"line",x0:0,x1:1,xref:"paper",y0:0,y1:0,
              line:{color:"black",width:1,opacity:.25}}],
  },{responsive:true});
}

function renderResultado(inst) {
  const s    = inst.series;
  const sect = INST[inst.sector_cod]?.series || {};
  const resColors = s.resultado_op.map(v=>v===null?"#ccc":(v>=0?"#4CAF50":"#E63946"));
  Plotly.react("chart_resultado",[
    sect.fechas ? {
      type:"scatter",x:sect.fechas,y:sect.resultado_op,name:"Sector",
      mode:"lines",line:{color:"#90A4AE",width:1.5,dash:"dot"},
      hovertemplate:"<b>Sector</b><br>$%{y:.0f}M<extra></extra>",yaxis:"y2"
    } : null,
    {type:"bar",x:s.fechas,y:s.resultado_op,name:inst.name,marker:{color:resColors},yaxis:"y",
      hovertemplate:`${inst.name}: $%{y:.0f}M<extra></extra>`},
  ].filter(Boolean),{
    ...LAYOUT, title:{text:"Resultado Operativo Acumulado (M$)",font:{size:13}},
    yaxis:{title:`${inst.name} (M$)`,tickprefix:"$",ticksuffix:"M"},
    yaxis2:{title:"Sector (M$)",tickprefix:"$",ticksuffix:"M",overlaying:"y",side:"right"},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
    shapes:[{type:"line",x0:0,x1:1,xref:"paper",y0:0,y1:0,line:{color:"black",width:1,opacity:.25}}],
  },{responsive:true});
}

function renderCartera(inst) {
  const s    = inst.series;
  const sect = INST[inst.sector_cod]?.series || {};
  Plotly.react("chart_cartera",[
    {type:"bar",x:s.fechas,y:s.vigentes_pct,name:"Vigentes / Cartera",
      marker:{color:"#4CAF5088"},yaxis:"y",
      hovertemplate:"Vigentes: %{y:.1f}%<extra></extra>"},
    sect.fechas ? {
      type:"scatter",x:sect.fechas,y:sect.vigentes_pct,name:"Sector vigentes",
      mode:"lines",line:{color:"#90A4AE",dash:"dot",width:1.5},yaxis:"y",
      hovertemplate:"<b>Sector</b> vigentes: %{y:.1f}%<extra></extra>"
    } : null,
    {type:"scatter",x:s.fechas,y:s.deterioro,
      name:inst.category==="admin"?"Deterioro":"Morosidad",
      mode:"lines+markers",line:{color:inst.color,width:2.5},marker:{size:6},yaxis:"y2",
      hovertemplate:`${inst.category==="admin"?"Deterioro":"Mora"}: %{y:.2f}%<extra></extra>`},
  ].filter(Boolean),{
    ...LAYOUT, title:{text:`${inst.name} — Calidad de Cartera`,font:{size:13}},
    yaxis:{title:"Vigentes (%)",ticksuffix:"%",range:[0,105]},
    yaxis2:{title:`${inst.category==="admin"?"Deterioro":"Morosidad"} (%)`,
             ticksuffix:"%",overlaying:"y",side:"right",range:inst.det_range||[0,55]},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
  },{responsive:true});
}

function renderEficiencia(inst) {
  const s    = inst.series;
  const sect = INST[inst.sector_cod]?.series || {};
  const eficColors = (s.eficiencia||[]).map(v=>
    v===null?"#ccc":v>50?"#E63946":v>40?"#FF9800":"#4CAF50");
  Plotly.react("chart_eficiencia",[
    sect.fechas ? {
      type:"scatter",x:sect.fechas,y:sect.eficiencia,name:"Sector",
      mode:"lines",line:{color:"#90A4AE",width:1.5,dash:"dot"},
      hovertemplate:"<b>Sector</b>: %{y:.1f}%<extra></extra>"
    } : null,
    {type:"bar",x:s.fechas,y:s.eficiencia,name:inst.name,marker:{color:eficColors},
      hovertemplate:`${inst.name}: %{y:.1f}%<extra></extra>`},
  ].filter(Boolean),{
    ...LAYOUT, title:{text:"Ratio de Eficiencia — Gastos / Margen Financiero Bruto",font:{size:13}},
    yaxis:{title:"Eficiencia (%)",ticksuffix:"%"},
    hovermode:"x unified", height:320, legend:{orientation:"h",y:-0.28},
    shapes:[
      {type:"line",x0:0,x1:1,xref:"paper",y0:50,y1:50,line:{color:"#E63946",dash:"dash",width:1.5}},
      {type:"line",x0:0,x1:1,xref:"paper",y0:40,y1:40,line:{color:"#FF9800",dash:"dash",width:1}},
    ],
  },{responsive:true});
}

function renderRanking(cat, selectedCod) {
  const r = RANKING[cat];
  if(!r) return;
  const hi = cod => cod===selectedCod ? (INST[cod]?.color||"#E63946") : "#B0BEC599";
  const sort = (vals, cods, noms, asc=true) => {
    const paired = vals.map((v,i)=>[v,cods[i],noms[i]]).filter(([v])=>v!==null);
    paired.sort((a,b)=>asc?(a[0]-b[0]):(b[0]-a[0]));
    return {x:paired.map(p=>p[0]),y:paired.map(p=>p[2]),cods:paired.map(p=>p[1])};
  };
  const det = sort(r.deterioro, r.codigos, r.nombres, true);
  const roa = sort(r.roa,       r.codigos, r.nombres, false);
  const ms  = sort(r.ms,        r.codigos, r.nombres, false);
  Plotly.react("chart_ranking",[
    {type:"bar",orientation:"h",x:det.x,y:det.y,xaxis:"x",yaxis:"y",
      marker:{color:det.cods.map(hi)},
      text:det.x.map(v=>v?.toFixed(2)+"%"),textposition:"outside",showlegend:false,
      hovertemplate:"<b>%{y}</b>: %{x:.2f}%<extra></extra>"},
    {type:"bar",orientation:"h",x:roa.x,y:roa.y,xaxis:"x2",yaxis:"y2",
      marker:{color:roa.cods.map(hi)},
      text:roa.x.map(v=>v?.toFixed(2)+"%"),textposition:"outside",showlegend:false,
      hovertemplate:"<b>%{y}</b>: %{x:.2f}%<extra></extra>"},
    {type:"bar",orientation:"h",x:ms.x,y:ms.y,xaxis:"x3",yaxis:"y3",
      marker:{color:ms.cods.map(hi)},
      text:ms.x.map(v=>v?.toFixed(1)+"%"),textposition:"outside",showlegend:false,
      hovertemplate:"<b>%{y}</b>: %{x:.1f}%<extra></extra>"},
  ],{
    ...LAYOUT,
    title:{text:`Ranking — ${(CATEGORIAS[cat]||cat)} <span style="font-size:11px;color:#aaa">(resaltado = seleccionado)</span>`,font:{size:13}},
    grid:{rows:1,columns:3,pattern:"independent"},
    annotations:[
      {text:r.det_label,         xref:"x domain", yref:"y domain", x:.5,y:1.1,showarrow:false,font:{size:11}},
      {text:"ROA (mayor=mejor)", xref:"x2 domain",yref:"y2 domain",x:.5,y:1.1,showarrow:false,font:{size:11}},
      {text:"Market Share (%)",  xref:"x3 domain",yref:"y3 domain",x:.5,y:1.1,showarrow:false,font:{size:11}},
    ],
    height:420, margin:{t:75,b:30,l:120,r:60}, showlegend:false,
  },{responsive:true});
}

// ── Tab 2: Calidad Tomadores ──────────────────────────────────────────────────
function renderAnx2Comp(inst) {
  const a = inst.anx2 || {};
  if(!a.fechas?.length) { noData('chart_anx2_comp'); return; }
  const traces = [
    {type:"bar",x:a.fechas,y:a.vigentes_pct,name:"Vigentes",
      marker:{color:"#43A04799"},hovertemplate:"Vigentes: %{y:.1f}%<extra></extra>"},
    {type:"bar",x:a.fechas,y:a.col_vencida_pct,name:"Col. Vencida",
      marker:{color:"#FF980099"},hovertemplate:"Col. Vencida: %{y:.2f}%<extra></extra>"},
    {type:"bar",x:a.fechas,y:a.en_gestion_pct,name:"En Gestión",
      marker:{color:"#F4433699"},hovertemplate:"En Gestión: %{y:.2f}%<extra></extra>"},
    {type:"bar",x:a.fechas,y:a.morosos_pct,name:"Morosos",
      marker:{color:"#B71C1C99"},hovertemplate:"Morosos: %{y:.2f}%<extra></extra>"},
  ].filter(t => t.y && t.y.some(v => v !== null));
  Plotly.react("chart_anx2_comp", traces, {
    ...LAYOUT, barmode:"stack",
    title:{text:`${inst.name} — Composición Cartera por Calidad de Cobro`,font:{size:13}},
    yaxis:{title:"(%)",ticksuffix:"%",range:[0,105]},
    hovermode:"x unified", height:360, legend:{orientation:"h",y:-0.28},
  },{responsive:true});
}

function renderAnx2Evol(inst) {
  const a    = inst.anx2 || {};
  const sect = INST[inst.sector_cod]?.anx2 || {};
  if(!a.fechas) { noData('chart_anx2_evol'); return; }
  const totalVenc = src => (src.fechas||[]).map((_,i) => {
    const cv=src.col_vencida_pct?.[i], eg=src.en_gestion_pct?.[i], mo=src.morosos_pct?.[i];
    if(cv===null&&eg===null&&mo===null) return null;
    return (cv||0)+(eg||0)+(mo||0);
  });
  const traces = [];
  if(sect.fechas) traces.push({
    type:"scatter",x:sect.fechas,y:totalVenc(sect),name:"Sector — Total Vencida",
    mode:"lines",line:{color:"#90A4AE",width:1.5,dash:"dot"},
    hovertemplate:"Sector total vencida: %{y:.2f}%<extra></extra>",
  });
  if(a.morosos_pct?.some(v=>v!==null)) traces.push({
    type:"scatter",x:a.fechas,y:a.morosos_pct,name:"Morosos",
    mode:"lines",line:{color:"#B71C1C",width:2,dash:"dash"},
    hovertemplate:"Morosos: %{y:.2f}%<extra></extra>",
  });
  traces.push({
    type:"scatter",x:a.fechas,y:totalVenc(a),name:`${inst.name} — Total Vencida`,
    mode:"lines+markers",line:{color:inst.color,width:3},marker:{size:7},
    hovertemplate:"Total vencida: %{y:.2f}%<extra></extra>",
  });
  Plotly.react("chart_anx2_evol", traces, {
    ...LAYOUT,
    title:{text:"Evolución Cartera Vencida / Cartera Bruta",font:{size:13}},
    yaxis:{title:"(%)",ticksuffix:"%"},
    hovermode:"x unified", height:360, legend:{orientation:"h",y:-0.28},
  },{responsive:true});
}

function renderAnx2Latest(inst) {
  const a = inst.anx2 || {};
  if(!a.fechas?.length) { noData('chart_anx2_latest'); return; }
  const pool = [inst._cod];
  (CAT_PEERS[inst.category]||[]).forEach(p => {
    if(p!==inst._cod && INST[p]?.anx2?.fechas?.length) pool.push(p);
  });
  if(INST[inst.sector_cod]?.anx2?.fechas?.length) pool.push(inst.sector_cod);
  const labels = pool.map(c => INST[c]?.name || c);
  const CATS   = ["Vigentes","Col. Vencida","En Gestión","Morosos"];
  const COLORS = ["#43A04799","#FF980099","#F4433699","#B71C1C99"];
  const KEYS   = ["vigentes_pct","col_vencida_pct","en_gestion_pct","morosos_pct"];
  const traces = KEYS.map((key,ki) => {
    const vals = pool.map(c => {
      const ai = INST[c]?.anx2 || {};
      const li = (ai.fechas?.length||0) - 1;
      return li >= 0 ? (ai[key]?.[li] || 0) : 0;
    });
    return {type:"bar",name:CATS[ki],x:labels,y:vals,marker:{color:COLORS[ki]},
      hovertemplate:`${CATS[ki]}: %{y:.1f}%<extra></extra>`};
  });
  Plotly.react("chart_anx2_latest", traces, {
    ...LAYOUT, barmode:"stack",
    title:{text:"Último Mes — Composición por Calidad (inst + peers + sector)",font:{size:13}},
    yaxis:{title:"(%)",ticksuffix:"%",range:[0,105]},
    hovermode:"x unified", height:380, legend:{orientation:"h",y:-0.28},
    margin:{...LAYOUT.margin,b:80},
  },{responsive:true});
}

// ── Tab 3: Distribución Plazos ────────────────────────────────────────────────
const PLZ_LABELS = ["Vista","< 30d","< 91d","< 181d","< 367d","< 3 años","≥ 3 años"];
const PLZ_KEYS   = ["vista","lt30","lt91","lt181","lt367","lt3a","geq3a"];
const PLZ_COLORS = ["#1A237E","#1565C0","#0288D1","#00ACC1","#00897B","#43A047","#66BB6A"];

function renderPlazosEvol(inst) {
  const p = inst.plazos || {};
  if(!p.fechas?.length) { noData('chart_plazos_evol'); return; }
  const traces = PLZ_KEYS.map((k,i) => ({
    type:"scatter", x:p.fechas, y:p[k]||[], name:PLZ_LABELS[i],
    stackgroup:"one", fillcolor:PLZ_COLORS[i]+"88",
    line:{color:PLZ_COLORS[i],width:1},
    hovertemplate:`${PLZ_LABELS[i]}: $%{y:.0f}M<extra></extra>`,
  })).filter(t => t.y?.some(v=>v!==null));
  Plotly.react("chart_plazos_evol", traces, {
    ...LAYOUT,
    title:{text:`${inst.name} — Distribución Cartera por Plazo (M$)`,font:{size:13}},
    yaxis:{title:"Monto (M$)",tickprefix:"$",ticksuffix:"M"},
    hovermode:"x unified", height:380, legend:{orientation:"h",y:-0.32},
    margin:{...LAYOUT.margin,b:90},
  },{responsive:true});
}

function renderPlazosComp(inst) {
  const p    = inst.plazos || {};
  const sect = INST[inst.sector_cod]?.plazos || {};
  if(!p.fechas?.length) { noData('chart_plazos_comp'); return; }

  const getLastDist = src => {
    if(!src.fechas?.length) return null;
    const li = src.fechas.length - 1;
    const vals = PLZ_KEYS.map(k => src[k]?.[li] ?? 0);
    const tot  = vals.reduce((a,b)=>a+b,0);
    return tot > 0 ? vals.map(v => v/tot*100) : null;
  };
  const instDist = getLastDist(p);
  const sectDist = getLastDist(sect);
  if(!instDist) { noData('chart_plazos_comp'); return; }

  const traces = [
    {type:"bar", name:inst.name, x:PLZ_LABELS, y:instDist,
      marker:{color:inst.color+"cc"},
      hovertemplate:`${inst.name} — %{x}: %{y:.1f}%<extra></extra>`},
  ];
  if(sectDist) traces.push({
    type:"bar", name:"Sector", x:PLZ_LABELS, y:sectDist,
    marker:{color:"#90A4AEcc"},
    hovertemplate:"Sector — %{x}: %{y:.1f}%<extra></extra>",
  });
  Plotly.react("chart_plazos_comp", traces, {
    ...LAYOUT, barmode:"group",
    title:{text:"Último Mes — Distribución por Plazo (%)",font:{size:13}},
    yaxis:{title:"(%)",ticksuffix:"%"},
    hovermode:"x unified", height:380, legend:{orientation:"h",y:-0.32},
    margin:{...LAYOUT.margin,b:90},
  },{responsive:true});
}

// ── Selector de instituciones ─────────────────────────────────────────────────
function populateInstSelector(cat) {
  const sel   = document.getElementById("instSelector");
  const insts = CAT_INST[cat] || [];
  sel.innerHTML = insts.map(([cod,name]) =>
    `<option value="${cod}">${name}</option>`
  ).join("\n");
  sel.style.borderColor = cat === "admin" ? "#E63946" : "#1565C0";
  return insts.length > 0 ? insts[0][0] : null;
}

function onCatChange(cat) {
  const firstCod = populateInstSelector(cat);
  document.getElementById("rankTitle").textContent =
    "Ranking — " + (CATEGORIAS[cat]||cat) + " — Último Mes";
  if(firstCod) updateDashboard(firstCod);
}

// ── updateDashboard ───────────────────────────────────────────────────────────
function updateDashboard(cod) {
  const inst = INST[cod];
  if(!inst) return;
  document.getElementById("metaInfo").textContent =
    `${inst.kpis?.n_meses||"—"} meses | último: ${inst.kpis?.fecha||"—"}`;

  renderKPIs(inst);

  // Tab 1
  renderMS(inst);
  renderDeterio(inst);
  renderRoaRoe(inst);
  renderResultado(inst);
  renderCartera(inst);
  renderEficiencia(inst);
  renderRanking(inst.category, cod);

  // Tab 2
  renderAnx2Comp(inst);
  renderAnx2Evol(inst);
  renderAnx2Latest(inst);

  // Tab 3
  renderPlazosEvol(inst);
  renderPlazosComp(inst);
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  // Acerca de es la primera pestaña: ocultar selectores hasta cambiar de tab
  document.getElementById('selectorBar').style.display = 'none';
  document.getElementById('kpiBar').style.display      = 'none';

  Plotly.newPlot("chart_mercado", FIG_MERCADO.data, FIG_MERCADO.layout, {responsive:true});
  Plotly.newPlot("chart_tasas",   FIG_TASAS.data,   FIG_TASAS.layout,   {responsive:true});
  onCatChange("admin");
});
</script>
</body>
</html>"""

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    generate_dashboard()
