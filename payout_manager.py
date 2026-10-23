"""
payout_manager.py — Vigilante de PAGOS: pool → Binance, con alerta instantánea
==============================================================================
Rastrea las tres cuentas que intervienen en el pipeline agresivo:

  1) DEPÓSITOS EN BINANCE  (API firmada /sapi/v1/capital/deposit/hisrec)
     → si aparece un depósito BTC nuevo acreditado → alerta Telegram
       inmediata con su valor en USD. Aquí "sube a Binance" de verdad:
       el pool pagó a tu dirección de depósito.

  2) BALANCE EN UNMINEABLE (api.unmineable.com/v4/address/{dir}?coin=BTC)
     → balance sin pagar + histórico pagado. Si cruza el umbral
       (PAYOUT_ALERT_MIN_BTC) avisa "payout en camino".

  3) BALANCE EN MONEROOCEAN (api.moneroocean.stream/miner/{wallet}/stats)
     → XMR pendiente de pago (mejor esfuerzo: si la API cambia, se ignora
       sin romper nada).

Estado persistente: data/payout_state.json (txids ya alertados, flags).
"""
import json
import os
import threading
import time

from config import BASE_DIR
from pool_stats import get_price

PAYOUT_STATE_FILE = os.path.join(BASE_DIR, "data", "payout_state.json")
UA = {"User-Agent": "btc-miner-studio/2.0"}
MO_API = "https://api.moneroocean.stream/miner/{addr}/stats"
UM_API = "https://api.unmineable.com/v4/address/{addr}?coin=BTC"


# ---------------------------------------------------------------------------
# Lecturas puntuales (las usa el watcher Y el dashboard)
# ---------------------------------------------------------------------------
def fetch_unmineable(btc_address: str):
    """Estado real de la dirección en unMineable (API v4, verificada 2026).
    Devuelve {balance, balance_payable, payment_threshold, mining_fee, auto}
    o None. El umbral de pago lo decide el pool (payment_threshold)."""
    if not btc_address:
        return None
    try:
        import requests
        r = requests.get(UM_API.format(addr=btc_address), headers=UA,
                         timeout=10)
        if r.status_code != 200:
            return None
        d = (r.json() or {}).get("data") or {}

        def _f(key, default=0.0):
            try:
                return float(d.get(key, default) or default)
            except (TypeError, ValueError):
                return default

        return {
            "pool": "unMineable",
            "balance": _f("balance"),
            "balance_payable": _f("balance_payable"),
            "payment_threshold": _f("payment_threshold", 0.00075),
            "mining_fee": _f("mining_fee"),
            "auto": bool(d.get("auto", True)),
        }
    except Exception:
        return None


def fetch_moneroocean(xmr_wallet: str):
    """XMR pendientes/pagados en MoneroOcean (mejor esfuerzo) o None."""
    if not xmr_wallet:
        return None
    try:
        import requests
        r = requests.get(MO_API.format(addr=xmr_wallet), headers=UA,
                         timeout=8)
        if r.status_code != 200:
            return None
        d = r.json()
        stats = d.get("stats", d)      # tolerante a dos formatos
        # Esquema real (2026): amtDue/amtPaid en piconero (1e12)
        due = stats.get("amtDue", d.get("amtDue",
                                        stats.get("ammtDue", 0)))
        paid = stats.get("amtPaid", d.get("amtPaid",
                                          stats.get("ammtPaid", 0)))
        hr = stats.get("hash", d.get("hash", 0)) or 0
        # ammt* vienen en piconero (1e12)
        try:
            due_xmr = float(due) / 1e12
            paid_xmr = float(paid) / 1e12
        except (TypeError, ValueError):
            return None
        if due_xmr > 1e6:              # parseo raro → descartar
            return None
        return {"pool": "MoneroOcean", "due_xmr": due_xmr,
                "paid_xmr": paid_xmr, "hashrate": float(hr)}
    except Exception:
        return None


def fetch_binance_deposits(binance, limit: int = 20) -> list:
    """Lista de depósitos BTC (o [] si no hay claves/servicio/simulado)."""
    if binance is None:
        return []
    try:
        hist = binance.deposit_history("BTC", limit)
        # Filtra simulados (modo sin claves) para no falsas alertas
        return [d for d in hist if not d.get("simulado")]
    except Exception:
        return []


