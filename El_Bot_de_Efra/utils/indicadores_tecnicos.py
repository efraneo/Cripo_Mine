# ============================================================
# utils/indicadores_tecnicos.py
# ============================================================
# Indicadores técnicos, tendencia de mercado, ATR, pullbacks
# y cálculos de niveles de entrada/salida.
# Versión reforzada con logging seguro y validaciones robustas.
# ============================================================

import os
import pandas as pd
import numpy as np
import logging
import ta  # Librería de indicadores técnicos
import yfinance as yf
from binance.client import Client
from utils.comun import safe_read_csv

# ===================== LOGGING HELPERS ======================
def _safe_import(module_name: str, attr: str, default=None):
    """Intenta importar dinámicamente un atributo, con fallback."""
    try:
        mod = __import__(module_name, fromlist=[attr])
        return getattr(mod, attr)
    except Exception:
        return default

log_error   = _safe_import("utils.logger", "log_error",   default=lambda e=None, archivo=None, funcion=None: logging.error(f"{archivo}.{funcion} -> {e}"))
log_info    = _safe_import("utils.logger", "log_info",    default=lambda msg=None, archivo=None, funcion=None: logging.info(f"{archivo}.{funcion} -> {msg}"))
log_warning = _safe_import("utils.logger", "log_warning", default=lambda msg=None, archivo=None, funcion=None: logging.warning(f"{archivo}.{funcion} -> {msg}"))

# ====================== CLIENT BINANCE ======================
# Si no hay credenciales, se puede usar solo para endpoints públicos
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
try:
    client = Client(BINANCE_API_KEY, BINANCE_API_SECRET)
except Exception as e:
    log_warning(f"No se pudo inicializar cliente Binance: {e}", archivo="indicadores_tecnicos.py", funcion="init_client")
    client = None

# ==================== VALIDACIONES BASE =====================
def validar_y_limpiar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Valida columnas mínimas y limpia nulos.
    Retorna DataFrame limpio o vacío si falla.
    """
    try:
        if df is None or df.empty:
            return pd.DataFrame()

        required = {"open", "high", "low", "close", "volume"}
        faltantes = required - set(df.columns)
        if faltantes:
            raise ValueError(f"Faltan columnas: {faltantes}")

        df = df.copy()
        df = df.replace([np.inf, -np.inf], np.nan).dropna()
        df = df.astype(float, errors="ignore")

        return df
    except Exception as e:
        log_warning(f"❌ Error en validación/limpieza de datos: {e}", archivo="indicadores_tecnicos.py", funcion="validar_y_limpiar_datos")
        return pd.DataFrame()

# ============================================================
# 📊 Descarga de datos (Binance + Yahoo Finance)
# ============================================================

def obtener_datos_binance(activo: str, intervalo: str = "1h", limite: int = 500):
    from binance.client import Client
    from utils.security import descifrar
    claves = get_claves_binance()  # según tu estructura
    api_key = descifrar(claves["clave1_binance"])
    api_secret = descifrar(claves["clave2_binance"])
    client = Client(api_key, api_secret)
    klines = client.get_klines(symbol=activo, interval=intervalo, limit=limite)
    df = pd.DataFrame(klines, columns=[
        "open_time","open","high","low","close","volume","close_time",
        "quote_asset_volume","number_of_trades",
        "taker_buy_base","taker_buy_quote","ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    df = df.astype(float, errors="ignore")
    return df



def obtener_datos_yahoo(symbol: str, interval="1h", period="60d"):
    """
    Descarga datos OHLCV desde Yahoo Finance.
    Devuelve DataFrame con columnas: open, high, low, close, volume.
    """
    try:
        df = yf.download(symbol, interval=interval, period=period, progress=False)
        if df.empty:
            return pd.DataFrame()

        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "close", "Volume": "volume"
        })
        df = df[["open", "high", "low", "close", "volume"]]

        return validar_y_limpiar_datos(df)

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="obtener_datos_yahoo")
        return pd.DataFrame()


# ============================================================
# 📈 Agregar indicadores técnicos
# ============================================================

def agregar_indicadores_tecnicos(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade indicadores técnicos al DataFrame.
    Devuelve DataFrame extendido con columnas nuevas.
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return df

        # RSI
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

        # MACD
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()

        # Medias móviles
        df["ema_10"] = ta.trend.EMAIndicator(df["close"], window=10).ema_indicator()
        df["ema_50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
        df["ema_200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()

        # Volatilidad
        df["atr"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        ).average_true_range()

        # Bandas de Bollinger
        boll = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
        df["bb_bbm"] = boll.bollinger_mavg()
        df["bb_bbh"] = boll.bollinger_hband()
        df["bb_bbl"] = boll.bollinger_lband()

        return df.dropna()

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="agregar_indicadores_tecnicos")
        return df

# ============================================================
# 📊 Tendencia de mercado
# ============================================================

def tendencia_mercado(df: pd.DataFrame, window_fast=10, window_slow=50) -> str:
    """
    Determina la tendencia del mercado usando medias móviles.
    - window_fast: periodo corto (default 10)
    - window_slow: periodo largo (default 50)

    Devuelve:
        "alcista", "bajista" o "lateral"
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty or "close" not in df.columns:
            return "sin_datos"

        ema_fast = df["close"].ewm(span=window_fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=window_slow, adjust=False).mean()

        if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
            return "alcista"
        elif ema_fast.iloc[-1] < ema_slow.iloc[-1]:
            return "bajista"
        else:
            return "lateral"

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="tendencia_mercado")
        return "error"


