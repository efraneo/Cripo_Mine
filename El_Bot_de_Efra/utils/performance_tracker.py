# utils/performance_tracker.py
# ==========================================================
# Módulo de seguimiento del desempeño de modelos IA
# ----------------------------------------------------------
# - Guarda predicciones históricas (acción, confianza, real)
# - Calcula precisión rolling, consistencia y error_score
# - Entrega refuerzo adaptativo de confianza
# ==========================================================

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional
from utils.logger import log_info, log_warning, log_error

# ----------------------------------------------------------
# Archivo histórico (CSV o JSON)
# ----------------------------------------------------------
DATA_DIR = os.path.join("data_historica", "performance")
os.makedirs(DATA_DIR, exist_ok=True)
TRACK_FILE = os.path.join(DATA_DIR, "predicciones_historicas.csv")

# ----------------------------------------------------------
# Registro de predicciones
# ----------------------------------------------------------
def registrar_prediccion(activo: str,
                         accion_predicha: str,
                         confianza: float,
                         accion_real: Optional[str] = None,
                         consistencia: float = 0.0,
                         boosted: bool = False,
                         fuente: str = "ensemble") -> bool:
    """
    Guarda una línea de predicción realizada y su resultado (si ya se conoce).
    """
    try:
        registro = {
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "activo": activo.upper(),
            "accion_predicha": accion_predicha,
            "accion_real": accion_real or "pendiente",
            "confianza": round(float(confianza), 6),
            "consistencia": round(float(consistencia), 6),
            "boosted": int(boosted),
            "fuente": fuente
        }
        df = pd.DataFrame([registro])
        if not os.path.exists(TRACK_FILE):
            df.to_csv(TRACK_FILE, index=False)
        else:
            df.to_csv(TRACK_FILE, mode="a", header=False, index=False)
        return True
    except Exception as e:
        log_error(e, archivo="performance_tracker.py", funcion="registrar_prediccion")
        return False

# ----------------------------------------------------------
# Carga histórico
# ----------------------------------------------------------
def cargar_historico(max_filas: int = 500) -> Optional[pd.DataFrame]:
    try:
        if not os.path.exists(TRACK_FILE):
            return None
        df = pd.read_csv(TRACK_FILE)
        if df.empty:
            return None
        if len(df) > max_filas:
            df = df.tail(max_filas)
        return df
    except Exception as e:
        log_error(e, archivo="performance_tracker.py", funcion="cargar_historico")
        return None

# ----------------------------------------------------------
# Evaluar desempeño histórico
# ----------------------------------------------------------
def evaluar_desempeno(activo: Optional[str] = None,
                      ventana: int = 100) -> Dict[str, Any]:
    """
    Calcula precisión rolling, consistencia y error_score.
    Retorna:
      {
        'accuracy': float,
        'consistencia_prom': float,
        'error_score': float,
        'conf_std': float,
        'n': int
      }
    """
    try:
        df = cargar_historico(max_filas=1000)
        if df is None or df.empty:
            return {"accuracy": 0.5, "consistencia_prom": 0.5, "error_score": 0.5, "conf_std": 0.5, "n": 0}
        if activo:
            df = df[df["activo"].str.upper() == activo.upper()]
        if df.empty:
            return {"accuracy": 0.5, "consistencia_prom": 0.5, "error_score": 0.5, "conf_std": 0.5, "n": 0}

        df = df.tail(ventana)
        # Convertir acción_real/predicha a buy/sell/hold → num
        map_acc = {"buy": 1, "sell": 0, "hold": 0.5}
        df["pred_num"] = df["accion_predicha"].map(map_acc)
        df["real_num"] = df["accion_real"].map(map_acc)
        df = df.dropna(subset=["pred_num", "real_num"])

        # calcular accuracy básica
        hits = np.abs(df["pred_num"] - df["real_num"]) < 0.5
        accuracy = float(np.mean(hits)) if len(hits) > 0 else 0.5
        consistencia_prom = float(np.mean(df["consistencia"])) if "consistencia" in df.columns else 0.5
        conf_std = float(np.std(df["confianza"])) if "confianza" in df.columns else 0.5
        error_score = float(1.0 - accuracy)

        return {
            "accuracy": round(accuracy, 4),
            "consistencia_prom": round(consistencia_prom, 4),
            "error_score": round(error_score, 4),
            "conf_std": round(conf_std, 4),
            "n": len(df)
        }
    except Exception as e:
        log_error(e, archivo="performance_tracker.py", funcion="evaluar_desempeno")
        return {"accuracy": 0.5, "consistencia_prom": 0.5, "error_score": 0.5, "conf_std": 0.5, "n": 0}

# ----------------------------------------------------------
# Calcular refuerzo adaptativo de confianza (boost IA)
# ----------------------------------------------------------
def boost_confianza_dinamico(conf_actual: float,
                             activo: Optional[str] = None,
                             consistencia: float = 0.5,
                             estabilidad: float = 0.5) -> Dict[str, Any]:
    """
    Calcula nuevo nivel de confianza usando métricas reales (históricas).
    """
    try:
        hist = evaluar_desempeno(activo=activo, ventana=150)
        acc = hist["accuracy"]
        error = hist["error_score"]
        conf_std = hist["conf_std"]
        consist_hist = hist["consistencia_prom"]

        # Ponderación basada en desempeño
        ajuste = (
            (acc * 0.5) +
            ((1.0 - error) * 0.3) +
            ((1.0 - conf_std) * 0.1) +
            ((consistencia + consist_hist) * 0.1)
        )
        nueva_conf = conf_actual * (0.8 + 0.5 * ajuste)
        nueva_conf = float(np.clip(nueva_conf, 0.0, 1.0))
        boosted = nueva_conf > conf_actual

        # Refuerzo especial si accuracy > 0.8 → confianza IA puede subir >85%
        if acc >= 0.8 and consistencia >= 0.7:
            nueva_conf = max(nueva_conf, 0.85 + 0.1 * (acc - 0.8))
            boosted = True

        resultado = {
            "nueva_conf": round(nueva_conf, 6),
            "boosted": boosted,
            "accuracy_hist": acc,
            "error_score": error,
            "consistencia_hist": consist_hist,
            "conf_std": conf_std,
            "muestras": hist["n"]
        }

        log_info(
            f"Refuerzo adaptativo IA ({activo}) → conf={conf_actual:.2f}→{nueva_conf:.2f} | acc_hist={acc:.2f} | boosted={boosted}",
            archivo="performance_tracker.py",
            funcion="boost_confianza_dinamico"
        )
        return resultado
    except Exception as e:
        log_error(e, archivo="performance_tracker.py", funcion="boost_confianza_dinamico")
        return {"nueva_conf": conf_actual, "boosted": False}
