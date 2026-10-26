"""
pools_catalog.py — Catálogo v4.1 de pools VERIFICADOS con handshake real
========================================================================
Verificación 27-10-2026 20:47 UTC (handshake stratum mining.subscribe →
respuesta JSON real, no solo TCP — ver pools_salud.stratum_ok):

  VIVO   gulf.moneroocean.stream:10128   MoneroOcean (auto-algoritmo)
  VIVO   xmrpool.eu:9999                 xmrpool.eu (RandomX)
  VIVO   pool.supportxmr.com:3333        SupportXMR (veterano)
  ZOMBI  rx.unmineable.com:3333/:443     unMineable (TCP sí, stratum no)
  MUERTO xmr.kryptex.network:7029        Kryptex (0 bytes)
  NxDOM  rx.mine.zergpool.com:5354       ZergPool (dominio sin DNS)
  NxDOM  randomxauto.*.nicehash.com      NiceHash (no resolvió + exige
                                         cuenta propia; no automatizable)
  MUERTO pool.hashvault.pro / nanopool   descartados hoy

Orden del catálogo = prioridad de intento: primero los VIVOS hoy (pagan
XMR y desbloquean el hashrate YA); unMineable queda al FINAL para
reintegrar el pago BTC-directo a Binance cuando vuelva a la vida (el
motor re-sondea y salta solo). Sin WALLET_XMR, wallet_monero.py genera
una offline en el arranque — por eso los objetivos XMR son siempre
disponibles.
"""
import os


def _user_wallet(cfg, worker):
    w = (cfg.get("WALLET_XMR") or "").strip()
    if not w:
        # v4.0: en vez de romper, se genera wallet offline (la llama
        # aggressive_engine.targets_available). Aquí el error guía.
        raise ValueError("Falta WALLET_XMR (se genera sola en el "
                         "arranque; también puedes poner la tuya)")
    return w


def _user_kryptex(cfg, worker):
    """Kryptex usa formato wallet/worker."""
    return f"{_user_wallet(cfg, worker)}/{(worker or 'cpu01') or 'cpu01'}"


def _user_unmineable(cfg, worker):
    addr = (cfg.get("BTC_PAYOUT_ADDRESS") or "").strip()
    if not addr:
        raise ValueError("Falta BTC_PAYOUT_ADDRESS (necesaria para que "
                         "unMineable pague en BTC a tu Binance)")
    return f"BTC:{addr}.{(worker or 'cpu01').strip() or 'cpu01'}"


def _t(id_, nombre, url, algo, pago, user_fn, pass_fn=None):
    return {"id": id_, "nombre": nombre, "url": url, "algo": algo,
            "pago": pago, "user_fn": user_fn, "pass_fn": pass_fn}


TARGETS = [
    _t("moneroocean",
       "MoneroOcean (auto-algoritmo, max profit, paga XMR)",
       "gulf.moneroocean.stream:10128", "auto", "XMR", _user_wallet),
    _t("xmrpool-eu",
       "xmrpool.eu (RandomX puro, paga XMR, umbral bajo)",
       "xmrpool.eu:9999", "rx/0", "XMR", _user_wallet),
    _t("supportxmr",
       "SupportXMR (respaldo veterano, paga XMR)",
       "pool.supportxmr.com:3333", "rx/0", "XMR", _user_wallet),
    _t("kryptex",
       "Kryptex XMR (respaldo, estaba muerto 27-10-2026)",
       "xmr.kryptex.network:7029", "rx/0", "XMR", _user_kryptex),
    _t("unmineable",
       "unMineable (paga BTC directo a Binance; ZOMBI 27-10-2026, "
       "se reintenta solo)",
       "rx.unmineable.com:3333", "rx/0", "BTC", _user_unmineable),
    _t("unmineable-ssl",
       "unMineable SSL (mismo pool, cifrado :443)",
       "stratum+ssl://rx.unmineable.com:443", "rx/0", "BTC",
       _user_unmineable),
]

URLS_POR_ID = {t["id"]: t["url"] for t in TARGETS}


def objetivo_por_id(id_: str):
    for t in TARGETS:
        if t["id"] == id_:
            return t
    return None


def resumen_catalogo() -> str:
    return " | ".join(f"{t['id']}→{t['pago']}" for t in TARGETS)


# Carpeta base del proyecto (misma convención que config.py)
try:
    from config import BASE_DIR  # noqa: F401
except Exception:                                        # noqa: BLE001
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
