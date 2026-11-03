# utils/binance_data.py
# ==========================================================
# Descarga de velas con fallback multi-fuente + indicadores
# ==========================================================

import pandas as pd
import time
from typing import Optional
from utils.logger import log_info, log_error, log_warning

try:
    from binance.client import Client
except Exception:
    Client = None

try:
    from trading_bot import TradingBot
except Exception:
    TradingBot = None


def _binance_fetch(symbol: str, interval: str = "1m", limit: int = 500,
                   api_key: Optional[str] = None, api_secret: Optional[str] = None) -> pd.DataFrame:
    """Descarga directa desde Binance, con manejo de errores y retries."""
    if Client is None:
        log_warning("python-binance no instalado, no se puede usar Binance", archivo="binance_data.py", funcion="_binance_fetch")
        return pd.DataFrame()

    for intento in range(3):
        try:
            client = Client(api_key, api_secret)
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines:
                time.sleep(1)
                continue

            df = pd.DataFrame(
                klines,
                columns=[
                    "timestamp", "open", "high", "low", "close", "volume",
                    "close_time", "quote_asset_volume", "number_of_trades",
                    "taker_buy_base", "taker_buy_quote", "ignore"
                ]
            )
            df["fecha"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("fecha", inplace=True)
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df[["open", "high", "low", "close", "volume"]]

        except Exception as e:
            log_warning(f"Intento {intento + 1}/3 fallido: {e}", archivo="binance_data.py", funcion="_binance_fetch")
            time.sleep(2 + intento)

    log_error("❌ Binance API no respondió tras 3 intentos.", archivo="binance_data.py", funcion="_binance_fetch")
    return pd.DataFrame()


def obtener_velas_binance(symbol: str, interval: str = "1m", limit: int = 500,
                          api_key: Optional[str] = None, api_secret: Optional[str] = None) -> pd.DataFrame:
    """Descarga velas (Binance o fallback). Calcula indicadores técnicos."""
    df = _binance_fetch(symbol, interval, limit, api_key, api_secret)
    if df is not None and not df.empty:
        log_info(f"✅ Velas obtenidas desde Binance ({symbol}, {interval})", archivo="binance_data.py", funcion="obtener_velas_binance")
        try:
            import ta
            df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
            macd_ind = ta.trend.MACD(df["close"])
            df["macd"] = macd_ind.macd()
            df["macd_signal"] = macd_ind.macd_signal()
            df["ma_fast"] = df["close"].rolling(window=9).mean()
            df["ma_slow"] = df["close"].rolling(window=21).mean()
        except Exception as e:
            log_warning(f"No se pudieron calcular indicadores: {e}", archivo="binance_data.py", funcion="obtener_velas_binance")
        return df

    # Fallback a otras fuentes
    if TradingBot:
        bot = TradingBot()
        fuentes = [
            ("Binance (interno)", bot.obtener_datos_binance),
            ("AlphaVantage", bot.obtener_datos_alphavantage),
            ("TwelveData", bot.obtener_datos_twelvedata),
            ("Yahoo", bot.obtener_datos_yahoo),
            ("CSV local", bot.obtener_datos_csv),
            ("Random Simulado", bot.obtener_datos_random),
        ]
        for nombre, fn in fuentes:
            try:
                df = fn(symbol, interval=interval, limit=limit)
                if df is not None and not df.empty:
                    log_info(f"✅ Velas obtenidas desde {nombre} ({symbol}, {interval})", archivo="binance_data.py", funcion="obtener_velas_binance")
                    import ta
                    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
                    macd_ind = ta.trend.MACD(df["close"])
                    df["macd"] = macd_ind.macd()
                    df["macd_signal"] = macd_ind.macd_signal()
                    df["ma_fast"] = df["close"].rolling(window=9).mean()
                    df["ma_slow"] = df["close"].rolling(window=21).mean()
                    return df
            except Exception as e:
                log_warning(f"⚠️ Error en fuente {nombre}: {e}", archivo="binance_data.py", funcion="obtener_velas_binance")

    log_error(f"❌ Ninguna fuente devolvió datos para {symbol}", archivo="binance_data.py", funcion="obtener_velas_binance")
    df_vacio = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df_vacio.attrs["__empty__"] = True
    return df_vacio
