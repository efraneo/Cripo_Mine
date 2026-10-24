"""
telegram_bot.py — Alertas y CONTROL REMOTO vía Telegram (Bot API oficial)
=========================================================================
Docs: https://core.telegram.org/bots/api  (solo /sendMessage y /getUpdates)

Setup en 2 minutos:
  1. Habla con @BotFather en Telegram → /newbot → guarda el TOKEN
  2. Escribe un mensaje a tu bot (p.ej. "hola") y llama a print_chat_ids()
     (o usa @userinfobot) para conocer tu CHAT_ID
  3. Pon ambos en secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

Comandos que el bot entiende (solo desde tu chat configurado):
  /estado   → hashrate, objetivo actual, uptime, shares, balances
  /pausar   → pausa el minero (ideal cuando necesitas la CPU)
  /reanudar → vuelve a minar
  /cambiar  → fuerza el failover al siguiente pool
  /ganancias→ PRUEBA DE GANANCIAS en vivo: saldo del pool, % del
             umbral de pago, cuánto BTC/día puedes ganar (3 escenarios)
             y la comparativa honesta ANTES vs AHORA
  /hidra    → estado de LA HIDRA: las 5 cabezas, récord de hashrate,
             exclusiones de Defender y reparaciones automáticas (v3.7)
  /apagar   → APAGA TODO: daemon + xmrig + este bot (v3.2)
  /ayuda    → lista de comandos

Alertas automáticas que envía el daemon:
  arranque/parada · failover con motivo · hito de shares · depósito
  acreditado en Binance (con USD) · balance de pool cruzando el umbral ·
  pausa térmica · resumen diario.
"""
import threading
import time

import requests

import control

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT_SEND = 12
ICON = {"ok": "🟢", "warn": "🟡", "error": "🔴", "info": "⚪", "money": "💸"}


