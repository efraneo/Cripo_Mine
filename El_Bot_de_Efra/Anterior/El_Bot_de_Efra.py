# Bot de Efrain Sarmiento Crespo para Trading

import os
import time
import traceback
import csv
import pytz
import datetime as dt
import pandas as pd
import schedule
import logging
from binance.client import Client
from sklearn.tree import DecisionTreeClassifier
import yfinance as yf
from indicadores_tecnicos import *
from patrones_velas import detectar_patrones_velas
from fibonacci import detectar_niveles_fibonacci
from telegram_alertas import send_telegram_alert, send_telegram_chart
from graficos import generar_grafico_velas
from api_key import api_key, api_secret

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("logs/bot_efra.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Mapeo Yahoo Finance
MAPEO_YAHOO = {
    "XAUUSDT": "GC=F",
    "EURUSDT": "EURUSD=X",
    "GBPUSDT": "GBPUSD=X",
    "US30": "^DJI",
    "NAS100": "^IXIC",
    "DXY": "DX-Y.NYB"
}

# Descargar datos desde Yahoo con reintentos
def descargar_datos_yahoo(ysymbol):
    intentos = [
        ("60m", "1d"),
        ("1d", "1d"),
        ("1d", "7d"),
    ]
    for intervalo, periodo in intentos:
        try:
            df = yf.download(tickers=ysymbol, interval=intervalo, period=periodo, auto_adjust=False, progress=False)
            if not df.empty:
                logger.info(f"✅ Datos obtenidos de Yahoo Finance para {ysymbol} con intervalo {intervalo}, periodo {periodo}")
                return df
        except Exception as e:
            logger.warning(f"⚠️ Error con {ysymbol}: {e}")
    logger.error(f"❌ Yahoo Finance tampoco encontró datos para {ysymbol}")
    return None

client = Client(api_key, api_secret)
RSI_SOBRECOMPRA = 70
RSI_SOBREVENTA = 30
UMBRAL_PRECISION = 0.60
ACTIVOS_FILE = 'activos.txt'

def leer_activos_por_categoria(filepath=ACTIVOS_FILE):
    activos_por_categoria = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for linea in f:
                if ':' in linea:
                    categoria, simbolos = linea.strip().split(':', 1)
                    lista = [s.strip().upper() for s in simbolos.split(',') if s.strip()]
                    activos_por_categoria[categoria.strip()] = lista
        logger.info(f"📄 Activos leídos desde {filepath}")
    except Exception as e:
        logger.error(f"❌ Error al leer el archivo de activos: {e}")
    return activos_por_categoria

def validar_y_clasificar_simbolos(symbols):
    logger.info("🔍 Iniciando validación de símbolos...")
    spot_info = client.get_exchange_info()
    spot_symbols_available = {s['symbol'] for s in spot_info['symbols']}

    try:
        futures_info = client.futures_exchange_info()
        futures_symbols_available = {s['symbol'] for s in futures_info['symbols']}
    except Exception as e:
        logger.warning(f"⚠️ No se pudo obtener info de futuros: {e}")
        futures_symbols_available = set()

    validos = []
    mercados = {}
    invalidos = []

    for symbol in symbols:
        logger.info(f"➡️ Verificando símbolo: {symbol}")

        # Caso especial para el oro
        if symbol.upper() in ["XAUUSDT", "ORO"]:
            ysymbol = "GC=F"
            df = yf.download(ysymbol, interval="1d", period="7d", progress=False, auto_adjust=False)
            if df.empty:
                logger.error(f"❌ No se encontraron datos para el oro desde Yahoo Finance.")
                invalidos.append(symbol)
            else:
                logger.info(f"🏅 {symbol} reconocido como ORO desde Yahoo Finance.")
                validos.append(symbol)
                mercados[symbol] = "oro"
            continue

        if symbol in spot_symbols_available and symbol in futures_symbols_available:
            logger.info(f"📌 {symbol} está en SPOT y FUTUROS.")
            print("1. Spot\n2. Futuros")
            eleccion = input("Selecciona el mercado: ").strip()
            if eleccion == "1":
                validos.append(symbol)
                mercados[symbol] = "spot"
            elif eleccion == "2":
                validos.append(symbol)
                mercados[symbol] = "futuros"
            else:
                logger.warning("❌ Opción inválida.")
                invalidos.append(symbol)
        elif symbol in spot_symbols_available:
            logger.info(f"✅ {symbol} reconocido como SPOT.")
            validos.append(symbol)
            mercados[symbol] = "spot"
        elif symbol in futures_symbols_available:
            logger.info(f"✅ {symbol} reconocido como FUTUROS.")
            validos.append(symbol)
            mercados[symbol] = "futuros"
        else:
            logger.warning(f"⚠️ {symbol} no está en Binance. Intentando buscar en Yahoo Finance...")
            ysymbol = MAPEO_YAHOO.get(symbol, symbol + "=X")
            df = yf.download(ysymbol, interval="1d", period="7d", progress=False, auto_adjust=False)
            if df.empty:
                logger.error(f"❌ Yahoo Finance tampoco encontró datos para {ysymbol}")
                invalidos.append(symbol)
            else:
                logger.info(f"✅ {symbol} reconocido desde Yahoo Finance como 'desconocido'.")
                validos.append(symbol)
                mercados[symbol] = "desconocido"

    logger.info("✅ Validación finalizada.")
    return validos, mercados, invalidos

# --- Obtención de datos robusta ---
def obtener_datos(symbol, mercado, intervalo='1m', periodo='1d'):
    logger.info(f"📥 Obteniendo datos para {symbol} desde {mercado}")

    if mercado in ["oro", "desconocido"]:
        symbol_y = MAPEO_YAHOO.get(symbol, symbol + "=X")
        df = descargar_datos_yahoo(symbol_y)
    elif mercado in ["spot", "futuros"]:
        try:
            klines = client.get_klines(symbol=symbol, interval=intervalo, limit=500)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        except Exception as e:
            logger.error(f"❌ Error al obtener datos de Binance para {symbol}: {e}")
            return None
    else:
        logger.warning(f"⚠️ Mercado no reconocido para {symbol}: {mercado}")
        return None

    if df is not None and not df.empty:
        df.rename(columns=str.lower, inplace=True)
        return df
    else:
        logger.warning(f"📉 Datos vacíos para {symbol}")
        return None

# --- IA ---
def entrenar_y_predecir(df):
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    df.dropna(inplace=True)
    X = df[['rsi', 'macd', 'macd_signal', 'ema_50', 'ema_200']]
    y = df['target']
    model = DecisionTreeClassifier().fit(X, y)
    logger.info("🧠 Modelo entrenado para predicción")
    return ('buy' if model.predict([X.iloc[-1]])[0] else 'sell'), model.score(X, y)

# --- Evaluación ---
def evaluar_estrategia(rsi, macd_signal, tendencia, volumen_fuerte, precision):
    logger.info(f"📋 Evaluando estrategia: RSI={rsi:.2f}, MACD_Signal={macd_signal:.2f}, Tendencia={tendencia}, Volumen fuerte={volumen_fuerte}, Precisión={precision:.2%}")
    if precision < 0.6 or not volumen_fuerte:
        return "NO INVERTIR"
    if rsi < 30 and macd_signal > 0 and tendencia == "Alcista":
        return "COMPRAR"
    if rsi > 70 and macd_signal < 0 and tendencia == "Bajista":
        return "VENDER"
    return "NO INVERTIR"

# --- Ejecución principal ---
def job(symbol):
    logger.info(f"🔁 Iniciando análisis de {symbol}")
    mercado = MERCADO_SYMBOLS[symbol]
    df = obtener_datos(symbol, mercado, intervalo=TIMEFRAME, periodo="7d")

    if df is None or len(df) < 50:
        logger.warning(f"📉 Datos insuficientes para {symbol}")
        send_telegram_alert(f"❌ Datos insuficientes para {symbol}")
        return

    df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
    df = agregar_indicadores_tecnicos(df)
    detectar_patrones_velas(df)
    detectar_niveles_fibonacci(df)

    action, acc = entrenar_y_predecir(df)
    tendencia = tendencia_mercado(df)
    rsi = df['rsi'].iloc[-1]
    macd_signal = df['macd_signal'].iloc[-1]
    volumen = volumen_fuerte(df)

    pred = evaluar_estrategia(rsi, macd_signal, tendencia, volumen, acc)

    resumen = f"""
📊 *Análisis:* {symbol}
🎯 *Precisión:* {acc:.2%}
🤖 *IA sugiere:* {action.upper()}
📌 *Recomendación:* {pred}
"""
    try:
        ts = int(time.time())
        os.makedirs("graficos", exist_ok=True)
        grafico_path = f"graficos/{symbol}_{ts}.png"
        generar_grafico_velas(df, symbol, filepath=grafico_path)
        send_telegram_chart(grafico_path, caption=resumen)
        logger.info(f"🖼️ Gráfico enviado para {symbol}: {grafico_path}")
    except Exception as e:
        logger.warning(f"⚠️ Error al generar o enviar gráfico de {symbol}: {e}")
        send_telegram_alert(resumen)

    logger.info(f"✅ Análisis de {symbol} completado")

# --- Programa principal ---
categorias = leer_activos_por_categoria()
print("\nCategorías:")
for i, cat in enumerate(categorias, 1):
    print(f"{i}. {cat}")

try:
    idx = int(input("Elige una categoría: ")) - 1
    categoria = list(categorias)[idx]
    SYMBOLS = categorias[categoria]
except Exception as e:
    logger.error(f"❌ Opción inválida: {e}")
    print("Opción inválida")
    exit()

SYMBOLS_VALIDOS, MERCADO_SYMBOLS, INVALIDOS = validar_y_clasificar_simbolos(SYMBOLS)
if not SYMBOLS_VALIDOS:
    send_telegram_alert("❌ No hay símbolos válidos")
    exit()

TIMEFRAME = input("🕒 Timeframe (1m, 5m, 15m, 1h, 4h): ").strip()
INTERVAL_MIN = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}.get(TIMEFRAME, 5)

for symbol in SYMBOLS_VALIDOS:
    schedule.every(INTERVAL_MIN).minutes.do(lambda sym=symbol: job(sym))

send_telegram_alert(f"🤖 Bot iniciado. Analizando cada {INTERVAL_MIN} minutos los activos: {', '.join(SYMBOLS_VALIDOS)}")
logger.info("🟢 Bot en ejecución continua")

while True:
    schedule.run_pending()
    time.sleep(1)
