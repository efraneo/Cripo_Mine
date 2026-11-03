"""
utils/data_fetcher.py
---------------------
Multiproveedor de velas OHLCV + wrappers de compatibilidad.

Exporta (entre otras):
- get_candles_multi(symbol, interval="1m", mercado="spot", min_rows=200, preferred=None)
- obtener_datos_con_fallback(symbol, interval="1h", mercado="spot", min_rows=200)
- obtener_datos_bin(symbol, interval="1h", lookback="30d")
- obtener_datos_yahoo(symbol, interval="1h", period="60d")
- fetch_binance_spot, fetch_binance_futures, fetch_yahoo, fetch_bybit, fetch_okx, fetch_coinbase, fetch_kraken
"""

import time, os, logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import requests

# Intento importar yfinance si está instalado
try:
    import yfinance as yf
except Exception:
    yf = None

from utils.logger import log_info, log_warning, log_error

# Columnas requeridas
REQ_COLS = ["open", "high", "low", "close", "volume"]


# ==========================================================
# 🔧 Helpers
# ==========================================================
def _to_dt_ms(x):
    """Convierte timestamp (ms o s) a datetime UTC."""
    x = int(x)
    if x > 10_000_000_000:  # milisegundos
        return datetime.fromtimestamp(x / 1000, tz=timezone.utc)
    return datetime.fromtimestamp(x, tz=timezone.utc)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza DataFrame para asegurar columnas estándar y DatetimeIndex.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=REQ_COLS)

    # Mapeo flexible de nombres de columnas
    mapping = {
        "o": "open", "open": "open", "Open": "open",
        "h": "high", "High": "high", "high": "high",
        "l": "low", "Low": "low", "low": "low",
        "c": "close", "C": "close", "Close": "close", "close": "close",
        "v": "volume", "V": "volume", "Volume": "volume", "volume": "volume",
    }
    cols = {c: mapping.get(c, c) for c in df.columns}
    df = df.rename(columns=cols).copy()

    # Identificar columna de tiempo
    if not isinstance(df.index, pd.DatetimeIndex):
        for cand in ["time", "datetime", "timestamp", "open_time", "close_time", "Date", "date", "t"]:
            if cand in df.columns:
                try:
                    df["__dt__"] = pd.to_datetime(df[cand], errors="coerce", utc=True)
                    df = df.drop(columns=[cand])
                    df = df.set_index("__dt__")
                    break
                except Exception:
                    continue

    # Forzar columnas numéricas
    for c in REQ_COLS:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Limpiar y ordenar
    df = df.dropna(subset=["open", "high", "low", "close"], how="any")
    df = df[REQ_COLS]
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Expect data.index as DatetimeIndex")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df

# ==========================================================
# 📡 Fetchers por proveedor (Binance + Yahoo)
# ==========================================================
def fetch_binance_spot(symbol: str, interval: str = "1m", min_rows: int = 200, max_calls: int = 5) -> pd.DataFrame:
    """
    Descarga velas de Binance Spot.
    - Intenta múltiples llamadas hasta alcanzar min_rows.
    - Devuelve DataFrame normalizado.
    """
    try:
        base = "https://api.binance.com"
        iv = interval
        limit = 1000 if min_rows > 500 else 500
        df_all = []
        end_time = None

        for _ in range(max_calls):
            params = {"symbol": symbol.upper(), "interval": iv, "limit": limit}
            if end_time:
                params["endTime"] = end_time
            r = requests.get(f"{base}/api/v3/klines", params=params, timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break

            rows = [{
                "time": _to_dt_ms(k[0]),
                "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[5]),
            } for k in data]

            df = pd.DataFrame(rows).set_index("time")
            df_all.append(df)
            end_time = int(data[0][0]) - 1  # retroceder en el tiempo
            if sum(len(x) for x in df_all) >= min_rows:
                break
            time.sleep(0.12)

        if not df_all:
            return pd.DataFrame()

        out = pd.concat(df_all, axis=0).sort_index()
        return _normalize_df(out).tail(max(min_rows, 1))

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="fetch_binance_spot")
        return pd.DataFrame()


