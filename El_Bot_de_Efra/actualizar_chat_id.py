import os
import time
import telegram
from config_loader import TELEGRAM_BOT_TOKEN
from logger import logger

def obtener_chat_id(timeout=60):
    """
    Escucha nuevos mensajes para capturar el chat_id.
    """
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info("🟡 Esperando mensaje para registrar chat_id...")

        start_time = time.time()
        updates = []

        while time.time() - start_time < timeout:
            updates = bot.get_updates(timeout=10)
            if updates:
                last_update = updates[-1]
                chat_id = last_update.message.chat_id
                nombre = last_update.message.chat.username or last_update.message.chat.first_name
                logger.info(f"🟢 Mensaje recibido de {nombre}, chat_id = {chat_id}")
                return chat_id

            time.sleep(2)

        logger.warning("⏳ No se recibió ningún mensaje dentro del tiempo límite.")
        return None

    except Exception as e:
        logger.error(f"❌ Error al obtener chat_id: {e}")
        return None

def guardar_chat_id(chat_id, ruta=".env"):
    """
    Guarda el chat_id en el archivo .env
    """
    try:
        lines = []
        if os.path.exists(ruta):
            with open(ruta, "r") as f:
                lines = f.readlines()

        with open(ruta, "w") as f:
            actualizado = False
            for line in lines:
                if line.startswith("TELEGRAM_CHAT_ID="):
                    f.write(f"TELEGRAM_CHAT_ID={chat_id}\n")
                    actualizado = True
                else:
                    f.write(line)
            if not actualizado:
                f.write(f"TELEGRAM_CHAT_ID={chat_id}\n")

        logger.info(f"💾 Chat ID guardado correctamente en {ruta}")
    except Exception as e:
        logger.error(f"❌ Error al guardar chat_id: {e}")

if __name__ == "__main__":
    chat_id = obtener_chat_id()
    if chat_id:
        guardar_chat_id(chat_id, ruta="telegram.env")
