# ==========================================================
# utils/auto_learning.py
# ----------------------------------------------------------
# 🤖 Aprendizaje adaptativo semanal (RF + XGB)
# - Evalúa tracking histórico y reentrena modelos ML
# - Ajusta pesos de entrenamiento según error_score
# - Actualiza confianza IA promedio (>85% cuando estable)
# ==========================================================

import os
import sqlite3
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any
from utils.logger import log_info, log_warning, log_error
from utils.tracking import compute_error_score

# ==========================================================
# 🧩 Configuración
# ==========================================================
DB_PATH = os.path.join("data", "tracking", "tracking.db")
MODELOS_ML_DIR = os.path.join("modelos_entrenados", "ml")
LOG_FILE = os.path.join("logs", "auto_learning.log")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(MODELOS_ML_DIR, exist_ok=True)
os.makedirs("logs", exist_ok=True)


def _get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ==========================================================
# 🧮 Extraer dataset histórico de tracking
# ==========================================================
def get_training_data_from_tracking(activo: str, lookback_days: int = 30):
    """
    Obtiene registros de tracking para reentrenamiento de ML.
    Retorna DataFrame con columnas: confidence, resultado, pred_label
    """
    try:
        conn = _get_conn()
        since = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d %H:%M:%S")
        df = pd.read_sql_query(
            "SELECT * FROM tracking WHERE activo=? AND fecha >= ? AND resultado IS NOT NULL",
            conn, params=(activo, since)
        )
        conn.close()
        if df.empty:
            return pd.DataFrame()
        return df
    except Exception as e:
        log_error(f"get_training_data_from_tracking fallo: {e}",
                  archivo="auto_learning.py", funcion="get_training_data_from_tracking")
        return pd.DataFrame()


# ==========================================================
# ⚙️ Función principal de autoaprendizaje
# ==========================================================
def auto_retrain_models(activo: str = "GEN") -> Dict[str, Any]:
    """
    Reentrena modelos ML en base al tracking y ajusta confianza promedio.
    Retorna dict resumen con métricas.
    """
    try:
        df = get_training_data_from_tracking(activo)
        if df.empty or len(df) < 30:
            msg = f"📉 Insuficientes datos para autoaprendizaje ({len(df)} registros)"
            log_warning(msg, archivo="auto_learning.py", funcion="auto_retrain_models")
            return {"status": "no_data", "msg": msg}

        # Generar dataset pseudo-supervisado
        df["target"] = df["resultado"].astype(int)
        df["conf"] = df["confidence"].clip(0, 1)
        df["error"] = 1.0 - df["resultado"]

        # Features sintéticas: historial de confianza y precisión reciente
        df["conf_smooth"] = df["conf"].rolling(5, min_periods=1).mean()
        df["acc_smooth"] = df["resultado"].rolling(5, min_periods=1).mean()
        df["volatilidad_conf"] = df["conf"].rolling(10, min_periods=1).std().fillna(0)
        df["tendencia"] = np.sign(df["acc_smooth"].diff().fillna(0))

        features = ["conf", "error", "conf_smooth", "acc_smooth", "volatilidad_conf", "tendencia"]
        X = df[features].values
        y = df["target"].values

        if len(X) < 20:
            log_warning("Dataset reducido para autoaprendizaje", archivo="auto_learning.py", funcion="auto_retrain_models")

        # -------------------------------
        # Entrenar RF adaptado
        # -------------------------------
        from sklearn.ensemble import RandomForestClassifier
        rf = RandomForestClassifier(n_estimators=150, random_state=42, n_jobs=1, class_weight="balanced_subsample")
        rf.fit(X, y)
        rf_path = os.path.join(MODELOS_ML_DIR, f"{activo}_rf.pkl")
        joblib.dump(rf, rf_path)

        # -------------------------------
        # Entrenar XGBoost adaptado
        # -------------------------------
        import xgboost as xgb
        dtrain = xgb.DMatrix(X, label=y)
        params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "verbosity": 0,
            "max_depth": 4,
            "eta": 0.2
        }
        bst = xgb.train(params, dtrain, num_boost_round=80)
        xgb_path = os.path.join(MODELOS_ML_DIR, f"{activo}_xgb.json")
        bst.save_model(xgb_path)

        # -------------------------------
        # Calcular nuevas métricas
        # -------------------------------
        error_score = compute_error_score(activo, window=100)
        conf_avg = float(df["confidence"].mean())
        precision = float(df["resultado"].mean())
        conf_final = np.clip(0.85 if precision > 0.8 else conf_avg * (1 + 0.1 * precision), 0.0, 1.0)

        resumen = {
            "status": "ok",
            "n_registros": len(df),
            "precision": round(precision, 3),
            "error_score": round(error_score, 3),
            "confianza_promedio": round(conf_avg, 3),
            "confianza_ajustada": round(conf_final, 3),
            "rf_model_path": rf_path,
            "xgb_model_path": xgb_path,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Guardar resumen en log
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(resumen) + "\n")

        log_info(f"✅ Autoaprendizaje completado para {activo} — "
                 f"precisión {precision:.2f}, confianza final {conf_final:.2f}",
                 archivo="auto_learning.py", funcion="auto_retrain_models")

        return resumen

    except Exception as e:
        log_error(f"auto_retrain_models fallo: {e}",
                  archivo="auto_learning.py", funcion="auto_retrain_models")
        return {"status": "error", "msg": str(e)}
