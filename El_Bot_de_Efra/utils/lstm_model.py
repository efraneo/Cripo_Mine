# utils/lstm_model.py
# ==========================================================
# LSTM optimizado: entrena la primera vez y guarda modelo+scaler en disk
# Añade evaluación de fiabilidad (in-sample) para estimar confianza real
# ==========================================================

import os
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
import joblib

# tensorflow imports
try:
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.callbacks import EarlyStopping
except Exception as e:
    raise ImportError("TensorFlow no disponible: " + str(e))

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error

MODELS_DIR = "models"
MODEL_PATH = os.path.join(MODELS_DIR, "lstm_model.h5")
SCALER_PATH = os.path.join(MODELS_DIR, "lstm_scaler.pkl")
os.makedirs(MODELS_DIR, exist_ok=True)

_model_cache = None
_scaler_cache: Optional[MinMaxScaler] = None


def _preparar_series(df: pd.DataFrame, pasos: int = 30):
    prices = df["close"].astype(float).values.reshape(-1, 1)
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled = scaler.fit_transform(prices)
    X, y = [], []
    for i in range(pasos, len(scaled)):
        X.append(scaled[i - pasos:i, 0])
        y.append(scaled[i, 0])
    X = np.array(X)
    y = np.array(y)
    if X.size == 0:
        return None, None, scaler
    return X.reshape((X.shape[0], X.shape[1], 1)), y, scaler


def _construir_modelo(input_shape):
    model = Sequential()
    model.add(LSTM(64, return_sequences=True, input_shape=input_shape))
    model.add(Dropout(0.15))
    model.add(LSTM(64))
    model.add(Dropout(0.15))
    model.add(Dense(1, activation="linear"))
    model.compile(optimizer="adam", loss="mse")
    return model


def entrenar_o_cargar(df: pd.DataFrame, pasos: int = 30, epochs: int = 12, batch_size: int = 32):
    global _model_cache, _scaler_cache

    if _model_cache is not None and _scaler_cache is not None:
        return _model_cache, _scaler_cache

    if os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH):
        model = load_model(MODEL_PATH)
        scaler = joblib.load(SCALER_PATH)
        _model_cache = model
        _scaler_cache = scaler
        return model, scaler

    X, y, scaler = _preparar_series(df, pasos=pasos)
    if X is None or y is None or len(X) < 10:
        raise ValueError("No hay suficientes datos para entrenar LSTM")

    model = _construir_modelo((X.shape[1], 1))
    es = EarlyStopping(monitor="loss", patience=3, restore_best_weights=True, verbose=0)
    model.fit(X, y, epochs=epochs, batch_size=batch_size, callbacks=[es], verbose=0)

    try:
        model.save(MODEL_PATH)
        joblib.dump(scaler, SCALER_PATH)
    except Exception:
        pass

    _model_cache = model
    _scaler_cache = scaler
    return model, scaler


def _evaluar_reliability_in_sample(model, scaler, df: pd.DataFrame, pasos: int = 30) -> float:
    """
    Calcula un score de fiabilidad entre 0..1 usando error in-sample
    (si hay suficientes ventanas). Mapea el RMSE relativo a una escala 0..1.
    """
    try:
        X, y, _ = _preparar_series(df, pasos=pasos)
        if X is None or y is None or len(X) < 5:
            return 0.5  # fallback medio

        preds = model.predict(X, verbose=0).flatten()
        rmse = np.sqrt(mean_squared_error(y, preds))
        # rmse está en escala escalada (0..1) -> rmse_rel = rmse
        rmse_rel = float(rmse)  # typical < 0.1 good, >0.2 poor

        # Mapear a fiabilidad: si rmse_rel ~ 0.02 → alta (0.9+), si ~0.2 → baja (0.0-0.3)
        # Usamos una decaimiento suave
        reliability = max(0.0, min(1.0, 1.0 - (rmse_rel * 4.0)))  # factor 4 empírico
        return float(reliability)
    except Exception:
        return 0.5


def predecir(df: pd.DataFrame, pasos: int = 30, horizonte: int = 5) -> Optional[Dict[str, Any]]:
    """
    Devuelve dict:
      {"tendencia":"UP"/"DOWN"/"HOLD", "confianza":0..1, "predicciones":[...], "ultimo_precio":float}
    """
    try:
        if df is None or df.empty or "close" not in df.columns:
            return None

        # Entrenar o cargar modelo
        model, scaler = entrenar_o_cargar(df, pasos=pasos)

        prices = df["close"].astype(float).values.reshape(-1, 1)
        scaled = scaler.transform(prices)
        if len(scaled) < pasos:
            return {"tendencia": "HOLD", "confianza": 0.0, "predicciones": [], "ultimo_precio": float(prices[-1])}

        seq = scaled[-pasos:].copy()
        preds_scaled = []
        for i in range(horizonte):
            p = model.predict(seq.reshape(1, pasos, 1), verbose=0)[0][0]
            preds_scaled.append(p)
            seq = np.vstack([seq[1:], [p]])

        preds = scaler.inverse_transform(np.array(preds_scaled).reshape(-1, 1)).flatten().tolist()
        ultimo = float(prices[-1])
        futuro = float(preds[-1]) if preds else ultimo
        cambio_pct = (futuro - ultimo) / (ultimo + 1e-12) * 100.0

        # volatilidad reciente
        returns = pd.Series(df["close"].astype(float)).pct_change().dropna()
        vol = float(returns.tail(60).std()) if not returns.empty else 1e-6
        vol = max(vol, 1e-6)

        # fuerza relativa del movimiento
        strength = abs((futuro - ultimo) / (ultimo + 1e-12))
        raw_conf = strength / (vol * 2.0 + 1e-12)

        # Fiabilidad del modelo calculada in-sample
        model_reliability = _evaluar_reliability_in_sample(model, scaler, df, pasos=pasos)

        # Mezclar: 60% raw_conf basado en señal, 40% fiabilidad del modelo
        confianza = max(0.0, min(1.0, 0.6 * (raw_conf / (raw_conf + 1.0)) + 0.4 * model_reliability))

        # decisión
        if cambio_pct > 0.2:
            tendencia = "UP"
        elif cambio_pct < -0.2:
            tendencia = "DOWN"
        else:
            tendencia = "HOLD"

        return {
            "tendencia": tendencia,
            "confianza": round(float(confianza), 4),
            "predicciones": [float(round(x, 8)) for x in preds],
            "ultimo_precio": round(float(ultimo), 8),
            "cambio_pct": round(float(cambio_pct), 4)
        }

    except Exception:
        return {"tendencia": "HOLD", "confianza": 0.0, "predicciones": [], "ultimo_precio": None, "cambio_pct": 0.0}
