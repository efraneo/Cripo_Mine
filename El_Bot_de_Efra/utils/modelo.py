# ==========================================================
# utils/modelo.py
# ----------------------------------------------------------
# Ensemble híbrido: LSTM + RandomForest + XGBoost
# - predecir_senal_ensemble(df, activo, pasos, futuros)
# - entrenar_y_predecir(df, activo, pasos, futuros, retrain_ml)
# - tracking de resultados para calcular error_score y mejorar confianza
# - robusto, modular y sin circular imports
# ==========================================================

import os
import joblib
import numpy as np
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, List

from utils.logger import log_info, log_warning, log_error
from utils.tracking import track_record, compute_error_score

# utils/modelo.py (arriba)
try:
    from utils.db import leer_activos_por_categoria
except Exception:
    # define un wrapper seguro por si falla la importación
    def leer_activos_por_categoria():
        return ({"Top": ["BTCUSDT", "ETHUSDT"]}, ["BTCUSDT", "ETHUSDT"])


# ==========================================================
# 📁 Directorios
# ==========================================================
MODELOS_ML_DIR = os.path.join("modelos_entrenados", "ml")
TRACKING_DIR = os.path.join("data", "tracking")
os.makedirs(MODELOS_ML_DIR, exist_ok=True)
os.makedirs(TRACKING_DIR, exist_ok=True)


# ==========================================================
# 🧩 Helpers: rutas y carga de modelos ML
# ==========================================================
def _ml_path(sym: str, kind: str) -> str:
    sym = (sym or "GEN").upper()
    if kind == "rf":
        return os.path.join(MODELOS_ML_DIR, f"{sym}_rf.pkl")
    elif kind == "xgb":
        return os.path.join(MODELOS_ML_DIR, f"{sym}_xgb.json")
    else:
        raise ValueError("kind must be 'rf' or 'xgb'")


def _cargar_modelo_ml(kind: str, activo: str):
    """Carga segura de modelo ML (RF o XGB)"""
    try:
        sym = (activo or "GEN").upper()
        path = _ml_path(sym, kind)
        if kind == "rf":
            if os.path.exists(path):
                return joblib.load(path)
            return None
        elif kind == "xgb":
            import xgboost as xgb
            if os.path.exists(path):
                booster = xgb.Booster()
                booster.load_model(path)
                return booster
        return None
    except Exception as e:
        log_warning(f"_cargar_modelo_ml error: {e}", archivo="modelo.py", funcion="_cargar_modelo_ml")
        return None


# ==========================================================
# 🔮 Predicción común ML -> probabilidad
# ==========================================================
def _ml_predict_proba(model, X_features):
    try:
        if model is None or X_features is None:
            return None

        # RandomForest
        try:
            from sklearn.ensemble import RandomForestClassifier
            if isinstance(model, RandomForestClassifier):
                probs = model.predict_proba(X_features)
                return float(np.clip(np.mean(probs[:, 1]), 0.0, 1.0))
        except Exception:
            pass

        # XGBoost
        try:
            import xgboost as xgb
            if isinstance(model, xgb.Booster):
                dmat = xgb.DMatrix(X_features)
                preds = model.predict(dmat)
                return float(np.clip(np.mean(preds), 0.0, 1.0))
        except Exception:
            pass

        # Fallback
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_features)
            return float(np.clip(np.mean(probs[:, 1]), 0.0, 1.0))
        if hasattr(model, "predict"):
            preds = model.predict(X_features)
            return float(np.clip(np.mean(preds), 0.0, 1.0))
        return None

    except Exception as e:
        log_warning(f"_ml_predict_proba error: {e}", archivo="modelo.py", funcion="_ml_predict_proba")
        return None


