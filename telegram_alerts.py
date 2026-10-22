# -*- coding: utf-8 -*-
"""telegram_alerts.py — Avisos de Cripo_Mine a TU Telegram.

Orden del dueño: "que me muestre cada vez que gane algo o encuentre algo
en el telegram (buscar BTC)". Aquí se centraliza el envío con THROTTLE
para no inundar el chat (Telegram corta a los ~30 msg/min por bot):

  * bloques y errores        -> aviso INMEDIATO siempre
  * shares aceptados         -> 1.º al instante; después agrupados cada
                                AGUARDAR_SHARES s ("N shares aceptados…")
  * depósitos Binance BTC    -> aviso INMEDIATO (es dinero que entró)
  * progreso del minuto      -> resumen cada AVISO_CADA s si hubo avance

Las credenciales salen de .streamlit/secrets.toml (TELEGRAM_BOT_TOKEN y
TELEGRAM_CHAT_ID), que son las MISMAS del bot efra — jamás se imprimen.
"""
import os
import time

import requests

AGUARDAR_SHARES = 60.0       # agrupa shares aceptados cada minuto
AVISO_CADA = 300.0           # resumen de progreso cada 5 min
_ULTIMO_ENVIO = {}           # clave -> ts (throttle por tipo)
_BUFFER_SHARES = {"n": 0, "ultimo": 0.0}


def _credenciales():
    """Lee el TOML directo (fuera de Streamlit `st.secrets` puede no cargar,
    y config.load_secrets filtra llaves fuera de DEFAULTS)."""
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".streamlit", "secrets.toml")
    try:
        import tomllib
        with open(ruta, "rb") as f:
            s = tomllib.load(f)
        plano = {k: v for k, v in s.items() if isinstance(v, str)}
        return (plano.get("TELEGRAM_BOT_TOKEN", ""),
                plano.get("TELEGRAM_CHAT_ID", ""))
    except Exception:
        return "", ""


def enviar(texto):
    """Envía un mensaje de texto. Best-effort: nunca rompe al minero."""
    token, chat = _credenciales()
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": texto, "parse_mode": "HTML"},
            timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def aviso_inmediato(texto, clave=None, min_seg=20.0):
    """Aviso instantáneo con throttle por clave (evita ráfagas iguales)."""
    ahora = time.time()
    if clave and ahora - _ULTIMO_ENVIO.get(clave, 0.0) < min_seg:
        return False
    if clave:
        _ULTIMO_ENVIO[clave] = ahora
    return enviar(texto)


def share_aceptado():
    """Un share aceptado = un "ganó". 1.º al instante, luego en tandas."""
    ahora = time.time()
    _BUFFER_SHARES["n"] += 1
    if _BUFFER_SHARES["n"] == 1:
        _BUFFER_SHARES["ultimo"] = ahora
        return enviar("⛏️ <b>Share ACEPTADO por el pool</b> — minuto "
                      f"{time.strftime('%H:%M:%S')} · ¡trabajo validado!")
    if ahora - _BUFFER_SHARES["ultimo"] >= AGUARDAR_SHARES:
        n = _BUFFER_SHARES["n"] - 1
        _BUFFER_SHARES["n"] = 1
        _BUFFER_SHARES["ultimo"] = ahora
        return enviar(f"⛏️ <b>+{n} shares aceptados</b> en el último "
                      f"minuto (agrupados para no inundar)")
    return False


def bloque_encontrado(detalles=""):
    return enviar(f"🏆 <b>¡BLOQUE ENCONTRADO!</b> {detalles}")


def deposito_encontrado(monto, coin="BTC"):
    return aviso_inmediato(
        f"💰 <b>DEPÓSITO {coin} ENCONTRADO en Binance</b>\n"
        f"💵 Monto: {monto}\n"
        f"🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}", clave="deposito",
        min_seg=60.0)


def resumen_si_hubo_avance(shares_ok, hashrate, blocks):
    """Cada AVISO_CADA s, sólo si algo cambió (hashrate ≠ 0 o shares)."""
    ahora = time.time()
    if ahora - _ULTIMO_ENVIO.get("resumen", 0.0) < AVISO_CADA:
        return False
    if not shares_ok and not hashrate:
        return False
    _ULTIMO_ENVIO["resumen"] = ahora
    return enviar(
        f"📊 <b>Minuto {time.strftime('%H:%M:%S')}</b>\n"
        f"⛏️ Shares aceptados: {shares_ok} · bloques: {blocks}\n"
        f"🔥 Hashrate: {hashrate:,.0f} H/s")
