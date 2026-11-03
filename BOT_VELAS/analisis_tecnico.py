# ==============================================================================
# ANALISIS_TECNICO.PY - RSI, 16 Patrones Japoneses, Datos Cuantitativos, Sesión
# ==============================================================================
import pandas as pd
from binance.client import Client
from datetime import datetime

# ─── Sesión de Mercado ───────────────────────────────────────────────────────
def obtener_sesion_mercado():
    hora = datetime.now().hour
    if 0 <= hora < 8:   return "🌏 ASIA", 5
    elif 8 <= hora < 14: return "🇪🇺 EUROPA", 10
    elif 14 <= hora < 21: return "🇺🇸 NEW YORK", 15
    else: return "🇺🇸 CIERRE", 5

# ─── Cálculo RSI ─────────────────────────────────────────────────────────────
def calcular_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period, min_periods=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period, min_periods=period).mean()
    rs = gain / loss.replace(0, 0.0001)
    return 100 - (100 / (1 + rs))

# ─── ✅ NUEVO: Detector de las 16 Velas Japonesas (IG.com) ─────────────────
def detectar_16_patrones(df):
    """Escanea las últimas 3 velas y detecta patrones japoneses clásicos"""
    patrones_detectados = []
    if len(df) < 3: return patrones_detectados

    v3, v2, v1 = df.iloc[-3], df.iloc[-2], df.iloc[-1] # v3=antigua, v2=media, v1=actual

    def cuerpo(v): return abs(v['Close'] - v['Open'])
    def mecha_sup(v): return v['High'] - max(v['Open'], v['Close'])
    def mecha_inf(v): return min(v['Open'], v['Close']) - v['Low']
    def es_alcista(v): return v['Close'] > v['Open']
    def es_bajista(v): return v['Close'] < v['Open']

    c1, c2, c3 = cuerpo(v1), cuerpo(v2), cuerpo(v3)
    ms1, mi1 = mecha_sup(v1), mecha_inf(v1)
    ms2, mi2 = mecha_sup(v2), mecha_inf(v2)
    ms3, mi3 = mecha_sup(v3), mecha_inf(v3)

    # 1. Martillo (Hammer) - Bajista -> Alcista
    if not es_alcista(v2) and es_alcista(v1) and c1 > 0 and mi1 > (2.5 * c1) and ms1 < c1:
        patrones_detectados.append("🔨 Martillo (Reversión Alcista)")
    # 2. Hombre Colgado (Hanging Man) - Alcista -> Bajista
    elif es_alcista(v2) and es_alcista(v1) and c1 > 0 and mi1 > (2.5 * c1) and ms1 < c1:
        patrones_detectados.append("🧍 Hombre Colgado (Reversión Bajista)")
    # 3. Martillo Invertido (Inverted Hammer)
    if not es_alcista(v2) and es_alcista(v1) and c1 > 0 and ms1 > (2.5 * c1) and mi1 < c1:
        patrones_detectados.append("🔨 Martillo Invertido")
    # 4. Estrella Fugaz (Shooting Star)
    elif es_alcista(v2) and not es_alcista(v1) and c1 > 0 and ms1 > (2.5 * c1) and mi1 < c1:
        patrones_detectados.append("🌠 Estrella Fugaz (Reversión Bajista)")
    # 5. Doji
    if c1 < (mi1 * 0.1) and c1 < (ms1 * 0.1):
        patrones_detectados.append("✝️ Doji (Indecisión)")
    # 6. Spin Top (Trompo)
    elif c1 < (mi1 * 0.3) and c1 < (ms1 * 0.3) and c1 > 0:
        patrones_detectados.append("🟢 Spin Top (Indecisión leve)")
    # 7. Marubozu Alcista
    if es_alcista(v1) and ms1 < (c1 * 0.05) and mi1 < (c1 * 0.05):
        patrones_detectados.append("⚡ Marubozu Alcista (Fuerza extrema)")
    # 8. Marubozu Bajista
    elif not es_alcista(v1) and ms1 < (c1 * 0.05) and mi1 < (c1 * 0.05):
        patrones_detectados.append("⚡ Marubozu Bajista (Debilidad extrema)")
    # 9. Engulfing Alcista (Avanzamiento Alcista)
    if not es_alcista(v2) and es_alcista(v1) and v1['Close'] > v2['Open'] and v1['Open'] < v2['Close']:
        patrones_detectados.append("🟢 Engulfing Alcista (Fuerte señal)")
    # 10. Engulfing Bajista (Avanzamiento Bajista)
    elif es_alcista(v2) and not es_alcista(v1) and v1['Close'] < v2['Open'] and v1['Open'] > v2['Close']:
        patrones_detectados.append("🔴 Engulfing Bajista (Fuerte señal)")
    # 11. Estrella de la Mañana (Morning Star) - 3 velas
    if not es_alcista(v3) and c2 < c3*0.3 and es_alcista(v1) and v1['Close'] > (v3['Open'] + v3['Close'])/2:
        patrones_detectados.append("🌅 Estrella de la Mañana (Fuerte reversión alcista)")
    # 12. Estrella de la Tarde (Evening Star) - 3 velas
    elif es_alcista(v3) and c2 < c3*0.3 and not es_alcista(v1) and v1['Close'] < (v3['Open'] + v3['Close'])/2:
        patrones_detectados.append("🌆 Estrella de la Tarde (Fuerte reversión bajista)")
    # 13. Bebé Abandonado Alcista (Abandoned Baby Bullish) - 3 velas con Gap
    if not es_alcista(v3) and c2 < (c3*0.1) and es_alcista(v1) and v2['Low'] > v3['High'] and v2['High'] < v1['Low']:
        patrones_detectados.append("👶 Bebé Abandonado Alcista (Muy raro/Fuerte)")
    # 14. Bebé Abandonado Bajista (Abandoned Baby Bearish)
    elif es_alcista(v3) and c2 < (c3*0.1) and not es_alcista(v1) and v2['Low'] > v1['High'] and v2['High'] < v3['Low']:
        patrones_detectados.append("👶 Bebé Abandonado Bajista (Muy raro/Fuerte)")
    # 15. Tres Soldados Blancos (Three White Soldiers)
    if es_alcista(v3) and es_alcista(v2) and es_alcista(v1) and v2['Close'] > v3['Close'] and v1['Close'] > v2['Close']:
        patrones_detectados.append("🙇‍♂️ Tres Soldados Blancos (Tendencia alcista fuerte)")
    # 16. Tres Cuervos Negros (Three Black Crows)
    elif not es_alcista(v3) and not es_alcista(v2) and not es_alcista(v1) and v2['Close'] < v3['Close'] and v1['Close'] < v2['Close']:
        patrones_detectados.append("🐦‍⬛ Tres Cuervos Negros (Tendencia bajista fuerte)")
    # Extra: Pin Bar Alcista/Bajista (Muy usado en scalping)
    if mi1 > (c1 * 3) and ms1 < (c1 * 0.5) and es_alcista(v1):
        patrones_detectados.append("📌 Pin Bar Alcista (Rechazo fuerte)")
    elif ms1 > (c1 * 3) and mi1 < (c1 * 0.5) and not es_alcista(v1):
        patrones_detectados.append("📌 Pin Bar Bajista (Rechazo fuerte)")

    return patrones_detectados if patrones_detectados else ["Ninguno (Sin patrón claro)"]

