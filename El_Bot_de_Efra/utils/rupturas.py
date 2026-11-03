# ==========================================================
# utils/rupturas.py
# ==========================================================
# Detección de rupturas de soportes y resistencias.
# Incluye validaciones de breakout, falsos rompimientos
# y confirmaciones por volumen.

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Logging centralizado
from utils.logger import log_error, log_warning, log_info

# ==========================================================
# 🔎 Funciones base: soportes y resistencias
# ==========================================================
def calcular_soporte(df: pd.DataFrame, ventana: int = 20):
    """
    Calcula el nivel de soporte en una ventana móvil.
    Soporte = mínimo de los últimos N candles.
    """
    try:
        return df["low"].rolling(window=ventana, min_periods=1).min().iloc[-1]
    except Exception as e:
        log_error(e, archivo="rupturas.py", funcion="calcular_soporte")
        return None


def calcular_resistencia(df: pd.DataFrame, ventana: int = 20):
    """
    Calcula el nivel de resistencia en una ventana móvil.
    Resistencia = máximo de los últimos N candles.
    """
    try:
        return df["high"].rolling(window=ventana, min_periods=1).max().iloc[-1]
    except Exception as e:
        log_error(e, archivo="rupturas.py", funcion="calcular_resistencia")
        return None

# ==========================================================
# 🚨 Detección de rupturas y falsos rompimientos
# ==========================================================
def detectar_ruptura(df: pd.DataFrame, ventana: int = 20, factor_volumen: float = 1.5):
    """
    Detecta rupturas de soporte o resistencia en las últimas velas.
    
    Parámetros:
    - df: DataFrame con columnas ["close", "high", "low", "volume"]
    - ventana: nº de velas para calcular soportes y resistencias
    - factor_volumen: multiplicador para confirmar ruptura con volumen
    
    Retorna:
    - dict con claves: {"tipo", "nivel", "confirmado", "falso"}
    """
    try:
        if df is None or df.empty or len(df) < ventana:
            return {"tipo": "ninguno", "nivel": None, "confirmado": False, "falso": False}

        soporte = calcular_soporte(df, ventana)
        resistencia = calcular_resistencia(df, ventana)

        close = df["close"].iloc[-1]
        vol = df["volume"].iloc[-1]
        vol_mean = df["volume"].rolling(ventana).mean().iloc[-1]

        # --- Ruptura alcista (resistencia) ---
        if close > resistencia:
            confirmado = vol > vol_mean * factor_volumen
            return {"tipo": "ruptura_alcista", "nivel": resistencia,
                    "confirmado": confirmado, "falso": not confirmado}

        # --- Ruptura bajista (soporte) ---
        if close < soporte:
            confirmado = vol > vol_mean * factor_volumen
            return {"tipo": "ruptura_bajista", "nivel": soporte,
                    "confirmado": confirmado, "falso": not confirmado}

        # --- Sin ruptura ---
        return {"tipo": "ninguno", "nivel": None, "confirmado": False, "falso": False}

    except Exception as e:
        log_error(e, archivo="rupturas.py", funcion="detectar_ruptura")
        return {"tipo": "error", "nivel": None, "confirmado": False, "falso": False}

# ==========================================================
# ✅ Confirmación de rupturas con varias velas
# ==========================================================
def confirmar_ruptura(df: pd.DataFrame, ventana: int = 20, velas_confirmacion: int = 3) -> dict:
    """
    Confirma rupturas de soporte/resistencia usando varias velas consecutivas.
    
    Parámetros:
    - df: DataFrame con columnas ["close", "high", "low", "volume"]
    - ventana: nº de velas para calcular soporte y resistencia
    - velas_confirmacion: nº de velas consecutivas necesarias para validar la ruptura
    
    Retorna:
    - dict {"confirmada": bool, "tipo": str, "nivel": float}
    """
    try:
        if df is None or df.empty or len(df) < ventana + velas_confirmacion:
            return {"confirmada": False, "tipo": "ninguno", "nivel": None}

        soporte = calcular_soporte(df, ventana)
        resistencia = calcular_resistencia(df, ventana)

        ultimos_cierres = df["close"].tail(velas_confirmacion)

        # --- Confirmación alcista (sobre resistencia varias velas) ---
        if all(c > resistencia for c in ultimos_cierres):
            return {"confirmada": True, "tipo": "ruptura_alcista", "nivel": resistencia}

        # --- Confirmación bajista (bajo soporte varias velas) ---
        if all(c < soporte for c in ultimos_cierres):
            return {"confirmada": True, "tipo": "ruptura_bajista", "nivel": soporte}

        return {"confirmada": False, "tipo": "ninguno", "nivel": None}

    except Exception as e:
        log_error(e, archivo="rupturas.py", funcion="confirmar_ruptura")
        return {"confirmada": False, "tipo": "error", "nivel": None}

# ==========================================================
# 🚀 Estrategias avanzadas de ruptura (Breakout Trading)
# ==========================================================
def estrategia_breakout(df: pd.DataFrame, ventana: int = 20, confirmacion: int = 2,
                        stop_loss_pct: float = 0.02, take_profit_pct: float = 0.04) -> dict:
    """
    Estrategia de trading basada en rupturas confirmadas de soporte/resistencia.
    
    Parámetros:
    - df: DataFrame OHLCV con al menos ["open","high","low","close","volume"]
    - ventana: nº de velas para calcular soporte/resistencia
    - confirmacion: nº de velas que deben confirmar la ruptura
    - stop_loss_pct: porcentaje dinámico para stop-loss
    - take_profit_pct: porcentaje dinámico para take-profit
    
    Retorna:
    - dict con {"senal": str, "nivel": float, "stop_loss": float, "take_profit": float}
    """
    try:
        confirm = confirmar_ruptura(df, ventana=ventana, velas_confirmacion=confirmacion)
        if not confirm["confirmada"]:
            return {"senal": "hold", "nivel": None, "stop_loss": None, "take_profit": None}

        precio_actual = df["close"].iloc[-1]

        if confirm["tipo"] == "ruptura_alcista":
            nivel = confirm["nivel"]
            stop_loss = nivel * (1 - stop_loss_pct)
            take_profit = precio_actual * (1 + take_profit_pct)
            return {
                "senal": "buy",
                "nivel": nivel,
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4)
            }

        elif confirm["tipo"] == "ruptura_bajista":
            nivel = confirm["nivel"]
            stop_loss = nivel * (1 + stop_loss_pct)
            take_profit = precio_actual * (1 - take_profit_pct)
            return {
                "senal": "sell",
                "nivel": nivel,
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4)
            }

        return {"senal": "hold", "nivel": None, "stop_loss": None, "take_profit": None}

    except Exception as e:
        log_error(e, archivo="rupturas.py", funcion="estrategia_breakout")
        return {"senal": "error", "nivel": None, "stop_loss": None, "take_profit": None}

# ==========================================================
# 🧩 Alias de compatibilidad
# ==========================================================
def detectar_rupturas(df: pd.DataFrame, ventana: int = 20, factor_volumen: float = 1.5):
    """
    Alias de compatibilidad para app.py.
    Redirige a detectar_ruptura().
    """
    return detectar_ruptura(df, ventana=ventana, factor_volumen=factor_volumen)
