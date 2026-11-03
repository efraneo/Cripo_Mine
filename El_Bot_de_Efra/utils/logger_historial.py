# ===== utils/logger_historial.py =====
"""
📘 Módulo de gestión de historial de operaciones.
-------------------------------------------------
- Guarda todas las predicciones y resultados en un CSV unificado.
- Compatible con logs antiguos: agrega columnas faltantes automáticamente.
- Soporta cierres automáticos por duración, stop dinámico y trailing stop.
- Lectura/filtrado seguro sin bloquear el bot.

Archivo principal: logs/historial.csv
"""

import csv
import os
from datetime import datetime
import pandas as pd

# 📂 Ruta del historial unificado
RUTA_HISTORIAL = os.path.join("logs", "historial.csv")

# Columnas base para señales IA / técnicas
COLUMNAS_BASE = [
    "fecha", "activo", "accion", "origen", "precision", "resultado",
    "RSI", "MACD", "volumen", "tendencia", "modo", "sentimiento", "precio"
]

# Columnas extendidas para operaciones en vivo (órdenes/cierres reales o simulados)
COLUMNAS_TRADE = [
    "fecha", "usuario", "activo", "accion", "precio_entrada", "precio_salida",
    "cantidad", "pnl", "razon_cierre", "origen"
]

# ✅ Lista unificada (sin duplicados, mantiene orden lógico)
COLUMNAS_UNIFICADAS = list(dict.fromkeys(COLUMNAS_BASE + COLUMNAS_TRADE))


# ============================================================
# 🛠 Helper: asegurar estructura de historial
# ============================================================
def _asegurar_historial():
    try:
        if os.path.exists(RUTA_HISTORIAL):
            try:
                df = pd.read_csv(RUTA_HISTORIAL, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(RUTA_HISTORIAL, encoding="latin-1")  # fallback
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        log_error(e, archivo="logger_historial.py", funcion="_asegurar_historial")
        return pd.DataFrame()

# ============================================================
# 🚀 Guardar predicciones / señales IA
# ============================================================
def guardar_log(prediccion, precision, rsi, macd, volumen, tendencia,
                activo=None, origen="IA", modo=None, sentimiento=None, precio=None, resultado=None):
    """
    Guarda una entrada en logs/historial.csv con datos de predicción IA/técnica.
    """
    try:
        _asegurar_historial()
        with open(RUTA_HISTORIAL, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNAS_UNIFICADAS)
            writer.writerow({
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "activo": activo or "N/A",
                "accion": prediccion,
                "origen": origen,
                "precision": round(float(precision), 4) if precision is not None else None,
                "resultado": resultado,
                "RSI": round(float(rsi), 2) if rsi is not None else None,
                "MACD": round(float(macd), 4) if macd is not None else None,
                "volumen": volumen,
                "tendencia": tendencia,
                "modo": modo,
                "sentimiento": sentimiento,
                "precio": precio
            })
    except Exception as e:
        try:
            from utils.logger import log_error
            log_error(e, archivo="utils/logger_historial.py", funcion="guardar_log")
        except Exception:
            print(f"[logger_historial] ❌ Error al guardar log: {e}")


# ============================================================
# 💾 Guardar eventos de trading (órdenes y cierres automáticos)
# ============================================================
def guardar_evento_trade(usuario, activo, accion, precio_entrada, precio_salida,
                         cantidad, pnl, origen="BINANCE", razon_cierre=None):
    """
    Guarda un evento de trading en logs/historial.csv (ejecución o cierre).
    """
    try:
        _asegurar_historial()
        with open(RUTA_HISTORIAL, mode="a", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=COLUMNAS_UNIFICADAS)
            writer.writerow({
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "usuario": usuario or "N/A",
                "activo": activo,
                "accion": accion,
                "precio_entrada": round(float(precio_entrada), 6) if precio_entrada is not None else None,
                "precio_salida": round(float(precio_salida), 6) if precio_salida is not None else None,
                "cantidad": round(float(cantidad), 6) if cantidad is not None else None,
                "pnl": round(float(pnl), 6) if pnl is not None else None,
                "razon_cierre": razon_cierre or "",
                "origen": origen
            })
    except Exception as e:
        try:
            from utils.logger import log_error
            log_error(e, archivo="utils/logger_historial.py", funcion="guardar_evento_trade")
        except Exception:
            print(f"[logger_historial] ❌ Error al guardar evento trade: {e}")


def guardar_evento_stop(usuario, activo, accion, entry_price, stop_price, pnl, razon, origen="BINANCE_STOP"):
    """
    Guarda un cierre automático por stop dinámico / trailing stop.
    """
    try:
        guardar_evento_trade(
            usuario=usuario,
            activo=activo,
            accion=accion,
            precio_entrada=entry_price,
            precio_salida=stop_price,
            cantidad=None,
            pnl=pnl,
            origen=origen,
            razon_cierre=razon
        )
    except Exception as e:
        try:
            from utils.logger import log_error
            log_error(e, archivo="utils/logger_historial.py", funcion="guardar_evento_stop")
        except Exception:
            print(f"[logger_historial] ❌ Error al guardar evento stop: {e}")


# ============================================================
# 📖 Lectura del historial
# ============================================================
def leer_historial():
    """Carga el historial completo como DataFrame seguro."""
    _asegurar_historial()
    try:
        return pd.read_csv(RUTA_HISTORIAL)
    except Exception as e:
        try:
            from utils.logger import log_error
            log_error(e, archivo="utils/logger_historial.py", funcion="leer_historial")
        except Exception:
            print(f"[logger_historial] ❌ Error al leer historial: {e}")
        return pd.DataFrame(columns=COLUMNAS_UNIFICADAS)


def cargar_historial_en_dataframe():
    """Alias de leer_historial(), se mantiene para compatibilidad."""
    return leer_historial()


def filtrar_historial(**filtros):
    """
    Filtra el historial por cualquier columna.
    Ejemplo:
        filtrar_historial(activo="BTCUSDT", modo="Real")
    """
    df = leer_historial()
    try:
        for col, val in filtros.items():
            if col in df.columns:
                df = df[df[col] == val]
        return df
    except Exception as e:
        try:
            from utils.logger import log_error
            log_error(e, archivo="utils/logger_historial.py", funcion="filtrar_historial")
        except Exception:
            print(f"[logger_historial] ❌ Error al filtrar historial: {e}")
        return df