def fetch_binance_futures(symbol: str, interval: str = "1m", min_rows: int = 200, max_calls: int = 5) -> pd.DataFrame:
    """
    Descarga velas de Binance Futures.
    Similar a Spot pero usando el endpoint de futuros.
    """
    try:
        base = "https://fapi.binance.com"
        iv = interval
        limit = 1000 if min_rows > 500 else 500
        df_all = []
        end_time = None

        for _ in range(max_calls):
            params = {"symbol": symbol.upper(), "interval": iv, "limit": limit}
            if end_time:
                params["endTime"] = end_time
            r = requests.get(f"{base}/fapi/v1/klines", params=params, timeout=10)
            if r.status_code != 200:
                break
            data = r.json()
            if not data:
                break

            rows = [{
                "time": _to_dt_ms(k[0]),
                "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[5]),
            } for k in data]

            df = pd.DataFrame(rows).set_index("time")
            df_all.append(df)
            end_time = int(data[0][0]) - 1
            if sum(len(x) for x in df_all) >= min_rows:
                break
            time.sleep(0.12)

        if not df_all:
            return pd.DataFrame()

        out = pd.concat(df_all, axis=0).sort_index()
        return _normalize_df(out).tail(max(min_rows, 1))

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="fetch_binance_futures")
        return pd.DataFrame()


def fetch_yahoo(symbol: str, interval: str = "1m", min_rows: int = 200) -> pd.DataFrame:
    """
    Intenta cargar velas desde Yahoo Finance con yfinance.
    Incluye fallback a símbolos equivalentes (USDT → USD).
    """
    try:
        if yf is None:
            log_warning("yfinance no disponible", archivo="data_fetcher.py", funcion="fetch_yahoo")
            return pd.DataFrame()

        # mapeo simple (interval -> periodo)
        map_iv = {
            "1m": ("1m", "7d"), "5m": ("5m", "30d"), "15m": ("15m", "60d"),
            "30m": ("30m", "60d"), "1h": ("60m", "730d"), "1d": ("1d", "10y")
        }
        iv, period = map_iv.get(interval, ("15m", "60d"))

        # Probar símbolo original y variantes (ej: ETHUSDT → ETHUSD)
        for s in [symbol, _maybe_usd_symbol(symbol)]:
            try:
                df = yf.download(s, interval=iv, period=period, progress=False, auto_adjust=False)
                if df is None or df.empty:
                    continue
                df = df.rename(columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume", "Adj Close": "close"
                })
                df.index = pd.to_datetime(df.index, utc=True)
                out = _normalize_df(df)
                if not out.empty:
                    return out.tail(max(min_rows, 1))
            except Exception:
                continue

        return pd.DataFrame()

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="fetch_yahoo")
        return pd.DataFrame()

