# utils/entrenamiento.py
# ==========================================================
# Versión extendida y robusta de herramientas de entrenamiento
# - Descarga y fallback (Binance)
# - Enriquecimiento con indicadores técnicos
# - Pipeline para LSTM + RandomForest (ensemble)
# - Evaluación (métricas clásicas + evaluación económica simple)
# - Guardado/carga de modelos y scalers
# - Utilidades para reentrenar por lotes
# ==========================================================

import os
import math
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
import time
import numpy as np
import pandas as pd
import joblib

# sklearn / tf
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

try:
    import tensorflow as tf
    from tensorflow.keras import models, layers, callbacks
except Exception:
    tf = None  # se maneja en funciones que lo necesiten

# Internals del proyecto (intentar mantener compatibilidad)
from utils.data_fetcher import (
    obtener_datos_bin,
    fetch_binance_spot,
    add_pivot_points,
    add_ichimoku,
    add_obv,
    add_vwap,
    load_local_csv,
    _normalize_df
)

# utils.modelo puede contener helpers de guardado que ya uses
try:
    from utils.modelo import (
        _norm_activo,
        guardar_scaler as guardar_scaler_modelo,
        cargar_scaler as cargar_scaler_modelo,
        entrenar_y_guardar_modelo
    )
except Exception:
    # funciones fallback si no existen; se implementan mínimas aquí
    def _norm_activo(sym: str) -> str:
        return str(sym).upper().replace("/", "_")

    def guardar_scaler_modelo(sym: str, scaler):
        p = Path("modelos_entrenados")
        p.mkdir(exist_ok=True)
        joblib.dump(scaler, p / f"{sym}_scaler.joblib")

    def cargar_scaler_modelo(sym: str):
        p = Path("modelos_entrenados") / f"{sym}_scaler.joblib"
        return joblib.load(p) if p.exists() else None

    entrenar_y_guardar_modelo = None

from utils.logger import log_info, log_warning, log_error

# Directorio modelos
MODELOS_DIR = Path("modelos_entrenados")
MODELOS_DIR.mkdir(exist_ok=True)

# ----------------------------------------------------------
# Utilidades: métricas y reporting
# ----------------------------------------------------------
def _metrics_bin(y_true, y_pred, y_prob=None):
    try:
        acc = accuracy_score(y_true, y_pred)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        auc = None
        if y_prob is not None and len(np.unique(y_true)) > 1:
            try:
                auc = roc_auc_score(y_true, y_prob)
            except Exception:
                auc = None
        return {"acc": acc, "prec": prec, "rec": rec, "f1": f1, "auc": auc}
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="_metrics_bin")
        return {}

# ----------------------------------------------------------
# Descarga datos (compatibilidad / fallback)
# ----------------------------------------------------------
def descargar_datos_binance(symbol="BTCUSDT", interval="1h", limit=1000, api_key=None, api_secret=None):
    """
    Descarga velas OHLCV desde Binance si Client disponible.
    Si falla, intenta usar fetch_binance_spot (API pública).
    Retorna DataFrame normalizado con index DatetimeIndex UTC.
    """
    try:
        # preferir wrapper obtener_datos_bin (usa API oficial si hay keys)
        try:
            df = obtener_datos_bin(symbol, interval=interval, lookback=f"{max(30, int(limit/24))}d")
            if df is not None and not df.empty:
                return _normalize_df(df).tail(limit)
        except Exception:
            pass

        # fallback público (requests)
        df = fetch_binance_spot(symbol, interval=interval, min_rows=min(limit, 1000))
        if df is None or df.empty:
            return pd.DataFrame()
        return _normalize_df(df).tail(limit)

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="descargar_datos_binance")
        return pd.DataFrame()


