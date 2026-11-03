# ==========================================================
# utils/risk_manager.py
# ==========================================================
# Módulo para gestión de riesgo en operaciones:
# - Tamaño de posición
# - Stop Loss y Take Profit
# - Evaluación de riesgo/recompensa
# - Validaciones dinámicas por activo
# ==========================================================

import math
import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict, Tuple
from datetime import datetime

# Configuración global
DEFAULT_CAPITAL = 1000.0
DEFAULT_RIESGO_PCT = 2.0  # % de capital arriesgado por operación
DEFAULT_RR_MIN = 1.5      # Riesgo/recompensa mínimo aceptado

# ==========================================================
# 📊 Cálculo de tamaño de posición
# ==========================================================
def calcular_tamano_posicion(capital: float,
                             riesgo_pct: float,
                             precio_entrada: float,
                             stop_loss: float) -> float:
    """
    Calcula el tamaño de la posición (cantidad de unidades).
    Fórmula:
        riesgo_monetario = capital * (riesgo_pct / 100)
        cantidad = riesgo_monetario / (|precio_entrada - stop_loss|)
    """
    try:
        riesgo_monetario = capital * (riesgo_pct / 100.0)
        riesgo_por_unidad = abs(precio_entrada - stop_loss)

        if riesgo_por_unidad <= 0:
            logging.warning("⚠️ Riesgo por unidad inválido (SL=Entrada).")
            return 0.0

        cantidad = riesgo_monetario / riesgo_por_unidad
        return round(cantidad, 6)
    except Exception as e:
        logging.error(f"❌ Error en calcular_tamano_posicion: {e}")
        return 0.0

# ==========================================================
# 🎯 Stop Loss, Take Profit y R:R
# ==========================================================
def calcular_sl_tp(precio_entrada: float,
                   riesgo_pct: float,
                   rr: float = DEFAULT_RR_MIN,
                   direccion: str = "buy") -> Tuple[float, float]:
    """
    Calcula niveles de SL y TP en base al ratio riesgo/recompensa (R:R).
    - direccion = "buy" o "sell"
    """
    try:
        if direccion not in ["buy", "sell"]:
            raise ValueError("La dirección debe ser 'buy' o 'sell'.")

        delta = precio_entrada * (riesgo_pct / 100.0)
        if direccion == "buy":
            sl = precio_entrada - delta
            tp = precio_entrada + delta * rr
        else:  # sell
            sl = precio_entrada + delta
            tp = precio_entrada - delta * rr

        return round(sl, 6), round(tp, 6)
    except Exception as e:
        logging.error(f"❌ Error en calcular_sl_tp: {e}")
        return precio_entrada, precio_entrada

# ==========================================================
# 🛡️ Evaluación de la operación
# ==========================================================
def evaluar_riesgo(precio_entrada: float,
                   stop_loss: float,
                   take_profit: float) -> Dict[str, float]:
    """
    Evalúa la operación en base a riesgo, recompensa y ratio.
    Retorna un dict con:
      - riesgo
      - recompensa
      - rr (riesgo/recompensa)
    """
    try:
        riesgo = abs(precio_entrada - stop_loss)
        recompensa = abs(take_profit - precio_entrada)
        rr = recompensa / riesgo if riesgo > 0 else 0

        return {
            "riesgo": riesgo,
            "recompensa": recompensa,
            "rr": round(rr, 2)
        }
    except Exception as e:
        logging.error(f"❌ Error en evaluar_riesgo: {e}")
        return {"riesgo": 0, "recompensa": 0, "rr": 0}

# ==========================================================
# ⚡ Funciones avanzadas y validaciones
# ==========================================================
def validar_operacion(capital: float,
                      riesgo_pct: float,
                      precio_entrada: float,
                      stop_loss: float,
                      take_profit: float,
                      rr_min: float = DEFAULT_RR_MIN) -> bool:
    """
    Valida si la operación cumple con el riesgo máximo permitido
    y el ratio mínimo R:R.
    """
    try:
        cantidad = calcular_tamano_posicion(capital, riesgo_pct, precio_entrada, stop_loss)
        if cantidad <= 0:
            logging.warning("⚠️ Operación inválida (cantidad <= 0).")
            return False

        evaluacion = evaluar_riesgo(precio_entrada, stop_loss, take_profit)
        if evaluacion["rr"] < rr_min:
            logging.warning(f"⚠️ Operación rechazada (R:R {evaluacion['rr']} < {rr_min}).")
            return False

        return True
    except Exception as e:
        logging.error(f"❌ Error en validar_operacion: {e}")
        return False


def resumen_operacion(capital: float,
                      riesgo_pct: float,
                      precio_entrada: float,
                      stop_loss: float,
                      take_profit: float,
                      direccion: str = "buy") -> str:
    """
    Retorna un resumen legible de la operación para logs/Telegram.
    """
    try:
        cantidad = calcular_tamano_posicion(capital, riesgo_pct, precio_entrada, stop_loss)
        evaluacion = evaluar_riesgo(precio_entrada, stop_loss, take_profit)

        return (
            f"📌 Operación {direccion.upper()}:\n"
            f"   • Entrada: {precio_entrada}\n"
            f"   • SL: {stop_loss} | TP: {take_profit}\n"
            f"   • Cantidad: {cantidad:.6f}\n"
            f"   • Riesgo: {evaluacion['riesgo']:.4f} | "
            f"Recompensa: {evaluacion['recompensa']:.4f} | "
            f"R:R = {evaluacion['rr']}\n"
        )
    except Exception as e:
        logging.error(f"❌ Error en resumen_operacion: {e}")
        return "❌ Error al generar resumen de operación."

# ============================================================
# 📌 Wrapper de compatibilidad para riesgo
# ============================================================

def calcular_riesgo(precio_actual: float, stop_loss: float, capital: float = 1000, riesgo_pct: float = 0.02) -> dict:
    """
    Calcula tamaño de posición y riesgo con SL dinámico.
    - precio_actual: precio de entrada
    - stop_loss: nivel de stop loss
    - capital: capital total disponible
    - riesgo_pct: % de riesgo (por defecto 2%)

    Devuelve dict con {cantidad, riesgo_usdt, riesgo_pct}
    """
    try:
        riesgo_usdt = capital * riesgo_pct
        riesgo_por_unidad = abs(precio_actual - stop_loss)
        cantidad = riesgo_usdt / riesgo_por_unidad if riesgo_por_unidad > 0 else 0

        return {
            "cantidad": cantidad,
            "riesgo_usdt": riesgo_usdt,
            "riesgo_pct": riesgo_pct * 100
        }
    except Exception as e:
        from utils.logger import log_error
        log_error(e, archivo="risk_manager.py", funcion="calcular_riesgo")
        return {"cantidad": 0, "riesgo_usdt": 0, "riesgo_pct": 0}
