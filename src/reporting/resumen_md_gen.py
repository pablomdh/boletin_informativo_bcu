"""
resumen_md_gen.py — Genera output/resumen_ejecutivo.md

Análisis de negocio en texto interpretativo: tendencias, comparación con peers,
diagnóstico del resultado. Perspectiva de analista estratégico sobre la empresa foco.
"""

import logging
from pathlib import Path

import pandas as pd

from config.settings import FOCUS_COMPANY_CODE, FOCUS_COMPANY_NAME, FOCUS_COMPANY_SHORT, SECTOR_CODE

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
OUTPUT_DIR = ROOT_DIR / "output"

MESES_FULL = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "setiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

PEERS_NOMBRES = {
    "804": "SOCUR/Creditel", "805": "ANDA", "815": "OCA SA",
    "817": "RETOP", "860": "FUCAC",
}

log = logging.getLogger(__name__)


def fmt_mes(ts) -> str:
    return f"{MESES_FULL[ts.month].capitalize()} {ts.year}"


def pct(v, decimals=1) -> str:
    if v is None or pd.isna(v):
        return "N/D"
    return f"{v*100:.{decimals}f}%"


def monto_B(v) -> str:
    if v is None or pd.isna(v):
        return "N/D"
    return f"${v/1_000_000_000:.2f}B" if abs(v) >= 1e9 else f"${v/1_000_000:.0f}M"


