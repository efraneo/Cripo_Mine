# utils/model_trainer.py
# ==========================================================
# Entrenador dinámico y utilidades para LSTM + ML (RF/XGB)
# - Preparación de datos LSTM
# - Entrenamiento / guardado / carga LSTM
# - Entrenamiento rápido de RF / XGBoost (reentrenado incremental)
# - Funciones públicas:
#     preparar_datos_lstm, entrenar_y_guardar_modelo,
#     cargar_modelo_lstm, cargar_scaler, guardar_scaler,
#     entrenar_ml_models, actualizar_modelo_dinamico, actualizar_modelos_en_vivo
# ==========================================================

import os
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List

# ML libs (opcionales)
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    _HAS_SK = True
except Exception:
    _HAS_SK = False

try:
    import xgboost as xgb
    from xgboost import XGBClassifier
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False

# Keras / TensorFlow
try:
    from tensorflow.keras.models import Sequential, load_model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
    from tensorflow.keras.callbacks import EarlyStopping
    _HAS_TF = True
except Exception:
    _HAS_TF = False

# Scaler
from sklearn.preprocessing import MinMaxScaler

# Logger interno del proyecto
from utils.logger import log_info, log_warning, log_error

# ----------------------------------------------------------
# Directorios
# ----------------------------------------------------------
ROOT = Path(".")
MODELOS_DIR = ROOT / "modelos_entrenados"
MODELOS_LSTM_DIR = MODELOS_DIR / "lstm"
MODELOS_ML_DIR = MODELOS_DIR / "ml"
SCALERS_DIR = ROOT / "data_historica" / "scalers"

for d in (MODELOS_DIR, MODELOS_LSTM_DIR, MODELOS_ML_DIR, SCALERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------
# Helpers: nombres y paths
# ----------------------------------------------------------
def _norm_activo(activo: Optional[str]) -> str:
    return (activo or "GEN").strip().upper()

def _lstm_path(activo: Optional[str]) -> Path:
    return MODELOS_LSTM_DIR / f"{_norm_activo(activo)}_lstm.keras"

def _scaler_path(activo: Optional[str]) -> Path:
    return SCALERS_DIR / f"{_norm_activo(activo)}_scaler.pkl"

def _ml_path(activo: Optional[str], kind: str) -> Path:
    return MODELOS_ML_DIR / f"{_norm_activo(activo)}_{kind}.pkl"

# ----------------------------------------------------------
# Scaler save/load
# ----------------------------------------------------------
def guardar_scaler(activo: str, scaler: MinMaxScaler) -> bool:
    try:
        joblib.dump(scaler, str(_scaler_path(activo)))
        log_info(f"Scaler guardado para {activo}", archivo="model_trainer.py", funcion="guardar_scaler")
        return True
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="guardar_scaler")
        return False

def cargar_scaler(activo: str) -> Optional[MinMaxScaler]:
    try:
        p = _scaler_path(activo)
        if p.exists():
            return joblib.load(str(p))
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="cargar_scaler")
    return None

# ==========================================================
# LSTM: preparar datos
# ==========================================================
def preparar_datos_lstm(df: pd.DataFrame, pasos: int = 20) -> Tuple[np.ndarray, np.ndarray, Optional[MinMaxScaler]]:
    """
    Prepara X,y y scaler para LSTM sobre la columna 'close'.
    """
    try:
        if df is None or df.empty or "close" not in df.columns:
            log_warning("preparar_datos_lstm: DataFrame inválido", archivo="model_trainer.py", funcion="preparar_datos_lstm")
            return np.array([]), np.array([]), None

        vals = df[["close"]].dropna().values.astype(float)
        if len(vals) < pasos + 1:
            log_warning("preparar_datos_lstm: filas insuficientes", archivo="model_trainer.py", funcion="preparar_datos_lstm")
            return np.array([]), np.array([]), None

        scaler = MinMaxScaler()
        scaled = scaler.fit_transform(vals)

        X, y = [], []
        for i in range(len(scaled) - pasos):
            X.append(scaled[i:i+pasos])
            y.append(scaled[i+pasos])
        X = np.array(X)
        y = np.array(y)
        if X.ndim == 2:
            X = X.reshape((X.shape[0], X.shape[1], 1))
        if y.ndim == 1:
            y = y.reshape(-1, 1)
        return X, y, scaler
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="preparar_datos_lstm")
        return np.array([]), np.array([]), None

