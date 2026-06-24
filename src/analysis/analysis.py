"""
analysis.py — Análisis de la empresa foco vs sector de administradoras de crédito BCU.

Genera para cada ejecución:
  output/01_market_share_cartera.png   — evolución de market share de cartera bruta
  output/02_ratio_deterioro.png        — evolución del ratio de deterioro
  output/03_resultado_operativo.png    — resultado operativo empresa foco vs peers
  output/04_comparativa_mora.png       — mora y rentabilidad empresa foco vs peers (último mes)
  output/resumen_ejecutivo.txt         — resumen en texto con hallazgos principales

La empresa foco se configura en config/settings.py (FOCUS_COMPANY_CODE).
"""

import logging
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import seaborn as sns

from config.settings import (
    FOCUS_COMPANY_CODE, FOCUS_COMPANY_NAME, FOCUS_COMPANY_SHORT,
    FOCUS_COMPANY_COLOR, SECTOR_CODE, SECTOR_COLOR,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "output"

# Peers principales para comparativas
PEERS = {
    "804": "SOCUR",
    "805": "ANDA",
    "815": "OCA SA",
    "860": "FUCAC",
    FOCUS_COMPANY_CODE: FOCUS_COMPANY_SHORT,
}

log = logging.getLogger(__name__)

# Estilo visual consistente
sns.set_theme(style="whitegrid", palette="muted")

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "setiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}


def _fmt_fecha(ts: pd.Timestamp) -> str:
    return f"{MESES_ES[ts.month].capitalize()} {ts.year}"
PEER_PALETTE = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", FOCUS_COMPANY_COLOR]


def cargar_datos(processed_dir: Path = PROCESSED_DIR) -> pd.DataFrame:
    csv = processed_dir / "serie_temporal.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"No se encontró {csv}. Correr primero: python parser.py"
        )
    df = pd.read_csv(csv, parse_dates=["fecha"])
    df["codigo"] = df["codigo"].astype(str)
    return df


def _fmt_monto(x, pos=None):
    """Formatea miles de pesos como 'M$XXX' o 'M$X.X B'."""
    if abs(x) >= 1_000_000:
        return f"${x/1_000_000:.1f}B"
    elif abs(x) >= 1_000:
        return f"${x/1_000:.0f}M"
    return f"${x:.0f}k"


def _fechas_labels(fechas: pd.Series) -> list[str]:
    return [f.strftime("%b\n%Y") for f in fechas]


# ─────────────────────────────────────────────────────────────────────────────
# 1. MARKET SHARE — cartera bruta
# ─────────────────────────────────────────────────────────────────────────────

def plot_market_share(df: pd.DataFrame, out_dir: Path) -> str:
    """
    Evolución del market share de cartera bruta de la empresa foco vs peers principales.
    Market share = cartera_bruta empresa / cartera_bruta sector total * 100
    """
    sector = df[df["codigo"] == SECTOR_CODE][["fecha", "cartera_bruta"]].rename(
        columns={"cartera_bruta": "sector_total"}
    )
    merged = df[df["codigo"].isin(PEERS)].merge(sector, on="fecha")
    merged["market_share"] = merged["cartera_bruta"] / merged["sector_total"] * 100
    merged = merged.sort_values("fecha")

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (codigo, nombre) in enumerate(PEERS.items()):
        data = merged[merged["codigo"] == codigo]
        if data.empty:
            continue
        color = FOCUS_COMPANY_COLOR if codigo == FOCUS_COMPANY_CODE else PEER_PALETTE[i % len(PEER_PALETTE)]
        lw = 2.5 if codigo == FOCUS_COMPANY_CODE else 1.5
        ax.plot(data["fecha"], data["market_share"], label=nombre,
                color=color, linewidth=lw, marker="o", markersize=4)

    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_title("Market Share — Cartera Bruta\nAdministradoras de Crédito > 150.000 UR", fontsize=13)
    ax.set_xlabel("")
    ax.set_ylabel("Share del sector (%)")
    ax.legend(loc="upper right", fontsize=9)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    dest = out_dir / "01_market_share_cartera.png"
    fig.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Guardado: %s", dest.name)
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# 2. RATIO DE DETERIORO
# ─────────────────────────────────────────────────────────────────────────────