# ==========================================================
# 📡 Fetchers por proveedor (Bybit, OKX, Coinbase, Kraken)
# ==========================================================
def fetch_bybit(symbol: str, interval: str = "1m", min_rows: int = 200) -> pd.DataFrame:
    """Descarga velas de Bybit (linear)."""
    try:
        base = "https://api.bybit.com"
        map_iv = {"1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
                  "1h": "60", "4h": "240", "1d": "D"}
        iv = map_iv.get(interval, "1")

        params = {"category": "linear", "symbol": symbol.upper(), "interval": iv,
                  "limit": min(1000, max(200, min_rows))}
        r = requests.get(f"{base}/v5/market/kline", params=params, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json().get("result", {}).get("list", [])
        if not data:
            return pd.DataFrame()

        rows = [{
            "time": _to_dt_ms(k[0]),
            "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]),
            "volume": float(k[5])
        } for k in data[::-1]]

        return _normalize_df(pd.DataFrame(rows).set_index("time")).tail(max(min_rows, 1))

    except Exception as e:
        log_warning(f"Bybit fallback error: {e}", archivo="data_fetcher.py", funcion="fetch_bybit")
        return pd.DataFrame()


def fetch_okx(symbol: str, interval: str = "1m", min_rows: int = 200) -> pd.DataFrame:
    """Descarga velas de OKX (instId)."""
    try:
        base = "https://www.okx.com"
        inst = symbol.upper().replace("USDT", "-USDT").replace("USD", "-USD")
        map_iv = {"1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
                  "1h": "1H", "4h": "4H", "1d": "1D"}
        bar = map_iv.get(interval, "1m")

        r = requests.get(f"{base}/api/v5/market/candles",
                         params={"instId": inst, "bar": bar,
                                 "limit": min(500, max(200, min_rows))},
                         timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()

        rows = [{
            "time": _to_dt_ms(k[0]),
            "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]),
            "volume": float(k[5])
        } for k in data[::-1]]

        return _normalize_df(pd.DataFrame(rows).set_index("time")).tail(max(min_rows, 1))

    except Exception as e:
        log_warning(f"OKX fallback error: {e}", archivo="data_fetcher.py", funcion="fetch_okx")
        return pd.DataFrame()


def fetch_coinbase(symbol: str, interval: str = "1m", min_rows: int = 200) -> pd.DataFrame:
    """Descarga velas de Coinbase."""
    try:
        base = "https://api.exchange.coinbase.com"
        product = symbol.upper().replace("USDT", "-USDT").replace("USD", "-USD")
        gran = {"1m": 60, "3m": 180, "5m": 300, "15m": 900,
                "30m": 1800, "1h": 3600, "1d": 86400}.get(interval, 60)

        r = requests.get(f"{base}/products/{product}/candles",
                         params={"granularity": gran}, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json()
        if not data:
            return pd.DataFrame()

        rows = [{
            "time": _to_dt_ms(k[0]),
            "open": float(k[3]), "high": float(k[2]),
            "low": float(k[1]), "close": float(k[4]),
            "volume": float(k[5])
        } for k in data]

        return _normalize_df(pd.DataFrame(rows).set_index("time").sort_index()).tail(max(min_rows, 1))

    except Exception as e:
        log_warning(f"Coinbase fallback error: {e}", archivo="data_fetcher.py", funcion="fetch_coinbase")
        return pd.DataFrame()


def fetch_kraken(symbol: str, interval: str = "1m", min_rows: int = 200) -> pd.DataFrame:
    """Descarga velas de Kraken (OHLC)."""
    try:
        base = "https://api.kraken.com"

        # candidatos según símbolo
        if symbol.upper().endswith("USDT"):
            base_sym = symbol.upper().replace("USDT", "")
            candidates = [f"X{base_sym}ZUSDT", f"{base_sym}USDT",
                          f"X{base_sym}ZUSD", f"{base_sym}USD"]
        else:
            candidates = [symbol.upper(), symbol.upper() + "USD"]

        ivmap = {"1m": 1, "5m": 5, "15m": 15, "30m": 30,
                 "1h": 60, "4h": 240, "1d": 1440}
        iv = ivmap.get(interval, 1)

        for pair in candidates:
            r = requests.get(f"{base}/0/public/OHLC", params={"pair": pair, "interval": iv}, timeout=10)
            if r.status_code != 200:
                continue

            result = r.json().get("result", {})
            if not result:
                continue

            kpair = [k for k in result.keys() if k != "last"]
            if not kpair:
                continue

            data = result[kpair[0]]
            if not data:
                continue

            rows = [{
                "time": _to_dt_ms(k[0]),
                "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[6])
            } for k in data]

            out = _normalize_df(pd.DataFrame(rows).set_index("time")).tail(max(min_rows, 1))
            if not out.empty:
                return out

        return pd.DataFrame()

    except Exception as e:
        log_warning(f"Kraken fallback error: {e}", archivo="data_fetcher.py", funcion="fetch_kraken")
        return pd.DataFrame()

# ==========================================================
# 🔀 Orquestador Multi-Proveedor
# ==========================================================
PROVIDERS = [
    ("binance_spot",    fetch_binance_spot),
    ("binance_futures", fetch_binance_futures),
    ("yahoo",           fetch_yahoo),
    ("bybit",           fetch_bybit),
    ("okx",             fetch_okx),
    ("coinbase",        fetch_coinbase),
    ("kraken",          fetch_kraken),
]

def _maybe_usd_symbol(sym: str) -> str:
    """Convierte símbolos USDT a USD para compatibilidad con Yahoo y otros."""
    if sym.endswith("USDT"):
        return sym.replace("USDT", "USD")
    return sym


def get_candles_multi(symbol: str, interval: str = "1m", mercado: str = "spot",
                      min_rows: int = 200, preferred=None) -> pd.DataFrame:
    """
    Orquesta intentos sobre múltiples proveedores.  
    - Prioriza Binance si mercado es cripto.  
    - Devuelve DataFrame de velas (puede ser < min_rows si no hay datos).  
    """
    order = [p for p, _ in PROVIDERS]

    if preferred:
        pref = [p for p in preferred if p in order]
        order = pref + [p for p in order if p not in pref]

    if mercado and mercado.lower() in ("spot", "futuros", "futures"):
        order = ["binance_spot", "binance_futures", "bybit", "okx", "coinbase", "kraken", "yahoo"]

    best_df = pd.DataFrame()
    best_name = None

    for name, fn in PROVIDERS:
        if name not in order:
            continue
        try:
            df = fn(symbol, interval, min_rows)
            if df is not None and not df.empty:
                log_info(f"[data] {name} -> {symbol} ({len(df)} filas)",
                         archivo="data_fetcher.py", funcion="get_candles_multi")

                if len(df) >= min_rows:
                    return df  # ✅ listo, suficiente
                if len(df) > len(best_df):
                    best_df = df
                    best_name = name
        except Exception as e:
            log_warning(f"{name} fallo: {e}",
                        archivo="data_fetcher.py", funcion="get_candles_multi")
            continue

    if best_df is not None and not best_df.empty:
        log_warning(f"⚠️ No se alcanzaron {min_rows} velas. Usando {len(best_df)} desde {best_name}.",
                    archivo="data_fetcher.py", funcion="get_candles_multi")
        return best_df

    return pd.DataFrame()


# ==========================================================
# 🧩 Wrappers de compatibilidad
# ==========================================================
def obtener_datos_con_fallback(symbol: str, interval: str = "1h",
                               mercado: str = "spot", min_rows: int = 200):
    """Wrapper que usa el orquestador multi-proveedor."""
    try:
        df = get_candles_multi(symbol, interval=interval,
                               mercado=mercado, min_rows=min_rows)
        if df is None or df.empty:
            log_warning(f"No se obtuvieron datos para {symbol} con intervalo {interval}",
                        archivo="data_fetcher.py", funcion="obtener_datos_con_fallback")
            return pd.DataFrame()
        return df
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="obtener_datos_con_fallback")
        return pd.DataFrame()


def obtener_datos_bin(symbol: str, interval: str = "1h", lookback: str = "30d"):
    """Wrapper para Binance (API oficial si hay keys, sino fallback público)."""
    try:
        try:
            from binance.client import Client
            api_key = os.getenv("BINANCE_API_KEY")
            api_secret = os.getenv("BINANCE_API_SECRET")
            if api_key and api_secret:
                client = Client(api_key, api_secret)
                klines = client.get_historical_klines(symbol, interval, lookback)
                if klines:
                    df = pd.DataFrame(klines, columns=[
                        "time", "open", "high", "low", "close", "volume",
                        "close_time", "qav", "num_trades",
                        "tbbav", "tbqav", "ignore"
                    ])
                    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
                    df.set_index("time", inplace=True)
                    df = df[["open", "high", "low", "close", "volume"]].astype(float)
                    return _normalize_df(df)
        except Exception:
            pass

        # fallback público
        return fetch_binance_spot(symbol, interval=interval, min_rows=200)

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="obtener_datos_bin")
        return pd.DataFrame()


def obtener_datos_yahoo(symbol: str, interval: str = "1h", period: str = "60d"):
    """Wrapper para Yahoo Finance."""
    try:
        return fetch_yahoo(symbol, interval=interval, min_rows=200)
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="obtener_datos_yahoo")
        return pd.DataFrame()


