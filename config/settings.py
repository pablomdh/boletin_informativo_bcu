"""
settings.py — Configuración global del pipeline BCU Credit Analysis.

Para analizar una empresa diferente, editar los valores de empresa foco aquí,
o crear config/local_settings.py con los valores reales (no se sube a git).

El código debe coincidir con el código BCU de la institución en los boletines grupo981.
"""

# ── Empresa foco (valores por defecto — sobreescribir en local_settings.py) ───
FOCUS_COMPANY_CODE = "XXXX"           # Código BCU de la institución a analizar
FOCUS_COMPANY_NAME = "Nombre S.A."    # Nombre completo para labels y títulos
FOCUS_COMPANY_SHORT = "NOMBRE"        # Nombre corto para leyendas
FOCUS_COMPANY_COLOR = "#E63946"       # Color de acento en visualizaciones

# ── Sector ────────────────────────────────────────────────────────────────────
SECTOR_CODE = "981"                   # Código del total del sector (grupo981)
SECTOR_COLOR = "#457B9D"

# ── Override local (privado, no trackeado en git) ─────────────────────────────
try:
    from config.local_settings import *  # noqa: F401, F403
except ImportError:
    pass
