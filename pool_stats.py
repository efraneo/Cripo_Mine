"""
pool_stats.py — Datos de red, precio y estadísticas de pools
============================================================
Fuentes PÚBLICAS reales (sin API key):
  • https://mempool.space  → hashrate y dificultad actuales de la red BTC,
    recompensa del último bloque (endpoints /api/v1/mining/hashrate/3d, /api/blocks)
  • https://api.binance.com → precio BTCUSDT (fallback: CoinGecko)
  • https://api.f2pool.com/bitcoin/{cuenta} → stats si tienes cuenta F2Pool
  • https://api.unmineable.com/v4/address/{dir} → legacy, puede estar caído
Con API key (opcional):
  • NiceHash API v2 (firma HMAC-SHA256: X-Time, X-Nonce, X-Api-Key, X-Signature)
"""
import hashlib
import hmac
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

UA = {"User-Agent": "btc-miner-studio/1.0"}
TIMEOUT = 6

# Recompensa actual por bloque (post-halving 2024): 3.125 BTC
BLOCK_REWARD_BTC = 3.125
BLOCKS_PER_DAY = 144


def _get_json(url: str, headers: dict = None):
    r = requests.get(url, headers={**UA, **(headers or {})}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# PRECIO BTC (cascada de 5 exchanges públicos para máxima resiliencia)
# ---------------------------------------------------------------------------
def price_binance():
    try:
        d = _get_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
        return float(d["price"])
    except Exception:
        return None


def price_coingecko():
    try:
        d = _get_json(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
        return float(d["bitcoin"]["usd"])
    except Exception:
        return None


def price_coinbase():
    try:
        d = _get_json("https://api.coinbase.com/v2/prices/BTC-USD/spot")
        return float(d["data"]["amount"])
    except Exception:
        return None


def price_bitso():
    try:
        d = _get_json("https://api.bitso.com/v3/ticker/?book=btc_usd")
        return float(d["payload"]["last"])
    except Exception:
        return None


def price_kraken():
    try:
        d = _get_json("https://api.kraken.com/0/public/Ticker?pair=XBTUSD")
        return float(d["result"]["XXBTZUSD"]["c"][0])
    except Exception:
        return None


_PRICE_CHAIN = {
    "binance": [price_binance, price_coinbase, price_kraken, price_bitso,
                price_coingecko],
    "coingecko": [price_coingecko, price_binance, price_coinbase, price_kraken,
                  price_bitso],
    "bitso": [price_bitso, price_binance, price_coinbase, price_kraken,
              price_coingecko],
}


def get_price(preferred: str = "binance") -> tuple:
    """Devuelve (precio, fuente). Lanza TODAS las fuentes de la cadena EN
    PARALELO y devuelve el primer resultado válido: un exchange caído o
    bloqueado ya no congela el dashboard (peor caso = 1 timeout, no 5)."""
    cadena = _PRICE_CHAIN.get(preferred, _PRICE_CHAIN["binance"])
    ex = ThreadPoolExecutor(max_workers=len(cadena))
    try:
        futs = {ex.submit(fn): fn for fn in cadena}
        for fut in as_completed(futs):
            try:
                p = fut.result()
            except Exception:
                continue
            if p and p > 0:
                return p, futs[fut].__name__.replace("price_", "").capitalize()
    finally:
        # no espera a los hilos lentos: el dashboard nunca se queda colgado
        ex.shutdown(wait=False, cancel_futures=True)
    return None, "no disponible"


# ---------------------------------------------------------------------------
# RED GLOBAL (mempool.space, API pública sin clave)
# ---------------------------------------------------------------------------
def network_stats() -> dict:
    """Hashrate de red (H/s) y dificultad actual de la red Bitcoin.
    Fuente: mempool.space /api/v1/mining/hashrate/3d (respuesta pequeña y
    rápida ~0.2 s). La recompensa usa la constante post-halving 2024 (3.125
    BTC) que es válida hasta el halving de 2028."""
    out = {"network_hashrate": None, "difficulty": None,
           "last_reward_btc": BLOCK_REWARD_BTC, "fuente": "mempool.space"}
    try:
        d = _get_json("https://mempool.space/api/v1/mining/hashrate/3d")
        out["network_hashrate"] = float(d.get("currentHashrate") or 0) or None
        out["difficulty"] = float(d.get("currentDifficulty") or 0) or None
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# RENTABILIDAD HONESTA
# ---------------------------------------------------------------------------
def estimate_profitability(user_hashrate: float, net: dict, price_usd) -> dict:
    """Estimación matemática (no promete nada): a tu hashrate actual, cuánto
    esperaría el pool pagarte en promedio si fuera PPS infinito."""
    nh = net.get("network_hashrate") or 0
    reward = net.get("last_reward_btc") or BLOCK_REWARD_BTC
    res = {
        "network_hashrate": nh,
        "reward_btc": reward,
        "btc_dia": 0.0, "usd_dia": 0.0, "usd_mes": 0.0, "usd_ano": 0.0,
        "prob_bloque_dia": 0.0, "anios_esperados_bloque": None,
        "sats_dia": 0.0,
    }
    if not nh or not user_hashrate:
        return res
    share = user_hashrate / nh                      # tu porción de la red
    res["prob_bloque_dia"] = share * BLOCKS_PER_DAY
    if res["prob_bloque_dia"] > 0:
        res["anios_esperados_bloque"] = 1.0 / res["prob_bloque_dia"] / 365.0
    res["btc_dia"] = share * BLOCKS_PER_DAY * reward
    res["sats_dia"] = res["btc_dia"] * 1e8
    if price_usd:
        res["usd_dia"] = res["btc_dia"] * price_usd
        res["usd_mes"] = res["usd_dia"] * 30
        res["usd_ano"] = res["usd_dia"] * 365
    return res


# ---------------------------------------------------------------------------
# F2Pool (API pública por cuenta)
# ---------------------------------------------------------------------------
def f2pool_stats(account: str):
    try:
        d = _get_json(f"https://api.f2pool.com/bitcoin/{account}")
        return {
            "pool": "F2Pool",
            "hashrate": float(d.get("hashrate", 0) or 0),
            "workers": int(d.get("workers", 0) or 0),
            "unpaid_btc": float(d.get("unpaid", 0) or 0) / 1e8,
            "total_earn_btc": float(d.get("user_total_earn", 0) or 0) / 1e8,
            "last_update": time.strftime("%H:%M:%S"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# unMineable (legacy; el servicio puede estar fuera de línea)
# ---------------------------------------------------------------------------
def unmineable_stats(address: str, coin: str = "BTC"):
    try:
        d = _get_json(f"https://api.unmineable.com/v4/address/{address}?coin={coin}")
        data = (d or {}).get("data", {})
        return {
            "pool": "unMineable",
            "balance": float(data.get("balance", 0) or 0),
            "paid": float(data.get("paid", 0) or 0),
            "hashrate": float(data.get("hashrate", 0) or 0),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# NiceHash API v2 (requiere clave; firma HMAC-SHA256)
# Docs: https://www.nicehash.com/docs  (GET /main/api/v2/mining/rigs/stats/algo)
# ---------------------------------------------------------------------------
def nicehash_stats(api_key: str, api_secret: str, org_id: str,
                   algorithm: str = "SHA256"):
    if not (api_key and api_secret and org_id):
        return None
    try:
        path = f"/main/api/v2/mining/rigs/stats/algo?algorithm={algorithm}"
        ts = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        payload = api_key + ts + nonce + " GET " + path
        sig = hmac.new(api_secret.encode(), payload.encode(),
                       hashlib.sha256).hexdigest()
        headers = {
            "X-Time": ts, "X-Nonce": nonce, "X-Api-Key": api_key,
            "X-Signature": sig, "X-Organization-Id": org_id, **UA,
        }
        d = _get_json("https://api.nicehash.com" + path, headers=headers)
        stats = (d or {}).get("miningRigsAlgoStats", [])
        if not stats:
            return {"pool": "NiceHash", "hashrate": 0.0, " rigs": 0}
        s = stats[0]
        return {
            "pool": "NiceHash",
            "hashrate": float(s.get("acceptedSpeed", 0) or 0),
            "rigs": int(s.get("acceptedAndActiveRigs", 0) or 0),
            "profit_usd_day": float(s.get("profitabilityInUsd", 0) or 0),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resumen compuesto para la pestaña "Red y Pool"
# ---------------------------------------------------------------------------
def pool_overview(pool_url: str, f2pool_account: str = "",
                  nicehash_creds: tuple = ()) -> dict:
    """Junta stats de red + API del pool que corresponda (si hay credenciales)."""
    net = network_stats()
    api = None
    if f2pool_account:
        api = f2pool_stats(f2pool_account)
    if api is None and nicehash_creds and all(nicehash_creds):
        api = nicehash_stats(*nicehash_creds)
    return {"red": net, "pool_api": api, "pool_url": pool_url}
