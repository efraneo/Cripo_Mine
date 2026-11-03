# ==========================================================
# utils/tracking.py
# ----------------------------------------------------------
# 📊 Sistema de tracking de predicciones IA
# - Guarda cada predicción en SQLite
# - Calcula precisión y error_score adaptativo
# - Se usa en conjunto con modelo.py y train_scheduler.py
# ==========================================================

import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from utils.logger import log_info, log_warning, log_error

# ==========================================================
# 📁 Configuración y conexión
# ==========================================================
DB_PATH = os.path.join("data", "tracking", "tracking.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _get_conn():
    """Crea y devuelve conexión SQLite"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            activo TEXT,
            pred_label TEXT,
            confidence REAL,
            precio_pred REAL,
            precio_real REAL,
            resultado INTEGER,
            delay REAL
        )
    """)
    conn.commit()
    return conn


# ==========================================================
# 🧩 Registrar una predicción
# ==========================================================
def track_record(
    activo: str,
    pred_label: str,
    confidence: float,
    precio_pred: Optional[float],
    precio_real: Optional[float] = None
):
    """
    Registra una nueva predicción.
    Si se proporciona precio_real, calcula resultado inmediato.
    """
    try:
        fecha = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        resultado = None
        delay = None

        if precio_pred is not None and precio_real is not None:
            if pred_label == "buy":
                resultado = 1 if precio_real > precio_pred else 0
            elif pred_label == "sell":
                resultado = 1 if precio_real < precio_pred else 0
            else:
                resultado = 1 if abs(precio_real - precio_pred) < 0.001 else 0
            delay = 0.0  # se puede actualizar si hay tracking diferido

        conn = _get_conn()
        conn.execute("""
            INSERT INTO tracking (fecha, activo, pred_label, confidence, precio_pred, precio_real, resultado, delay)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha, activo, pred_label, confidence, precio_pred, precio_real, resultado, delay))
        conn.commit()
        conn.close()

        log_info(f"Tracking guardado: {activo} | {pred_label} ({confidence*100:.1f}%)",
                 archivo="tracking.py", funcion="track_record")
    except Exception as e:
        log_error(f"track_record fallo: {e}", archivo="tracking.py", funcion="track_record")


# ==========================================================
# 🧮 Actualizar con resultado real posterior
# ==========================================================
def update_real_result(activo: str, precio_real: float, delay_horas: float = 1.0):
    """
    Cuando se conoce el precio real más adelante, actualiza el último registro.
    """
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, precio_pred, pred_label FROM tracking WHERE activo=? ORDER BY id DESC LIMIT 1", (activo,))
        row = cur.fetchone()
        if not row:
            log_warning(f"No hay predicciones previas para {activo}", archivo="tracking.py", funcion="update_real_result")
            conn.close()
            return False

        _id, precio_pred, pred_label = row
        resultado = None
        if pred_label == "buy":
            resultado = 1 if precio_real > precio_pred else 0
        elif pred_label == "sell":
            resultado = 1 if precio_real < precio_pred else 0
        else:
            resultado = 1 if abs(precio_real - precio_pred) < 0.001 else 0

        conn.execute("""
            UPDATE tracking SET precio_real=?, resultado=?, delay=? WHERE id=?
        """, (precio_real, resultado, delay_horas, _id))
        conn.commit()
        conn.close()

        log_info(f"Resultado actualizado para {activo} → {'✅' if resultado == 1 else '❌'}",
                 archivo="tracking.py", funcion="update_real_result")
        return True
    except Exception as e:
        log_error(f"update_real_result fallo: {e}", archivo="tracking.py", funcion="update_real_result")
        return False


# ==========================================================
# 📊 Calcular error_score adaptativo
# ==========================================================
def compute_error_score(activo: str, window: int = 100) -> float:
    """
    Devuelve un score [0,1] basado en precisión y confianza reciente.
    - Combina exactitud, estabilidad y sesgo de confianza
    - Requiere al menos 10 registros válidos
    """
    try:
        conn = _get_conn()
        df = pd.read_sql_query(
            "SELECT * FROM tracking WHERE activo=? ORDER BY id DESC LIMIT ?",
            conn, params=(activo, window)
        )
        conn.close()

        if df.empty or len(df) < 10:
            return 0.6  # valor base

        df = df.dropna(subset=["confidence"])
        df["resultado"] = df["resultado"].fillna(0)
        df["conf_sesgo"] = abs(df["confidence"] - df["resultado"])
        df["error_local"] = 1.0 - (1.0 - df["conf_sesgo"]) * (0.5 + 0.5 * df["resultado"])

        # precisión bruta
        precision = float(df["resultado"].mean())
        # estabilidad: desviación de confianza
        estabilidad = 1.0 - float(df["confidence"].std())
        # sesgo: diferencia media entre confianza y realidad
        sesgo = 1.0 - float(df["conf_sesgo"].mean())

        # score compuesto (ponderado)
        score = 0.5 * precision + 0.3 * estabilidad + 0.2 * sesgo
        score = float(max(0.0, min(1.0, score)))

        log_info(f"Error_score({activo}) = {score:.3f} | precisión={precision:.2f}",
                 archivo="tracking.py", funcion="compute_error_score")
        return round(score, 4)
    except Exception as e:
        log_error(f"compute_error_score fallo: {e}", archivo="tracking.py", funcion="compute_error_score")
        return 0.6


# ==========================================================
# 🧠 Limpieza de histórico antiguo
# ==========================================================
def purge_old_records(days: int = 30):
    """Elimina registros antiguos para mantener la base ligera"""
    try:
        limit_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        conn = _get_conn()
        conn.execute("DELETE FROM tracking WHERE fecha < ?", (limit_date,))
        deleted = conn.total_changes
        conn.commit()
        conn.close()
        log_info(f"{deleted} registros antiguos eliminados del tracking.",
                 archivo="tracking.py", funcion="purge_old_records")
    except Exception as e:
        log_error(f"purge_old_records fallo: {e}", archivo="tracking.py", funcion="purge_old_records")