# ==========================================================
# 🌐 Integración con AlphaVantage / TwelveData / CSV locales
# ==========================================================
from pathlib import Path

DATA_DIR = Path("data/historical")
DATA_DIR.mkdir(parents=True, exist_ok=True)

ALPHA_KEY = os.getenv("ALPHAVANTAGE_KEY", "")
TWELVE_KEY = os.getenv("TWELVEDATA_KEY", "")


def fetch_alpha_daily(symbol: str, outputsize: str = "compact") -> pd.DataFrame:
    """
    Descarga datos diarios desde AlphaVantage.
    Guarda CSV en data/historical/{symbol}_alphavantage_daily.csv
    """
    try:
        if not ALPHA_KEY:
            log_warning("ALPHAVANTAGE_KEY no configurada",
                        archivo="data_fetcher.py", funcion="fetch_alpha_daily")
            return pd.DataFrame()

        base = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": ALPHA_KEY
        }
        r = requests.get(base, params=params, timeout=30)
        if r.status_code != 200:
            log_error(f"AlphaVantage error {r.status_code}",
                      archivo="data_fetcher.py", funcion="fetch_alpha_daily")
            return pd.DataFrame()

        j = r.json()
        key = "Time Series (Daily)"
        if key not in j:
            log_error(f"Respuesta inesperada: {j}",
                      archivo="data_fetcher.py", funcion="fetch_alpha_daily")
            return pd.DataFrame()

        df = pd.DataFrame.from_dict(j[key], orient="index").astype(float)
        df.index = pd.to_datetime(df.index, utc=True)
        df = df.sort_index()
        out = DATA_DIR / f"{symbol}_alphavantage_daily.csv"
        df.to_csv(out)
        log_info(f"AlphaVantage guardado en {out}",
                 archivo="data_fetcher.py", funcion="fetch_alpha_daily")
        return _normalize_df(df)

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="fetch_alpha_daily")
        return pd.DataFrame()


