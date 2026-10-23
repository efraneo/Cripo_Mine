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

from config import DATA_DIR
from pool_stats import get_price

# DATA_DIR (no BASE_DIR/data): en la nube solo /tmp es escribible.
PAYOUT_STATE_FILE = os.path.join(DATA_DIR, "payout_state.json")
UA = {"User-Agent": "btc-miner-studio/2.0"}
MO_API = "https://api.moneroocean.stream/miner/{addr}/stats"
UM_API = "https://api.unmineable.com/v4/address/{addr}?coin={coin}"


# ---------------------------------------------------------------------------
# Lecturas puntuales (las usa el watcher Y el dashboard)
# ---------------------------------------------------------------------------
def fetch_unmineable(btc_address: str, coin: str = "BTC"):
    """Estado real de la dirección en unMineable (API v4, verificada 2026).
    Devuelve {balance, balance_payable, payment_threshold, mining_fee, auto}
    o None. El umbral de pago lo decide el pool (payment_threshold).
    `coin` = BTC | USDT (la misma API sirve para las dos monedas de pago)."""
    if not btc_address:
        return None
    try:
        import requests
        r = requests.get(UM_API.format(addr=btc_address,
                                       coin=(coin or "BTC").upper()),
                         headers=UA, timeout=10)
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


