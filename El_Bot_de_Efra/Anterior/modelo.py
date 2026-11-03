# utils/modelo.py
# ==========================================================
# Ensemble híbrido: LSTM + RandomForest + XGBoost (dinámico)
# - predecir_senal_ensemble(df, activo, pasos, futuros)
# - cálculo de base_conf, consistencia y boost dinámico
# - tolerante a modelos faltantes
# ==========================================================

import os
import numpy as np
import joblib
from typing import Tuple, Dict, Any, Optional

from utils.model_trainer import cargar_modelo_lstm, cargar_scaler, construir_features_ml
from utils.logger import log_info, log_warning, log_error
from utils.confidence_boost import dynamic_confidence_boost

# intentos de importar modelos ML
try:
    from sklearn.ensemble import RandomForestClassifier
    _HAS_SK = True
except Exception:
    _HAS_SK = False

try:
    import xgboost as xgb
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False

# directorio ML (consistente con model_trainer)
MODELOS_ML_DIR = os.path.join("modelos_entrenados", "ml")

def _ml_model_path(activo: str, kind: str) -> str:
    return os.path.join(MODELOS_ML_DIR, f"{(activo or 'GEN').upper()}_{kind}.pkl")

def _cargar_modelo_ml(kind: str, activo: str):
    try:
        path = _ml_model_path(activo, kind)
        if os.path.exists(path):
            return joblib.load(path)
    except Exception as e:
        log_warning(f"Error cargando ML model ({kind}) para {activo}: {e}", archivo="modelo.py", funcion="_cargar_modelo_ml")
    return None

def _ml_predict_proba(model, X_features):
    try:
        if model is None or X_features is None:
            return None
        # sklearn RF / XGB sklearn wrapper
        if _HAS_SK and hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_features)
            return float(np.clip(np.mean(probs[:, 1]), 0.0, 1.0))
        # xgboost Booster or sklearn wrapper
        if _HAS_XGB:
            try:
                # if it's sklearn wrapper
                if hasattr(model, "predict_proba"):
                    probs = model.predict_proba(X_features)
                    return float(np.clip(np.mean(probs[:, 1]), 0.0, 1.0))
                # else try Booster predict on DMatrix
                if hasattr(xgb, "DMatrix"):
                    dmat = xgb.DMatrix(X_features)
                    preds = model.predict(dmat)
                    return float(np.clip(np.mean(preds), 0.0, 1.0))
            except Exception:
                return None
        return None
    except Exception as e:
        log_warning(f"_ml_predict_proba error: {e}", archivo="modelo.py", funcion="_ml_predict_proba")
        return None

def _lstm_predict_confianza_y_preds(df, activo: str, pasos: int = 20, futuros: int = 5) -> Tuple[Optional[str], float, list]:
    try:
        model = cargar_modelo_lstm(activo, compile_model=False)
        scaler = cargar_scaler(activo)
        if model is None or scaler is None:
            return None, 0.0, []
        if df is None or df.empty or "close" not in df.columns:
            return None, 0.0, []
        vals = df[["close"]].dropna().values.astype(float)
        if len(vals) < pasos:
            return None, 0.0, []
        scaled = scaler.transform(vals)
        ultimos = scaled[-pasos:].reshape((1, pasos, 1))
        preds_scaled = []
        for _ in range(futuros):
            p = model.predict(ultimos, verbose=0)
            val = float(p[0, 0])
            preds_scaled.append(val)
            ultimos = np.concatenate([ultimos[:,1:,:], np.array(p).reshape((1,1,1))], axis=1)
        preds = scaler.inverse_transform(np.array(preds_scaled).reshape(-1,1)).flatten()
        if len(preds) < 2:
            return None, 0.0, preds.tolist()
        trend = np.sign(np.diff(preds))
        accion = "buy" if trend[0] > 0 else "sell" if trend[0] < 0 else "hold"
        var = float(np.var(preds))
        slope = float(np.mean(np.diff(preds)))
        conf_var = max(0.0, 1.0 - min(var / (abs(np.mean(preds)) + 1e-9), 1.0))
        conf_slope = min(1.0, min(abs(slope) / (abs(np.mean(preds)) + 1e-9), 1.0) * 2.0)
        confianza_lstm = float(np.clip(0.45*conf_var + 0.55*conf_slope, 0.0, 1.0))
        return accion, confianza_lstm, preds.tolist()
    except Exception as e:
        log_error(e, archivo="modelo.py", funcion="_lstm_predict_confianza_y_preds")
        return None, 0.0, []

