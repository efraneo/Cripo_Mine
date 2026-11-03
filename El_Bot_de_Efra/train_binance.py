# train_binance.py
# ==========================================================
# Entrenamiento robusto: descarga datos, añade indicadores,
# entrena LSTM + RandomForest y guarda modelos.
# ==========================================================

import os
import math
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import tensorflow as tf
from tensorflow.keras import layers, models, callbacks

# Importa tus utilidades (asegúrate que utils/data_fetcher.py está disponible)
from utils.data_fetcher import obtener_datos_bin, add_pivot_points, add_ichimoku, add_obv, add_vwap, _normalize_df
from utils.logger import log_info, log_error

# Config
ACTIVO = os.getenv("TRAIN_ACTIVO", "BNBUSDT")
INTERVALO = os.getenv("TRAIN_INTERVALO", "1h")
LOOKBACK_LIMIT = int(os.getenv("TRAIN_LIMIT", "1500"))
SEQ_LEN = int(os.getenv("SEQ_LEN", "24"))  # longitud secuencia LSTM (p.ej. 24 horas)
TEST_SIZE = float(os.getenv("TEST_SIZE", "0.2"))
RANDOM_STATE = 42
MODEL_DIR = "modelos_entrenados"
os.makedirs(MODEL_DIR, exist_ok=True)


# -------------------------
# Helpers locales
# -------------------------
def label_direction(df: pd.DataFrame, horizon: int = 1):
    """
    Crea etiqueta binaria: 1 si close(t+h) > close(t), 0 otherwise.
    horizon = pasos adelante (en velas).
    """
    df = df.copy()
    df["future_close"] = df["close"].shift(-horizon)
    df["target"] = (df["future_close"] > df["close"]).astype(int)
    df = df.drop(columns=["future_close"])
    return df

def create_lag_features(df: pd.DataFrame, lags=(1,2,3,6,12,24)):
    """Genera diferencias, returns y lags simples para features clásicos."""
    df = df.copy()
    df["ret_1"] = df["close"].pct_change().fillna(0)
    for l in lags:
        df[f"close_lag_{l}"] = df["close"].shift(l)
        df[f"ret_{l}"] = df["close"].pct_change(l).fillna(0)
    return df

def build_sequence_dataset(df: pd.DataFrame, feature_cols: list, seq_len: int, target_col: str):
    """
    Convierte DataFrame en X (n_samples, seq_len, n_features) y y (n_samples,)
    Eliminamos filas con NaNs.
    """
    data = df[feature_cols].values
    targets = df[target_col].values
    X, y = [], []
    for i in range(len(df) - seq_len):
        X.append(data[i:i+seq_len])
        y.append(targets[i+seq_len-1])  # label aligned to end of sequence
    X = np.array(X, dtype=np.float32)
    y = np.array(y, dtype=np.int32)
    return X, y