# ============================================================
# 🔄 Detección de Pullbacks
# ============================================================

def detectar_pullback(df: pd.DataFrame, window=20, umbral=0.02) -> str:
    """
    Detecta pullbacks en el precio en función de una media móvil.
    - window: periodo de la media móvil
    - umbral: porcentaje de retroceso aceptado

    Devuelve:
        "pullback_buy", "pullback_sell" o "no_pullback"
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty or "close" not in df.columns:
            return "no_pullback"

        ma = df["close"].rolling(window=window, min_periods=1).mean()
        precio = df["close"].iloc[-1]
        ma_val = ma.iloc[-1]

        if precio > ma_val * (1 + umbral):
            return "pullback_buy"
        elif precio < ma_val * (1 - umbral):
            return "pullback_sell"
        else:
            return "no_pullback"

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="detectar_pullback")
        return "error"


# ============================================================
# 🎯 Calcular entrada ideal
# ============================================================

def calcular_entrada_ideal(df: pd.DataFrame, tipo_pullback: str, riesgo_pct=0.02) -> dict:
    """
    Calcula un punto de entrada ideal basado en pullbacks detectados.
    - tipo_pullback: "pullback_buy" o "pullback_sell"
    - riesgo_pct: porcentaje de riesgo para definir SL y TP

    Devuelve:
        dict con {"entrada": float, "sl": float, "tp": float}
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty or "close" not in df.columns:
            return {}

        precio_actual = df["close"].iloc[-1]

        if tipo_pullback == "pullback_buy":
            sl = precio_actual * (1 - riesgo_pct)
            tp = precio_actual * (1 + riesgo_pct * 2)
            return {"entrada": precio_actual, "sl": sl, "tp": tp}

        elif tipo_pullback == "pullback_sell":
            sl = precio_actual * (1 + riesgo_pct)
            tp = precio_actual * (1 - riesgo_pct * 2)
            return {"entrada": precio_actual, "sl": sl, "tp": tp}

        return {}

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="calcular_entrada_ideal")
        return {}

# ============================================================
# 🟢🔴 Soportes y Resistencias
# ============================================================

def detectar_soportes_resistencias(df: pd.DataFrame, window=20) -> dict:
    """
    Detecta soportes y resistencias básicos en una ventana de precios.
    - window: número de velas a considerar

    Devuelve:
        {"soporte": float, "resistencia": float}
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return {"soporte": None, "resistencia": None}

        soporte = df["low"].tail(window).min()
        resistencia = df["high"].tail(window).max()

        return {"soporte": soporte, "resistencia": resistencia}

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="detectar_soportes_resistencias")
        return {"soporte": None, "resistencia": None}


# ============================================================
# ✅ Confirmación de Señales
# ============================================================

def confirmar_senal(df: pd.DataFrame, accion: str, tolerancia=0.02) -> bool:
    """
    Confirma una señal de compra/venta usando niveles técnicos.
    - accion: "buy" o "sell"
    - tolerancia: margen de error permitido

    Devuelve:
        True si la señal se confirma, False si no.
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty or "close" not in df.columns:
            return False

        precio = df["close"].iloc[-1]
        niveles = detectar_soportes_resistencias(df)

        if accion == "buy" and precio > niveles["soporte"] * (1 + tolerancia):
            return True
        if accion == "sell" and precio < niveles["resistencia"] * (1 - tolerancia):
            return True

        return False

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="confirmar_senal")
        return False


# ============================================================
# 🔮 Proyecciones futuras simples
# ============================================================

