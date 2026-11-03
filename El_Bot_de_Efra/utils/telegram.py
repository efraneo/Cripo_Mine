# ============================================================
# utils/telegram.py — Wrapper unificado para app.py
# ============================================================

from utils.telegram_utils import (
    send_telegram_alert as _send_telegram_alert,
    send_telegram_chart as _send_telegram_chart,
    send_telegram_sticker as _send_telegram_sticker
)

# 👇 Cambiamos a telegram_alertas (no telegram_client)
from telegram_alertas import (
    enviar_sticker_bienvenida,
    enviar_gif_bienvenida,
    enviar_senal_con_confirmacion,
    manejar_confirmacion,
    iniciar_bot_telegram,
    manejar_prediccion
)

# ------------------------------------------------------------
# API compatible con "app.py"
# ------------------------------------------------------------

def send_telegram_message(msg: str):
    """
    Compatibilidad con app.py → manda un mensaje simple.
    """
    return _send_telegram_alert(msg)

def send_telegram_chart(path: str, caption=None):
    """
    Compatibilidad con app.py → manda gráfico.
    """
    return _send_telegram_chart(path, caption=caption)

def send_telegram_sticker(sticker_id: str):
    """
    Compatibilidad con app.py → manda sticker custom.
    """
    return _send_telegram_sticker(sticker_id)

# Alias adicionales para claridad
send_sticker_bienvenida = enviar_sticker_bienvenida
send_gif_bienvenida = enviar_gif_bienvenida
send_signal_with_confirmation = enviar_senal_con_confirmacion
