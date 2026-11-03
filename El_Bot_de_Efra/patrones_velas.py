# ==========================================================
# patrones_velas.py
# ==========================================================
# Detector robusto de patrones de velas.
# - Intenta usar TA-Lib si está disponible (rápido y completo).
# - Si no existe TA-Lib, usa heurísticas basadas en relaciones O/H/L/C.
# - Detecta varios patrones comunes (hammer, shooting star, engulfing,
#   doji, morning/evening star, three soldiers/crows, piercing, dark cloud, harami, tweezer).
# ==========================================================

import logging
from typing import List
import pandas as pd
import numpy as np

_logger = logging.getLogger("patrones_velas")
if not _logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | [patrones] %(message)s"))
    _logger.addHandler(ch)
    _logger.setLevel(logging.INFO)

# Intentar importar talib (opcional)
try:
    import talib
    _HAS_TALIB = True
except Exception:
    _HAS_TALIB = False
    _logger.info("TA-Lib no disponible — usando heurísticas en patrones_velas.py")

# ---------------------------
# Helpers básicos
# ---------------------------
def _last_row(df: pd.DataFrame) -> pd.Series:
    return df.iloc[-1] if (df is not None and not df.empty) else pd.Series()

def _is_doji(open_, close_, high_, low_, threshold=0.1) -> bool:
    # ratio cuerpo/tamaño vela pequeño
    size = abs(high_ - low_)
    if size == 0:
        return False
    cuerpo = abs(close_ - open_)
    return (cuerpo / size) <= threshold

# ---------------------------
# Heurísticas para patrones
# ---------------------------
def _hammer(open_, high_, low_, close_) -> bool:
    cuerpo = abs(close_ - open_)
    cola_inferior = min(open_, close_) - low_
    cola_superior = high_ - max(open_, close_)
    return (cola_inferior >= 2*cuerpo) and (cola_superior <= cuerpo)

def _shooting_star(open_, high_, low_, close_) -> bool:
    cuerpo = abs(close_ - open_)
    cola_superior = high_ - max(open_, close_)
    cola_inferior = min(open_, close_) - low_
    return (cola_superior >= 2*cuerpo) and (cola_inferior <= cuerpo)

def _engulfing(prev_o, prev_c, o, c) -> str:
    # return 'bull' or 'bear' or ''
    if (c > o) and (prev_c < prev_o) and (c > prev_o) and (o < prev_c):
        return "bull"  # bullish engulfing
    if (c < o) and (prev_c > prev_o) and (c < prev_o) and (o > prev_c):
        return "bear"
    return ""

def _three_white_soldiers(df: pd.DataFrame) -> bool:
    # últimas 3 velas alcistas con cuerpos crecientes y sin largas sombras superiores
    if len(df) < 3:
        return False
    last3 = df.iloc[-3:]
    if not all(last3['close'] > last3['open']):
        return False
    corpos = (last3['close'] - last3['open']).abs()
    return (corpos.iloc[2] > corpos.iloc[1] > corpos.iloc[0])

