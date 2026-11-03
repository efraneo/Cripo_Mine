# ==========================================================
# utils/regime.py
# ==========================================================
# Detección de régimen de mercado y asignación de pesos
# ==========================================================

import pandas as pd
import numpy as np
import logging


# ==========================================================
# 📈 Detección de régimen de mercado
# ==========================================================
def detect_regime(df: pd.DataFrame) -> pd.Series:
    """
    Detecta el régimen de mercado en base a indicadores técnicos.
    Requiere columnas: ['close', 'ema20', 'ema50', 'ema200', 'adx'].
    Retorna un pd.Series con el campo 'regimen'.
    """
    try:
        if df is None or df.empty:
            logging.warning("⚠️ detect_regime: DataFrame vacío")
            return pd.Series({"regimen": "desconocido"})

        required_cols = ["close", "ema20", "ema50", "ema200", "adx"]
        for col in required_cols:
            if col not in df.columns:
                logging.warning(f"⚠️ detect_regime: Falta columna {col}")
                return pd.Series({"regimen": "desconocido"})

        last = df.iloc[-1]

        alcista = (last["close"] > last["ema200"]) and (last["ema20"] > last["ema50"]) and (last["adx"] > 20)
        bajista = (last["close"] < last["ema200"]) and (last["ema20"] < last["ema50"]) and (last["adx"] > 20)

        if alcista:
            return pd.Series({"regimen": "alcista"})
        if bajista:
            return pd.Series({"regimen": "bajista"})

        # Si no hay tendencia fuerte, se asume rango
        return pd.Series({"regimen": "rango"})

    except Exception as e:
        logging.error(f"❌ detect_regime error: {e}")
        return pd.Series({"regimen": "desconocido"})


# ==========================================================
# ⚖️ Ajuste de pesos por régimen
# ==========================================================
def regime_weights(regimen: str, extra_factors: dict = None) -> dict:
    """
    Devuelve un diccionario de pesos (bull, bear) en función del régimen.
    - regimen: 'alcista', 'bajista', 'rango' o 'desconocido'
    - extra_factors: ajustes dinámicos, ej. {'volatilidad': 0.9}
    """
    try:
        base_weights = {
            "alcista": dict(bull=1.0, bear=0.6),
            "bajista": dict(bull=0.6, bear=1.0),
            "rango": dict(bull=0.8, bear=0.8),
            "desconocido": dict(bull=0.7, bear=0.7),
        }

        weights = base_weights.get(regimen, base_weights["desconocido"])

        # Ajustes adicionales
        if extra_factors:
            for key, factor in extra_factors.items():
                if key == "volatilidad":
                    weights = {k: v * factor for k, v in weights.items()}
                if key == "volumen":
                    weights = {k: min(1.2, v * (1 + factor)) for k, v in weights.items()}

        return weights

    except Exception as e:
        logging.error(f"❌ regime_weights error: {e}")
        return dict(bull=0.7, bear=0.7)


# ==========================================================
# 📊 Función auxiliar: resumen extendido
# ==========================================================
def summarize_regime(df: pd.DataFrame) -> dict:
    """
    Devuelve un resumen extendido del régimen:
    - regimen
    - volatilidad reciente
    - volumen relativo
    """
    try:
        reg = detect_regime(df)["regimen"]

        volatilidad = df["close"].pct_change().rolling(20).std().iloc[-1] if "close" in df else np.nan
        volumen_rel = (
            df["volume"].iloc[-1] / df["volume"].rolling(20).mean().iloc[-1]
            if "volume" in df else np.nan
        )

        return {
            "regimen": reg,
            "volatilidad": float(volatilidad) if not np.isnan(volatilidad) else None,
            "volumen_rel": float(volumen_rel) if not np.isnan(volumen_rel) else None,
        }

    except Exception as e:
        logging.error(f"❌ summarize_regime error: {e}")
        return {"regimen": "desconocido", "volatilidad": None, "volumen_rel": None}