# ----------------------------------------------------------
# Enriquecimiento de features (robusto y estable)
# ----------------------------------------------------------
def agregar_indicadores_extra(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega un conjunto útil de indicadores técnicos:
    RSI, EMA, SMA, Bollinger, CCI, OBV, CMF, Momentum, VWAP, Pivot Points, Ichimoku parcial.
    """
    try:
        if df is None or df.empty:
            return df

        df = df.copy()
        # asegurar tipos
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

        # RSI (14)
        delta = df["close"].diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rs = up / down.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))
        df["rsi_14"] = df["rsi_14"].fillna(50)

        # SMA / EMA
        df["sma_20"] = df["close"].rolling(20).mean()
        df["ema_10"] = df["close"].ewm(span=10, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

        # Bollinger
        std20 = df["close"].rolling(20).std()
        df["bollinger_mid"] = df["sma_20"]
        df["bollinger_up"] = df["sma_20"] + 2 * std20
        df["bollinger_low"] = df["sma_20"] - 2 * std20

        # CCI (20)
        tp = (df["high"] + df["low"] + df["close"]) / 3
        ma_tp = tp.rolling(20).mean()
        md_tp = (tp - ma_tp).abs().rolling(20).mean()
        df["cci_20"] = (tp - ma_tp) / (0.015 * md_tp.replace(0, np.nan))

        # OBV
        df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()

        # CMF (20)
        denom = (df["high"] - df["low"]).replace(0, np.nan)
        mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / denom
        mfv = mfm * df["volume"]
        df["cmf_20"] = mfv.rolling(20).sum() / df["volume"].rolling(20).sum()

        # Momentum
        df["momentum_4"] = df["close"].diff(4)

        # VWAP (rolling intraday approximate)
        typical = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap_14"] = (typical * df["volume"]).rolling(14).sum() / df["volume"].rolling(14).sum()

        # Pivot points (diarios) - helper simple
        try:
            piv = (df["high"].shift(1) + df["low"].shift(1) + df["close"].shift(1)) / 3
            df["pivot"] = piv
            df["r1"] = 2 * piv - df["low"].shift(1)
            df["s1"] = 2 * piv - df["high"].shift(1)
        except Exception:
            pass

        # Ichimoku minimal (tenkan/kijun)
        try:
            df["tenkan"] = (df["high"].rolling(9).max() + df["low"].rolling(9).min()) / 2
            df["kijun"] = (df["high"].rolling(26).max() + df["low"].rolling(26).min()) / 2
        except Exception:
            pass

        # limpiar
        df = df.fillna(method="ffill").fillna(method="bfill").fillna(0)
        return df

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="agregar_indicadores_extra")
        return df


# ----------------------------------------------------------
# Preparación dataset supervisado (features + target)
# ----------------------------------------------------------
def preparar_dataset(df: pd.DataFrame, feature_cols: list = None, horizon: int = 1):
    """
    Prepara X (DataFrame) y y (Series) para clasificación binaria:
    target = 1 si close(t+horizon) > close(t) else 0.
    feature_cols: lista de columnas a usar (si None, se auto-eligen).
    """
    try:
        if df is None or df.empty:
            raise ValueError("DataFrame vacío")

        df = df.copy()
        df["future_close"] = df["close"].shift(-horizon)
        df["target"] = (df["future_close"] > df["close"]).astype(int)
        df = df.dropna(subset=["target"])

        if feature_cols is None:
            # heurística: usar indicadores agregados y lagged returns
            candidates = [c for c in df.columns if c not in ("future_close", "target")]
            # preferir indicadores comunes
            prefer = ["rsi_14", "ema_10", "ema_50", "sma_20", "cci_20", "obv", "cmf_20", "momentum_4", "vwap_14", "pivot", "tenkan", "kijun"]
            feature_cols = [c for c in prefer if c in candidates]
            # añadir retornos y volumen si no están
            for extra in ["close", "volume"]:
                if extra in candidates and extra not in feature_cols:
                    feature_cols.append(extra)

        X = df[feature_cols].astype(float).copy()
        y = df["target"].astype(int).copy()
        return X, y

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="preparar_dataset")
        return pd.DataFrame(), pd.Series(dtype=int)


# ----------------------------------------------------------
# LSTM training helper (sequence -> predict direction)
# ----------------------------------------------------------
def entrenar_lstm(df: pd.DataFrame, pasos: int = 24, epochs: int = 30, batch_size: int = 32,
                  modelo_path: str = None, verbose: int = 0):
    """
    Entrena un LSTM simple sobre la serie de precios (close) normalizada.
    Retorna (modelo, scaler). Guarda el modelo si modelo_path provisto.
    """
    try:
        if tf is None:
            raise RuntimeError("TensorFlow no disponible; instala tensorflow para entrenar LSTM")

        if df is None or df.empty or "close" not in df.columns:
            raise ValueError("Data insuficiente para LSTM")

        # normalizar close
        scaler = MinMaxScaler()
        closes = df[["close"]].astype(float).values
        scaled = scaler.fit_transform(closes)

        # crear secuencias y labels: predecir subida/bajada en next step
        X, y = [], []
        for i in range(len(scaled) - pasos - 1):
            seq = scaled[i: i + pasos]
            target = 1 if (scaled[i + pasos + 0][0] > scaled[i + pasos - 1][0]) else 0
            X.append(seq)
            y.append(target)

        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)
        if X.size == 0:
            raise ValueError("Secuencias insuficientes para LSTM (incrementa 'pasos' o baja limit)")

        X = X.reshape((X.shape[0], X.shape[1], 1))

        # modelo
        model = models.Sequential([
            layers.Input(shape=(X.shape[1], X.shape[2])),
            layers.LSTM(64, return_sequences=True),
            layers.Dropout(0.2),
            layers.LSTM(32),
            layers.Dropout(0.2),
            layers.Dense(16, activation="relu"),
            layers.Dense(1, activation="sigmoid")
        ])
        model.compile(optimizer="adam", loss="binary_crossentropy", metrics=["accuracy"])

        es = callbacks.EarlyStopping(monitor="val_loss", patience=8, restore_best_weights=True, verbose=1)
        rl = callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=4, min_lr=1e-6, verbose=1)

        model.fit(X, y, validation_split=0.1, epochs=epochs, batch_size=batch_size, callbacks=[es, rl], verbose=verbose)

        if modelo_path:
            try:
                model.save(modelo_path)
                log_info(f"LSTM guardado en {modelo_path}", archivo="entrenamiento.py", funcion="entrenar_lstm")
            except Exception as e:
                log_warning(f"No se pudo guardar LSTM: {e}", archivo="entrenamiento.py", funcion="entrenar_lstm")

        return model, scaler

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="entrenar_lstm")
        return None, None


# ----------------------------------------------------------
# RandomForest training helper
# ----------------------------------------------------------
def entrenar_random_forest(X: pd.DataFrame, y: pd.Series, n_estimators: int = 200, max_depth: int = 8):
    try:
        if X is None or X.empty:
            raise ValueError("X vacío para RandomForest")
        rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, n_jobs=-1, random_state=42)
        rf.fit(X, y)
        return rf
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="entrenar_random_forest")
        return None


# ----------------------------------------------------------
# Ensemble pipeline (entrenar + evaluar)
# ----------------------------------------------------------
def entrenar_ensemble(df: pd.DataFrame, activo: str,
                      feature_cols: list = None,
                      horizon: int = 1,
                      test_size: float = 0.2,
                      rf_params: dict = None,
                      lstm_params: dict = None):
    """
    Pipeline que:
    - prepara dataset (para horizon)
    - entrena RandomForest (sobre features tabulares)
    - entrena LSTM (sobre secuencias precio)
    - devuelve dict con modelos, scalers y métricas
    """
    try:
        if rf_params is None:
            rf_params = {"n_estimators": 200, "max_depth": 8}
        if lstm_params is None:
            lstm_params = {"pasos": 24, "epochs": 20, "batch_size": 32, "verbose": 0}

        # enriquecer
        df_en = agregar_indicadores_extra(df)

        # preparar X,y con horizon
        X_all, y_all = preparar_dataset(df_en, feature_cols, horizon)
        if X_all.empty or y_all.empty:
            log_warning("Dataset vacío tras preparar_dataset", archivo="entrenamiento.py", funcion="entrenar_ensemble")
            return None, {"error": "empty_dataset"}

        # split por tiempo (mantener orden temporal)
        split_idx = int(len(X_all) * (1 - test_size))
        X_train = X_all.iloc[:split_idx]
        X_test = X_all.iloc[split_idx:]
        y_train = y_all.iloc[:split_idx]
        y_test = y_all.iloc[split_idx:]

        # normalizar features para RF (fit en train)
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # entrenar RF
        rf = entrenar_random_forest(pd.DataFrame(X_train_scaled, columns=X_train.columns), y_train, **rf_params)

        # preparar secuencias para LSTM (usar close y mismo split)
        pasos = int(lstm_params.get("pasos", 24))
        # construir arrays X_seq_train/X_seq_test a partir de df_en (alineando con índice de X_train/X_test)
        # método: reconstruir a partir de df_en ordenado y tomar filas correspondientes
        df_en_sorted = df_en.reset_index(drop=True)
        # crear array de closes
        closes = df_en_sorted["close"].astype(float).values
        # construir X_seq full then split using same index boundaries as X_train/X_test
        # para simplicidad tomamos la porción correspondiente a X_train.index (posiciones)
        # Nota: indices de X_train se corresponden a df_en rows desde 0 (porque preparar_dataset no reindexó)
        # Para mayor robustez, trabajamos con posiciones:
        pos_train_end = X_train.index[-1]
        pos_test_start = X_test.index[0] if len(X_test.index) > 0 else pos_train_end + 1

        # build sequences function
        def build_sequences_from_close(close_arr, pasos, start_pos, end_pos):
            Xs = []
            ys = []
            for i in range(start_pos, end_pos - pasos):
                seq = close_arr[i: i + pasos]
                # binary label next step
                label = 1 if close_arr[i + pasos] > close_arr[i + pasos - 1] else 0
                Xs.append(seq.reshape(-1, 1))
                ys.append(label)
            return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.int32)

        # try to derive positions robustly
        total_len = len(df_en_sorted)
        # fallback: use ends based on lengths
        try:
            # approximate positions
            train_len = len(X_train)
            test_len = len(X_test)
            # create full sliding windows, then split by counts
            X_seq_full = []
            y_seq_full = []
            for i in range(0, total_len - pasos - 1):
                seq = closes[i: i + pasos]
                label = 1 if closes[i + pasos] > closes[i + pasos - 1] else 0
                X_seq_full.append(seq.reshape(-1, 1))
                y_seq_full.append(label)
            X_seq_full = np.array(X_seq_full, dtype=np.float32)
            y_seq_full = np.array(y_seq_full, dtype=np.int32)
            # split corresponding counts aligned with earlier split ratio
            split_seq_idx = int(len(X_seq_full) * (1 - test_size))
            X_seq_train = X_seq_full[:split_seq_idx]
            y_seq_train = y_seq_full[:split_seq_idx]
            X_seq_test = X_seq_full[split_seq_idx:]
            y_seq_test = y_seq_full[split_seq_idx:]
        except Exception:
            # último recurso: vacíos
            X_seq_train = X_seq_test = np.array([])
            y_seq_train = y_seq_test = np.array([])

        # scale sequences (per-step) using MinMaxScalar fitted on closes of train
        scaler_close = MinMaxScaler()
        try:
            # flatten sequences to fit scaler
            if X_seq_train.size:
                flat = X_seq_train.reshape(-1, 1)
                scaler_close.fit(flat)
                X_seq_train_flat = scaler_close.transform(flat).reshape(X_seq_train.shape)
                X_seq_test_flat = scaler_close.transform(X_seq_test.reshape(-1, 1)).reshape(X_seq_test.shape) if X_seq_test.size else X_seq_test
                X_seq_train = X_seq_train_flat
                X_seq_test = X_seq_test_flat
        except Exception:
            pass

        # Entrenar LSTM rápido si hay datos
        lstm_model = None
        try:
            if tf is not None and X_seq_train.size:
                lstm_model, lstm_scaler = entrenar_lstm(
                    pd.DataFrame({"close": closes}), pasos=pasos,
                    epochs=int(lstm_params.get("epochs", 20)),
                    batch_size=int(lstm_params.get("batch_size", 32)),
                    modelo_path=None, verbose=int(lstm_params.get("verbose", 0))
                )
            else:
                lstm_model = None
                lstm_scaler = None
        except Exception as e:
            log_warning(f"No se entrenó LSTM: {e}", archivo="entrenamiento.py", funcion="entrenar_ensemble")

        # Predicciones y evaluación
        # RF predict (usar X_test_scaled)
        y_pred_rf = None; y_prob_rf = None
        if rf is not None and X_test_scaled is not None:
            try:
                y_prob_rf = rf.predict_proba(X_test_scaled)[:, 1]
                y_pred_rf = (y_prob_rf >= 0.5).astype(int)
            except Exception:
                y_pred_rf = None

        # LSTM predict (usar X_seq_test -> prob)
        y_pred_lstm = None; y_prob_lstm = None
        if lstm_model is not None and X_seq_test.size:
            try:
                preds = lstm_model.predict(X_seq_test, verbose=0)
                y_prob_lstm = preds.ravel()
                y_pred_lstm = (y_prob_lstm >= 0.5).astype(int)
            except Exception:
                y_pred_lstm = None

        # Ensemble: promedio de probabilidades (cuando ambos existan)
        y_prob_ens = None; y_pred_ens = None
        # Align lengths: X_test snapshots vs X_seq_test number may differ; we compare on the common suffix length
        try:
            # choose minimal length available for y_test comparison
            common_len = None
            if y_test is not None:
                common_len = len(y_test)
            # create best-effort aligned arrays (this is heuristic; for production align indices strictly)
            probs = []
            if y_prob_rf is not None:
                probs.append(y_prob_rf[-common_len:] if common_len is not None and len(y_prob_rf) >= common_len else y_prob_rf)
            if y_prob_lstm is not None:
                probs.append(y_prob_lstm[-common_len:] if common_len is not None and len(y_prob_lstm) >= common_len else y_prob_lstm)
            if probs:
                minlen = min(len(p) for p in probs)
                probs_trim = [p[-minlen:] for p in probs]
                y_prob_ens = np.mean(np.vstack(probs_trim), axis=0)
                y_pred_ens = (y_prob_ens >= 0.5).astype(int)
                # trim y_test to minlen
                y_test_trim = y_test.iloc[-minlen:]
            else:
                y_test_trim = y_test
        except Exception:
            y_test_trim = y_test

        # calcular métricas sobre la mejor alineación disponible
        metrics_rf = _metrics_bin(y_test_trim, y_pred_rf[-len(y_test_trim):] if (y_pred_rf is not None and len(y_pred_rf) >= len(y_test_trim)) else np.zeros(len(y_test_trim), dtype=int), y_prob_rf[-len(y_test_trim):] if y_prob_rf is not None else None) if rf else {}
        metrics_lstm = _metrics_bin(y_test_trim, y_pred_lstm[-len(y_test_trim):] if (y_pred_lstm is not None and len(y_pred_lstm) >= len(y_test_trim)) else np.zeros(len(y_test_trim), dtype=int), y_prob_lstm[-len(y_test_trim):] if y_prob_lstm is not None else None) if lstm_model else {}
        metrics_ens = _metrics_bin(y_test_trim, y_pred_ens[-len(y_test_trim):] if (y_pred_ens is not None and len(y_pred_ens) >= len(y_test_trim)) else np.zeros(len(y_test_trim), dtype=int), y_prob_ens[-len(y_test_trim):] if y_prob_ens is not None else None) if y_prob_ens is not None else {}

        resultado = {
            "rf": {"model": rf, "metrics": metrics_rf},
            "lstm": {"model": lstm_model, "metrics": metrics_lstm},
            "ensemble": {"prob": y_prob_ens, "pred": y_pred_ens, "metrics": metrics_ens},
            "scalers": {"features_scaler": scaler, "close_scaler": (scaler_close if 'scaler_close' in locals() else None)},
            "feature_cols": X_all.columns.tolist(),
            "horizon": horizon
        }

        log_info(f"entrenar_ensemble -> terminado activo={activo}, horizon={horizon}", archivo="entrenamiento.py", funcion="entrenar_ensemble")
        return resultado, {"rf": metrics_rf, "lstm": metrics_lstm, "ens": metrics_ens}

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="entrenar_ensemble")
        return None, {"error": str(e)}


# ----------------------------------------------------------
# Guardado y carga de modelos (con paths versionados)
# ----------------------------------------------------------
def guardar_modelo(model, activo: str, kind: str = "lstm"):
    """
    Guarda un modelo (LSTM o sklearn) en modelos_entrenados con timestamp.
    kind: 'lstm'|'rf'|'scaler'
    """
    try:
        sym = _norm_activo(activo)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        if kind == "lstm":
            path = MODELOS_DIR / f"{sym}_lstm_{ts}.keras"
            model.save(path)
            return str(path)
        elif kind == "rf":
            path = MODELOS_DIR / f"{sym}_rf_{ts}.joblib"
            joblib.dump(model, path)
            return str(path)
        elif kind == "scaler":
            path = MODELOS_DIR / f"{sym}_scaler_{ts}.joblib"
            joblib.dump(model, path)
            return str(path)
        else:
            raise ValueError("kind desconocido")
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="guardar_modelo")
        return None


def cargar_model_rf(path_or_activo):
    try:
        if isinstance(path_or_activo, (str, Path)) and Path(path_or_activo).exists():
            return joblib.load(path_or_activo)
        # buscar por patrón en MODELOS_DIR
        p = MODELOS_DIR
        cand = sorted(list(p.glob(f"{str(path_or_activo).upper()}*_rf_*.joblib")), reverse=True)
        if cand:
            return joblib.load(cand[0])
        return None
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="cargar_model_rf")
        return None


def cargar_model_lstm(path_or_activo):
    try:
        if tf is None:
            log_warning("TF no disponible; no se puede cargar LSTM", archivo="entrenamiento.py", funcion="cargar_model_lstm")
            return None
        if isinstance(path_or_activo, (str, Path)) and Path(path_or_activo).exists():
            return models.load_model(path_or_activo)
        p = MODELOS_DIR
        cand = sorted(list(p.glob(f"{str(path_or_activo).upper()}*_lstm_*.keras")), reverse=True)
        if cand:
            return models.load_model(cand[0])
        return None
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="cargar_model_lstm")
        return None


# ----------------------------------------------------------
# Evaluación sencilla "económica" (simulación rápida)
# ----------------------------------------------------------
def simular_estrategia_from_preds(df: pd.DataFrame, preds: np.ndarray, notional: float = 10.0, sl_pct: float = 0.02, tp_pct: float = 0.02):
    """
    Simula muy simplificado: si pred==1 -> abrir position BUY con notional USDT, cerrar next candle.
    Calcula PnL simple (no fees). Devuelve sum PnL en USDT y número de trades.
    """
    try:
        if df is None or df.empty or preds is None:
            return {"pnl": 0.0, "trades": 0}

        # align preds to df tail (assume preds aligned to last N rows)
        n = len(preds)
        prices = df["close"].astype(float).values[-n:]
        pnl = 0.0
        trades = 0
        for i, p in enumerate(preds):
            if p == 1:
                entry = prices[i]
                # naive exit next candle (if exists)
                exitp = prices[i + 1] if (i + 1) < len(prices) else prices[i]
                ret = (exitp - entry) / entry
                pnl += notional * ret
                trades += 1
        return {"pnl": pnl, "trades": trades}
    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="simular_estrategia_from_preds")
        return {"pnl": 0.0, "trades": 0}


# ----------------------------------------------------------
# High-level wrappers (compatibilidad con train_binance.py)
# ----------------------------------------------------------
def entrenar_modelo(df: pd.DataFrame, activo: str,
                    pasos: int = 24, futuros: int = 1,
                    epochs: int = 20, batch_size: int = 32,
                    horizon: int = 1):
    """
    Wrapper para entrenar ensemble y guardar artefactos.
    """
    try:
        log_info(f"Iniciando entrenar_modelo for {activo}", archivo="entrenamiento.py", funcion="entrenar_modelo")
        resultado, metrics = entrenar_ensemble(df, activo, feature_cols=None, horizon=horizon,
                                               rf_params=None,
                                               lstm_params={"pasos": pasos, "epochs": epochs, "batch_size": batch_size, "verbose": 0})
        if resultado is None:
            log_warning("No se entrenó resultado", archivo="entrenamiento.py", funcion="entrenar_modelo")
            return None

        # guardar artefactos: RF, LSTM (si exis), scalers
        rf_model = resultado.get("rf", {}).get("model")
        lstm_model = resultado.get("lstm", {}).get("model") if resultado.get("lstm") else None
        scalers = resultado.get("scalers", {})

        paths = {}
        if rf_model is not None:
            p_rf = guardar_modelo(rf_model, activo, kind="rf")
            paths["rf"] = p_rf
        if lstm_model is not None:
            p_lstm = guardar_modelo(lstm_model, activo, kind="lstm")
            paths["lstm"] = p_lstm
        if scalers.get("features_scaler") is not None:
            p_s = guardar_modelo(scalers["features_scaler"], activo, kind="scaler")
            paths["scaler"] = p_s

        log_info(f"Entrenamiento completo. Paths: {paths}", archivo="entrenamiento.py", funcion="entrenar_modelo")
        return {"resultado": resultado, "metrics": metrics, "paths": paths}

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="entrenar_modelo")
        return None


def evaluar_modelo(df: pd.DataFrame, activo: str, horizon: int = 1):
    """
    Carga últimos modelos guardados (RF/LSTM), corre predicciones sobre df y devuelve resumen.
    """
    try:
        # cargar modelos
        rf = cargar_model_rf(activo)
        lstm = cargar_model_lstm(activo)

        df_en = agregar_indicadores_extra(df)
        X, y = preparar_dataset(df_en, None, horizon=horizon)
        if X.empty:
            return {"accion": "hold", "precision": 0.0, "detalle": "no_data"}

        scaler = None
        # cargar scaler si existe
        try:
            scaler = cargar_scaler_modelo(_norm_activo(activo))
        except Exception:
            scaler = None

        # RF
        y_prob_rf = None; y_pred_rf = None
        if rf is not None:
            try:
                Xs = X.copy()
                if scaler is not None:
                    Xs = scaler.transform(Xs)
                y_prob_rf = rf.predict_proba(Xs)[:, 1]
                y_pred_rf = (y_prob_rf >= 0.5).astype(int)
            except Exception:
                pass

        # LSTM: construir secuencias desde df (simple)
        y_prob_lstm = None; y_pred_lstm = None
        if lstm is not None and tf is not None:
            try:
                pasos = lstm.input_shape[1]
                closes = df["close"].astype(float).values
                Xs = []
                for i in range(0, len(closes) - pasos - 1):
                    seq = closes[i: i + pasos].reshape(-1, 1)
                    Xs.append(seq)
                if len(Xs) > 0:
                    Xs = np.array(Xs, dtype=np.float32)
                    # if scaler for closes exists try to scale
                    try:
                        close_scaler = cargar_scaler_modelo(_norm_activo(activo))
                        if close_scaler is not None:
                            flat = Xs.reshape(-1, 1)
                            flat_t = close_scaler.transform(flat)
                            Xs = flat_t.reshape(Xs.shape)
                    except Exception:
                        pass
                    preds = lstm.predict(Xs, verbose=0)
                    y_prob_lstm = preds.ravel()
                    y_pred_lstm = (y_prob_lstm >= 0.5).astype(int)
            except Exception:
                pass

        # ensemble average (best effort) on overlapping tail
        probs = []
        if y_prob_rf is not None:
            probs.append(y_prob_rf)
        if y_prob_lstm is not None:
            probs.append(y_prob_lstm)
        if not probs:
            return {"accion": "hold", "precision": 0.0, "detalle": "no_models"}

        # align by truncating to minlen
        minlen = min(len(p) for p in probs)
        probs_trim = [p[-minlen:] for p in probs]
        prob_ens = np.mean(np.vstack(probs_trim), axis=0)
        pred_ens = (prob_ens >= 0.5).astype(int)

        # metrics vs available y (trim)
        y_trim = y.iloc[-minlen:]
        metrics = _metrics_bin(y_trim.values, pred_ens, prob_ens)

        # simulation economic
        sim = simular_estrategia_from_preds(df, pred_ens, notional=10.0)

        return {
            "accion": "buy" if prob_ens[-1] >= 0.5 else "hold",
            "precision": metrics.get("acc", 0.0),
            "metrics": metrics,
            "simulacion": sim
        }

    except Exception as e:
        log_error(e, archivo="entrenamiento.py", funcion="evaluar_modelo")
        return {"accion": "hold", "precision": 0.0, "metrics": {}, "simulacion": {}}


# ----------------------------------------------------------
# Reentrenar por lista de símbolos (batch)
# ----------------------------------------------------------
def reentrenar_periodico(symbols: list, max_epochs: int = 10):
    """
    Reentrena modelos para una lista de symbols:
    - descarga/enriquece
    - llama a entrenar_modelo
    Devuelve dict symbol -> success(bool)
    """
    results = {}
    for s in symbols:
        try:
            log_info(f"Reentrenando {s}", archivo="entrenamiento.py", funcion="reentrenar_periodico")
            df = descargar_datos_binance(s, interval="1h", limit=2000)
            if df is None or df.empty:
                results[s] = False
                continue
            # opción: enrich_symbol_data para descargar Alpha/Twelve
            try:
                _ = enrich_symbol_data(s)
            except Exception:
                pass

            out = entrenar_modelo(df, s, pasos=24, futuros=1, epochs=min(5, max_epochs), batch_size=32)
            results[s] = bool(out)
        except Exception as e:
            log_error(e, archivo="entrenamiento.py", funcion="reentrenar_periodico")
            results[s] = False
    return results


# ----------------------------------------------------------
# Función utilitaria: probar varios horizontes y elegir mejor por F1
# ----------------------------------------------------------
def buscar_mejor_horizon(df: pd.DataFrame, activos: str, horizons=(1,3,6), *, feature_cols=None):
    """
    Ejecuta entrenar_ensemble para varios horizontes y devuelve el mejor por F1 (ensemble.metrics.f1).
    Retorna (mejor_horizon, resultados_por_horizon)
    """
    resultados = {}
    best = None
    best_f1 = -1.0
    for h in horizons:
        try:
            res, metrics = entrenar_ensemble(df, activos, feature_cols=feature_cols, horizon=h)
            f1 = 0.0
            try:
                f1 = metrics.get("ens", {}).get("f1") or 0.0
            except Exception:
                f1 = 0.0
            resultados[h] = {"res": res, "metrics": metrics, "f1": f1}
            if f1 > best_f1:
                best_f1 = f1
                best = h
        except Exception as e:
            log_warning(f"Error en horizon {h}: {e}", archivo="entrenamiento.py", funcion="buscar_mejor_horizon")
            resultados[h] = {"error": str(e)}
    return best, resultados


# ----------------------------------------------------------
# Export public API (lista)
# ----------------------------------------------------------
__all__ = [
    "descargar_datos_binance",
    "agregar_indicadores_extra",
    "preparar_dataset",
    "entrenar_lstm",
    "entrenar_random_forest",
    "entrenar_ensemble",
    "guardar_modelo",
    "cargar_model_rf",
    "cargar_model_lstm",
    "simular_estrategia_from_preds",
    "entrenar_modelo",
    "evaluar_modelo",
    "reentrenar_periodico",
    "buscar_mejor_horizon"
]
