"""
binance_api.py — Cliente REST de Binance (Spot API v3 + Capital SAPI)
=====================================================================
Implementa las llamadas firmadas con HMAC-SHA256 según la documentación
oficial (https://developers.binance.com/docs). Solo usa `requests`, sin
dependencias pesadas.

Funciones disponibles:
  • ping()                     → latencia de la API
  • btc_price()                → precio BTC/USDT en vivo
  • deposit_address("BTC")     → dirección de depósito de TU cuenta
  • deposit_history("BTC")     → historial de depósitos recibidos
  • spot_balances()            → balances spot (solo monedas con saldo)

Seguridad:
  • La API key SOLO necesita permiso de lectura.
  • Nunca actives el permiso de retiro para esta app.
  • Mejor práctica: restringe la key por IP en el panel de Binance.
"""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

BASE_URL = "https://api.binance.com"
RECV_WINDOW = 10000


class BinanceError(Exception):
    """Error legible de la API de Binance."""


class BinanceAPI:
    def __init__(self, api_key: str = "", api_secret: str = "",
                 base_url: str = BASE_URL, timeout: int = 8):
        self.key = (api_key or "").strip()
        self.secret = (api_secret or "").strip()
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "btc-miner-studio/1.0"})
        if self.key:
            self.session.headers.update({"X-MBX-APIKEY": self.key})

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    def _public(self, path: str, params: dict = None) -> dict:
        url = f"{self.base}{path}"
        r = self.session.get(url, params=params or {}, timeout=self.timeout)
        return self._check(r)

    def _signed(self, path: str, params: dict = None, method: str = "GET") -> dict:
        if not self.key or not self.secret:
            raise BinanceError("Faltan BINANCE_API_KEY / BINANCE_API_SECRET "
                               "en .streamlit/secrets.toml")
        p = dict(params or {})
        p["timestamp"] = int(time.time() * 1000)
        p["recvWindow"] = RECV_WINDOW
        query = urlencode(p, True)
        sig = hmac.new(self.secret.encode(), query.encode(),
                       hashlib.sha256).hexdigest()
        url = f"{self.base}{path}?{query}&signature={sig}"
        r = (self.session.get if method == "GET" else self.session.post)(url,
                                                                         timeout=self.timeout)
        return self._check(r)

    @staticmethod
    def _check(r: requests.Response) -> dict:
        if r.status_code == 200:
            try:
                return r.json()
            except Exception as e:
                raise BinanceError(f"Respuesta no JSON: {e}") from e
        try:
            data = r.json()
            code = data.get("code", r.status_code)
            msg = data.get("msg", r.text[:200])
        except Exception:
            code, msg = r.status_code, r.text[:200]
        if r.status_code in (401, 403):
            raise BinanceError(f"API key inválida o sin permisos ({code}): {msg}. "
                               f"Revisa BINANCE_API_KEY/SECRET y que la key tenga "
                               f"permiso de lectura. Si activaste whitelist de IP, "
                               f"agrega la IP de este servidor.")
        if r.status_code == 429:
            raise BinanceError("Límite de peticiones alcanzado (429). Espera unos "
                               "segundos y reintenta.")
        if r.status_code == 418:
            raise BinanceError("IP baneada temporalmente por Binance (418). "
                               "Demasiadas peticiones; espera unos minutos.")
        raise BinanceError(f"Error Binance {code}: {msg}")

    # ------------------------------------------------------------------
    # Público (sin firma)
    # ------------------------------------------------------------------
    def ping(self) -> dict:
        t0 = time.time()
        self._public("/api/v3/ping")
        return {"latency_ms": round((time.time() - t0) * 1000, 1)}

    def btc_price(self, symbol: str = "BTCUSDT") -> float:
        data = self._public("/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])

    def server_time(self) -> dict:
        return self._public("/api/v3/time")

    # ------------------------------------------------------------------
    # Firmadas
    # ------------------------------------------------------------------
    def deposit_address(self, coin: str = "BTC", network: str = "BTC") -> dict:
        """Dirección de depósito de tu cuenta para recibir el minado.
        Respuesta: {address, tag?, coin, network, ...}"""
        return self._signed("/sapi/v1/capital/deposit/address",
                            {"coin": coin, "network": network})

    def deposit_history(self, coin: str = "BTC", limit: int = 20) -> list:
        """Historial de depósitos. status: 0=pendiente, 1=éxito."""
        data = self._signed("/sapi/v1/capital/deposit/hisrec",
                            {"coin": coin, "limit": min(max(limit, 1), 50)})
        return data if isinstance(data, list) else []

    def account(self) -> dict:
        return self._signed("/api/v3/account")

    def spot_balances(self, only_nonzero: bool = True) -> list:
        """Lista de {asset, free, locked} (solo saldos != 0 si only_nonzero)."""
        acc = self.account()
        out = []
        for b in acc.get("balances", []):
            try:
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
            except Exception:
                continue
            if only_nonzero and free <= 0 and locked <= 0:
                continue
            out.append({"asset": b.get("asset"), "free": free, "locked": locked})
        return out

    def btc_balance(self) -> float:
        for b in self.spot_balances():
            if b["asset"] == "BTC":
                return float(b["free"])
        return 0.0


# ===========================================================================
# Modo demo (sin claves): datos claramente etiquetados como SIMULADOS
# ===========================================================================
class SimulatedBinance:
    """Sustituto seguro cuando el usuario aún no configuró sus claves."""

    def __init__(self):
        self.simulado = True

    def ping(self):
        return {"latency_ms": None, "simulado": True}

    def btc_price(self, symbol="BTCUSDT"):
        # precio aproximado de respaldo; la app igual intenta mempool.space
        return 64000.0

    def deposit_address(self, coin="BTC", network="BTC"):
        return {"address": "bc1qSIMULAD0xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "coin": coin, "network": network, "simulado": True}

    def deposit_history(self, coin="BTC", limit=20):
        return [{
            "amount": "0.00012345", "coin": "BTC", "status": 1,
            "address": "bc1qSIMULAD0xxxxxxxxxxxxxxxx", "txId": "simulado...",
            "insertTime": int(time.time() * 1000) - 3600_000,
            "simulado": True,
        }]

    def spot_balances(self, only_nonzero=True):
        return [{"asset": "BTC", "free": 0.00012345, "locked": 0.0,
                 "simulado": True},
                {"asset": "USDT", "free": 12.34, "locked": 0.0,
                 "simulado": True}]

    def btc_balance(self):
        return 0.00012345


def make_binance(api_key: str, api_secret: str):
    """Devuelve BinanceAPI si hay claves, o SimulatedBinance si no."""
    if api_key and api_secret:
        return BinanceAPI(api_key, api_secret)
    return SimulatedBinance()


def format_deposit_status(status: int) -> str:
    return {0: "⏳ Pendiente", 1: "✅ Acreditado", 6: "❌ Rechazado"}.get(
        status, f"Código {status}")