# ---------------------------------------------------------------------------
class PayoutWatcher(threading.Thread):
    """Hilo daemon que sondea cada `poll` segundos y alerta cambios."""

    def __init__(self, cfg: dict, binance, on_alert=None, poll: int = 90):
        super().__init__(daemon=True, name="payout-watcher")
        self.cfg = cfg
        self.binance = binance
        self.on_alert = on_alert or (lambda msg, lvl="info": None)
        self.poll = max(30, int(poll))
        self._stop = threading.Event()
        self._state = self._load()
        self.last_snapshot = {}

    # ------------------------------------------------------------------
    def _load(self) -> dict:
        base = {"known_txids": [], "accum_alerted": False,
                "mo_alerted": False, "deposit_total_btc": 0.0}
        try:
            with open(PAYOUT_STATE_FILE, "r", encoding="utf-8") as f:
                base.update(json.load(f))
        except Exception:
            pass
        return base

    def _save(self):
        try:
            os.makedirs(os.path.dirname(PAYOUT_STATE_FILE), exist_ok=True)
            tmp = PAYOUT_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f)
            os.replace(tmp, PAYOUT_STATE_FILE)
        except Exception:
            pass

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------
    def tick(self) -> dict:
        """Una pasada de vigilancia; devuelve el snapshot actual."""
        cfg = self.cfg
        price, _ = get_price("binance")
        snap = {"ts": time.time(), "price_usd": price,
                "unmineable": None, "moneroocean": None,
                "binance_nuevos": [], "binance_total_btc":
                    self._state.get("deposit_total_btc", 0.0)}

        # --- 1) Depósitos nuevos en Binance -------------------------------
        deps = fetch_binance_deposits(self.binance, 20)
        known = set(self._state.get("known_txids", []))
        nuevos = []
        for d in deps:
            txid = str(d.get("txId", ""))
            if not txid or txid in known:
                continue
            known.add(txid)
            try:
                amount = float(d.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0.0
            rec = {"txid": txid[:40], "amount_btc": amount,
                   "status": int(d.get("status", -1)),
                   "insertTime": int(d.get("insertTime", 0)),
                   "usd": (amount * price) if price else None}
            nuevos.append(rec)
            # Solo alertamos los acreditados (status 1); pendientes se ven
            if rec["status"] == 1 and amount > 0:
                self.on_alert(
                    f"DEPÓSITO RECIBIDO EN BINANCE: {amount:.8f} BTC"
                    + (f" (≈ USD {rec['usd']:,.2f})" if rec["usd"] else ""),
                    "money")
                self._state["deposit_total_btc"] = \
                    self._state.get("deposit_total_btc", 0.0) + amount
        if nuevos:
            self._state["known_txids"] = list(known)[-200:]
            snap["binance_nuevos"] = nuevos
            self._save()

        # --- 2) unMineable: balance y umbral (el umbral real lo da la API) --
        um = fetch_unmineable((cfg.get("BTC_PAYOUT_ADDRESS") or "").strip())
        snap["unmineable"] = um
        if um:
            payable = float(um.get("balance_payable", 0) or 0)
            try:
                umbral_cfg = float(cfg.get("PAYOUT_ALERT_MIN_BTC", 0) or 0)
            except (TypeError, ValueError):
                umbral_cfg = 0.0
            # umbral del pool si existe; si no, el configurado; si no, 0.00075
            umbral = float(um.get("payment_threshold") or 0) \
                or umbral_cfg or 0.00075
            snap["umbral_unmineable"] = umbral
            if payable >= umbral and not self._state.get("accum_alerted"):
                self.on_alert(
                    f"PAYOUT EN CAMINO (unMineable): pagable {payable:.8f} "
                    f"BTC ≥ umbral del pool {umbral:.5f}. El pago llegará a "
                    f"tu dirección de Binance.", "money")
                self._state["accum_alerted"] = True
                self._save()
            elif payable < umbral * 0.5 and self._state.get("accum_alerted"):
                self._state["accum_alerted"] = False   # pagó: rearmar
                self.on_alert("unMineable pagó: el balance bajó (revisa "
                              "el depósito en Binance)", "ok")
                self._save()

        # --- 3) MoneroOcean: XMR pendientes --------------------------------
        mo = fetch_moneroocean((cfg.get("WALLET_XMR") or "").strip())
        snap["moneroocean"] = mo
        if mo and mo["due_xmr"] >= 0.001 and \
                not self._state.get("mo_alerted"):
            self.on_alert(f"MoneroOcean: {mo['due_xmr']:.4f} XMR pendientes "
                          f"de pago a tu wallet (umbral pool ~0.001 XMR)",
                          "info")
            self._state["mo_alerted"] = True
            self._save()
        elif mo and mo["due_xmr"] < 0.0005 and \
                self._state.get("mo_alerted"):
            self._state["mo_alerted"] = False
            self._save()

        self.last_snapshot = snap
        return snap

    # ------------------------------------------------------------------
    def snapshot_light(self) -> dict:
        """Versión ligera para /estado de Telegram (sin llamadas de red)."""
        um = self.last_snapshot.get("unmineable") or {}
        mo = self.last_snapshot.get("moneroocean") or {}
        return {
            "unmineable": {
                "balance": float(um.get("balance", 0) or 0),
                "balance_payable": float(um.get("balance_payable", 0) or 0),
                "threshold": float(um.get("payment_threshold", 0) or 0),
            },
            "moneroocean": {"due_xmr": float(mo.get("due_xmr", 0) or 0)},
            "binance_total_btc": self._state.get("deposit_total_btc", 0.0),
        }

    # ------------------------------------------------------------------
    def run(self):
        # primera pasada rápida, luego el ritmo normal
        self._stop.wait(10)
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                pass
            self._stop.wait(self.poll)
