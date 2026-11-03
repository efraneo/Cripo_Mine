# ==========================================================
# utils/data_providers.py
# ==========================================================
# Proveedor de datos externo (Alpha Vantage) como fallback
# ==========================================================

import os
import requests
import pandas as pd
import logging
from utils.logger import log_error


# ==========================================================
# 🔑 Configuración
# ==========================================================
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", None)


# ==========================================================
# 📊 Fetch Alpha Vantage
# ==========================================================
def obtener_datos_alphavantage(symbol: str, intervalo: str = "5min", output: str = "compact") -> pd.DataFrame:
    """
    Obtiene datos OHLCV de Alpha Vantage como fallback si Binance y Yahoo fallan.

    Parámetros:
    -----------
    symbol : str
        Símbolo del activo (ej. "AAPL", "BTCUSD").
    intervalo : str
        Intervalo soportado por Alpha Vantage
        (1min, 5min, 15min, 30min, 60min, daily, weekly, monthly).
    output : str
        "compact" (últimas 100 velas) o "full" (todas las disponibles).

    Retorna:
    --------
    pd.DataFrame con columnas [open, high, low, close, volume].
    """
    if not ALPHAVANTAGE_API_KEY:
        logging.warning("⚠️ No se configuró ALPHAVANTAGE_API_KEY en credenciales.env")
        return pd.DataFrame()

    try:
        # Construcción dinámica de la URL según el intervalo
        if intervalo in ["daily", "weekly", "monthly"]:
            fn_map = {"daily": "TIME_SERIES_DAILY", "weekly": "TIME_SERIES_WEEKLY", "monthly": "TIME_SERIES_MONTHLY"}
            fn = fn_map.get(intervalo, "TIME_SERIES_DAILY")
            url = f"https://www.alphavantage.co/query?function={fn}&symbol={symbol}&outputsize={output}&apikey={ALPHAVANTAGE_API_KEY}"
            key = f"{fn.replace('_', ' ').title()} Time Series"
        else:
            url = (
                f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY"
                f"&symbol={symbol}&interval={intervalo}&outputsize={output}&apikey={ALPHAVANTAGE_API_KEY}"
            )
            key = f"Time Series ({intervalo})"

        response = requests.get(url, timeout=15)
        data = response.json()

        if key not in data:
            logging.warning(f"⚠️ Alpha Vantage no devolvió datos para {symbol}")
            return pd.DataFrame()

        # Normalizar datos
        df = pd.DataFrame.from_dict(data[key], orient="index", dtype=float)
        df.rename(
            columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume",
            },
            inplace=True,
        )
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)

        logging.info(f"✅ Alpha Vantage entregó {len(df)} velas para {symbol}")
        return df

    except Exception as e:
        log_error(e, archivo="data_providers.py", funcion="obtener_datos_alphavantage")
        return pd.DataFrame()
