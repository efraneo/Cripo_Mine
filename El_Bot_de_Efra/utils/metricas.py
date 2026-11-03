# ===== utils/metricas.py =====
"""
Módulo de métricas de performance para backtesting / trading en vivo.
--------------------------------------------------
Incluye:
✅ WinRate (%)
✅ Profit Factor
✅ Expectancy (media de PnL por operación)
✅ Sharpe Ratio
✅ Calmar Ratio
✅ Max Drawdown
✅ Precisión de modelo (para señales)
"""

import numpy as np
import pandas as pd
from utils.logger import log_error


# ============================================================
# 📊 Función principal: calcular métricas básicas
# ============================================================
def calcular_metricas_basicas(df: pd.DataFrame) -> dict:
    """
    Calcula métricas de performance a partir de un DataFrame de historial de operaciones.
    Se espera que el DF tenga al menos la columna 'pnl' (ganancia/perdida en USDT).
    Opcionalmente puede tener 'fecha' para orden temporal.

    Args:
        df (pd.DataFrame): historial con columna 'pnl'.

    Returns:
        dict con métricas.
    """
    metricas = {
        "winrate": 0.0,
        "profit_factor": 0.0,
        "expectancy": 0.0,
        "sharpe": 0.0,
        "calmar": 0.0,
        "max_drawdown": 0.0
    }

    try:
        if df.empty or "pnl" not in df.columns:
            return metricas

        pnl = df["pnl"].dropna().astype(float)
        if pnl.empty:
            return metricas

        # ================================
        # ✅ WinRate
        # ================================
        wins = (pnl > 0).sum()
        total = len(pnl)
        metricas["winrate"] = (wins / total) * 100 if total > 0 else 0.0

        # ================================
        # ✅ Profit Factor (suma ganancias / suma pérdidas absolutas)
        # ================================
        sum_gains = pnl[pnl > 0].sum()
        sum_losses = abs(pnl[pnl < 0].sum())
        if sum_losses > 0:
            metricas["profit_factor"] = sum_gains / sum_losses
        else:
            metricas["profit_factor"] = float("inf") if sum_gains > 0 else 0.0

        # ================================
        # ✅ Expectancy (media de PnL)
        # ================================
        metricas["expectancy"] = pnl.mean()

        # ================================
        # ✅ Sharpe Ratio
        # ================================
        if pnl.std() > 0:
            metricas["sharpe"] = (pnl.mean() / pnl.std()) * np.sqrt(len(pnl))
        else:
            metricas["sharpe"] = 0.0

        # ================================
        # ✅ Calmar Ratio (rendimiento medio / max drawdown)
        # ================================
        equity = pnl.cumsum()
        rolling_max = equity.cummax()
        drawdown = equity - rolling_max
        max_dd = drawdown.min() if not drawdown.empty else 0.0
        max_dd_pct = abs(max_dd) / rolling_max.max() * 100 if rolling_max.max() > 0 else 0.0
        metricas["max_drawdown"] = max_dd_pct

        avg_return = pnl.mean() * len(pnl)
        if max_dd != 0:
            metricas["calmar"] = avg_return / abs(max_dd)
        else:
            metricas["calmar"] = 0.0

    except Exception as e:
        log_error(e, archivo="utils/metricas.py", funcion="calcular_metricas_basicas")

    return metricas


# =======================================
# 📌 Precisión simple en DataFrames
# =======================================
def calcular_precision_simple(df, pred_col="pred_signal", horizon=10):
    """Evalúa precisión básica comparando predicción vs movimiento futuro."""
    try:
        if df is None or df.empty or "close" not in df.columns or pred_col not in df.columns:
            return None
        df = df.copy()
        df["fut_close"] = df["close"].shift(-horizon)
        valid = df.dropna(subset=["fut_close", pred_col])
        if valid.empty:
            return None

        def hit(row):
            sig = row[pred_col]
            if sig == 1:
                return 1 if row["fut_close"] > row["close"] else 0
            elif sig == -1:
                return 1 if row["fut_close"] < row["close"] else 0
            return np.nan

        valid["hit"] = valid.apply(hit, axis=1)
        valid = valid.dropna(subset=["hit"])
        if valid.empty:
            return None

        return float(valid["hit"].mean()) * 100.0
    except Exception:
        return None


# =======================================
# 📌 Precisión de modelo (para señales)
# =======================================
def calcular_precision_modelo(y_true, y_pred) -> float:
    """
    Calcula precisión del modelo comparando señales reales vs. predichas.
    Args:
        y_true: lista/array de valores reales
        y_pred: lista/array de valores predichos
    Returns:
        float -> precisión entre 0 y 1
    """
    try:
        y_true, y_pred = np.array(y_true), np.array(y_pred)
        if len(y_true) == 0:
            return 0.0
        aciertos = np.sum(y_true == y_pred)
        return aciertos / len(y_true)
    except Exception as e:
        log_error(e, archivo="utils/metricas.py", funcion="calcular_precision_modelo")
        return 0.0