def plot_ratio_deterioro(df: pd.DataFrame, out_dir: Path) -> str:
    """
    Evolución del ratio de deterioro: abs(deterioro_balance) / cartera_bruta * 100
    Un ratio creciente indica deterioro de calidad de cartera.
    """
    peers_df = df[df["codigo"].isin(PEERS)].copy()
    peers_df = peers_df[peers_df["cartera_bruta"].notna() & (peers_df["cartera_bruta"] > 0)]
    peers_df["ratio_deterioro"] = (
        peers_df["deterioro_balance"].abs() / peers_df["cartera_bruta"] * 100
    )
    peers_df = peers_df.sort_values("fecha")

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (codigo, nombre) in enumerate(PEERS.items()):
        data = peers_df[peers_df["codigo"] == codigo]
        if data.empty:
            continue
        color = FOCUS_COMPANY_COLOR if codigo == FOCUS_COMPANY_CODE else PEER_PALETTE[i % len(PEER_PALETTE)]
        lw = 2.5 if codigo == FOCUS_COMPANY_CODE else 1.5
        ax.plot(data["fecha"], data["ratio_deterioro"], label=nombre,
                color=color, linewidth=lw, marker="o", markersize=4)

    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax.set_title("Ratio de Deterioro — Deterioro / Cartera Bruta\nAdministradoras de Crédito > 150.000 UR", fontsize=13)
    ax.set_xlabel("")
    ax.set_ylabel("Ratio deterioro (%)")
    ax.legend(loc="upper right", fontsize=9)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    dest = out_dir / "02_ratio_deterioro.png"
    fig.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Guardado: %s", dest.name)
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# 3. RESULTADO OPERATIVO
# ─────────────────────────────────────────────────────────────────────────────

def plot_resultado_operativo(df: pd.DataFrame, out_dir: Path) -> str:
    """
    Evolución del resultado operativo de la empresa foco vs peers.
    Permite evaluar si la empresa foco está ganando o perdiendo rentabilidad operativa.
    """
    peers_df = df[df["codigo"].isin(PEERS)].copy()
    peers_df = peers_df[peers_df["resultado_operativo"].notna()]
    peers_df = peers_df.sort_values("fecha")

    fig, ax = plt.subplots(figsize=(12, 6))
    for i, (codigo, nombre) in enumerate(PEERS.items()):
        data = peers_df[peers_df["codigo"] == codigo]
        if data.empty:
            continue
        color = FOCUS_COMPANY_COLOR if codigo == FOCUS_COMPANY_CODE else PEER_PALETTE[i % len(PEER_PALETTE)]
        lw = 2.5 if codigo == FOCUS_COMPANY_CODE else 1.5
        ax.plot(data["fecha"], data["resultado_operativo"] / 1000, label=nombre,
                color=color, linewidth=lw, marker="o", markersize=4)

    ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:.0f}M"))
    ax.set_title("Resultado Operativo (en millones de pesos)\nAdministradoras de Crédito > 150.000 UR", fontsize=13)
    ax.set_xlabel("")
    ax.set_ylabel("Resultado operativo (M$)")
    ax.legend(loc="upper right", fontsize=9)
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    dest = out_dir / "03_resultado_operativo.png"
    fig.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Guardado: %s", dest.name)
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# 4. COMPARATIVA PEERS — último mes
# ─────────────────────────────────────────────────────────────────────────────