# ==========================================================
# LSTM: entrenar y guardar
# ==========================================================
def entrenar_y_guardar_modelo(df: pd.DataFrame, pasos: int = 20, epochs: int = 15, batch_size: int = 32, activo: Optional[str] = None) -> Tuple[Optional[Any], Optional[MinMaxScaler]]:
    """
    Entrena un LSTM simple y guarda modelo + scaler.
    Retorna (model, scaler) o (None, None).
    """
    try:
        if not _HAS_TF:
            log_warning("TensorFlow no disponible: no se puede entrenar LSTM", archivo="model_trainer.py", funcion="entrenar_y_guardar_modelo")
            return None, None

        X, y, scaler = preparar_datos_lstm(df, pasos=pasos)
        if X.size == 0 or y.size == 0 or scaler is None:
            return None, None

        # Modelo sencillo y económico para entrenamiento frecuente
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
        model = Sequential([
            Input(shape=(pasos, 1)),
            LSTM(64, return_sequences=True),
            Dropout(0.15),
            LSTM(32),
            Dropout(0.15),
            Dense(1, activation="linear")
        ])
        model.compile(optimizer="adam", loss="mse")
        # Early stopping para evitar sobreentrenar y gastar CPU
        callbacks = [EarlyStopping(monitor="loss", patience=4, restore_best_weights=True)]
        model.fit(X, y, epochs=epochs, batch_size=batch_size, verbose=0, callbacks=callbacks)

        # Guardar
        path = _lstm_path(activo)
        try:
            model.save(str(path), overwrite=True)
            guardar_scaler(activo or "GEN", scaler)
            log_info(f"Modelo LSTM guardado: {path}", archivo="model_trainer.py", funcion="entrenar_y_guardar_modelo")
        except Exception as e:
            log_warning(f"Error guardando LSTM: {e}", archivo="model_trainer.py", funcion="entrenar_y_guardar_modelo")

        return model, scaler
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="entrenar_y_guardar_modelo")
        return None, None

def cargar_modelo_lstm(activo: Optional[str], compile_model: bool = False):
    """
    Carga un modelo LSTM guardado (si existe).
    """
    try:
        if not _HAS_TF:
            return None
        p = _lstm_path(activo)
        if p.exists():
            return load_model(str(p), compile=compile_model)
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="cargar_modelo_lstm")
    return None

# ==========================================================
# ML: features builder (simple). Puedes mejorar aquí.
# ==========================================================
def construir_features_ml(df: pd.DataFrame, pasos_feat: int = 20) -> Optional[pd.DataFrame]:
    """
    Retorna DataFrame con features para ML (window-based).
    - features: returns, slope, ma_short, ma_long, vol_mean
    """
    try:
        if df is None or df.empty or "close" not in df.columns:
            return None
        close = df["close"].astype(float)
        vol = df["volume"].astype(float) if "volume" in df.columns else pd.Series(np.zeros(len(close)))
        rows = []
        for i in range(pasos_feat, len(df)):
            window = close.iloc[i-pasos_feat:i]
            if window.isna().any():
                continue
            ret = (window.iloc[-1] - window.iloc[0]) / (window.iloc[0] + 1e-9)
            ma5 = window.tail(5).mean()
            ma20 = window.mean()
            slope = (ma5 - ma20) / (ma20 + 1e-9)
            vol_mean = vol.iloc[i-pasos_feat:i].mean()
            rows.append({
                "ret": ret, "slope": slope, "ma5": ma5, "ma20": ma20, "vol_mean": vol_mean,
                "target": 1 if close.iloc[i] > close.iloc[i-1] else 0
            })
        if not rows:
            return None
        return pd.DataFrame(rows).dropna()
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="construir_features_ml")
        return None

