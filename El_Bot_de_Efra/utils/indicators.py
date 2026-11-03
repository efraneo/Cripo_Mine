# ==========================================================
# utils/indicators.py
# ==========================================================
# Módulo para cálculo de indicadores técnicos clásicos.
# Incluye:
#   - RSI
#   - MACD
#   - EMAs
#   - Bandas de Bollinger
#   - ATR (Average True Range)
#   - Soportes y Resistencias
# ==========================================================

import pandas as pd
import numpy as np
import logging

# ==========================================================
# 📊 Medias móviles
# ==========================================================
def ema(series: pd.Series, window: int = 14) -> pd.Series:
    """Cálculo de Exponential Moving Average (EMA)."""
    try:
        return series.ewm(span=window, adjust=False).mean()
    except Exception as e:
        logging.error(f"❌ Error en ema: {e}")
        return pd.Series(dtype=float)


def sma(series: pd.Series, window: int = 14) -> pd.Series:
    """Cálculo de Simple Moving Average (SMA)."""
    try:
        return series.rolling(window=window).mean()
    except Exception as e:
        logging.error(f"❌ Error en sma: {e}")
        return pd.Series(dtype=float)

# ==========================================================
# 📉 RSI y MACD
# ==========================================================
def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Índice de Fuerza Relativa (RSI)."""
    try:
        delta = series.diff()
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(window=window).mean()
        avg_loss = pd.Series(loss).rolling(window=window).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - (100 / (1 + rs))
    except Exception as e:
        logging.error(f"❌ Error en rsi: {e}")
        return pd.Series(dtype=float)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """
    Calcula MACD (Moving Average Convergence Divergence).
    Retorna:
        macd_line, signal_line, histograma
    """
    try:
        ema_fast = ema(series, fast)
        ema_slow = ema(series, slow)
        macd_line = ema_fast - ema_slow
        signal_line = ema(macd_line, signal)
        hist = macd_line - signal_line
        return macd_line, signal_line, hist
    except Exception as e:
        logging.error(f"❌ Error en macd: {e}")
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

# ==========================================================
# 📊 Bandas de Bollinger y ATR
# ==========================================================
def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
    """
    Calcula Bandas de Bollinger.
    Retorna:
        banda_superior, media, banda_inferior
    """
    try:
        rolling_mean = series.rolling(window=window).mean()
        rolling_std = series.rolling(window=window).std()
        upper_band = rolling_mean + (rolling_std * num_std)
        lower_band = rolling_mean - (rolling_std * num_std)
        return upper_band, rolling_mean, lower_band
    except Exception as e:
        logging.error(f"❌ Error en bollinger_bands: {e}")
        return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    Average True Range (ATR).
    Mide volatilidad considerando gaps.
    """
    try:
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=window).mean()
    except Exception as e:
        logging.error(f"❌ Error en atr: {e}")
        return pd.Series(dtype=float)


# ==========================================================
# ⚡ Momentum y estocástico
# ==========================================================
def momentum(series: pd.Series, window: int = 10) -> pd.Series:
    """Momentum simple = precio actual - precio de N velas atrás."""
    try:
        return series.diff(window)
    except Exception as e:
        logging.error(f"❌ Error en Momentum: {e}")
        return pd.Series(index=series.index, dtype=float)


def stochastic(df: pd.DataFrame, k_window: int = 14, d_window: int = 3):
    """
    Oscilador estocástico %K y %D.
    Retorna (k, d).
    """
    try:
        low_min = df["low"].rolling(window=k_window, min_periods=1).min()
        high_max = df["high"].rolling(window=k_window, min_periods=1).max()
        k = 100 * (df["close"] - low_min) / (high_max - low_min)
        d = k.rolling(window=d_window, min_periods=1).mean()
        return k, d
    except Exception as e:
        logging.error(f"❌ Error en Stochastic: {e}")
        return (
            pd.Series(index=df.index, dtype=float),
            pd.Series(index=df.index, dtype=float),
        )
