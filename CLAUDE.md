# BCU Credit Market Analysis — Instrucciones para Claude Code

## Objetivo del proyecto

Pipeline de análisis del **mercado de administradoras de crédito al consumo de Uruguay**, basado en los boletines mensuales del Banco Central del Uruguay (BCU). Permite monitorear la posición competitiva de cualquier institución frente al sector, analizando evolución de cartera, morosidad y rentabilidad.

Los outputs (dashboards HTML, gráficos, resúmenes ejecutivos en Markdown) están diseñados para apoyar decisiones estratégicas y de negocio.

## Contexto del mercado

El BCU publica mensualmente estados financieros consolidados de todas las **Administradoras de Crédito** con cartera superior a 150.000 UR (grupo 981). Los datos están en miles de pesos uruguayos. Los principales actores del sector son:

| Código | Nombre | Perfil |
|--------|--------|--------|
| 803 | DIRECTOS | — |
| 804 | SOCUR (Creditel) | Crédito al consumo, mayor escala |
| 805 | ANDA | Crédito al consumo |
| 815 | OCA SA | Tarjeta de crédito / consumo |
| 817 | RETOP | — |
| 846 | DEL ESTE | — |
| 852 | VERENDY | — |
| 853 | E.de Valor | — |
| 854 | PASS CARD | Tarjeta de crédito |
| 858 | BAUTZEN | — |
| 860 | FUCAC | Cooperativa de crédito |
| 4302 | CASH S.A. | Crédito al consumo |
| 7886 | RMSA | — |
| 7890 | Floder S.A. | — |
| 7894 | Sol.Integrales | — |
| 981 | TOTAL SECTOR | Agregado |

## Empresa foco (configurable)

El pipeline analiza una empresa de referencia contra el resto del sector. Configurar en `config/settings.py`:

```python
FOCUS_COMPANY_CODE = "XXXX"        # código BCU de la empresa a analizar
FOCUS_COMPANY_NAME = "Nombre S.A." # nombre completo para labels y títulos
FOCUS_COMPANY_SHORT = "NOMBRE"     # nombre corto para leyendas
FOCUS_COMPANY_COLOR = "#E63946"    # color de acento en visualizaciones
```

El contexto específico de la empresa foco (estrategia, análisis propietarios) va en `private/` (no trackeado en git).

## Estructura del proyecto

```
informe_bcu/
├── CLAUDE.md                    # Este archivo
├── .gitignore
├── main.py                      # Orquestador del pipeline
├── requirements.txt
├── src/
│   ├── ingestion/               # Scrapers de descarga
│   │   ├── scraper.py           # Descarga grupo981 (administradoras)
│   │   └── scraper_bancos.py    # Descarga grupo99/997 (bancos)
│   ├── processing/              # ETL y cálculo de indicadores
│   │   ├── parser.py            # XLS → DataFrame consolidado
│   │   ├── parser_bancos.py     # XLS bancos → DataFrame
│   │   └── indicadores.py       # Cálculo de ratios financieros
│   ├── analysis/                # Módulos de análisis
│   │   ├── analysis.py          # Gráficos matplotlib
│   │   ├── anexo1_analysis.py   # Análisis por plazos (Anexo 1)
│   │   └── anexo2_analysis.py   # Análisis por segmentos (Anexo 2)
│   ├── reporting/               # Generación de outputs
│   │   ├── dashboard_gen.py     # Dashboard Plotly HTML
│   │   └── resumen_md_gen.py    # Resumen ejecutivo Markdown
│   └── agents/                  # Agentes IA (extensión futura)
├── data/
│   ├── raw/                     # XLS descargados del BCU (nunca editar)
│   │   └── bancos/              # Boletines grupos bancarios
│   └── processed/               # CSVs generados por el pipeline
├── output/
│   ├── charts/                  # Gráficos .png (matplotlib)
│   ├── dashboards/              # Dashboards .html (Plotly)
│   └── reports/                 # Resúmenes ejecutivos (.md, .txt)
├── notebooks/                   # Exploración interactiva
├── docs/
│   └── decisiones.md            # Log de decisiones técnicas
├── tests/
├── config/
│   └── settings.py              # Constantes globales (empresa foco, códigos)
└── private/                     # Análisis propietario — NO en git
    ├── to_do.md
    ├── done.md
    └── <empresa>_contexto.md
```

## Pipeline de ejecución

```bash
pip install -r requirements.txt

# Pipeline completo
python main.py

# Opciones
python main.py --skip-dl      # Usar XLS ya descargados (evita re-descarga)
python main.py --only-parse   # Solo ETL, sin visualizaciones
python main.py --force-dl     # Re-descargar aunque ya existan
```

Orden de módulos: `ingestion` → `processing` → `analysis` → `reporting`

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| Descarga | `requests` |
| Parsing | `pandas` + `xlrd` (formato .xls legacy) |
| Indicadores | `pandas` puro |
| Visualización | `matplotlib` + `seaborn` + `plotly` |
| Reporting | Markdown + HTML estático |
| Agentes (futuro) | `anthropic` SDK |

Sin base de datos — todo en archivos CSV locales.

## Convenciones de código

- Rutas siempre relativas a la raíz del proyecto: `ROOT_DIR = Path(__file__).resolve().parent.parent.parent`
- Nunca hardcodear rutas absolutas ni índices de fila en XLS
- Encoding UTF-8 explícito en todos los CSV
- Nombres de columnas en `snake_case`
- Métricas en miles de pesos uruguayos (tal como vienen del BCU)
- Buscar métricas por substring en columna 0, no por número de fila

## Estructura del XLS grupo981 (verificada con abril 2026)

- **Fila 8**: headers de instituciones (col 1–15 empresas, col 16 = total sector 981)
- **Celda [5,0]**: texto de fecha (`'Datos al 30 de abril de 2026'`)
- **Hoja Situación**: activos (búsqueda `'1 - ACTIVOS'`), patrimonio (`'3 - PATRIMONIO'`)
- **Hoja Resultados**: ingresos/gastos intereses, márgenes, resultado operativo
- **Hoja Anexo 1**: distribución cartera por plazos (instituciones desde col 3)
- **Hoja Anexo 2**: cartera bruta (fila 9), deterioro (fila 10), vigentes (fila 11)
- Usar `MonthEnd(0)` al parsear fecha desde nombre de archivo

## Reglas de trabajo

1. Antes de modificar el parser: inspeccionar la estructura del XLS con un snippet de diagnóstico
2. Correr cada módulo antes de pasar al siguiente: ingestion → processing → analysis → reporting
3. Al agregar análisis nuevos: documentar en `docs/decisiones.md`
4. `cartera_bruta > activos_total` es normal: el balance descuenta provisiones, el Anexo 2 no
5. El contexto específico de la empresa analizada va en `private/` — nunca en archivos públicos

## Decisiones técnicas clave

Ver `docs/decisiones.md` para el log completo. Resumen:
- SSL `verify=False` en requests al BCU (cert incompatible con macOS Python 3.12)
- Fecha = cierre del mes (`MonthEnd(0)`) desde nombre de archivo
- `cartera_bruta > activos_total` es esperado (Anexo 2 es bruto, balance neta provisiones)
- Los imports en `main.py` son dinámicos (dentro de bloques `try`) para mejor manejo de errores