def fetch_twelvedata_intraday(symbol: str, interval: str = "1min", outputsize: int = 500) -> pd.DataFrame:
    """
    Descarga datos intradía desde TwelveData.
    Guarda CSV en data/historical/{symbol}_twelvedata_{interval}.csv
    """
    try:
        if not TWELVE_KEY:
            log_warning("TWELVEDATA_KEY no configurada",
                        archivo="data_fetcher.py", funcion="fetch_twelvedata_intraday")
            return pd.DataFrame()

        base = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVE_KEY,
            "format": "JSON"
        }
        r = requests.get(base, params=params, timeout=30)
        if r.status_code != 200:
            log_error(f"TwelveData error {r.status_code}",
                      archivo="data_fetcher.py", funcion="fetch_twelvedata_intraday")
            return pd.DataFrame()

        j = r.json()
        if "values" not in j:
            log_error(f"TwelveData respuesta inválida: {j}",
                      archivo="data_fetcher.py", funcion="fetch_twelvedata_intraday")
            return pd.DataFrame()

        df = pd.DataFrame(j["values"])
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.set_index("datetime").sort_index()
        df = df.rename(columns={
            "open": "open", "high": "high", "low": "low",
            "close": "close", "volume": "volume"
        }).astype(float)

        out = DATA_DIR / f"{symbol}_twelvedata_{interval}.csv"
        df.to_csv(out)
        log_info(f"TwelveData guardado en {out}",
                 archivo="data_fetcher.py", funcion="fetch_twelvedata_intraday")
        return _normalize_df(df)

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="fetch_twelvedata_intraday")
        return pd.DataFrame()


def load_local_csv(path: str) -> pd.DataFrame:
    """Carga un CSV local y lo normaliza."""
    try:
        df = pd.read_csv(path, parse_dates=True, index_col=0)
        return _normalize_df(df)
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="load_local_csv")
        return pd.DataFrame()