# ─── Datos Cuantitativos Completos ───────────────────────────────────────────
def obtener_datos_cuantitativos(client, symbol):
    try:
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=20)
        df = pd.DataFrame(klines, columns=['Time','Open','High','Low','Close','Vol','CT','QV','Trades','TBB','TBQ','I'])
        for col in ['Open','High','Low','Close','Vol']: df[col] = df[col].astype(float)

        df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['RSI'] = calcular_rsi(df['Close'], 14)

        ultimo, anterior = df.iloc[-1], df.iloc[-2]
        hace_5 = df.iloc[-6] if len(df) >= 6 else df.iloc[0]
        vol_prom = df['Vol'].tail(5).mean()
        vol_ratio = round(ultimo['Vol'] / vol_prom, 2) if vol_prom > 0 else 1.0
        
        ema9, ema21 = df['EMA_9'].iloc[-1], df['EMA_21'].iloc[-1]
        if ultimo['Close'] > ema9 > ema21:    tendencia = "ALCISTA FUERTE ✅"
        elif ultimo['Close'] > ema9:           tendencia = "ALCISTA SUAVE"
        elif ultimo['Close'] < ema9 < ema21:   tendencia = "BAJISTA FUERTE ⚠️"
        else:                                   tendencia = "BAJISTA SUAVE"

        # ✅ Detectar patrones japoneses
        patrones = detectar_16_patrones(df)
        cuerpo = abs(ultimo['Close'] - ultimo['Open'])
        mecha_inf = min(ultimo['Open'], ultimo['Close']) - ultimo['Low']
        rsi_val = df['RSI'].iloc[-1]

        return {
            'symbol': symbol, 'precio': round(ultimo['Close'], 2),
            'cambio_1v': round(((ultimo['Close'] - anterior['Close']) / anterior['Close']) * 100, 4),
            'cambio_5v': round(((ultimo['Close'] - hace_5['Close']) / hace_5['Close']) * 100, 4),
            'patrones_japoneses': patrones, # ✅ NUEVO
            'tendencia': tendencia, 'ema9': round(ema9, 2), 'ema21': round(ema21, 2),
            'dist_ema9': round(((ultimo['Close'] / ema9) - 1) * 100, 4),
            'rsi': round(rsi_val, 1) if not pd.isna(rsi_val) else 50.0,
            'vol_ratio': vol_ratio, 'es_ballena': vol_ratio >= 2.5,
            'cuerpo': round(cuerpo, 4), 'mecha_inf': round(mecha_inf, 4),
            'mecha_sup': round(ultimo['High'] - max(ultimo['Open'], ultimo['Close']), 4),
            'rango': round(ultimo['High'] - ultimo['Low'], 4),
            'sesion': obtener_sesion_mercado()[0], 'trades': int(ultimo.get('Trades', 0))
        }
    except Exception as e:
        return None