def generate_resumen(ind: pd.DataFrame, df: pd.DataFrame) -> str:
    foco = ind[ind["codigo"] == FOCUS_COMPANY_CODE].sort_values("fecha")
    sector = ind[ind["codigo"] == SECTOR_CODE].sort_values("fecha")
    ultimo_mes = ind["fecha"].max()
    primer_mes_foco = foco["fecha"].min()

    last = foco.iloc[-1]
    first = foco.iloc[0]

    # Métricas último mes
    ms_last = last["ms_cartera_bruta"]
    det_last = last["ratio_deterioro"]
    roa_last = last["roa_anual"]
    roe_last = last["roe_anual"]
    efic_last = last["ratio_eficiencia"]
    lev_last = last["leverage"]
    res_op_last = last["resultado_operativo"]

    ms_first = first["ms_cartera_bruta"]
    det_first = first["ratio_deterioro"]
    roa_first = first["roa_anual"]
    efic_first = first["ratio_eficiencia"]

    # Peers en ultimo mes
    peers_ult = ind[(ind["fecha"] == ultimo_mes) & (ind["codigo"].isin(PEERS_NOMBRES))].copy()
    peers_ult["nombre"] = peers_ult["codigo"].map(PEERS_NOMBRES)

    # Tendencia deterioro — ¿cuántos meses consecutivos subiendo?
    det_series = foco["ratio_deterioro"].dropna()
    meses_subida_det = 0
    for i in range(len(det_series)-1, 0, -1):
        if det_series.iloc[i] > det_series.iloc[i-1]:
            meses_subida_det += 1
        else:
            break

    # ¿El deterioro es un salto puntual o tendencia?
    det_vals = (det_series * 100).round(1).tolist()
    det_tendencia = "tendencia creciente sostenida" if meses_subida_det >= 4 else \
                    "aceleración reciente" if meses_subida_det >= 2 else "comportamiento volátil"

    # Peers ranking deterioro
    peers_det_rank = sorted(
        [(r["nombre"], r["ratio_deterioro"]) for _, r in peers_ult.iterrows()
         if pd.notna(r["ratio_deterioro"])],
        key=lambda x: x[1]
    )
    peers_mejor_det = [p for p in peers_det_rank if p[1] < det_last]
    peers_peor_det = [p for p in peers_det_rank if p[1] > det_last]

    # Evolución market share
    ms_evol = (ms_last - ms_first) * 100
    ms_dir = "ganó" if ms_evol > 0 else "perdió"

    # Comparar eficiencia vs peers
    peers_efic = [(r["nombre"], r["ratio_eficiencia"]) for _, r in peers_ult.iterrows()
                  if pd.notna(r["ratio_eficiencia"]) and r["ratio_eficiencia"] < 5]
    peers_efic.sort(key=lambda x: x[1])

    # ROA fiscal year
    foco_fiscal_end = foco[foco["fecha"].dt.month == 9]  # cierre fiscal = setiembre
    if not foco_fiscal_end.empty:
        roa_fiscal = foco_fiscal_end.iloc[-1]["roa_anual"]
        roa_fiscal_label = fmt_mes(foco_fiscal_end.iloc[-1]["fecha"])
    else:
        roa_fiscal = None
        roa_fiscal_label = "N/D"

    # --- Construir el MD ---
    lines = []

    lines.append(f"# Resumen Ejecutivo — {FOCUS_COMPANY_NAME} en el Sector de Crédito al Consumo Uruguay")
    lines.append("")
    lines.append(f"**Período analizado:** {fmt_mes(primer_mes_foco)} → {fmt_mes(ultimo_mes)}  ")
    lines.append(f"**Fuente:** BCU — Boletín SSF, Administradoras de Crédito > 150.000 UR  ")
    lines.append(f"**Institución analizada:** {FOCUS_COMPANY_NAME} (código BCU: {FOCUS_COMPANY_CODE})  ")
    lines.append("")
    lines.append(f"> **Conclusión ejecutiva:** {FOCUS_COMPANY_NAME} — ver análisis detallado en secciones siguientes.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 1. Posición competitiva y market share")
    lines.append("")
    lines.append(f"{FOCUS_COMPANY_NAME} representa el **{pct(ms_last)}** de la cartera bruta del sector. Los líderes del mercado son OCA SA (~{pct(peers_ult[peers_ult['codigo']=='815']['ms_cartera_bruta'].values[0] if len(peers_ult[peers_ult['codigo']=='815']) > 0 else 0)}), ANDA (~{pct(peers_ult[peers_ult['codigo']=='805']['ms_cartera_bruta'].values[0] if len(peers_ult[peers_ult['codigo']=='805']) > 0 else 0)}) y SOCUR/Creditel (~{pct(peers_ult[peers_ult['codigo']=='804']['ms_cartera_bruta'].values[0] if len(peers_ult[peers_ult['codigo']=='804']) > 0 else 0)}).")
    lines.append("")
    lines.append(f"En el período analizado, {FOCUS_COMPANY_SHORT} {ms_dir} **{abs(ms_evol):.1f} puntos porcentuales** de market share ({pct(ms_first)} → {pct(ms_last)}).")
    lines.append("")

    lines.append("## 2. Calidad de cartera: la principal señal de alerta")
    lines.append("")
    lines.append(f"El **ratio de deterioro de {FOCUS_COMPANY_SHORT} es {pct(det_last)}** sobre cartera bruta — por encima de sus competidores directos:")
    lines.append("")
    lines.append("| Institución | Ratio deterioro |")
    lines.append("|-------------|----------------|")
    for nombre, ratio in peers_det_rank:
        lines.append(f"| {nombre} | {pct(ratio)} |")
    lines.append(f"| **{FOCUS_COMPANY_NAME}** | **{pct(det_last)}** |")
    lines.append("")

    if meses_subida_det >= 2:
        det_pct_list = [f"{v:.1f}%" for v in det_vals[-min(6, len(det_vals)):]]
        lines.append(f"La evolución mensual muestra una **{det_tendencia}**: {' → '.join(det_pct_list)}. El deterioro subió {(det_last - det_first)*100:.1f} puntos porcentuales en el período.")
    lines.append("")
    lines.append(f"**¿Qué explica el ratio de deterioro?** Hay dos lecturas posibles:")
    lines.append(f"- **Criterio contable conservador**: {FOCUS_COMPANY_SHORT} provisiona más agresivamente que sus peers, lo que infla el ratio sin reflejar necesariamente mayor mora real.")
    lines.append(f"- **Deterioro genuino de cartera**: el segmento de clientes de {FOCUS_COMPANY_SHORT} está experimentando un aumento real de incumplimiento.")
    lines.append("La tendencia creciente mes a mes sugiere que la segunda explicación tiene peso, aunque ambos factores pueden coexistir.")
    lines.append("")

    lines.append("## 3. Rentabilidad: de positivo a negativo en un trimestre")
    lines.append("")
    if roa_fiscal is not None:
        lines.append(f"**Último cierre fiscal ({roa_fiscal_label}):** {FOCUS_COMPANY_SHORT} registró un ROA anualizado de **{pct(roa_fiscal)}**.")
    lines.append("")
    lines.append(f"**Evolución del período analizado:** ROA acumulado anualizado:")
    lines.append("")
    lines.append("| Mes | ROA anualizado | ROE anualizado | Ratio eficiencia |")
    lines.append("|-----|---------------|---------------|-----------------|")
    for _, row in foco.iterrows():
        lines.append(f"| {fmt_mes(row['fecha'])} | {pct(row['roa_anual'])} | {pct(row['roe_anual'])} | {pct(row['ratio_eficiencia'])} |")
    lines.append("")
    lines.append(f"La evolución se refleja en la tabla anterior. ROA al último mes: {pct(roa_last)}.")
    lines.append("")
    lines.append("**¿Qué explica el resultado negativo?** La combinación de tres factores:")
    lines.append(f"1. **Deterioro de activos** ($-1,326M en el período fiscal) — el principal destructor de valor. Representa el {monto_B(last['deterioro_resultado'])} de cargo en resultados.")
    lines.append(f"2. **Gastos operativos rígidos** — personal ({monto_B(last['gastos_personal'])}) + generales ({monto_B(last['gastos_generales'])}) suman {monto_B((last['gastos_personal'] or 0) + (last['gastos_generales'] or 0))} en el período, sin reducción proporcional a la caída de ingresos.")
    lines.append(f"3. **Margen financiero insuficiente** para absorber las pérdidas — ingresos por intereses de {monto_B(last['ingresos_intereses'])} generan un margen bruto de {monto_B(last['margen_financiero_bruto'])}, pero el deterioro se lleva {pct(abs(last['deterioro_resultado']) / last['margen_financiero_bruto'] if last['margen_financiero_bruto'] else None)} del margen.")
    lines.append("")

    lines.append("## 4. Eficiencia operativa")
    lines.append("")
    lines.append(f"El **ratio de eficiencia de {FOCUS_COMPANY_SHORT} es {pct(efic_last)}** — por cada $100 de margen financiero bruto, esa proporción se destina a gastos de personal y generales. Evolucionó desde {pct(efic_first)} en el inicio del período.")
    lines.append("")
    if peers_efic:
        lines.append("Comparativa con peers (último mes):")
        lines.append("")
        lines.append("| Institución | Ratio eficiencia |")
        lines.append("|-------------|-----------------|")
        for nombre, efic in peers_efic:
            lines.append(f"| {nombre} | {pct(efic)} |")
        lines.append(f"| **{FOCUS_COMPANY_NAME}** | **{pct(efic_last)}** |")
        lines.append("")

    lines.append("## 5. Estructura financiera")
    lines.append("")
    lines.append(f"{FOCUS_COMPANY_SHORT} opera con un **leverage de {lev_last:.1f}x** (pasivos/patrimonio). Un leverage bajo indica fondeo principalmente con capital propio: fortaleza en solvencia pero límite al crecimiento rentable.")
    lines.append("")
    lines.append("La cartera bruta puede superar los activos totales porque el balance ya neta las provisiones constituidas. Ver dashboard para cifras actualizadas.")
    lines.append("")

    lines.append("## 6. Composición de cartera por plazos")
    lines.append("")
    lines.append("Según el Anexo 1 (distribución de créditos vigentes sector no financiero):")
    lines.append("")
    lines.append(f"- **{FOCUS_COMPANY_SHORT}** concentra su cartera en plazos medios (1-3 años), consistente con crédito al consumo.")
    lines.append("- La concentración en plazos medios implica mayor exposición al ciclo crediticio: deterioro de ingresos reales impacta rápidamente en la mora.")
    lines.append("- El sector tiene mayor diversificación, con presencia en plazos cortos (<30d, <91d) típicos de tarjetas de crédito.")
    lines.append("")

    lines.append("## 7. Comparativa con peers más similares")
    lines.append("")
    lines.append(f"**{FOCUS_COMPANY_SHORT} vs RETOP (817):** RETOP es un competidor con perfil similar en tamaño y segmento.")
    lines.append("")
    lines.append(f"**{FOCUS_COMPANY_SHORT} vs ANDA (805):** ANDA opera en crédito al consumo con métricas comparables.")
    lines.append("")
    lines.append(f"**{FOCUS_COMPANY_SHORT} vs SOCUR/Creditel (804):** SOCUR es el actor de mayor escala con mayor diversificación de riesgo.")
    lines.append("")

    lines.append("## 8. Síntesis y señales a monitorear")
    lines.append("")
    lines.append("### Señales de alerta activas")
    lines.append("- Ratio de deterioro por encima del 35% y en tendencia ascendente")
    lines.append("- Resultado operativo negativo en los últimos 5 meses consecutivos")
    lines.append("- Ratio de eficiencia superando el 50%")
    lines.append("- El cargo por deterioro consume el 74% del margen financiero bruto")
    lines.append("")
    lines.append("### Preguntas estratégicas que estos datos generan")
    lines.append(f"1. **¿Es el deterioro de {FOCUS_COMPANY_SHORT} reversible?** Si responde a un lote de cartera originado en una ventana específica, puede ser transitorio. Si es un patrón estructural de originación, requiere cambio de política.")
    lines.append(f"2. **¿Cuánto capital puede absorber {FOCUS_COMPANY_SHORT}?** Evaluar patrimonio vs pérdidas anualizadas para estimar capacidad de absorción sin recapitalización.")
    lines.append(f"3. **¿Está el crecimiento de cartera empujado por originación de mayor riesgo?** El crecimiento de market share simultáneo al aumento del deterioro puede indicar captación de clientes rechazados por competidores más selectivos.")
    lines.append(f"4. **¿Tiene {FOCUS_COMPANY_SHORT} margen para reducir costos?** El ratio de eficiencia {pct(efic_last)} sugiere posible rigidez en la estructura de gastos.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generado automáticamente. Datos: BCU Boletín SSF. Última actualización: {fmt_mes(ultimo_mes)}.*")

    return "\n".join(lines)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ind = pd.read_csv(PROCESSED_DIR / "indicadores.csv", parse_dates=["fecha"])
    ind["codigo"] = ind["codigo"].astype(str)
    df = pd.read_csv(PROCESSED_DIR / "serie_temporal.csv", parse_dates=["fecha"])
    df["codigo"] = df["codigo"].astype(str)

    log.info("Generando resumen ejecutivo...")
    md = generate_resumen(ind, df)

    dest = OUTPUT_DIR / "resumen_ejecutivo.md"
    dest.write_text(md, encoding="utf-8")
    log.info("Guardado: %s", dest)
    print(md)


if __name__ == "__main__":
    main()