def _three_black_crows(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    last3 = df.iloc[-3:]
    if not all(last3['close'] < last3['open']):
        return False
    corpos = (last3['open'] - last3['close']).abs()
    return (corpos.iloc[2] > corpos.iloc[1] > corpos.iloc[0])

# ---------------------------
# Función principal (pública)
# ---------------------------
def detectar_patrones_velas(df: pd.DataFrame) -> List[str]:
    """
    Devuelve lista de patrones detectados en la última vela / últimas velas.
    - Intenta TA-Lib (si existe) para detectar muchos patrones.
    - Si TA-Lib no está presente, aplica heurísticas para un conjunto de patrones clave.
    """
    patrones = []

    try:
        if df is None or df.empty:
            return ["⚠️ DataFrame vacío o inválido."]

        required_columns = {'open', 'high', 'low', 'close'}
        if not required_columns.issubset(set(df.columns)):
            return ["⚠️ Faltan columnas necesarias para detectar patrones de velas."]

        # Si TA-Lib está presente, usar su detección para varios patrones
        if _HAS_TALIB:
            try:
                # lista de funciones TA-Lib para patrones (no exhaustiva)
                talib_funcs = {
                    'CDLHAMMER': talib.CDLHAMMER,
                    'CDLSHOOTINGSTAR': talib.CDLSHOOTINGSTAR,
                    'CDLENGULFING': talib.CDLENGULFING,
                    'CDLDOJI': talib.CDLDOJI,
                    'CDLMORNINGSTAR': talib.CDLMORNINGSTAR,
                    'CDLEVENINGSTAR': talib.CDLEVENINGSTAR,
                    'CDL3WHITESOLDIERS': talib.CDL3WHITESOLDIERS,
                    'CDL3BLACKCROWS': talib.CDL3BLACKCROWS,
                    'CDLPIERCING': talib.CDLPIERCING,
                    'CDLDARKCLOUDCOVER': talib.CDLDARKCLOUDCOVER,
                    'CDLHARAMI': talib.CDLHARAMI,
                    'CDLDOJI': talib.CDLDOJI,
                    'CDLDRAGONFLYDOJI': getattr(talib, 'CDLDRAGONFLYDOJI', None),
                    'CDLTAKURI': getattr(talib, 'CDLTAKURI', None)
                }

                o = df['open'].values
                h = df['high'].values
                l = df['low'].values
                c = df['close'].values

                for name, func in talib_funcs.items():
                    if func is None:
                        continue
                    try:
                        res = func(o, h, l, c)
                        # si el último valor no es 0 -> patrón detectado en última vela (valor positivo o negativo indica dirección)
                        if len(res) and res[-1] != 0:
                            label = name.replace('CDL', '')
                            patrones.append(label)
                    except Exception:
                        continue

                # Normalizar nombres populares (opcional)
                # por ejemplo CDLMORNINGSTAR -> MorningStar
                patrones = [p.title() for p in patrones]
                if patrones:
                    return patrones
            except Exception as e:
                _logger.warning(f"TA-Lib falló al detectar patrones: {e}")

        # ------------------------------
        # Si no TA-Lib (o fallo), usar heurísticas
        # ------------------------------
        # Inspeccionamos últimas 3 velas para varios patrones y la última para otros.
        if len(df) >= 1:
            last = df.iloc[-1]
            o, h, l, c = float(last['open']), float(last['high']), float(last['low']), float(last['close'])

            # Doji
            if _is_doji(o, c, h, l, threshold=0.15):
                patrones.append("Doji")

            # Hammer / Inverted Hammer / Shooting Star
            if _hammer(o, h, l, c):
                patrones.append("Hammer")
            if _shooting_star(o, h, l, c):
                patrones.append("ShootingStar")

        # Engulfing (requiere vela anterior)
        if len(df) >= 2:
            prev = df.iloc[-2]
            direction = _engulfing(prev['open'], prev['close'], df.iloc[-1]['open'], df.iloc[-1]['close'])
            if direction == "bull":
                patrones.append("EngulfingBull")
            elif direction == "bear":
                patrones.append("EngulfingBear")

        # Three white soldiers / three black crows
        try:
            if _three_white_soldiers(df):
                patrones.append("ThreeWhiteSoldiers")
            if _three_black_crows(df):
                patrones.append("ThreeBlackCrows")
        except Exception:
            pass

        # Piercing / Dark Cloud (reversal patterns) heuristics (two-candle patterns)
        if len(df) >= 2:
            prev = df.iloc[-2]
            last = df.iloc[-1]
            # Piercing: previous bear, then bullish that closes > midpoint of previous body
            if (prev['close'] < prev['open']) and (last['close'] > last['open']) and (last['close'] > (prev['open'] + prev['close'])/2):
                patrones.append("Piercing")
            # Dark cloud cover: previous bull then bearish closes below midpoint
            if (prev['close'] > prev['open']) and (last['close'] < last['open']) and (last['close'] < (prev['open'] + prev['close'])/2):
                patrones.append("DarkCloudCover")

        # Harami (two-candle pattern)
        if len(df) >= 2:
            prev = df.iloc[-2]
            last = df.iloc[-1]
            # Harami Bull: prev big bear, last smaller bull inside prev body
            if (prev['close'] < prev['open']) and (last['close'] > last['open']) and (last['open'] > prev['close']) and (last['close'] < prev['open']):
                patrones.append("HaramiBull")
            # Harami Bear:
            if (prev['close'] > prev['open']) and (last['close'] < last['open']) and (last['open'] < prev['close']) and (last['close'] > prev['open']):
                patrones.append("HaramiBear")

        # Tweezer Tops / Bottoms (simple heuristic comparing highs/lows)
        if len(df) >= 2:
            prev = df.iloc[-2]
            last = df.iloc[-1]
            if abs(prev['high'] - last['high']) / max(prev['high'], last['high']) < 0.001:
                patrones.append("TweezerTop")
            if abs(prev['low'] - last['low']) / max(prev['low'], last['low']) < 0.001:
                patrones.append("TweezerBottom")

        # De-duplicar y limpiar
        patrones = list(dict.fromkeys([p for p in patrones if p]))

        if not patrones:
            return ["No pattern detected"]
        return patrones

    except Exception as e:
        _logger.error(f"❌ Error en detectar_patrones_velas: {e}")
        return [f"Error detecting patterns: {e}"]
