"""
binance_api.py — Cliente REST de Binance (Spot API v3 + Capital SAPI)
=====================================================================
"""
import hashlib
import hmac
import time
from urllib.parse import urlencode
import requests

BASE_URL = "https://api.binance.com"
RECV_WINDOW = 10000

class BinanceError(Exception):
    pass

class BinanceAPI:
    def __init__(self, api_key: str = "", api_secret: str = "", base_url: str = BASE_URL, timeout: int = 8):
        self.key = (api_key or "").strip()
        self.secret = (api_secret or "").strip()
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "btc-miner-studio/1.0"})
        if self.key:
            self.session.headers.update({"X-MBX-APIKEY": self.key})

    def _public(self, path: str, params: dict = None) -> dict:
        url = f"{self.base}{path}"
        r = self.session.get(url, params=params or {}, timeout=self.timeout)
        return self._check(r)

    def _signed(self, path: str, params: dict = None, method: str = "GET") -> dict:
        if not self.key or not self.secret:
            raise BinanceError("Faltan BINANCE_API_KEY / BINANCE_API_SECRET")
        p = dict(params or {})
        p["timestamp"] = int(time.time() * 1000)
        p["recvWindow"] = RECV_WINDOW
        query = urlencode(p, True)
        sig = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{self.base}{path}?{query}&signature={sig}"
        r = (self.session.get if method == "GET" else self.session.post)(url, timeout=self.timeout)
        return self._check(r)

    @staticmethod
    def _check(r: requests.Response) -> dict:
        if r.status_code == 200:
            try: return r.json()
            except: raise BinanceError(f"Respuesta no JSON")
        try:
            data = r.json()
            code = data.get("code", r.status_code)
            msg = data.get("msg", r.text[:200])
        except:
            code, msg = r.status_code, r.text[:200]
        raise BinanceError(f"Error Binance {code}: {msg}")

    def ping(self) -> dict:
        t0 = time.time()
        self._public("/api/v3/ping")
        return {"latency_ms": round((time.time() - t0) * 1000, 1)}

    def btc_price(self, symbol: str = "BTCUSDT") -> float:
        data = self._public("/api/v3/ticker/price", {"symbol": symbol})
        return float(data["price"])

    def deposit_address(self, coin: str = "BTC", network: str = "BTC") -> dict:
        return self._signed("/sapi/v1/capital/deposit/address", {"coin": coin, "network": network})

    def deposit_history(self, coin: str = "BTC", limit: int = 20) -> list:
        data = self._signed("/sapi/v1/capital/deposit/hisrec", {"coin": coin, "limit": min(max(limit, 1), 50)})
        return data if isinstance(data, list) else []

    def account(self) -> dict:
        return self._signed("/api/v3/account")

    def spot_balances(self, only_nonzero: bool = True) -> list:
        acc = self.account()
        out = []
        for b in acc.get("balances", []):
            try:
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
            except: continue
            if only_nonzero and free <= 0 and locked <= 0: continue
            out.append({"asset": b.get("asset"), "free": free, "locked": locked})
        return out

    def btc_balance(self) -> float:
        for b in self.spot_balances():
            if b["asset"] == "BTC": return float(b["free"])
        return 0.0

class SimulatedBinance:
    def __init__(self): self.simulado = True
    def ping(self): return {"latency_ms": None, "simulado": True}
    def btc_price(self, symbol="BTCUSDT"): return 64000.0
    def deposit_address(self, coin="BTC", network="BTC"): return {"address": "bc1qSIMULAD0", "coin": coin, "network": network, "simulado": True}
    def deposit_history(self, coin="BTC", limit=20): return []
    def spot_balances(self, only_nonzero=True): return [{"asset": "BTC", "free": 0.0, "locked": 0.0, "simulado": True}]
    def btc_balance(self): return 0.0

def make_binance(api_key: str, api_secret: str):
    if api_key and api_secret: return BinanceAPI(api_key, api_secret)
    return SimulatedBinance()

def format_deposit_status(status: int) -> str:
    return {0: "⏳ Pendiente", 1: "✅ Acreditado", 6: "❌ Rechazado"}.get(status, f"Código {status}")