# ==========================================================
# ML: entrenar RF / XGB rápidos (no heavy)
# ==========================================================
def entrenar_ml_models(df_features: pd.DataFrame, activo: Optional[str], quick_params: Dict[str, Any] = None) -> Dict[str, Optional[Any]]:
    """
    Entrena RandomForest y XGBoost si están disponibles.
    Guarda modelos en modelos_entrenados/ml/.
    Retorna dict {'rf': obj or None, 'xgb': obj or None, 'scores': {...}}
    """
    resultados = {"rf": None, "xgb": None, "scores": {}}
    try:
        if df_features is None or df_features.empty:
            log_warning("entrenar_ml_models: features vacíos", archivo="model_trainer.py", funcion="entrenar_ml_models")
            return resultados

        quick_params = quick_params or {}
        X = df_features[["ret", "slope", "ma5", "ma20", "vol_mean"]].values
        y = df_features["target"].values

        # train-test split
        if len(X) < 30:
            log_warning("entrenar_ml_models: pocas filas (<30) — entrenamiento ML saltado", archivo="model_trainer.py", funcion="entrenar_ml_models")
            return resultados

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, shuffle=False)

        # RandomForest
        if _HAS_SK:
            try:
                rf = RandomForestClassifier(n_estimators=50, max_depth=6, random_state=42)
                rf.fit(X_train, y_train)
                preds = rf.predict(X_test)
                acc = float(accuracy_score(y_test, preds))
                joblib.dump(rf, str(_ml_path(activo, "rf")))
                resultados["rf"] = rf
                resultados["scores"]["rf_acc"] = acc
                log_info(f"RF entrenado y guardado ({activo}) acc={acc:.3f}", archivo="model_trainer.py", funcion="entrenar_ml_models")
            except Exception as e:
                log_warning(f"RF falló: {e}", archivo="model_trainer.py", funcion="entrenar_ml_models")

        # XGBoost (sklearn wrapper si disponible)
        if _HAS_XGB:
            try:
                xparams = quick_params.get("xgb", {})
                xgbm = XGBClassifier(n_estimators=50, max_depth=4, use_label_encoder=False, eval_metric="logloss", **xparams)
                xgbm.fit(X_train, y_train)
                preds = xgbm.predict(X_test)
                acc = float(accuracy_score(y_test, preds))
                joblib.dump(xgbm, str(_ml_path(activo, "xgb")))
                resultados["xgb"] = xgbm
                resultados["scores"]["xgb_acc"] = acc
                log_info(f"XGB entrenado y guardado ({activo}) acc={acc:.3f}", archivo="model_trainer.py", funcion="entrenar_ml_models")
            except Exception as e:
                log_warning(f"XGB falló: {e}", archivo="model_trainer.py", funcion="entrenar_ml_models")

        return resultados
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="entrenar_ml_models")
        return resultados

