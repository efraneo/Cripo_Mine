# ===== utils/migrar_historial.py =====
"""
🛠 Migrador automático de historial
------------------------------------
- Unifica el formato de logs/historial.csv para evitar errores.
- Se ejecuta al inicio del bot (importarlo en app.py).
- Crea backup antes de modificar nada.
"""

import os
import pandas as pd
from datetime import datetime

# Rutas y columnas
RUTA_HISTORIAL = os.path.join("logs", "historial.csv")

COLUMNAS_BASE = [
    "fecha", "activo", "accion", "origen", "precision", "resultado",
    "RSI", "MACD", "volumen", "tendencia", "modo", "sentimiento", "precio"
]

COLUMNAS_TRADE = [
    "fecha", "usuario", "activo", "accion", "precio_entrada", "precio_salida",
    "cantidad", "pnl", "razon_cierre", "origen"
]

COLUMNAS_UNIFICADAS = list(dict.fromkeys(COLUMNAS_BASE + COLUMNAS_TRADE))


def migrar_historial_si_necesario():
    """Verifica y migra historial.csv si faltan columnas o estructura inconsistente."""
    if not os.path.exists(RUTA_HISTORIAL):
        os.makedirs("logs", exist_ok=True)
        pd.DataFrame(columns=COLUMNAS_UNIFICADAS).to_csv(RUTA_HISTORIAL, index=False)
        print("🆕 Historial creado vacío.")
        return

    try:
        df = pd.read_csv(RUTA_HISTORIAL)

        # Si ya está normalizado, no hacemos nada
        if all(col in df.columns for col in COLUMNAS_UNIFICADAS):
            return

        # Crear backup antes de migrar
        backup_path = RUTA_HISTORIAL.replace(".csv", f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        os.rename(RUTA_HISTORIAL, backup_path)
        print(f"📦 Backup creado en {backup_path}")

        # Agregar columnas faltantes
        for col in COLUMNAS_UNIFICADAS:
            if col not in df.columns:
                df[col] = None

        # Reordenar
        df = df[COLUMNAS_UNIFICADAS]

        # Guardar de nuevo
        df.to_csv(RUTA_HISTORIAL, index=False)
        print(f"✅ Historial migrado a formato unificado ({RUTA_HISTORIAL})")

    except Exception as e:
        print(f"❌ Error migrando historial: {e}")
