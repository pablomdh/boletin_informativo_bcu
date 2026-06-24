# BCU Credit Market Analysis

Pipeline de análisis del **mercado de administradoras de crédito al consumo de Uruguay**, basado en los boletines mensuales del Banco Central del Uruguay (BCU).

Monitorea la posición competitiva de cualquier institución frente al sector: evolución de cartera, morosidad, rentabilidad y estructura de fondeo.

**Dashboard público:** https://pablomdh.github.io/boletin_informativo_bcu/

Los datos se actualizan automáticamente el día 15 de cada mes via GitHub Actions.

---

## Instituciones analizadas — Grupo 981 (Administradoras de Crédito)

> Incluye administradoras con cartera superior a 150.000 UR, según clasificación BCU.

| Código | Nombre |
|--------|--------|
| 803 | DIRECTOS |
| 804 | SOCUR (Creditel) |
| 805 | ANDA |
| 815 | OCA SA |
| 817 | RETOP |
| 846 | DEL ESTE |
| 852 | VERENDY |
| 853 | E.de Valor |
| 854 | PASS CARD |
| 858 | BAUTZEN |
| 860 | FUCAC |
| 4302 | CASH S.A. |
| 7886 | RMSA |
| 7890 | Floder S.A. |
| 7894 | Sol.Integrales |
| 981 | TOTAL SECTOR |

### Contexto sectorial — otros grupos BCU

| Grupo | Descripción |
|-------|-------------|
| 99 | Bancos oficiales (BROU, BHU) |
| 996 | Cooperativas de intermediación financiera |
| 997 | Bancos privados (Itaú, Santander, BBVA, Scotiabank, entre otros) |
| 998 | Casas financieras |

---

## Outputs

| Archivo | Descripción |
|---------|-------------|
| `output/dashboards/dashboard_interactivo.html` | Dashboard interactivo — market share, deterioro, ROA/ROE, ranking, plazos y calidad de cartera por segmento |
| `output/reports/resumen_ejecutivo.md` | Resumen narrativo en Markdown |

---

## Reproducir localmente

```bash
# 1. Clonar e instalar dependencias
git clone https://github.com/pablomdh/boletin_informativo_bcu.git
cd boletin_informativo_bcu
pip install -r requirements.txt

# 2. Pipeline completo (descarga + análisis)
python main.py

# Opciones
python main.py --skip-dl    # usar XLS ya descargados
python main.py --only-parse # solo ETL, sin visualizaciones
python main.py --force-dl   # re-descargar aunque ya existan los XLS
```

## Configurar la empresa foco

Para analizar una institución diferente, crear `config/local_settings.py` (ignorado por git):

```python
FOCUS_COMPANY_CODE  = "XXXX"        # código BCU (ver tabla arriba)
FOCUS_COMPANY_NAME  = "Nombre S.A."
FOCUS_COMPANY_SHORT = "NOMBRE"
FOCUS_COMPANY_COLOR = "#E63946"
```

Si no existe el archivo, el pipeline usa los valores por defecto de `config/settings.py`.

---

## Fuente de datos

**Banco Central del Uruguay — Boletín SSF**

> https://www.bcu.gub.uy/Servicios-Financieros-SSF/Boletin%20SSF

Los archivos se publican mensualmente en formato `.xls` (un archivo por grupo, por mes). Los datos están expresados en **miles de pesos uruguayos** y se publican con aproximadamente un mes de rezago. La fecha de última descarga se registra en `data/processed/ultima_actualizacion.json`.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Descarga | `requests` |
| Parsing | `pandas` + `xlrd` (formato `.xls` legacy) |
| Indicadores | `pandas` |
| Visualización | `matplotlib` + `seaborn` + `plotly` |
| CI/CD | GitHub Actions (actualización mensual automática) |
| Hosting | GitHub Pages |

---

## Licencia del código

Este proyecto está publicado bajo la licencia **MIT**. Ver [`LICENSE`](LICENSE).

---

## Aviso legal y uso de datos

### Fuente pública y marco legal uruguayo

Los datos utilizados en este proyecto son **información pública** producida por el Banco Central del Uruguay y publicados en su sitio web oficial. Su acceso, reutilización y redistribución están amparados por la **Ley N.° 18.381 de Acceso a la Información Pública** (Uruguay, 2008), que establece el derecho de acceso libre y gratuito a la información en poder del Estado.

El BCU publica esta información bajo el principio de **datos abiertos de gobierno**, sin restricciones de uso comercial o no comercial, siempre que se cite la fuente.

### Atribución

Toda reproducción o uso derivado de estos datos debe citar:

> **Fuente:** Banco Central del Uruguay — Boletín SSF (https://www.bcu.gub.uy)

### Limitación de responsabilidad

**Este proyecto no tiene afiliación oficial con el Banco Central del Uruguay ni con ninguna de las instituciones financieras analizadas.**

Los análisis, interpretaciones y visualizaciones son de elaboración propia a partir de datos públicos y **no constituyen asesoramiento financiero, regulatorio ni de inversión**. La información puede contener errores de procesamiento o estar desactualizada. El uso de este material es responsabilidad exclusiva del usuario.