# ==========================================================
# 🔁 LSTM predicción + confianza
# ==========================================================
def _lstm_predict_confianza_y_preds(df, activo: str, pasos: int = 20, futuros: int = 5) -> Tuple[Optional[str], float, List[float]]:
    """Carga y predice usando modelo LSTM (import local para evitar circular imports)"""
    try:
        from utils.model_trainer import cargar_modelo as cargar_lstm_modelo, cargar_scaler
    except Exception as e:
        log_warning(f"utils.model_trainer no disponible: {e}", archivo="modelo.py", funcion="_lstm_predict_confianza_y_preds")
        return None, 0.0, []

    try:
        sym = (activo or "GEN").upper()
        model = cargar_lstm_modelo(sym)
        scaler = cargar_scaler(sym)
        if model is None or scaler is None:
            return None, 0.0, []

        if df is None or "close" not in df.columns or df.empty:
            return None, 0.0, []

        vals = df[["close"]].values.astype(float)
        if len(vals) < pasos:
            return None, 0.0, []

        scaled = scaler.transform(vals)
        ultimos = scaled[-pasos:].reshape((1, pasos, 1))

        preds_scaled = []
        for _ in range(futuros):
            p = model.predict(ultimos, verbose=0)
            preds_scaled.append(float(p[0, 0]))
            ultimos = np.concatenate([ultimos[:, 1:, :], np.array(p).reshape((1, 1, 1))], axis=1)

        preds = scaler.inverse_transform(np.array(preds_scaled).reshape(-1, 1)).flatten()

        if preds.size < 1:
            return None, 0.0, []

        trend = np.sign(np.diff(preds)) if preds.size >= 2 else [0]
        accion = "buy" if trend[0] > 0 else "sell" if trend[0] < 0 else "hold"

        var = float(np.var(preds))
        slope = float(np.mean(np.diff(preds))) if preds.size >= 2 else 0.0
        meanp = float(np.mean(preds))
        conf_var = max(0.0, 1.0 - min(var / (abs(meanp) + 1e-9), 1.0))
        conf_slope = min(1.0, abs(slope) / (abs(meanp) + 1e-9))
        confianza_lstm = float(np.clip(0.45 * conf_var + 0.55 * conf_slope, 0.0, 1.0))

        return accion, confianza_lstm, preds.tolist()
    except Exception as e:
        log_error(e, archivo="modelo.py", funcion="_lstm_predict_confianza_y_preds")
        return None, 0.0, []


# ==========================================================
# 🧮 Construcción de features ML
# ==========================================================
def construir_features_ml(df, pasos_feat: int = 20):
    try:
        if df is None or df.empty or "close" not in df.columns:
            return None
        closes = df["close"].values.astype(float)
        n = len(closes)
        ret = (closes[-1] - closes[-min(21, n)]) / (closes[-min(21, n)] + 1e-9)
        ma5 = np.mean(closes[-5:]) if n >= 5 else np.mean(closes)
        ma20 = np.mean(closes[-20:]) if n >= 20 else np.mean(closes)
        slope = (ma5 - ma20) / (ma20 + 1e-9)
        vol_mean = float(np.nanmean(df["volume"].tail(20))) if "volume" in df.columns else np.nan
        return np.array([[ret, slope, ma5, ma20, vol_mean]])
    except Exception as e:
        log_warning(f"construir_features_ml fallo: {e}", archivo="modelo.py", funcion="construir_features_ml")
        return None


