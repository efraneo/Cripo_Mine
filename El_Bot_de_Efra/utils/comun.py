# ==========================================================
# utils/comun.py
# ==========================================================
"""
Funciones comunes y utilitarias compartidas por todo el bot.
"""

import os
import pandas as pd
import yfinance as yf
from utils.logger import log_error
from binance.client import Client
from config_loader import API_KEY, API_SECRET
import yaml

# ==========================================================
# 📂 Cargar configuración desde YAML
# ==========================================================
def cargar_config(path: str = "config.yaml") -> dict:
    """
    Carga la configuración desde un archivo YAML.
    - Si no existe, devuelve un diccionario vacío.
    - Maneja errores con log_error.
    """
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
            return config if config else {}
    except Exception as e:
        log_error(e, archivo="utils/comun.py", funcion="cargar_config")
        return {}

# ==========================================================
# 🔧 Otras funciones utilitarias (si deseas agregar más)
# ==========================================================
def normalizar_texto(txt: str) -> str:
    """Devuelve el texto en minúsculas y sin espacios extras."""
    try:
        return str(txt).strip().lower()
    except Exception:
        return ""


def es_float(valor) -> bool:
    """Verifica si un valor puede convertirse en float."""
    try:
        float(valor)
        return True
    except Exception:
        return False


def cargar_activos(mercado=None):
    """
    Carga lista de activos desde activos.csv en la raíz del proyecto.
    Si se especifica 'mercado' ('yahoo' o 'binance'), filtra por ese tipo.
    Retorna una lista de tuplas: (simbolo, mercado)
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "..", "activos.csv")
        df = pd.read_csv(path)

        if mercado:
            df = df[df["mercado"].str.lower() == mercado.lower()]

        return list(zip(df["simbolo"], df["mercado"]))
    except Exception as e:
        log_error(e, archivo="comun.py", funcion="cargar_activos")
        return []

def obtener_datos_yahoo(symbol, interval="1h", period="7d"):
    import yfinance as yf
    import pandas as pd

    # 🔹 Forzar a string si es tuple
    if isinstance(symbol, tuple):
        symbol = symbol[0]

    try:
        df = yf.download(symbol, interval=interval, period=period)
        if not df.empty:
            df.rename(columns=str.lower, inplace=True)
        return df
    except Exception as e:
        from utils.logger import log_error
        log_error(e, archivo="comun.py", funcion="obtener_datos_yahoo")
        return pd.DataFrame()

def obtener_datos_binance(symbol, interval="1h", lookback="60d"):
    """
    Descarga datos OHLC desde Binance usando la API oficial.
    """
    client = Client(API_KEY, API_SECRET)
    try:
        klines = client.get_historical_klines(symbol, interval, lookback)
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df = normalizar_columnas(df)
        return df
    except Exception as e:
        log_error(e, archivo="comun.py", funcion="obtener_datos_binance")
        return pd.DataFrame()

def normalizar_columnas(df):
    """
    Asegura que las columnas OHLC estén en minúsculas estandarizadas.
    También renombra columnas si vienen en español o formatos comunes.
    Devuelve solo las columnas necesarias si están presentes.
    """
    df = df.copy()
    df.columns = [col.lower().strip() for col in df.columns]

    # Renombrar posibles nombres alternativos
    mapeo = {
        "apertura": "open",
        "máximo": "high",
        "minimo": "low",
        "mínimo": "low",
        "cierre": "close",
        "volumen": "volume",
        "fecha": "date",
        "tiempo": "date"
    }
    df.rename(columns=mapeo, inplace=True)

    columnas_requeridas = ["open", "high", "low", "close", "volume"]
    columnas_presentes = [col for col in columnas_requeridas if col in df.columns]

    if not columnas_presentes or len(columnas_presentes) < 4:
        return pd.DataFrame()  # Datos insuficientes

    return df[columnas_presentes]

def leer_csv_seguro(path, **kwargs):
    """
    Lee un archivo CSV con manejo de errores silencioso.
    
    Parámetros:
    - path: Ruta al archivo CSV.
    - **kwargs: Otros argumentos opcionales para `pd.read_csv`.

    Retorna:
    - DataFrame con los datos, o vacío si ocurre un error.
    """
    try:
        return pd.read_csv(path, **kwargs)
    except Exception as e:
        log_error(e, archivo="lectura_segura.py", funcion="leer_csv_seguro")
        print(f"⚠️ Error al leer el archivo: {path}")
        return pd.DataFrame()

import pandas as pd

def agregar_indicadores_tecnicos(df):
    """
    Agrega indicadores RSI, MACD, y volumen al DataFrame de precios.
    El DataFrame debe contener columnas: 'close', 'high', 'low', 'volume'
    """
    try:
        # RSI
        delta = df['close'].diff()
        ganancia = delta.clip(lower=0)
        perdida = -delta.clip(upper=0)
        media_ganancia = ganancia.rolling(14).mean()
        media_perdida = perdida.rolling(14).mean()
        rs = media_ganancia / media_perdida
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = ema_12 - ema_26

        # Tendencia (basada en la pendiente del MACD)
        df['tendencia'] = df['MACD'].diff().apply(lambda x: 'Alcista' if x > 0 else 'Bajista')

        return df
    except Exception as e:
        print(f"Error al calcular indicadores: {e}")
        return df

def tendencia_mercado(df):
    """
    Determina la tendencia del mercado con base en el MACD y RSI.
    Retorna 'Alcista' o 'Bajista'.
    """
    try:
        if df is None or df.empty:
            return "Indefinida"

        macd = df["MACD"].iloc[-1]
        rsi = df["RSI"].iloc[-1]

        if macd > 0 and rsi > 50:
            return "Alcista"
        elif macd < 0 and rsi < 50:
            return "Bajista"
        else:
            return "Indefinida"

    except Exception as e:
        print(f"Error al calcular tendencia: {e}")
        return "Indefinida"

import socket

def hay_conexion_internet(host="8.8.8.8", puerto=53, tiempo_espera=3):
    """
    Verifica si hay conexión a Internet intentando conectar con un DNS público (por defecto Google DNS).
    Retorna True si hay conexión, False en caso contrario.
    """
    try:
        socket.setdefaulttimeout(tiempo_espera)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, puerto))
        return True
    except Exception:
        return False

# ============================================================
# 📂 Función robusta para lectura de CSVs sin romper la app
# ============================================================
import pandas as pd
from utils.logger import log_error

def safe_read_csv(path, expected_cols=None):
    import csv, pandas as pd
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            sample = f.read(2048)
        delimiter = csv.Sniffer().sniff(sample).delimiter
        df = pd.read_csv(path, sep=delimiter, on_bad_lines="skip", engine="python")

        if expected_cols:
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = None
            df = df[[c for c in expected_cols if c in df.columns]]
        return df
    except Exception as e:
        from utils.logger import log_error
        log_error(e, archivo="comun.py", funcion="safe_read_csv")
        return pd.DataFrame()