def plot_comparativa_peers(df: pd.DataFrame, out_dir: Path) -> str:
    """
    Comparativa de la empresa foco vs peers en el último mes disponible:
    - Panel izquierdo: ratio de deterioro
    - Panel derecho: margen financiero bruto / cartera_bruta (rentabilidad relativa)
    """
    ultimo_mes = df["fecha"].max()
    ult = df[(df["fecha"] == ultimo_mes) & df["codigo"].isin(PEERS)].copy()
    ult = ult[ult["cartera_bruta"].notna() & (ult["cartera_bruta"] > 0)]
    ult["ratio_deterioro"] = ult["deterioro_balance"].abs() / ult["cartera_bruta"] * 100
    ult["rentabilidad_cartera"] = ult["margen_financiero_bruto"] / ult["cartera_bruta"] * 100
    ult["nombre"] = ult["codigo"].map(PEERS)
    ult = ult.sort_values("ratio_deterioro")

    colors = [FOCUS_COMPANY_COLOR if c == FOCUS_COMPANY_CODE else SECTOR_COLOR for c in ult["codigo"]]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Panel 1: ratio deterioro
    axes[0].barh(ult["nombre"], ult["ratio_deterioro"], color=colors)
    axes[0].xaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    axes[0].set_title(f"Ratio de Deterioro\n({_fmt_fecha(ultimo_mes)})", fontsize=11)
    axes[0].set_xlabel("Deterioro / Cartera bruta (%)")
    for i, (_, row) in enumerate(ult.iterrows()):
        axes[0].text(row["ratio_deterioro"] + 0.1, i, f"{row['ratio_deterioro']:.1f}%",
                     va="center", fontsize=9)

    # Panel 2: rentabilidad relativa
    ult2 = ult.sort_values("rentabilidad_cartera")
    colors2 = [FOCUS_COMPANY_COLOR if c == FOCUS_COMPANY_CODE else SECTOR_COLOR for c in ult2["codigo"]]
    axes[1].barh(ult2["nombre"], ult2["rentabilidad_cartera"], color=colors2)
    axes[1].xaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    axes[1].set_title(f"Margen Financiero / Cartera Bruta\n({_fmt_fecha(ultimo_mes)})", fontsize=11)
    axes[1].set_xlabel("Margen financiero bruto / Cartera bruta (%)")
    for i, (_, row) in enumerate(ult2.iterrows()):
        axes[1].text(row["rentabilidad_cartera"] + 0.1, i, f"{row['rentabilidad_cartera']:.1f}%",
                     va="center", fontsize=9)

    fig.suptitle(f"Comparativa {FOCUS_COMPANY_NAME} vs Peers Principales", fontsize=13, fontweight="bold")
    fig.tight_layout()

    dest = out_dir / "04_comparativa_mora.png"
    fig.savefig(dest, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("Guardado: %s", dest.name)
    return str(dest)


# ─────────────────────────────────────────────────────────────────────────────
# 5. RESUMEN EJECUTIVO
# ─────────────────────────────────────────────────────────────────────────────

def generar_resumen_ejecutivo(df: pd.DataFrame, out_dir: Path) -> str:
    """
    Genera un resumen en texto con los principales hallazgos sobre la empresa foco.
    """
    foco = df[df["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    sector = df[df["codigo"] == SECTOR_CODE].sort_values("fecha")
    ultimo_mes = df["fecha"].max()
    primer_mes = df["fecha"].min()

    def val(serie, col):
        v = serie[serie["fecha"] == ultimo_mes][col]
        return float(v.iloc[0]) if not v.empty and pd.notna(v.iloc[0]) else None

    def val_inicio(serie, col):
        v = serie[serie["fecha"] == primer_mes][col]
        return float(v.iloc[0]) if not v.empty and pd.notna(v.iloc[0]) else None

    # Calcular métricas clave
    foco_cartera = val(foco,"cartera_bruta")
    sector_cartera = val(sector, "cartera_bruta")
    foco_ms = (foco_cartera / sector_cartera * 100) if foco_cartera and sector_cartera else None

    foco_det = val(foco,"deterioro_balance")
    foco_ratio_det = (abs(foco_det) / foco_cartera * 100) if foco_det and foco_cartera else None

    foco_cartera_inicio = val_inicio(foco,"cartera_bruta")
    crec_cartera = (
        (foco_cartera / foco_cartera_inicio - 1) * 100
        if foco_cartera and foco_cartera_inicio else None
    )

    foco_res_op = val(foco,"resultado_operativo")
    foco_res_op_inicio = val_inicio(foco,"resultado_operativo")

    # Comparar ratio deterioro con peers en último mes
    peers_det = []
    for codigo, nombre in PEERS.items():
        if codigo == FOCUS_COMPANY_CODE:
            continue
        p = df[(df["codigo"] == codigo) & (df["fecha"] == ultimo_mes)]
        if p.empty:
            continue
        cart = float(p["cartera_bruta"].iloc[0]) if pd.notna(p["cartera_bruta"].iloc[0]) else None
        det = float(p["deterioro_balance"].iloc[0]) if pd.notna(p["deterioro_balance"].iloc[0]) else None
        if cart and det:
            peers_det.append((nombre, abs(det) / cart * 100))

    resumen = f"""RESUMEN EJECUTIVO — {FOCUS_COMPANY_NAME} EN EL SECTOR DE CRÉDITO AL CONSUMO URUGUAYO
{'=' * 75}

Período analizado: {_fmt_fecha(primer_mes)} → {_fmt_fecha(ultimo_mes)}
Fuente: BCU — Boletín SSF, Administradoras de Crédito > 150.000 UR
Cifras en miles de pesos uruguayos.

1. POSICIÓN COMPETITIVA (Market Share)
{'-' * 40}
"""
    if foco_ms:
        resumen += f"   {FOCUS_COMPANY_NAME} controla el {foco_ms:.1f}% de la cartera bruta del sector.\n"
    if crec_cartera:
        direccion = "crecimiento" if crec_cartera > 0 else "caída"
        resumen += f"   La cartera bruta de {FOCUS_COMPANY_SHORT} acumula un {direccion} de {abs(crec_cartera):.1f}% en el período.\n"

    resumen += f"""
2. CALIDAD DE CARTERA (Deterioro)
{'-' * 40}
"""
    if foco_ratio_det:
        resumen += f"   Ratio de deterioro de {FOCUS_COMPANY_SHORT}: {foco_ratio_det:.1f}% de la cartera bruta.\n"
    if peers_det:
        resumen += "   Comparativa con peers (último mes):\n"
        for nombre, ratio in sorted(peers_det, key=lambda x: x[1]):
            resumen += f"     {nombre:15s}: {ratio:.1f}%\n"
        if foco_ratio_det:
            mejores = [p for p in peers_det if p[1] < foco_ratio_det]
            peores = [p for p in peers_det if p[1] > foco_ratio_det]
            if mejores:
                resumen += f"   {FOCUS_COMPANY_SHORT} tiene mayor deterioro que: {', '.join(p[0] for p in mejores)}\n"
            if peores:
                resumen += f"   {FOCUS_COMPANY_SHORT} tiene menor deterioro que: {', '.join(p[0] for p in peores)}\n"

    resumen += f"""
3. RESULTADO OPERATIVO
{'-' * 40}
"""
    if foco_res_op is not None:
        signo = "positivo" if foco_res_op > 0 else "NEGATIVO"
        resumen += f"   Resultado operativo de {FOCUS_COMPANY_SHORT} (último mes): ${foco_res_op/1000:.0f}M ({signo})\n"
    if foco_res_op_inicio is not None and foco_res_op is not None and primer_mes != ultimo_mes:
        if foco_res_op_inicio < 0 and foco_res_op < 0:
            mejora = foco_res_op > foco_res_op_inicio
            resumen += f"   {'Mejora' if mejora else 'Deterioro'} respecto a {_fmt_fecha(primer_mes)}.\n"
        elif foco_res_op_inicio != 0:
            var = (foco_res_op - foco_res_op_inicio) / abs(foco_res_op_inicio) * 100
            resumen += f"   Variación vs {_fmt_fecha(primer_mes)}: {var:+.1f}%\n"

    resumen += f"""
4. MÉTRICAS CLAVE (último mes — {_fmt_fecha(ultimo_mes)})
{'-' * 40}
"""
    metricas_mostrar = [
        ("activos_total", "Activos totales"),
        ("cartera_bruta", "Cartera bruta"),
        ("cartera_vigente", "Cartera vigente"),
        ("patrimonio", "Patrimonio"),
        ("ingresos_intereses", "Ingresos por intereses"),
        ("margen_financiero_bruto", "Margen financiero bruto"),
    ]
    for col, label in metricas_mostrar:
        v = val(foco,col)
        if v is not None:
            resumen += f"   {label:35s}: ${v/1000:>10,.0f}M\n"

    resumen += "\n" + "=" * 75 + "\n"

    dest = out_dir / "resumen_ejecutivo.txt"
    dest.write_text(resumen, encoding="utf-8")
    log.info("Guardado: %s", dest.name)
    return resumen


# ─────────────────────────────────────────────────────────────────────────────
# Orquestador principal
# ─────────────────────────────────────────────────────────────────────────────

def analizar(processed_dir: Path = PROCESSED_DIR, out_dir: Path = OUTPUT_DIR):
    """Corre todos los análisis y guarda los resultados en output/."""
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Cargando datos desde %s...", processed_dir)
    df = cargar_datos(processed_dir)
    log.info("Dataset: %d filas, %d meses, %d instituciones",
             len(df), df["fecha"].nunique(), df["codigo"].nunique())

    n_meses = df["fecha"].nunique()
    if n_meses < 2:
        log.warning("Solo %d mes disponible — gráficos de evolución limitados.", n_meses)

    plot_market_share(df, out_dir)
    plot_ratio_deterioro(df, out_dir)
    plot_resultado_operativo(df, out_dir)
    plot_comparativa_peers(df, out_dir)
    resumen = generar_resumen_ejecutivo(df, out_dir)

    print("\n" + resumen)
    log.info("Análisis completo. Archivos en: %s", out_dir.resolve())


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    analizar()
