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

def fetch_unmineable(btc_address: str):
    if not btc_address: return None
    try:
        import requests
        # Sanitizacion de la wallet para evitar errores de API
        addr = btc_address.strip()
        r = requests.get(UM_API.format(addr=addr), headers=UA, timeout=10)
        if r.status_code != 200: return None
        d = (r.json() or {}).get("data") or {}
        def _f(key, default=0.0):
            try: return float(d.get(key, default) or default)
            except: return default
        return {"pool": "unMineable", "balance": _f("balance"), "balance_payable": _f("balance_payable"), "payment_threshold": _f("payment_threshold", 0.00075), "mining_fee": _f("mining_fee"), "auto": bool(d.get("auto", True))}
    except: return None

def fetch_moneroocean(xmr_wallet: str):
    if not xmr_wallet: return None
    try:
        import requests
        r = requests.get(MO_API.format(addr=xmr_wallet), headers=UA, timeout=8)
        if r.status_code != 200: return None
        d = r.json()
        stats = d.get("stats", d)
        due = stats.get("amtDue", d.get("amtDue", stats.get("ammtDue", 0)))
        paid = stats.get("amtPaid", d.get("amtPaid", stats.get("ammtPaid", 0)))
        try:
            due_xmr = float(due) / 1e12
            paid_xmr = float(paid) / 1e12
        except: return None
        return {"pool": "MoneroOcean", "due_xmr": due_xmr, "paid_xmr": paid_xmr}
    except: return None

def fetch_binance_deposits(binance, limit: int = 20) -> list:
    if binance is None: return []
    try:
        hist = binance.deposit_history("BTC", limit)
        return [d for d in hist if not d.get("simulado")]
    except: return []

class PayoutWatcher(threading.Thread):
    def __init__(self, cfg: dict, binance, on_alert=None, poll: int = 90):
        super().__init__(daemon=True, name="payout-watcher")
        self.cfg = cfg
        self.binance = binance
        self.on_alert = on_alert or (lambda msg, lvl="info": None)
        self.poll = max(30, int(poll))
        self._stop = threading.Event()
        self._state = self._load()
        self.last_snapshot = {}

    def _load(self) -> dict:
        base = {"known_txids": [], "accum_alerted": False, "mo_alerted": False, "deposit_total_btc": 0.0}
        try:
            with open(PAYOUT_STATE_FILE, "r", encoding="utf-8") as f:
                base.update(json.load(f))
        except: pass
        return base

    def _save(self):
        try:
            os.makedirs(os.path.dirname(PAYOUT_STATE_FILE), exist_ok=True)
            tmp = PAYOUT_STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f)
            os.replace(tmp, PAYOUT_STATE_FILE)
        except: pass

    def stop(self):
        self._stop.set()

    def tick(self) -> dict:
        cfg = self.cfg
        price, _ = get_price("binance")
        snap = {"ts": time.time(), "price_usd": price, "unmineable": None, "moneroocean": None, "binance_nuevos": [], "binance_total_btc": self._state.get("deposit_total_btc", 0.0)}
        
        deps = fetch_binance_deposits(self.binance, 20)
        known = set(self._state.get("known_txids", []))
        nuevos = []
        for d in deps:
            txid = str(d.get("txId", ""))
            if not txid or txid in known: continue
            known.add(txid)
            try:
                amount = float(d.get("amount", 0) or 0)
            except: amount = 0.0
            rec = {"txid": txid[:40], "amount_btc": amount, "status": int(d.get("status", -1)), "insertTime": int(d.get("insertTime", 0)), "usd": (amount * price) if price else None}
            nuevos.append(rec)
            if rec["status"] == 1 and amount > 0:
                balance_total = 0.0
                try:
                    if self.binance: balance_total = self.binance.btc_balance()
                except: pass
                msg = (f"MONEY! Deposit received in Binance: {amount:.8f} BTC"
                       f"\nValue: {rec['usd']:,.2f} USD" if rec['usd'] else "")
                msg += f"\nTotal Balance Binance: {balance_total:.8f} BTC"
                self.on_// l la ruta correcta es on_alert(msg, "money")
                self.on_alert(msg, "money")
                self._state["deposit_total_btc"] = self._state.get("deposit_// l la ruta correcta es deposit_total_btc", 0.0) + amount
                self._state["deposit_total_btc"] = self._state.get("deposit_total_btc", 0.0) + amount
        if nuevos:
            self._state["known_txids"] = list(known)[-200:]
            snap["binance_nuevos"] = nuevos
            self._save()

        um = fetch_unmineable((cfg.get("BTC_PAYOUT_ADDRESS") or "").strip())
        snap["unmineable"] = um
        if um:
            payable = float(um.get("balance_payable", 0) or 0)
            umbral = float(um.get("payment_threshold") or 0) or float(cfg.get("PAYOUT_ALERT_MIN_BTC", 0) or 0) or 0.00075
            if payable >= umbral and not self._state.get("accum_alerted"):
                self.on_alert(f"PAYOUT COMING (unMineable): {payable:.8f} BTC >= threshold {umbral:.5f}", "money")
                self._state["accum_alerted"] = True
                self._save()
            elif payable < umbral * 0.5 and self._state.get("accum_alerted"):
                self._state["accum_alerted"] = False
                self.on_alert("unMineable paid: balance dropped. Check Binance!", "ok")
                self._save()

        mo = fetch_moneroocean((cfg.get("WALLET_XMR") or "").strip())
        snap["moneroocean"] = mo
        if mo and mo["due_xmr"] >= 0.001 and not self._state.get("mo_alerted"):
            self.on_alert(f"MoneroOcean: {mo['due_xmr']:.4f} XMR pending", "info")
            self._state["mo_alerted"] = True
            self._save()
        elif mo and mo["due_xmr"] < 0.0005 and self._state.get("mo_// l la ruta correcta es mo_alerted"):
        elif mo and mo["due_xmr"] < 0.0005 and self._state.get("mo_alerted"):
            self._state["mo_alerted"] = False
            self._save()

        self.last_snapshot = snap
        return snap

    def snapshot_light(self) -> dict:
        um = self.last_snapshot.get("unmineable") or {}
        mo = self.last_snapshot.get("moneroocean") or {}
        return {"unmineable": {"balance": float(um.get("balance", 0) or 0), "balance_payable": float(um.get("balance_payable", 0) or 0), "threshold": float(um.get("payment_threshold", 0) or 0)}, "moneroocean": {"due_xmr": float(mo.get("due_xmr", 0) or 0)}, "binance_total_btc": self._state.get("deposit_total_btc", 0.0)}

    def run(self):
        self._stop.wait(10)
        while not self._stop.is_set():
            try: self.tick()
            except: pass
            self._stop.wait(self.poll)
