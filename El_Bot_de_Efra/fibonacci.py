# ==========================================================
# fibonacci.py
# ==========================================================
# Cálculo de retrocesos y extensiones de Fibonacci
# - Mejoras: salida dual (lista de niveles numéricos + dict legible)
# - Función detectar_niveles_fibonacci devuelve tanto lista de floats
#   como dict con etiquetas, para compatibilidad con otros módulos.
# ==========================================================

import logging
from typing import Dict, List, Tuple, Union

# ==========================================================
# 🔢 Retrocesos
# ==========================================================
def calcular_fibonacci_retracements(minimo: float, maximo: float) -> Dict[str, float]:
    """
    Calcula niveles de retroceso de Fibonacci.
    Retorna dict mapeando etiqueta->precio (float).
    """
    try:
        diferencia = maximo - minimo
        return {
            "0.0%": maximo,
            "23.6%": maximo - 0.236 * diferencia,
            "38.2%": maximo - 0.382 * diferencia,
            "50.0%": maximo - 0.5 * diferencia,
            "61.8%": maximo - 0.618 * diferencia,
            "78.6%": maximo - 0.786 * diferencia,
            "100.0%": minimo,
        }
    except Exception as e:
        logging.error(f"❌ Error en calcular_fibonacci_retracements: {e}")
        return {}

# ==========================================================
# 🔢 Extensiones
# ==========================================================
def calcular_fibonacci_extensions(minimo: float, maximo: float) -> Dict[str, float]:
    """
    Calcula niveles de extensión de Fibonacci.
    Retorna dict mapeando etiqueta->precio (float).
    """
    try:
        diferencia = maximo - minimo
        return {
            "100.0%": maximo,
            "127.2%": maximo + 0.272 * diferencia,
            "161.8%": maximo + 0.618 * diferencia,
            "200.0%": maximo + 1.0 * diferencia,
            "261.8%": maximo + 1.618 * diferencia,
        }
    except Exception as e:
        logging.error(f"❌ Error en calcular_fibonacci_extensions: {e}")
        return {}

# ==========================================================
# 📊 Detector general
# ==========================================================
def detectar_niveles_fibonacci(df) -> Union[List[float], Tuple[List[float], Dict[str, Dict[str, float]]]]:
    """
    Detecta niveles de retroceso y extensión de Fibonacci.
    Soporta DataFrames con ['low','high'] o solo ['close'].
    Retorna lista de niveles float ordenados (desc).
    """
    try:
        # 🔒 Validaciones iniciales
        if df is None:
            logging.warning("⚠️ detectar_niveles_fibonacci: df es None")
            return []

        if not hasattr(df, "empty"):
            logging.warning("⚠️ detectar_niveles_fibonacci: objeto no es DataFrame")
            return []

        if df.empty or getattr(df, "attrs", {}).get("__empty__", False):
            if not getattr(df, "attrs", {}).get("__empty__", False):
                logging.warning("⚠️ detectar_niveles_fibonacci: DataFrame vacío")
            return []

        # 🔹 Detectar rangos
        if "low" in df.columns and "high" in df.columns:
            minimo, maximo = float(df["low"].min()), float(df["high"].max())
        elif "close" in df.columns:
            minimo, maximo = float(df["close"].min()), float(df["close"].max())
        else:
            logging.warning("⚠️ detectar_niveles_fibonacci: faltan columnas ['low','high','close']")
            return []

        # 🔹 Cálculo
        retrocesos = calcular_fibonacci_retracements(minimo, maximo)
        extensiones = calcular_fibonacci_extensions(minimo, maximo)

        valores = list(set(list(retrocesos.values()) + list(extensiones.values())))
        valores_sorted = sorted([float(v) for v in valores if v is not None], reverse=True)

        # 🔹 Dict legible (si lo necesitas más adelante)
        dict_legible = {
            "retracements": retrocesos,
            "extensions": extensiones,
            "min_max": {"minimo": minimo, "maximo": maximo}
        }

        return valores_sorted

    except Exception as e:
        logging.error(f"❌ Error en detectar_niveles_fibonacci: {e}")
        return []
