# Decisiones técnicas y de diseño

Registro de decisiones no evidentes tomadas durante el desarrollo.
Las decisiones estratégicas sobre la empresa analizada van en `private/`.

---

## 2026-06-09 — SSL verify=False para descarga BCU

**Problema**: El servidor del BCU (bcu.gub.uy) presenta error `CERTIFICATE_VERIFY_FAILED` en macOS Python 3.12. La cadena de certificados del BCU no está en el bundle de CA raíces que usa Python en macOS.

**Decisión**: Usar `verify=False` en las requests al BCU + suprimir el warning de urllib3. Justificación:
- Es un sitio gubernamental oficial, el riesgo de MITM es bajo en este contexto
- Los datos son públicos y no se envía información sensible

**Alternativa documentada**: `pip install certifi` y pasar `verify=certifi.where()` en lugar de `verify=False`.

---

## 2026-06-09 — Fecha de Situación vs Anexo 2

**Observación**: La celda de fecha en Situación (`[5,0]`) contiene el último día del mes reportado (ej: "Datos al 30 de abril de 2026"). Se usa ese timestamp como `fecha` del registro.

**Decisión**: Usar `MonthEnd(0)` al parsear desde nombre de archivo para consistencia. La fecha representa el cierre del mes, no el inicio.

---

## 2026-06-09 — cartera_bruta > activos_total es esperado

**Observación**: Para algunas instituciones, `cartera_bruta` (Anexo 2) puede superar `activos_total` (hoja Situación).

**Explicación**: La cartera bruta (Anexo 2) incluye el valor nominal bruto de los créditos. Los `activos_total` en el balance ya descuentan el deterioro (provisiones). La diferencia es el saldo de provisiones constituidas.

**Decisión**: Mantener ambas métricas tal como vienen del BCU. No "corregir". Para ratios de cobertura, usar: `deterioro_balance / cartera_bruta`.

---

## 2026-06-09 — Cambios en composición del sector (nota de seguimiento)

**Observación**: En agosto 2025 figuraba **816 PROMOTORA DE CREDITOS S.A.** que desaparece en octubre 2025. Puede ser fusión, liquidación o cambio de categoría regulatoria.

**Decisión**: No afecta el análisis del sector agregado. Registrado para referencia si aparecen inconsistencias en el total histórico.

---

## 2026-06-09 — Tasas de cobertura: verificación de criterio contable

**Observación**: Al analizar el Anexo 2, conviene verificar si un ratio de deterioro elevado refleja genuina mayor mora o un criterio contable más conservador. La forma de discriminar es comparar las tasas de cobertura por segmento (provisión/saldo) de la institución foco vs el sector:
- Vigentes: tasa esperada ~4-6%
- Colocación vencida: ~25-30%
- En gestión: ~60-65%
- Morosos: ~100%

Si las tasas de la empresa foco son similares al sector, el ratio de deterioro elevado refleja mayor proporción de cartera en mal estado, no un criterio más estricto.

**Decisión**: Incluir comparativa de tasas de cobertura por segmento en el análisis estándar.

---

## 2026-06-23 — Estructura de paquetes Python

**Decisión**: Los módulos en `src/layer/` usan `ROOT_DIR = Path(__file__).resolve().parent.parent.parent` para apuntar a la raíz del proyecto (3 niveles: `src/capa/archivo.py` → raíz).

`main.py` en la raíz importa con la sintaxis de paquete: `from src.ingestion.scraper import descargar_todos`.

---

## 2026-06-23 — Empresa foco configurable

**Decisión**: Centralizar toda la configuración de la empresa foco en `config/settings.py`. Los módulos `src/analysis/`, `src/reporting/` y `src/processing/indicadores.py` importan `FOCUS_COMPANY_CODE`, `FOCUS_COMPANY_NAME`, `FOCUS_COMPANY_SHORT`, `FOCUS_COMPANY_COLOR` y `SECTOR_CODE` desde allí.

`settings.py` contiene valores neutros (placeholders) para el repo público. Los valores reales van en `config/local_settings.py` (en `.gitignore`), que es importado al final de `settings.py` con `try/except ImportError` para sobreescribir los defaults sin modificar el código fuente.

**Patrón para dicts con empresa foco**: los `INST_NAMES` y `PEER_COLORS` se definen sin la empresa foco en el literal y se agrega con `dict[FOCUS_COMPANY_CODE] = FOCUS_COMPANY_NAME` después del `import`.