def proyectar_precio(df: pd.DataFrame, pasos=5) -> list:
    """
    Proyecta el precio futuro usando una regresión lineal básica.
    - pasos: número de velas a proyectar

    Devuelve:
        lista con precios proyectados
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty or "close" not in df.columns:
            return []

        from sklearn.linear_model import LinearRegression
        import numpy as np

        y = df["close"].values
        X = np.arange(len(y)).reshape(-1, 1)

        modelo = LinearRegression()
        modelo.fit(X, y)

        X_pred = np.arange(len(y), len(y) + pasos).reshape(-1, 1)
        predicciones = modelo.predict(X_pred)

        return predicciones.tolist()

    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="proyectar_precio")
        return []

# ============================================================
# 🛠️ Funciones auxiliares y utilidades finales
# ============================================================

def normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza los nombres de columnas del DataFrame a minúsculas estándar.
    - Convierte Open, High, Low, Close, Volume a open, high, low, close, volume.
    """
    try:
        mapping = {
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "close",
            "Volume": "volume"
        }
        return df.rename(columns={c: mapping.get(c, c.lower()) for c in df.columns})
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="normalizar_columnas")
        return df


def combinar_indicadores(df: pd.DataFrame, indicadores: list) -> pd.DataFrame:
    """
    Combina múltiples indicadores técnicos en un solo DataFrame.
    - indicadores: lista de funciones a aplicar sobre df.

    Devuelve un DataFrame enriquecido con todas las columnas de indicadores.
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return df

        for indicador_fn in indicadores:
            try:
                df_temp = indicador_fn(df.copy())
                if isinstance(df_temp, pd.DataFrame):
                    df = df.join(df_temp, how="outer")
            except Exception as e:
                log_warning(f"Error aplicando {indicador_fn.__name__}: {e}",
                            archivo="indicadores_tecnicos.py", funcion="combinar_indicadores")

        return df
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="combinar_indicadores")
        return df


def resumen_indicadores(df: pd.DataFrame) -> dict:
    """
    Genera un resumen con los últimos valores de indicadores clave.
    Incluye RSI, MACD, MACD signal, tendencia, soporte y resistencia.
    """
    try:
        if df is None or df.empty:
            return {}

        resumen = {
            "rsi": float(df["rsi"].iloc[-1]) if "rsi" in df.columns else None,
            "macd": float(df["macd"].iloc[-1]) if "macd" in df.columns else None,
            "macd_signal": float(df["macd_signal"].iloc[-1]) if "macd_signal" in df.columns else None,
            "tendencia": tendencia_mercado(df),
        }

        niveles = detectar_soportes_resistencias(df)
        resumen.update(niveles)

        return resumen
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="resumen_indicadores")
        return {}

# ============================================================
# 📌 Wrappers de indicadores clásicos (compatibilidad)
# ============================================================

def calcular_rsi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """
    Calcula RSI y devuelve una Serie con los valores.
    Compatible con backtesting.py y app.py.
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return pd.Series(dtype=float)
        rsi = ta.momentum.RSIIndicator(df["close"], window=window).rsi()
        return rsi
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="calcular_rsi")
        return pd.Series(dtype=float)


def calcular_macd(df: pd.DataFrame, short: int = 12, long: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    Calcula MACD, MACD Signal y MACD Diff.
    Devuelve un DataFrame con las tres columnas.
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return pd.DataFrame(columns=["macd", "macd_signal", "macd_diff"])
        macd = ta.trend.MACD(df["close"], window_slow=long, window_fast=short, window_sign=signal)
        return pd.DataFrame({
            "macd": macd.macd(),
            "macd_signal": macd.macd_signal(),
            "macd_diff": macd.macd_diff()
        }, index=df.index)
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="calcular_macd")
        return pd.DataFrame(columns=["macd", "macd_signal", "macd_diff"])


def calcular_ema(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """
    Calcula una media móvil exponencial (EMA).
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return pd.Series(dtype=float)
        ema = ta.trend.EMAIndicator(df["close"], window=window).ema_indicator()
        return ema
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="calcular_ema")
        return pd.Series(dtype=float)


def calcular_sma(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    Calcula una media móvil simple (SMA).
    """
    try:
        df = validar_y_limpiar_datos(df)
        if df.empty:
            return pd.Series(dtype=float)
        sma = df["close"].rolling(window=window, min_periods=1).mean()
        return sma
    except Exception as e:
        log_error(e, archivo="indicadores_tecnicos.py", funcion="calcular_sma")
        return pd.Series(dtype=float)


# ============================================================
# 🧪 Pruebas rápidas (solo si se ejecuta directamente)
# ============================================================
if __name__ == "__main__":
    import yfinance as yf
    simbolo = "BTC-USD"
    print(f"🔎 Descargando datos de prueba para {simbolo}...")
    df_test = yf.download(simbolo, period="7d", interval="1h")
    df_test = normalizar_columnas(df_test)

    print("📊 Calculando indicadores...")
    df_ind = agregar_indicadores_tecnicos(df_test)
    print(resumen_indicadores(df_ind))
