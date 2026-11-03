# ==========================================================
# utils/telegram_utils.py — PTB v20+ (Opción 1: parse_mode="Markdown")
# ==========================================================
import os
import asyncio
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError
#from telegram.helpers import escape_markdown  # útil para sanitizar strings Markdown

from utils.logger import log_error

# ----------------------------------------------------------
# Carga de credenciales desde variables de entorno
# ----------------------------------------------------------
TELEGRAM_TOKEN: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_CHAT_ID")

# Validación temprana (no lanzamos excepción, pero dejamos traza)
if not TELEGRAM_TOKEN:
    log_error("TELEGRAM_BOT_TOKEN no está definido en entorno",
              archivo="telegram_utils.py", funcion="module_import")
if not TELEGRAM_CHAT_ID:
    log_error("TELEGRAM_CHAT_ID no está definido en entorno",
              archivo="telegram_utils.py", funcion="module_import")

# Instancia del bot (la API de PTB v20 admite uso directo de Bot en async)
bot_telegram = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None


# ----------------------------------------------------------
# Helpers de ejecución async/Sync
# ----------------------------------------------------------
def _ensure_loop():
    """Devuelve el event loop actual o crea uno nuevo si hace falta."""
    try:
        loop = asyncio.get_event_loop()
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def run_async_task(coro):
    """
    Ejecuta corutinas desde contexto síncrono de forma segura.
    - Si ya hay loop corriendo, programa el task y lo devuelve (Future).
    - Si no hay loop, crea uno, corre y devuelve el resultado.
    """
    try:
        loop = asyncio.get_running_loop()
        # Ya hay un loop corriendo: devolvemos la future (no bloqueante)
        return asyncio.ensure_future(coro)
    except RuntimeError:
        # No hay loop en ejecución: corremos el coro y devolvemos su resultado
        loop = _ensure_loop()
        return loop.run_until_complete(coro)


# ----------------------------------------------------------
# Funciones ASYNC principales
# ----------------------------------------------------------
async def send_telegram_alert(mensaje: str, markdown: bool = True):
    """
    Envía un mensaje al chat de Telegram.
    - Por defecto usa Markdown (PTB v20+: parse_mode="Markdown").
    - Sanitiza el texto si markdown=True (escape_markdown nivel 2).
    """
    if not bot_telegram or not TELEGRAM_CHAT_ID:
        log_error("Bot/ChatID no inicializados; no se envió el mensaje.",
                  archivo="telegram_utils.py", funcion="send_telegram_alert")
        return

    try:
        text = (escape_markdown(mensaje, version=2) if markdown else mensaje)
        await bot_telegram.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown" if markdown else None,
            disable_web_page_preview=True
        )
    except TelegramError as e:
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_alert")
    except Exception as e:
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_alert_unexpected")


async def send_telegram_chart(ruta_img: str, caption: Optional[str] = None, markdown: bool = False):
    """
    Envía una imagen (gráfico) a Telegram.
    - caption puede ir en Markdown si markdown=True (se escapa automáticamente).
    """
    if not bot_telegram or not TELEGRAM_CHAT_ID:
        log_error("Bot/ChatID no inicializados; no se envió la imagen.",
                  archivo="telegram_utils.py", funcion="send_telegram_chart")
        return

    try:
        if not os.path.exists(ruta_img):
            log_error(f"Archivo no encontrado: {ruta_img}",
                      archivo="telegram_utils.py", funcion="send_telegram_chart")
            return

        cap = escape_markdown(caption, version=2) if (caption and markdown) else (caption or "")
        with open(ruta_img, "rb") as f:
            await bot_telegram.send_photo(
                chat_id=TELEGRAM_CHAT_ID,
                photo=f,
                caption=cap,
                parse_mode="Markdown" if (caption and markdown) else None
            )
    except TelegramError as e:
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_chart")
    except Exception as e:
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_chart_unexpected")


async def send_telegram_sticker(sticker_id: str):
    """
    Envía un sticker a Telegram.
    - Asegúrate de usar un file_id válido o una URL directa de sticker.
    """
    if not bot_telegram or not TELEGRAM_CHAT_ID:
        log_error("Bot/ChatID no inicializados; no se envió el sticker.",
                  archivo="telegram_utils.py", funcion="send_telegram_sticker")
        return

    try:
        await bot_telegram.send_sticker(
            chat_id=TELEGRAM_CHAT_ID,
            sticker=sticker_id
        )
    except TelegramError as e:
        # Error común: "Wrong remote file identifier specified"
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_sticker")
    except Exception as e:
        log_error(e, archivo="telegram_utils.py", funcion="send_telegram_sticker_unexpected")


# ----------------------------------------------------------
# Wrappers SÍNCRONOS (compatibilidad con código no-async)
# ----------------------------------------------------------
def send_telegram_alert_sync(mensaje: str, markdown: bool = True):
    return run_async_task(send_telegram_alert(mensaje, markdown=markdown))

def send_telegram_chart_sync(ruta_img: str, caption: Optional[str] = None, markdown: bool = False):
    return run_async_task(send_telegram_chart(ruta_img, caption=caption, markdown=markdown))

def send_telegram_sticker_sync(sticker_id: str):
    return run_async_task(send_telegram_sticker(sticker_id))


#===========================================
# Mi propio Helper
#===========================================
import html

def escape_markdown(text: str) -> str:
    """
    Escapa caracteres peligrosos en Markdown V2 (PTB v20+ no lo trae por defecto).
    """
    if not text:
        return ""
    escape_chars = r"\_*[]()~`>#+-=|{}.!"
    for ch in escape_chars:
        text = text.replace(ch, "\\" + ch)
    return text