def build_lstm_model(input_shape, units=64, dropout=0.2):
    model = models.Sequential([
        layers.Input(shape=input_shape),
        layers.LSTM(units, return_sequences=True),
        layers.Dropout(dropout),
        layers.LSTM(max(8, units//2)),
        layers.Dropout(dropout),
        layers.Dense(32, activation="relu"),
        layers.Dropout(dropout),
        layers.Dense(1, activation="sigmoid")
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
                  loss="binary_crossentropy",
                  metrics=["accuracy"])
    return model


# -------------------------
# Pipeline principal
# -------------------------
def main():
    try:
        print(f"📥 Descargando datos: {ACTIVO} {INTERVALO} (limit={LOOKBACK_LIMIT})")
        df = obtener_datos_bin(ACTIVO, interval=INTERVALO, lookback=f"{max(30, int(LOOKBACK_LIMIT/24))}d")
        if df is None or df.empty:
            print("❌ No se obtuvieron datos desde Binance. Revisa conectividad o claves.")
            return

        # Normalizar y asegurar columnas
        df = _normalize_df(df)
        df = df.tail(LOOKBACK_LIMIT).copy()
        df.index = pd.to_datetime(df.index, utc=True)

        # Añadir indicadores técnicos (tus funciones en data_fetcher)
        df = add_pivot_points(df)
        df = add_ichimoku(df)
        df = add_obv(df)
        df = add_vwap(df)

        # Ingeniería de features
        df = create_lag_features(df, lags=(1,2,3,6,12,24))
        # indicadores extra: medias móviles y volátil
        df["ma_10"] = df["close"].rolling(10).mean()
        df["ma_50"] = df["close"].rolling(50).mean()
        df["vol_std_10"] = df["volume"].rolling(10).std()
        df["roc_5"] = df["close"].pct_change(5)
        df = df.fillna(method="ffill").fillna(0)

        # Etiquetado (binario) — predecir 1 vela adelante
        df = label_direction(df, horizon=1)

        # Features a usar (evitar usar raw datetime/index)
        feature_cols = [c for c in df.columns if c not in ("target",)]
        # quitar columnas poco informativas o que "filtran" futuro explícito
        # (si añadiste alguna columna con shift negativo, eliminarla)
        feature_cols = [c for c in feature_cols if not c.startswith("chikou")]  # chikou es futuro-retrocedido
        # Selección final (asegura que existan)
        feature_cols = [c for c in feature_cols if c in df.columns]

        # Train/test split por tiempo (no aleatorio)
        split_idx = int(len(df) * (1 - TEST_SIZE))
        df_train = df.iloc[:split_idx]
        df_test = df.iloc[split_idx:]

        # Normalizar features con StandardScaler (fit sólo en train)
        scaler = StandardScaler()
        scaler_fit_df = df_train[feature_cols].astype(float)
        scaler.fit(scaler_fit_df)

        # Construir secuencias para LSTM
        X_train, y_train = build_sequence_dataset(df_train, feature_cols, SEQ_LEN, "target")
        X_test, y_test = build_sequence_dataset(df_test, feature_cols, SEQ_LEN, "target")

        # Aplicar scaler a cada vector dentro de la secuencia (transform por reshape)
        n_train, s, f = X_train.shape
        X_train_flat = X_train.reshape(-1, f)
        X_train_flat = scaler.transform(X_train_flat)
        X_train = X_train_flat.reshape(n_train, s, f)

        n_test = X_test.shape[0]
        X_test_flat = X_test.reshape(-1, f)
        X_test_flat = scaler.transform(X_test_flat)
        X_test = X_test_flat.reshape(n_test, s, f)

        # ---------------------------
        # Entrenar LSTM
        # ---------------------------
        input_shape = (X_train.shape[1], X_train.shape[2])
        model = build_lstm_model(input_shape, units=64, dropout=0.25)

        cb = [
            callbacks.EarlyStopping(monitor="val_loss", patience=6, restore_best_weights=True, verbose=1),
            callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=3, min_lr=1e-6, verbose=1),
        ]
        history = model.fit(
            X_train, y_train,
            validation_split=0.1,
            epochs=100,
            batch_size=32,
            callbacks=cb,
            verbose=2
        )

        # Predicciones LSTM (probabilities)
        y_pred_prob_lstm = model.predict(X_test).ravel()
        y_pred_lstm = (y_pred_prob_lstm >= 0.5).astype(int)

        # ---------------------------
        # Entrenar RandomForest sobre snapshots (features agregadas por ventana)
        # ---------------------------
        # Para RF, usamos la última fila de cada secuencia (snapshot)
        def seq_to_snapshot(X):
            # toma el último step de cada secuencia
            return X[:, -1, :]

        X_train_snap = seq_to_snapshot(X_train)
        X_test_snap = seq_to_snapshot(X_test)

        rf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=RANDOM_STATE, n_jobs=-1)
        rf.fit(X_train_snap, y_train)
        y_pred_prob_rf = rf.predict_proba(X_test_snap)[:, 1]
        y_pred_rf = (y_pred_prob_rf >= 0.5).astype(int)

        # ---------------------------
        # Ensemble simple: promedio de probabilidades
        # ---------------------------
        y_prob_ens = (y_pred_prob_lstm + y_pred_prob_rf) / 2.0
        y_pred_ens = (y_prob_ens >= 0.5).astype(int)

        # ---------------------------
        # Métricas
        # ---------------------------
        def metrics(y_true, y_pred, y_prob=None):
            acc = accuracy_score(y_true, y_pred)
            prec = precision_score(y_true, y_pred, zero_division=0)
            rec = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            auc = roc_auc_score(y_true, y_prob) if y_prob is not None and len(np.unique(y_true))>1 else None
            return {"acc": acc, "prec": prec, "rec": rec, "f1": f1, "auc": auc}

        m_lstm = metrics(y_test, y_pred_lstm, y_pred_prob_lstm)
        m_rf = metrics(y_test, y_pred_rf, y_pred_prob_rf)
        m_ens = metrics(y_test, y_pred_ens, y_prob=y_prob_ens)

        print("=== Resultados ===")
        print("LSTM:", m_lstm)
        print("RF:  ", m_rf)
        print("ENS: ", m_ens)

        # Guardar modelos y scaler
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        lstm_path = os.path.join(MODEL_DIR, f"lstm_{ACTIVO}_{ts}.keras")
        rf_path = os.path.join(MODEL_DIR, f"rf_{ACTIVO}_{ts}.joblib")
        scaler_path = os.path.join(MODEL_DIR, f"scaler_{ACTIVO}_{ts}.joblib")

        model.save(lstm_path)
        joblib.dump(rf, rf_path)
        joblib.dump(scaler, scaler_path)

        print(f"Modelos guardados:\n - LSTM: {lstm_path}\n - RF: {rf_path}\n - Scaler: {scaler_path}")

        # Info a logs
        log_info(f"Entrenamiento finalizado. ENS metrics: {m_ens}", archivo="train_binance.py", funcion="main")

    except Exception as e:
        log_error(e, archivo="train_binance.py", funcion="main")
        raise


if __name__ == "__main__":
    main()
