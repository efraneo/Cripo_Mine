# ==========================================================
# utils/patterns.py
# ==========================================================
# Detección de patrones de velas japonesas con soporte extendido.
# Incluye puntuación (bull/bear) para integración en estrategias.
# ==========================================================

import pandas as pd
import logging


# ==========================================================
# 🔧 Helpers internos
# ==========================================================
def _body_size(o, c) -> pd.Series:
    """Devuelve el tamaño del cuerpo de la vela."""
    return (c - o).abs()


def _candle_range(h, l) -> pd.Series:
    """Devuelve el rango total de la vela (alto - bajo)."""
    return (h - l).abs()


# ==========================================================
# 📊 Detector principal de patrones
# ==========================================================
def detect_patterns(df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Detecta patrones de velas japonesas y devuelve un DataFrame extendido.

    Parámetros:
    -----------
    df : pd.DataFrame
        Debe contener columnas ['open', 'high', 'low', 'close'].
    weights : dict, opcional
        Ponderaciones para el cálculo de score (bull/bear).

    Retorna:
    --------
    pd.DataFrame con columnas adicionales:
        - pat_doji, pat_hammer, pat_inv_hammer, pat_engulf_bull, pat_engulf_bear,
          pat_marubozu_bull, pat_marubozu_bear, pat_shooting_star,
          pat_morning_star, pat_evening_star
        - score_bull, score_bear
    """
    try:
        if df is None or df.empty:
            logging.warning("⚠️ detect_patterns: DataFrame vacío")
            return pd.DataFrame()

        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            logging.warning(f"⚠️ detect_patterns: faltan columnas {required - set(df.columns)}")
            return df.copy()

        d = df.copy()
        o, h, l, c = d["open"], d["high"], d["low"], d["close"]

        body = _body_size(o, c)
        rng = _candle_range(h, l)
        upper_wick = h - c.where(c > o, o)
        lower_wick = (o.where(c > o, c)) - l

        # ==========================
        # 🔎 Patrones básicos
        # ==========================
        d["pat_doji"] = (body <= (0.1 * rng)).astype(int)

        d["pat_hammer"] = (
            (lower_wick >= 2 * body) & (upper_wick <= body) & (c > l + 0.25 * rng)
        ).astype(int)

        d["pat_inv_hammer"] = (
            (upper_wick >= 2 * body) & (lower_wick <= body) & (c < h - 0.25 * rng)
        ).astype(int)

        prev_o, prev_c = o.shift(1), c.shift(1)
        d["pat_engulf_bull"] = (
            (c > o) & (prev_c < prev_o) & (c >= prev_o) & (o <= prev_c)
        ).astype(int)
        d["pat_engulf_bear"] = (
            (c < o) & (prev_c > prev_o) & (c <= prev_o) & (o >= prev_c)
        ).astype(int)

        d["pat_marubozu_bull"] = (
            (c > o) & ((h - c) <= 0.1 * body) & ((o - l) <= 0.1 * body)
        ).astype(int)
        d["pat_marubozu_bear"] = (
            (o > c) & ((h - o) <= 0.1 * body) & ((c - l) <= 0.1 * body)
        ).astype(int)

        # ==========================
        # 🔎 Patrones extendidos
        # ==========================
        d["pat_shooting_star"] = (
            (upper_wick >= 2 * body) & (lower_wick <= body) & (c < h - 0.2 * rng)
        ).astype(int)

        # Morning Star (3 velas, patrón alcista)
        d["pat_morning_star"] = (
            (prev_c < prev_o) &
            (d["pat_doji"].shift(1) | d["pat_inv_hammer"].shift(1)) &
            (c > o) & (c > prev_o)
        ).astype(int)

        # Evening Star (3 velas, patrón bajista)
        d["pat_evening_star"] = (
            (prev_c > prev_o) &
            (d["pat_doji"].shift(1) | d["pat_inv_hammer"].shift(1)) &
            (c < o) & (c < prev_o)
        ).astype(int)

        # ==========================
        # ⚖️ Puntuación (ajustable)
        # ==========================
        default_weights = {
            "engulf_bull": 0.8,
            "hammer": 0.6,
            "inv_hammer": 0.4,
            "marubozu_bull": 0.6,
            "shooting_star": -0.5,
            "morning_star": 0.7,
            "engulf_bear": 0.8,
            "marubozu_bear": 0.6,
            "evening_star": 0.7,
            "doji": -0.2,
        }
        w = {**default_weights, **(weights or {})}

        d["score_bull"] = (
            d["pat_engulf_bull"] * w["engulf_bull"]
            + d["pat_hammer"] * w["hammer"]
            + d["pat_inv_hammer"] * w["inv_hammer"]
            + d["pat_marubozu_bull"] * w["marubozu_bull"]
            + d["pat_morning_star"] * w["morning_star"]
            + d["pat_doji"] * w["doji"]
        )

        d["score_bear"] = (
            d["pat_engulf_bear"] * w["engulf_bear"]
            + d["pat_marubozu_bear"] * w["marubozu_bear"]
            + d["pat_evening_star"] * w["evening_star"]
            + d["pat_shooting_star"] * w["shooting_star"]
            + d["pat_doji"] * w["doji"]
        )

        return d

    except Exception as e:
        logging.error(f"❌ detect_patterns error: {e}")
        return df.copy()
