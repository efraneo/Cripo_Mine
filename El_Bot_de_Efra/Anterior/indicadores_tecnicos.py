# === indicadores_tecnicos.py ===
import pandas as pd
import numpy as np
import logging
import os
import ta
from utils.logger import log_error
from binance.client import Client
import yfinance as yf

def agregar_import_yfinance():
    try:
        import yfinance as yf
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
        import yfinance as yf

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# Claves API desde variables de entorno
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = Client(api_key, api_secret)

# Símbolos no disponibles en Binance
SIMBOLOS_NO_BINANCE = {
    'XAUUSDT': 'GC=F',
    'XAGUSDT': 'SI=F',
    'GOLDUSDT': 'GC=F',
    'SILVERUSDT': 'SI=F'
}

# === Validación y limpieza de datos ===
def validar_y_limpiar_datos(df):
    try:
        columnas_requeridas = ['open', 'high', 'low', 'close', 'volume']
        if df is None or df.empty:
            raise ValueError("El DataFrame está vacío.")
        if not all(col in df.columns for col in columnas_requeridas):
            raise ValueError(f"Faltan columnas requeridas: {columnas_requeridas}")

        df.drop_duplicates(inplace=True)
        df.dropna(subset=columnas_requeridas, inplace=True)
        df = df.astype(float)

        if len(df) < 200:
            raise ValueError("Datos insuficientes después de limpieza (min: 200 filas).")

        return df
    except Exception as e:
        logging.warning(f"❌ Error en validación/limpieza de datos: {e}")
        return pd.DataFrame()

# === Funciones para obtener datos ===
def obtener_datos_binance(symbol, interval):
    try:
        if symbol.upper() in SIMBOLOS_NO_BINANCE:
            logging.info(f"🔄 Redirigiendo {symbol} a Yahoo Finance ({SIMBOLOS_NO_BINANCE[symbol.upper()]})")
            return None

        klines = client.get_klines(symbol=symbol.upper(), interval=interval, limit=1000)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df

    except Exception as e:
        logging.warning(f"❌ Error al obtener datos de Binance para {symbol} ({interval}): {e}")
        return None

def obtener_datos_yahoo(symbol, intervalo='1h', periodo='7d'):
    try:
        df = yf.download(symbol, interval=intervalo, period=periodo, progress=False)
        if df is None or df.empty:
            raise ValueError("Yahoo Finance devolvió un DataFrame vacío.")

        df.reset_index(inplace=True)
        df.columns = [c.lower() for c in df.columns]
        df.rename(columns={"date": "fecha"}, inplace=True)
        return df
    except Exception as e:
        logging.error(f"Error en obtener_datos_yahoo para {symbol}")
        logging.error(e, exc_info=True)
        return pd.DataFrame()

# ==============================
# 🧠 Validar símbolo antes de intentar descargar
# ==============================

VALID_SYMBOLS_YF = {
    'XAGUSD=X': 'Silver',
    'XAUUSD=X': 'Gold',
    'EURUSD=X': 'Euro/Dólar',
    'USDJPY=X': 'Dólar/Yen',
    'GBPUSD=X': 'Libra/Dólar',
    # Puedes expandir esta lista o generar dinámicamente
}

def es_simbolo_valido_yahoo(symbol):
    prueba = yf.download(symbol, period="1d", interval="1d", progress=False)
    return not prueba.empty

# === Agregar indicadores ===
def agregar_indicadores_tecnicos(df):
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            raise ValueError("DataFrame inválido tras limpieza.")

        # Indicadores para IA y estrategias
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        macd = ta.trend.MACD(df['close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['ema_10'] = ta.trend.EMAIndicator(df['close'], window=10).ema_indicator()  # ➕ IA
        df['ema_50'] = ta.trend.EMAIndicator(df['close'], window=50).ema_indicator()
        df['ema_200'] = ta.trend.EMAIndicator(df['close'], window=200).ema_indicator()
        df['sma_20'] = ta.trend.SMAIndicator(df['close'], window=20).sma_indicator()  # ➕ Estrategia
        df['sma_50'] = ta.trend.SMAIndicator(df['close'], window=50).sma_indicator()  # ➕ Estrategia

        df.dropna(inplace=True)
        return df

    except Exception as e:
        logging.warning(f"❌ Error al calcular indicadores técnicos: {e}")
        return df if df is not None else pd.DataFrame()

# === Tendencia y volumen ===
def tendencia_mercado(df):
    try:
        if df is None or df.empty:
            return 'Indefinida'
        if df['ema_50'].iloc[-1] > df['ema_200'].iloc[-1]:
            return 'Alcista'
        elif df['ema_50'].iloc[-1] < df['ema_200'].iloc[-1]:
            return 'Bajista'
        else:
            return 'Lateral'
    except Exception as e:
        logging.warning(f"❌ Error al detectar tendencia: {e}")
        return 'Indefinida'

def volumen_fuerte(df, ventana=10, umbral=1.2):
    try:
        if df is None or df.empty or 'volume' not in df.columns:
            raise ValueError("DataFrame inválido o sin columna 'volume'.")

        if len(df) < ventana:
            return False

        volumen_actual = df['volume'].iloc[-1]
        volumen_medio = df['volume'].rolling(window=ventana).mean().iloc[-1]

        if pd.isna(volumen_medio):
            return False

        return volumen_actual > umbral * volumen_medio

    except Exception as e:
        logging.warning(f"❌ Error al detectar volumen fuerte: {e}")
        return False
