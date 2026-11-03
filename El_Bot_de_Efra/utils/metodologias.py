# ==========================================================
# utils/metodologias.py
# ==========================================================
# Metodologías de trading (RSI, MACD, MAs, Volumen, etc.)
# Versión avanzada con calibración dinámica de confianza.
# Integración completa con dynamic_confidence_boost()
# ==========================================================

import pandas as pd
import numpy as np
from typing import List, Dict, Any

from utils.confidence_boost import dynamic_confidence_boost  # 🔥 Nuevo módulo
from utils.logger import log_info, log_warning, log_error


# ==========================================================
# 🧩 Helper seguro
# ==========================================================
def _safe_last(df, col, default=None):
    try:
        return float(df[col].iloc[-1])
    except Exception:
        return default


# ==========================================================
# 🧠 Núcleo principal: aplicar_metodologias()
# ==========================================================
def aplicar_metodologias(
    df: pd.DataFrame,
    prediccion_lstm: Dict[str, Any] = None,
    confianza_ia: float = 0.0,
    resumen: str = ""
) -> List[Dict[str, Any]]:
    """
    Recibe DataFrame OHLCV con indicadores técnicos.
    Devuelve una lista de señales individuales, calibradas y robustas:
        [{"metodo": "RSI", "senal": "BUY", "confianza": 0.82}, ...]

    Parámetros:
        df               → DataFrame con indicadores técnicos
        prediccion_lstm  → resultado de la IA LSTM (dict con confianza)
        confianza_ia     → confianza general actual de IA
        resumen           → texto opcional para logs o alertas
    """
    metodos: List[Dict[str, Any]] = []

    if df is None or df.empty:
        log_warning("⚠️ DataFrame vacío en aplicar_metodologias", archivo="metodologias.py")
        return [{"metodo": "fallback", "senal": "BUY", "confianza": 0.5}]

    # ==========================================================
    # 1️⃣ RSI
    # ==========================================================
    if "rsi" in df.columns:
        rsi = _safe_last(df, "rsi")
        if rsi is not None:
            if rsi <= 20:
                metodos.append({"metodo": "RSI", "senal": "BUY", "confianza": 0.95})
            elif rsi >= 80:
                metodos.append({"metodo": "RSI", "senal": "SELL", "confianza": 0.95})
            else:
                distancia = abs(rsi - 50) / 50.0
                conf = min(0.85, 0.4 + distancia * 0.45)
                senal = "BUY" if rsi < 50 else "SELL"
                metodos.append({"metodo": "RSI", "senal": senal, "confianza": conf})

    # ==========================================================
    # 2️⃣ MACD
    # ==========================================================
    if "macd" in df.columns and "macd_signal" in df.columns:
        macd = _safe_last(df, "macd")
        signal = _safe_last(df, "macd_signal")
        if macd is not None and signal is not None:
            diff = macd - signal
            ratio = abs(diff) / (abs(signal) + 1e-6)
            conf = min(0.95, 0.45 + min(ratio, 1.5) * 0.33)
            senal = "BUY" if diff > 0 else "SELL"
            metodos.append({"metodo": "MACD", "senal": senal, "confianza": conf})

    # ==========================================================
    # 3️⃣ Cruce de Medias Móviles
    # ==========================================================
    if "ma_fast" in df.columns and "ma_slow" in df.columns:
        fast = _safe_last(df, "ma_fast")
        slow = _safe_last(df, "ma_slow")
        if fast is not None and slow is not None:
            diff = fast - slow
            conf = min(0.95, 0.5 + (abs(diff) / (abs(slow) + 1e-6)) * 0.5)
            senal = "BUY" if diff > 0 else "SELL"
            metodos.append({"metodo": "MA Crossover", "senal": senal, "confianza": conf})

    # ==========================================================
    # 4️⃣ Volumen Relativo
    # ==========================================================
    if "volume" in df.columns:
        try:
            vol = float(df["volume"].iloc[-1])
            avg_vol = float(df["volume"].rolling(window=min(len(df), 20)).mean().iloc[-1])
            ratio = vol / (avg_vol + 1e-12)
            conf = min(0.95, 0.4 + (min(ratio, 2.5) - 1) * 0.3)
            price_now = _safe_last(df, "close")
            price_prev = _safe_last(df.iloc[:-1], "close")
            senal = "BUY" if (price_now or 0) > (price_prev or 0) else "SELL"
            metodos.append({"metodo": "Volumen", "senal": senal, "confianza": conf})
        except Exception as e:
            log_warning(f"Error Volumen: {e}", archivo="metodologias.py", funcion="aplicar_metodologias")

    # ==========================================================
    # 5️⃣ Bandas de Bollinger
    # ==========================================================
    if all(k in df.columns for k in ["bb_upper", "bb_lower", "close"]):
        close, bb_u, bb_l = map(lambda c: _safe_last(df, c), ["close", "bb_upper", "bb_lower"])
        if None not in (close, bb_u, bb_l):
            if close > bb_u:
                metodos.append({"metodo": "Bollinger", "senal": "SELL", "confianza": 0.9})
            elif close < bb_l:
                metodos.append({"metodo": "Bollinger", "senal": "BUY", "confianza": 0.9})

    # ==========================================================
    # 6️⃣ ATR Breakout
    # ==========================================================
    if all(k in df.columns for k in ["atr", "high", "low", "close"]):
        atr, high, low, close = map(lambda c: _safe_last(df, c), ["atr", "high", "low", "close"])
        if None not in (atr, high, low, close):
            rh, rl = df["high"].rolling(20).max().iloc[-1], df["low"].rolling(20).min().iloc[-1]
            if close > rh + 0.5 * atr:
                metodos.append({"metodo": "ATR Breakout", "senal": "BUY", "confianza": 0.9})
            elif close < rl - 0.5 * atr:
                metodos.append({"metodo": "ATR Breakout", "senal": "SELL", "confianza": 0.9})

    # ==========================================================
    # 7️⃣ ADX
    # ==========================================================
    if "adx" in df.columns:
        adx = _safe_last(df, "adx")
        if adx and adx >= 30:
            metodos.append({"metodo": "ADX", "senal": "BUY", "confianza": 0.6})

    # ==========================================================
    # 8️⃣ Stochastic Oscillator
    # ==========================================================
    if all(k in df.columns for k in ["stoch_k", "stoch_d"]):
        k, d = _safe_last(df, "stoch_k"), _safe_last(df, "stoch_d")
        if None not in (k, d):
            if k > d and k < 30:
                metodos.append({"metodo": "Stochastic", "senal": "BUY", "confianza": 0.8})
            elif k < d and k > 70:
                metodos.append({"metodo": "Stochastic", "senal": "SELL", "confianza": 0.8})

    # ==========================================================
    # 9️⃣ Patrones de Velas
    # ==========================================================
    if "patron_signal" in df.columns:
        pat = str(df["patron_signal"].iloc[-1]).upper()
        if "BUY" in pat or "BULL" in pat:
            metodos.append({"metodo": "Patrones", "senal": "BUY", "confianza": 0.85})
        elif "SELL" in pat or "BEAR" in pat:
            metodos.append({"metodo": "Patrones", "senal": "SELL", "confianza": 0.85})

    # ==========================================================
    # 🔚 Fallback final
    # ==========================================================
    if not metodos:
        metodos.append({"metodo": "fallback", "senal": "BUY", "confianza": 0.5})

    # ==========================================================
    # 📌 Adjuntar DF (meta) para backtests rápidos downstream
    # ==========================================================
    try:
        if not any(isinstance(m, dict) and "_df" in m for m in metodos):
            metodos.append({"_df": df})
    except Exception as e:
        log_warning(f"No se pudo adjuntar DF: {e}", archivo="metodologias.py", funcion="aplicar_metodologias")

    # ==========================================================
    # 🚀 No aplicar boost aquí: dejamos la tarea de ajustar
    # la confianza IA a la capa de combinación (prediccion.py)
    # ==========================================================
    return metodos