# ==========================================================
# Función principal: actualizar_modelo_dinamico
# - Entrena LSTM si no existe, intenta reentrenar incrementalmente
# - Entrena ML models si hay features
# Retorna: dict con detalles y métricas
# ==========================================================
def actualizar_modelo_dinamico(df: pd.DataFrame, activo: str, resumen: str = "", pasos: int = 20) -> Dict[str, Any]:
    """
    Actualiza (o crea) modelos LSTM y ML para un activo dado, usando datos df (OHLCV).
    Retorna dict con:
      { 'lstm_model': model or None, 'scaler': scaler or None,
        'ml': {'rf':..., 'xgb':...}, 'base_conf': float, 'consistencia': float, 'boosted': bool }
    """
    out = {
        "activo": _norm_activo(activo),
        "lstm_model": None,
        "scaler": None,
        "ml": {},
        "base_conf": 0.0,
        "consistencia": 0.0,
        "boosted": False,
        "detalles": {}
    }
    try:
        sym = _norm_activo(activo)
        # 1) LSTM: cargar o entrenar si no existe
        model = cargar_modelo_lstm(sym, compile_model=False)
        scaler = cargar_scaler(sym)
        if model is None or scaler is None:
            log_info(f"No existe modelo previo para {sym}. Entrenando nuevo...", archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")
            model, scaler = entrenar_y_guardar_modelo(df, pasos=pasos, epochs=10, batch_size=16, activo=sym)
            if model is None:
                log_warning(f"Entrenamiento LSTM no produjo modelo para {sym}", archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")
        else:
            # Intento de re-entrenamiento ligero (compilar antes de fit)
            try:
                if _HAS_TF:
                    model.compile(optimizer="adam", loss="mse")
                    X, y, _ = preparar_datos_lstm(df, pasos=pasos)
                    if X.size and y.size:
                        model.fit(X, y, epochs=2, batch_size=16, verbose=0)
                        model.save(str(_lstm_path(sym)), overwrite=True)
                        guardar_scaler(sym, scaler)
                        log_info(f"Reentrenamiento LSTM ligero completado para {sym}", archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")
            except Exception as e:
                log_warning(f"Reentrenamiento LSTM falló: {e}", archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")

        out["lstm_model"] = model
        out["scaler"] = scaler

        # 2) ML: construir features y entrenar ML models si hay suficiente data
        df_feats = construir_features_ml(df, pasos_feat=20)
        if df_feats is not None and not df_feats.empty:
            ml_res = entrenar_ml_models(df_feats, activo=sym)
            out["ml"] = ml_res
        else:
            out["ml"] = {"rf": None, "xgb": None, "scores": {}}

        # 3) Estimar base_conf y consistencia preliminar (heurística)
        # - base_conf: usar varianza de predicciones LSTM si disponible
        base_conf = 0.0
        consistencia = 0.0
        try:
            if model is not None and scaler is not None:
                # usar últimas predicciones rápidas para estimar confianza
                vals = df[["close"]].dropna().values.astype(float)
                if len(vals) >= pasos:
                    scaled = scaler.transform(vals)
                    ult = scaled[-pasos:].reshape((1, pasos, 1))
                    preds = []
                    for _ in range(4):
                        p = model.predict(ult, verbose=0)
                        preds.append(float(p[0, 0]))
                        ult = np.concatenate([ult[:,1:,:], np.array(p).reshape((1,1,1))], axis=1)
                    preds = np.array(preds)
                    var = float(np.var(preds))
                    slope = float(np.mean(np.diff(preds)))
                    conf_var = max(0.0, 1.0 - min(var / (abs(np.mean(preds)) + 1e-9), 1.0))
                    conf_slope = min(1.0, min(abs(slope) / (abs(np.mean(preds)) + 1e-9), 1.0)*2)
                    base_conf = float(np.clip(0.45*conf_var + 0.55*conf_slope, 0.0, 1.0))
                    consistencia = 1.0 - float(np.std(preds))  # heurística
        except Exception as e:
            log_warning(f"Estimación base_conf falló: {e}", archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")

        out["base_conf"] = round(float(base_conf), 6)
        out["consistencia"] = float(np.clip(consistencia, 0.0, 1.0))

        out["detalles"]["resumen"] = resumen
        out["detalles"]["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_info(f"Modelo dinámico actualizado para {sym} — base_conf={out['base_conf']*100:.2f}% cons={out['consistencia']:.3f}",
                 archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")

        return out
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="actualizar_modelo_dinamico")
        return out

# ==========================================================
# Función de alto nivel para scheduler
# ==========================================================
def actualizar_modelos_en_vivo(df: pd.DataFrame, activo: str, resumen: str = "") -> Dict[str, Any]:
    """
    Interfaz amigable para train_scheduler.py — devuelve métricas clave para logs.
    """
    try:
        res = actualizar_modelo_dinamico(df, activo=activo, resumen=resumen)
        # preparar salida estándar
        salida = {
            "activo": res.get("activo", activo),
            "confianza": float(res.get("base_conf", 0.0)),
            "consistencia": float(res.get("consistencia", 0.0)),
            "boosted": bool(res.get("boosted", False)),
            "detalles": res.get("detalles", {})
        }
        return salida
    except Exception as e:
        log_error(e, archivo="model_trainer.py", funcion="actualizar_modelos_en_vivo")
        return {"activo": activo, "confianza": 0.0, "consistencia": 0.0, "boosted": False, "detalles": {}}