def enrich_symbol_data(symbol: str) -> list:
    """
    Enriquecimiento de datos para un símbolo:
    - Descarga desde AlphaVantage (daily)
    - Descarga desde TwelveData (intraday)
    - Devuelve lista de paths de CSV guardados
    """
    saved = []
    try:
        p1 = fetch_alpha_daily(symbol, outputsize="compact")
        if not p1.empty:
            saved.append(str(DATA_DIR / f"{symbol}_alphavantage_daily.csv"))

        # AlphaVantage tiene límite de 5 req/min → pausa
        time.sleep(12)

        p2 = fetch_twelvedata_intraday(symbol, interval="5min")
        if not p2.empty:
            saved.append(str(DATA_DIR / f"{symbol}_twelvedata_5min.csv"))

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="enrich_symbol_data")

    return saved

# ==========================================================
# 📊 Indicadores Técnicos (helpers para entrenamientos LSTM)
# ==========================================================
import pandas as pd
import numpy as np

def add_pivot_points(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula Pivot Points clásicos (diarios) y los añade al DataFrame.
    """
    try:
        df = df.copy()
        if {"high", "low", "close"} - set(df.columns):
            return df

        pivot = (df["high"] + df["low"] + df["close"]) / 3
        r1 = 2 * pivot - df["low"]
        s1 = 2 * pivot - df["high"]
        r2 = pivot + (df["high"] - df["low"])
        s2 = pivot - (df["high"] - df["low"])

        df["pivot"] = pivot
        df["r1"], df["s1"] = r1, s1
        df["r2"], df["s2"] = r2, s2
        return df
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="add_pivot_points")
        return df


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula componentes principales del Ichimoku Cloud.
    """
    try:
        df = df.copy()
        high = df["high"]
        low = df["low"]

        # Tenkan-sen (9 períodos)
        df["tenkan"] = (high.rolling(9).max() + low.rolling(9).min()) / 2
        # Kijun-sen (26 períodos)
        df["kijun"] = (high.rolling(26).max() + low.rolling(26).min()) / 2
        # Senkou Span A (promedio de tenkan y kijun, adelantado 26)
        df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(26)
        # Senkou Span B (promedio 52, adelantado 26)
        df["senkou_b"] = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
        # Chikou Span (cierre retrasado 26)
        df["chikou"] = df["close"].shift(-26)

        return df
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="add_ichimoku")
        return df


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula On-Balance Volume (OBV).
    """
    try:
        df = df.copy()
        df["obv"] = (np.sign(df["close"].diff()) * df["volume"]).fillna(0).cumsum()
        return df
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="add_obv")
        return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula VWAP (Volume Weighted Average Price).
    """
    try:
        df = df.copy()
        q = df["volume"]
        p = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (p * q).cumsum() / q.cumsum()
        return df
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="add_vwap")
        return df

def save_df_to_csv(df: pd.DataFrame, name: str) -> str:
    """
    Guarda un DataFrame en data/historical/{name}.csv
    Retorna la ruta guardada.
    """
    if df is None or df.empty:
        return ""
    out = DATA_DIR / f"{name}.csv"
    try:
        df.to_csv(out)
        log_info(f"Guardado {len(df)} filas en {out}", archivo="data_fetcher.py", funcion="save_df_to_csv")
        return str(out)
    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="save_df_to_csv")
        return ""

def enrich_symbol_data(symbol: str) -> list:
    """
    Enriquecimiento de datos para un símbolo:
    - Descarga desde AlphaVantage y TwelveData
    - Añade indicadores técnicos básicos
    - Guarda CSVs y devuelve paths
    """
    saved = []
    try:
        p1 = fetch_alpha_daily(symbol, outputsize="compact")
        if not p1.empty:
            p1 = add_pivot_points(add_obv(add_vwap(p1)))
            saved.append(save_df_to_csv(p1, f"{symbol}_alphavantage_daily"))

        time.sleep(12)  # evitar límite API

        p2 = fetch_twelvedata_intraday(symbol, interval="5min")
        if not p2.empty:
            p2 = add_ichimoku(add_obv(p2))
            saved.append(save_df_to_csv(p2, f"{symbol}_twelvedata_5min"))

    except Exception as e:
        log_error(e, archivo="data_fetcher.py", funcion="enrich_symbol_data")

    return saved