def _api(cfg, method: str, params: dict = None, timeout: int = 10):
    token = (cfg.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Falta TELEGRAM_BOT_TOKEN en secrets")
    url = API.format(token=token, method=method)
    r = requests.get(url, params=params or {}, timeout=timeout)
    data = r.json() if r.headers.get("content-type", "").startswith(
        "application/json") else {}
    if not data.get("ok"):
        desc = data.get("description", f"HTTP {r.status_code}")
        raise RuntimeError(f"Telegram {method}: {desc}")
    return data


def configured(cfg) -> bool:
    return bool((cfg.get("TELEGRAM_BOT_TOKEN") or "").strip() and
                str(cfg.get("TELEGRAM_CHAT_ID") or "").strip())


def send(cfg, text: str, level: str = "info", silent: bool = False) -> bool:
    """Envía un mensaje (HTML). Nunca explota: devuelve True/False."""
    if not configured(cfg):
        return False
    prefix = ICON.get(level, "") + " "
    payload = {
        "chat_id": str(cfg["TELEGRAM_CHAT_ID"]).strip(),
        "text": prefix + text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": bool(silent),
    }
    try:
        _api(cfg, "sendMessage", payload, timeout=TIMEOUT_SEND)
        return True
    except Exception as e:
        # log al evento del daemon (si existe el store) pero sin romper nada
        try:
            from state_store import StateStore
            StateStore.get().append_event(f"Telegram: {e}", "warn")
        except Exception:
            pass
        return False


def print_chat_ids(cfg):
    """Ayuda de setup: imprime los chats que han escrito al bot."""
    data = _api(cfg, "getUpdates", {"limit": 20})
    found = {}
    for u in data.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            found[str(chat["id"])] = chat.get("first_name",
                                              chat.get("title", "?"))
    return found


# ---------------------------------------------------------------------------
# Mensajes con formato
# ---------------------------------------------------------------------------
def msg_daemon_started(cfg, status: dict):
    eng = status.get("engine") or {}
    t = eng.get("target") or status.get("target") or {}
    disp = eng.get("disponibles") or []
    extra = ""
    if len(disp) == 1:
        extra = ("\n<b>Modo SOLO-BTC</b>: sin WALLET_XMR solo mina "
                 "unMineable y todo lo minado llega en BTC a tu "
                 "dirección (Binance si es su dirección de depósito).")
    send(cfg, (
        "<b>DAEMON AGRESIVO INICIADO</b>\n"
        f"Objetivo: <b>{t.get('nombre', '—')}</b>\n"
        f"Pool: <code>{t.get('url', '—')}</code>\n"
        f"Algoritmo: <code>{t.get('algo', '—')}</code> · pago en "
        f"<b>{t.get('pago', '—')}</b>\n"
        f"Failover automático activado. Comandos: /ayuda" + extra), "ok")


def msg_daemon_stopped(cfg, reason: str = ""):
    send(cfg, "<b>DAEMON DETENIDO</b>" + (f"\nMotivo: {reason}" if reason
                                           else ""), "warn")


def msg_switch(cfg, snap_entry: dict):
    send(cfg, (
        "<b>FAILOVER</b> — cambio de pool\n"
        f"De: <code>{snap_entry.get('from')}</code> → "
        f"A: <b>{snap_entry.get('to')}</b>\n"
        f"Motivo: {snap_entry.get('reason')}"), "warn")


def msg_share_milestone(cfg, shares_ok: int, hashrate: str):
    send(cfg, f"<b>{shares_ok}</b> shares aceptados acumulados · "
              f"hashrate {hashrate}", "ok", silent=True)


def msg_deposit(cfg, amount_btc: float, usd: float, txid: str):
    send(cfg, (
        "<b>DEPÓSITO RECIBIDO EN BINANCE</b>\n"
        f"Monto: <b>{amount_btc:.8f} BTC</b>"
        + (f" (≈ USD {usd:,.2f})" if usd else "") + "\n"
        f"tx: <code>{str(txid)[:32]}</code>"), "money")


def msg_payout_incoming(cfg, source: str, balance: float, coin: str,
                        threshold: float):
    send(cfg, (
        "<b>PAYOUT EN CAMINO</b>\n"
        f"Balance en {source}: <b>{balance:.8f} {coin}</b>\n"
        f"Umbral: {threshold:.4f} {coin} → el pool pagará a tu dirección "
        f"próximamente"), "money")


def msg_thermal(cfg, paused: bool, temp: float):
    if paused:
        send(cfg, f"<b>PAUSA TÉRMICA</b> · CPU a {temp:.0f}°C. Se reanuda "
                  f"solo al bajar.", "warn")
    else:
        send(cfg, f"<b>Reanudado</b> · temperatura normalizada "
                  f"({temp:.0f}°C)", "ok")


def msg_daily(cfg, lines: list):
    send(cfg, "<b>RESUMEN DIARIO</b>\n" + "\n".join(lines), "info")


# ---------------------------------------------------------------------------
class TelegramController(threading.Thread):
    """Escucha comandos por long-polling y actúa sobre control.json."""

    def __init__(self, cfg: dict, get_status_fn, on_event=None,
                 hidra_fn=None):
        super().__init__(daemon=True, name="telegram-ctrl")
        self.cfg = cfg
        self.get_status = get_status_fn or (lambda *a, **k: {})
        self.on_event = on_event or (lambda m, l="info": None)
        self.hidra_fn = hidra_fn or (lambda: None)   # v3.7: snapshot HIDRA
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------
    def run(self):
        if not configured(self.cfg):
            self.on_event("Telegram no configurado (TELEGRAM_BOT_TOKEN / "
                          "TELEGRAM_CHAT_ID): seguimos sin alertas", "warn")
            return
        offset = 0
        my_chat = str(self.cfg["TELEGRAM_CHAT_ID"]).strip()
        self.on_event("Telegram conectado: escuchando comandos", "ok")
        while not self._stop.is_set():
            try:
                data = _api(self.cfg, "getUpdates", {
                    "offset": offset, "limit": 5, "timeout": 25,
                    "allowed_updates": '["message"]'}, timeout=35)
                for u in data.get("result", []):
                    offset = max(offset, int(u.get("update_id", 0)) + 1)
                    msg = u.get("message") or {}
                    chat = str((msg.get("chat") or {}).get("id", ""))
                    text = (msg.get("text") or "").strip()
                    if chat != my_chat or not text.startswith("/"):
                        continue     # solo el dueño; ignora extraños
                    self._handle(text.lower().split()[0])
            except Exception:
                self._stop.wait(5)

    # ------------------------------------------------------------------
    def _handle(self, cmd: str):
        self.on_event(f"Comando Telegram: {cmd}", "info")
        if cmd == "/estado":
            st = self.get_status()
            t = (st.get("engine") or {}).get("target") or {}
            tot = st.get("totals") or {}
            pay = st.get("payout") or {}
            um = pay.get("unmineable") or {}
            send(self.cfg, (
                "<b>ESTADO DEL MINERO</b>\n"
                f"Objetivo: <b>{t.get('nombre', '—')}</b>\n"
                f"Hashrate: <b>{st.get('hashrate_txt', '—')}</b>\n"
                f"Shares OK: <b>{tot.get('shares_ok', 0)}</b> · "
                f"Rechazados: {tot.get('shares_rej', 0)}\n"
                f"Uptime: {st.get('uptime_txt', '—')}\n"
                f"unMineable: {um.get('balance', 0):.8f} BTC "
                f"(pagable {um.get('balance_payable', 0):.8f})\n"
                f"Pausado: {'sí' if (st.get('engine') or {}).get('paused') else 'no'}"))
        elif cmd == "/pausar":
            control.write(paused_manual=True, updated_by="telegram")
            send(self.cfg, "Pausa manual activada. /reanudar para volver.",
                 "warn")
        elif cmd == "/reanudar":
            control.write(paused_manual=False, updated_by="telegram")
            send(self.cfg, "Reanudado. A romperla de nuevo.", "ok")
        elif cmd == "/cambiar":
            control.write(force_target="next", updated_by="telegram")
            send(self.cfg, "Failover forzado al siguiente pool…", "info")
        elif cmd == "/ganancias":
            # PRUEBA DE GANANCIAS completa (datos en vivo + proyección)
            try:
                import probar_ganancias
                probar_ganancias.enviar_prueba(self.cfg, motivo="comando")
            except Exception as e:                 # noqa: BLE001
                # Fallback: resumen ligero con los datos del daemon
                st = self.get_status(include_earnings=True)
                pay = st.get("payout") or {}
                um = pay.get("unmineable") or {}
                mo = pay.get("moneroocean") or {}
                deps = pay.get("binance_total_btc", 0.0)
                lines = [f"<b>GANANCIAS</b> (modo ligero: {e})"]
                if um:
                    lines.append(
                        f"unMineable: <b>{um.get('balance', 0):.8f}</b> BTC "
                        f"sin pagar (pagable {um.get('balance_payable', 0):.8f}"
                        + (f", umbral pool {um.get('threshold', 0):.5f}"
                           if um.get("threshold") else "") + ")")
                if mo:
                    lines.append(f"MoneroOcean: <b>{mo.get('due_xmr', 0):.6f}"
                                 f"</b> XMR pendientes")
                lines.append(f"Depósitos BTC vistos en Binance: "
                             f"<b>{deps:.8f}</b> BTC")
                send(self.cfg, "\n".join(lines), "money")
        elif cmd == "/hidra":
            # v3.7: estado de las 5 cabezas de LA HIDRA
            try:
                ss = self.hidra_fn() or {}
                if not ss:
                    raise RuntimeError("hidra sin snapshot")
                fuego = ss.get("fuego") or {}
                esc = ss.get("escudo") or {}
                best = float(ss.get("best_hashrate") or 0)
                act = ss.get("acciones") or []
                lines = ["<b>LA HIDRA (5 cabezas)</b>"]
                lines.append(f"Estado: <b>{'ACTIVA' if ss.get('activa') else 'APAGADA'}"
                             "</b> (fuego · escudo · médico · vigía · casa)")
                if fuego:
                    lines.append(f"FUEGO: hilos {fuego.get('fisicos', '?')} "
                                 f"físicos · RAM {fuego.get('ram_gb', '?')} GB · "
                                 f"AMD {'sí' if fuego.get('amd') else 'no'}")
                if esc:
                    lines.append(f"ESCUDO: admin {'sí' if esc.get('admin') else 'NO'} · "
                                 f"{esc.get('exclusiones', 0)} rutas + "
                                 f"{esc.get('procesos', 0)} procesos excluidos"
                                 + (f" · <b>{esc.get('amenazas_xmrig', 0)} "
                                    "detecciones xmrig</b>" if esc.get("amenazas_xmrig") else ""))
                if best > 0:
                    import config as _cfg
                    lines.append(f"RÉCORD: <b>{_cfg.format_hashrate(best)}</b>")
                if act:
                    last = act[-1]
                    lines.append(f"Última reparación: {last.get('tipo', '?')} "
                                 f"({', '.join(last.get('acciones', []) or ['—'])})")
                else:
                    lines.append("Sin reparaciones necesarias: todo limpio ✔")
                send(self.cfg, "\n".join(lines), "info")
            except Exception as e:                 # noqa: BLE001
                send(self.cfg, f"<b>HIDRA</b> aún sin datos ({e}). Se "
                               f"activa al arrancar el daemon.", "info")
        elif cmd in ("/apagar", "/stop", "/cerrar"):
            control.write(action="stop", updated_by="telegram")
            send(self.cfg, "<b>APAGADO TOTAL</b> en marcha: cerrando el "
                 "daemon, el minero (xmrig) y este bot. El saldo pendiente "
                 "en cada pool NO se pierde: consúltalo con /ganancias o "
                 "ejecutando recolectar_pool.py antes de apagar.", "warn")
        elif cmd in ("/ayuda", "/start", "/help"):
            send(self.cfg, (
                "<b>Comandos disponibles</b>\n"
                "/estado — resumen en vivo\n"
                "/pausar — detiene el minado (la CPU queda libre)\n"
                "/reanudar — vuelve a minar\n"
                "/cambiar — fuerza failover al siguiente pool\n"
                "/ganancias — PRUEBA: saldo del pool + cuánto "
                "BTC/día puedes ganar\n"
                "/hidra — estado de LA HIDRA (5 cabezas + récord "
                "de hashrate)\n"
                "/apagar — APAGA TODO (daemon + xmrig + bot)\n"
                "/ayuda — esta lista"), "info")
        else:
            send(self.cfg, "Comando no reconocido. /ayuda", "info")