def fetch_binance_deposits(binance, limit: int = 20,
                           coin: str = "BTC", on_error=None) -> list:
    """Lista de depósitos (BTC o USDT) o [] si no hay claves/servicio.
    Si Binance devuelve error (key inválida, IP baneada, 429/418) se avisa
    vía `on_error(exc)` para NO morir en silencio — antes un 4xx dejaba las
    alertas de depósito muertas sin decir nada."""
    if binance is None:
        return []
    try:
        hist = binance.deposit_history((coin or "BTC").upper(), limit)
        # Filtra simulados (modo sin claves) para no falsas alertas
        return [d for d in hist if not d.get("simulado")]
    except Exception as e:
        if on_error is not None:
            try:
                on_error(e)
            except Exception:
                pass
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
        coin = str(cfg.get("PAYOUT_COIN") or "BTC").strip().upper() or "BTC"
        _addr_key = "USDT_PAYOUT_ADDRESS" if coin == "USDT" \
            else "BTC_PAYOUT_ADDRESS"
        price, _ = get_price("binance")
        snap = {"ts": time.time(), "price_usd": price, "coin": coin,
                "unmineable": None, "moneroocean": None,
                "binance_nuevos": [], "binance_total_btc":
                    self._state.get("deposit_total_btc", 0.0)}

        # --- 1) Depósitos nuevos en Binance -------------------------------
        _binance_errs = [0]

        def _on_bin_err(_e):
            _binance_errs[0] += 1
            # Tras 3 fallos seguidos avisamos UNA vez (se rearma al volver)
            if _binance_errs[0] == 3:
                self.on_alert(
                    f"ALERTAS DE BINANCE CAÍDAS: no puedo consultar "
                    f"depósitos ({type(_e).__name__}: {str(_e)[:120]}). "
                    f"Revisa la API key o la IP whitelisteada.", "error")
            self._state["binance_failing"] = _binance_errs[0] > 2

        deps = fetch_binance_deposits(self.binance, 20, coin=coin,
                                      on_error=_on_bin_err)
        if self._state.get("binance_failing") and \
                _binance_errs[0] == 0:
            self._state["binance_failing"] = False
            self.on_alert("Alertas de Binance restauradas: consultas OK",
                          "ok")
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
                   # USD: si el pago es en USDT el monto YA es USD; en BTC
                   # hay que convertirlo al precio del momento.
                   "usd": (amount if coin == "USDT" else
                           (amount * price) if price else None)}
            nuevos.append(rec)
            # Solo alertamos los acreditados (status 1); pendientes se ven
            if rec["status"] == 1 and amount > 0:
                self.on_alert(
                    f"DEPÓSITO RECIBIDO EN BINANCE: {amount:.8f} {coin}"
                    + (f" (≈ USD {rec['usd']:,.2f})" if rec["usd"] else ""),
                    "money")
                self._state["deposit_total_btc"] = \
                    self._state.get("deposit_total_btc", 0.0) + amount
        if nuevos:
            # Lista ordenada y estable (antes era un set: el truncado
            # [-200:] descartaba txids al azar y re-alertaba depósitos).
            historial = sorted(
                ((str(d.get("txId", ""))[:40], int(d.get("insertTime", 0)))
                 for d in deps if str(d.get("txId", ""))),
                key=lambda x: x[1])
            self._state["known_txids"] = [t for t, _ in historial][-200:]
            snap["binance_nuevos"] = nuevos
            self._save()

        # --- 2) unMineable: balance y umbral (el umbral real lo da la API) --
        um = fetch_unmineable((cfg.get(_addr_key) or "").strip(), coin=coin)
        snap["unmineable"] = um
        if um:
            payable = float(um.get("balance_payable", 0) or 0)
            try:
                umbral_cfg = float(cfg.get("PAYOUT_ALERT_MIN_BTC", 0) or 0)
            except (TypeError, ValueError):
                umbral_cfg = 0.0
            # umbral por defecto según la moneda de pago elegida
            umbral_def = 1.5 if coin == "USDT" else 0.00075
            # umbral del pool si existe; si no, el configurado; si no, default
            umbral = float(um.get("payment_threshold") or 0) \
                or umbral_cfg or umbral_def
            snap["umbral_unmineable"] = umbral
            if payable >= umbral and not self._state.get("accum_alerted"):
                self.on_alert(
                    f"PAYOUT EN CAMINO (unMineable): pagable {payable:.8f} "
                    f"{coin} ≥ umbral del pool {umbral:.4f}. El pago llegará "
                    f"tu Spot de Binance como {coin}.", "money")
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

        # --- 4) Informe periódico de GANANCIAS (aviso "cuando gane algo") --
        if um:
            self._earnings_report(um, payable, umbral, coin, time.time())

        self.last_snapshot = snap
        return snap

    # ------------------------------------------------------------------
    def _earnings_report(self, um: dict, payable: float, umbral: float,
                         coin: str, now: float):
        """Aviso periódico a Telegram con lo ganado, ritmo y ETA al pago.

        Cadencia: EARNINGS_REPORT_HOURS (secrets, default 4 h; 0 = off).
        El primer tick solo fija la línea base (sin spamear). Si no ha
        crecido el balance desde el último informe, se omite."""
        try:
            rep_h = float(self.cfg.get("EARNINGS_REPORT_HOURS", 4) or 0)
        except (TypeError, ValueError):
            rep_h = 4.0
        if rep_h <= 0 or umbral <= 0:
            return
        st = self._state
        if not st.get("earn_ts"):                    # línea base la 1ª vez
            st.update({"earn_ts": now, "earn_bal": payable,
                       "earn_report": now})
            self._save()
            return
        if now - float(st.get("earn_report", 0)) < rep_h * 3600:
            return
        base_bal = float(st.get("earn_bal", 0) or 0)
        base_ts = float(st.get("earn_ts", 0) or 0)
        delta = payable - base_bal
        st.update({"earn_report": now, "earn_bal": payable, "earn_ts": now})
        self._save()
        if delta <= 0 and payable <= 0:
            return                                    # nada nuevo que avisar
        # ritmo (coin/hora) y ETA honestos sobre la ventana medida
        horas = max((now - base_ts) / 3600.0, 1e-6)
        ritmo = max(payable - base_bal, 0.0) / horas
        falta = max(umbral - payable, 0.0)
        if ritmo > 0 and falta > 0:
            eta_h = falta / ritmo
            eta_txt = (f"{eta_h/24:.1f} días" if eta_h >= 48 else
                       f"{eta_h:.1f} horas")
        else:
            eta_txt = "sin datos suficientes aún"
        pct = (payable / umbral * 100.0) if umbral else 0.0
        prec = 6 if coin == "USDT" else 8
        self.on_alert(
            f"<b>GANANCIA ACUMULADA</b>\n"
            f"Saldo pool: <b>{payable:.{prec}f} {coin}</b> "
            f"({pct:.2f}% de {umbral:g} {coin})\n"
            f"Últimas {horas:.1f} h: +{max(delta, 0):.{prec}f} {coin} "
            f"· ritmo {ritmo:.6f} {coin}/h\n"
            f"ETA al pago en tu Spot de Binance: <b>{eta_txt}</b>",
            "money")

    # ------------------------------------------------------------------
    def snapshot_light(self) -> dict:
        """Versión ligera para /estado de Telegram (sin llamadas de red)."""
        um = self.last_snapshot.get("unmineable") or {}
        mo = self.last_snapshot.get("moneroocean") or {}
        return {
            "coin": str(self.cfg.get("PAYOUT_COIN") or "BTC").upper(),
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