def predecir_senal_ensemble(df, activo: str = None, pasos: int = 20, futuros: int = 5) -> Tuple[str, float, Dict[str, Any]]:
    """
    Ensemble híbrido (LSTM + RF + XGB) con tracking adaptativo de rendimiento.
    Retorna (accion, confianza_final, info_dict)
    """
    try:
        from utils.performance_tracker import (
            boost_confianza_dinamico,
            registrar_prediccion,
            evaluar_desempeno
        )

        activo = (activo or "GEN").upper()
        info = {"activo": activo, "detalles": {}}

        # 1️⃣ LSTM
        accion_lstm, conf_lstm, preds = _lstm_predict_confianza_y_preds(df, activo=activo, pasos=pasos, futuros=futuros)
        info["detalles"]["lstm"] = {"accion": accion_lstm, "conf": conf_lstm, "preds": preds}

        # 2️⃣ Features ML
        df_feats = construir_features_ml(df, pasos_feat=20)
        X_feat = None
        if df_feats is not None and not df_feats.empty:
            last = df_feats.tail(1)[["ret", "slope", "ma5", "ma20", "vol_mean"]].values
            X_feat = last

        # 3️⃣ Modelos ML
        rf = _cargar_modelo_ml("rf", activo)
        xgbm = _cargar_modelo_ml("xgb", activo)

        prob_rf = _ml_predict_proba(rf, X_feat) if rf is not None and X_feat is not None else None
        prob_xgb = _ml_predict_proba(xgbm, X_feat) if xgbm is not None and X_feat is not None else None
        info["detalles"]["rf"] = {"exists": rf is not None, "prob": prob_rf}
        info["detalles"]["xgb"] = {"exists": xgbm is not None, "prob": prob_xgb}

        # 4️⃣ Votos
        votes, confs = [], []
        if accion_lstm:
            votes.append(1 if accion_lstm == "buy" else 0 if accion_lstm == "sell" else 0.5)
            confs.append(conf_lstm)
        if prob_rf is not None:
            votes.append(1 if prob_rf >= 0.5 else 0)
            confs.append(prob_rf)
        if prob_xgb is not None:
            votes.append(1 if prob_xgb >= 0.5 else 0)
            confs.append(prob_xgb)

        if not votes:
            accion_final = accion_lstm or "hold"
            confianza_final = conf_lstm or 0.0
            info.update({"votos": votes, "confs_raw": confs})
            return accion_final, float(confianza_final), info

        mean_vote = float(np.mean(votes))
        accion_final = "buy" if mean_vote >= 0.5 else "sell"

        # 5️⃣ Base Confidence (ponderación dinámica)
        weight_lstm = 0.5 if all(p is None for p in (prob_rf, prob_xgb)) else 0.35
        weight_ml = 1.0 - weight_lstm
        ml_conf = np.mean([p for p in (prob_rf, prob_xgb) if p is not None]) if any(
            p is not None for p in (prob_rf, prob_xgb)
        ) else 0.0
        base_conf = float(np.clip(weight_lstm * (conf_lstm or 0.0) + weight_ml * ml_conf, 0.0, 1.0))

        # 6️⃣ Consistencia
        try:
            consistencia = 1.0 - float(np.std(votes))
            consistencia = float(np.clip(consistencia, 0.0, 1.0))
        except Exception:
            consistencia = 0.0

        # 7️⃣ Métricas históricas reales (performance_tracker)
        hist = evaluar_desempeno(activo=activo)
        estabilidad = 1.0 - min(abs(hist["conf_std"]), 1.0)
        error_score = hist["error_score"]

        info.update({
            "votos": votes,
            "confs_raw": confs,
            "base_conf": base_conf,
            "consistencia": consistencia,
            "estabilidad": estabilidad,
            "error_score": error_score,
            "accuracy_hist": hist["accuracy"],
            "muestras_hist": hist["n"]
        })

        # 8️⃣ Boost dinámico normal (confidence_boost)
        try:
            nueva_conf, boosted_primary = dynamic_confidence_boost(
                metodologias=[],
                prediccion_lstm={"confianza": conf_lstm},
                confianza_actual=base_conf,
                score_methods=float(np.mean(confs)) if confs else 0.0,
                rf_score=float(prob_rf or 0.0),
                consistencia=consistencia,
                error_score=error_score,
                estabilidad=estabilidad,
                resumen=f"Ensemble dinámico para {activo}"
            )
        except Exception as e:
            log_warning(f"dynamic_confidence_boost fallo: {e}", archivo="modelo.py", funcion="predecir_senal_ensemble")
            nueva_conf, boosted_primary = base_conf, False

        confianza_final = float(np.clip(nueva_conf, 0.0, 1.0))
        info["boosted"] = boosted_primary

        # 9️⃣ Refuerzo adaptativo (performance_tracker)
        try:
            boost_hist = boost_confianza_dinamico(
                conf_actual=confianza_final,
                activo=activo,
                consistencia=consistencia,
                estabilidad=estabilidad
            )
            confianza_final = boost_hist["nueva_conf"]
            info["boosted_hist"] = boost_hist["boosted"]
            info["accuracy_hist"] = boost_hist["accuracy_hist"]
        except Exception as e:
            log_warning(f"boost_confianza_dinamico fallo: {e}", archivo="modelo.py", funcion="predecir_senal_ensemble")

        confianza_final = float(round(confianza_final, 6))

        # 🔟 Registrar predicción histórica
        try:
            registrar_prediccion(
                activo=activo,
                accion_predicha=accion_final,
                confianza=confianza_final,
                consistencia=consistencia,
                boosted=info.get("boosted", False) or info.get("boosted_hist", False),
                fuente="ensemble"
            )
        except Exception as e:
            log_warning(f"registro predicción fallo: {e}", archivo="modelo.py", funcion="predecir_senal_ensemble")

        return accion_final, confianza_final, info

    except Exception as e:
        log_error(e, archivo="modelo.py", funcion="predecir_senal_ensemble")
        return "hold", 0.0, {"error": str(e)}