# ==========================================================
# 🧠 Ensemble híbrido: LSTM + RF + XGB + Tracking
# ==========================================================
def predecir_senal_ensemble(df, activo: str = None, pasos: int = 20, futuros: int = 5) -> Tuple[str, float, Dict[str, Any]]:
    try:
        activo = (activo or "GEN").upper()
        info: Dict[str, Any] = {"activo": activo, "detalles": {}}

        # 1️⃣ LSTM
        accion_lstm, conf_lstm, preds = _lstm_predict_confianza_y_preds(df, activo=activo, pasos=pasos, futuros=futuros)
        info["detalles"]["lstm"] = {"accion": accion_lstm, "conf": conf_lstm, "preds": preds}

        # 2️⃣ ML Features
        X_feat = construir_features_ml(df, pasos_feat=20)

        # 3️⃣ Modelos RF/XGB
        rf = _cargar_modelo_ml("rf", activo)
        xgbm = _cargar_modelo_ml("xgb", activo)
        prob_rf = _ml_predict_proba(rf, X_feat) if rf and X_feat is not None else None
        prob_xgb = _ml_predict_proba(xgbm, X_feat) if xgbm and X_feat is not None else None
        info["detalles"]["rf"] = {"exists": rf is not None, "prob": prob_rf}
        info["detalles"]["xgb"] = {"exists": xgbm is not None, "prob": prob_xgb}

        # 4️⃣ Votos y consistencia
        votes, confs = [], []
        if accion_lstm: confs.append(conf_lstm); votes.append(1 if accion_lstm == "buy" else 0 if accion_lstm == "sell" else 0.5)
        if prob_rf is not None: confs.append(prob_rf); votes.append(1 if prob_rf >= 0.5 else 0)
        if prob_xgb is not None: confs.append(prob_xgb); votes.append(1 if prob_xgb >= 0.5 else 0)

        if not votes:
            accion_final = accion_lstm or "hold"
            confianza_final = conf_lstm
            return accion_final, confianza_final, info

        accion_final = "buy" if np.mean(votes) >= 0.5 else "sell"
        consistencia = float(np.clip(1.0 - np.std(votes), 0.0, 1.0))
        ml_conf = np.mean([p for p in (prob_rf, prob_xgb) if p is not None]) if confs else 0.0
        base_conf = float(np.clip(0.35 * conf_lstm + 0.65 * ml_conf, 0.0, 1.0))

        # 5️⃣ Tracking adaptativo (aprendizaje histórico)
        try:
            error_score = compute_error_score(activo=activo, window=150)
        except Exception as e:
            log_warning(f"compute_error_score fallo: {e}", archivo="modelo.py", funcion="predecir_senal_ensemble")
            error_score = 0.6

        estabilidad = 0.4 + 0.6 * consistencia

        info.update({
            "base_conf": base_conf,
            "consistencia": consistencia,
            "error_score": error_score,
            "estabilidad": estabilidad,
        })

        # 6️⃣ Ajuste dinámico de confianza
        from utils.confidence_boost import dynamic_confidence_boost
        nueva_conf, boosted = dynamic_confidence_boost(
            metodologias=[],
            prediccion_lstm={"confianza": conf_lstm},
            confianza_actual=base_conf,
            score_methods=float(np.mean(confs)) if confs else 0.0,
            rf_score=float(prob_rf or 0.0),
            consistencia=consistencia,
            error_score=error_score,
            estabilidad=estabilidad,
            resumen=f"IA Ensemble adaptativo para {activo}"
        )
        confianza_final = float(round(np.clip(nueva_conf, 0.0, 1.0), 6))
        info["boosted"] = boosted

        # 7️⃣ Tracking registro
        try:
            precio_base = float(df["close"].iloc[-1])
        except Exception:
            precio_base = None

        track_record(
            activo=activo,
            pred_label=accion_final,
            confidence=confianza_final,
            precio_pred=precio_base,
            precio_real=None
        )

        return accion_final, confianza_final, info

    except Exception as e:
        log_error(e, archivo="modelo.py", funcion="predecir_senal_ensemble")
        return "hold", 0.0, {"error": str(e)}


# ==========================================================
# ⚙️ Entrenamiento dinámico ML + Predicción final
# ==========================================================
def entrenar_y_predecir(df, activo: str = None, pasos: int = 20, futuros: int = 5, retrain_ml: bool = True):
    try:
        activo = (activo or "GEN").upper()
        info = {"activo": activo}

        closes = df["close"].values.astype(float)
        n = len(closes)
        X, y = [], []
        for i in range(20, n - 1):
            window = closes[i-20:i]
            if len(window) < 5: continue
            ret = (closes[i] - window[0]) / (window[0] + 1e-9)
            ma5, ma20 = np.mean(window[-5:]), np.mean(window)
            slope = (ma5 - ma20) / (ma20 + 1e-9)
            vol_mean = np.nanmean(df["volume"].iloc[i-20:i]) if "volume" in df.columns else np.nan
            X.append([ret, slope, ma5, ma20, vol_mean])
            y.append(1 if closes[i+1] > closes[i] else 0)
        X, y = np.array(X), np.array(y)

        if retrain_ml and len(X) >= 50:
            try:
                from sklearn.ensemble import RandomForestClassifier
                rf = RandomForestClassifier(n_estimators=100, random_state=42)
                rf.fit(X, y)
                joblib.dump(rf, _ml_path(activo, "rf"))
                log_info(f"RF actualizado para {activo}", archivo="modelo.py", funcion="entrenar_y_predecir")
            except Exception as e:
                log_warning(f"RF train fallo: {e}", archivo="modelo.py", funcion="entrenar_y_predecir")

            try:
                import xgboost as xgb
                dtrain = xgb.DMatrix(X, label=y)
                bst = xgb.train({"objective": "binary:logistic", "eval_metric": "logloss"}, dtrain, num_boost_round=40)
                bst.save_model(_ml_path(activo, "xgb"))
                log_info(f"XGB actualizado para {activo}", archivo="modelo.py", funcion="entrenar_y_predecir")
            except Exception as e:
                log_warning(f"XGB train fallo: {e}", archivo="modelo.py", funcion="entrenar_y_predecir")

        accion, conf, info_pred = predecir_senal_ensemble(df, activo=activo, pasos=pasos, futuros=futuros)
        info.update(info_pred)
        info["accion"] = accion
        info["confianza"] = conf

        return accion, conf, info
    except Exception as e:
        log_error(e, archivo="modelo.py", funcion="entrenar_y_predecir")
        return "hold", 0.0, {"error": str(e)}
