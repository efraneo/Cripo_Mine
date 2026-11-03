# ============================================================
# utils/telegram_client.py — Cliente unificado para Telegram
# ============================================================

import os
import json
import csv
import requests
from datetime import datetime

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

from utils.logger import log_error, log_info
from utils.comun import cargar_activos, obtener_datos_binance, normalizar_columnas
from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
from utils.binance_client import ejecutar_orden_market
from utils.db_handler import guardar_en_base_datos

# ============================================================
# Configuración
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if TELEGRAM_BOT_TOKEN:
    bot_telegram = Bot(token=TELEGRAM_BOT_TOKEN)
else:
    bot_telegram = None
    log_error("TELEGRAM_BOT_TOKEN no configurado", archivo="telegram_client.py", funcion="init")

CONFIRMACION_PATH = "estado_confirmacion.json"
ultima_senal = {}

# ============================================================
# 🎨 Estilos por acción de trading (Stickers + GIFs motivadores)
# ============================================================
ACCION_ESTILOS = {
    "buy": {
        "emoji": "🟢📈🚀",
        "sticker": "CAACAgIAAxkBAAEBwNhlVf61gQFQ5aQBuyStickerBull",
        "gif": "https://media.giphy.com/media/3oEjI6SIIHBdRxXI40/giphy.gif"
    },
    "sell": {
        "emoji": "🔴📉💥",
        "sticker": "CAACAgIAAxkBAAEBwNplVf62kJsSellBearSticker",
        "gif": "https://media.giphy.com/media/3o7aCTfyhYawdOXcFW/giphy.gif"
    },
    "hold": {
        "emoji": "🟡🤔⏳",
        "sticker": "CAACAgIAAxkBAAEBwNxlVf63HodHoldStickerNeutral",
        "gif": "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif"
    }
}


def enviar_sticker_accion(chat_id: str, accion: str) -> bool:
    """
    Envía un sticker acorde a la acción (buy/sell/hold).
    """
    try:
        if not bot_telegram:
            log_error("Bot Telegram no inicializado", archivo="telegram_client.py", funcion="enviar_sticker_accion")
            return False
        estilo = ACCION_ESTILOS.get(accion.lower())
        if not estilo:
            return False
        bot_telegram.send_sticker(chat_id=chat_id, sticker=estilo["sticker"])
        return True
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="enviar_sticker_accion")
        return False


def enviar_gif_accion(chat_id: str, accion: str) -> bool:
    """
    Envía un GIF motivador acorde a la acción, solo si precisión > 90%.
    """
    try:
        if not bot_telegram:
            log_error("Bot Telegram no inicializado", archivo="telegram_client.py", funcion="enviar_gif_accion")
            return False
        estilo = ACCION_ESTILOS.get(accion.lower())
        if not estilo:
            return False
        gif_url = estilo.get("gif")
        if not gif_url:
            return False
        bot_telegram.send_animation(chat_id=chat_id, animation=gif_url)
        return True
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="enviar_gif_accion")
        return False

# ============================================================
# 📂 Guardar operación en CSV
# ============================================================
def guardar_operacion_csv(datos, archivo="logs/operaciones.csv"):
    """Guarda una operación en CSV (append)."""
    try:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        existe = os.path.exists(archivo)
        with open(archivo, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(datos.keys()))
            if not existe:
                writer.writeheader()
            writer.writerow(datos)
        return True
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="guardar_operacion_csv")
        return False

# ============================================================
# 📨 Mensajes de texto
# ============================================================
def send_telegram_alert(mensaje: str, botones=None):
    """Enviar un mensaje a Telegram (texto + opcional inline buttons)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": mensaje,
            "parse_mode": "HTML"
        }
        if botones:
            payload["reply_markup"] = {
                "inline_keyboard": [[{"text": b["texto"], "url": b["url"]}] for b in botones]
            }
        requests.post(url, json=payload)
        log_info(f"Mensaje enviado a Telegram: {mensaje[:40]}...", archivo="telegram_client.py", funcion="send_telegram_alert")
        return True
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="send_telegram_alert")
        return False

# ============================================================
# 🖼️ Gráficos (charts)
# ============================================================
def send_telegram_chart(imagen_path: str, caption="📊 Análisis Técnico"):
    """Enviar una imagen a Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if not os.path.exists(imagen_path):
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(imagen_path, "rb") as img:
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML"
            }
            files = {"photo": img}
            requests.post(url, data=data, files=files)
        log_info(f"Gráfico enviado a Telegram: {imagen_path}", archivo="telegram_client.py", funcion="send_telegram_chart")
        return True
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="send_telegram_chart")
        return False

# ============================================================
# ✅ Manejar confirmación de señal (inline buttons)
# ============================================================
def manejar_confirmacion(update, context):
    """Maneja las respuestas de confirmación en Telegram."""
    query = update.callback_query
    data = query.data
    chat_id = query.message.chat_id

    try:
        estado = {}
        if os.path.exists(CONFIRMACION_PATH):
            with open(CONFIRMACION_PATH, "r") as f:
                estado = json.load(f)

        senal = estado.get("senal", {})

        if data == "confirmar":
            estado["estado"] = "pendiente_monto"
            estado["usuario"] = chat_id
            with open(CONFIRMACION_PATH, "w") as f:
                json.dump(estado, f)

            query.edit_message_text(
                text="✅ Confirmado.\n💵 Ahora envíame el monto a invertir en USDT:",
                parse_mode="HTML"
            )

        elif data == "cancelar":
            query.edit_message_text("❌ Operación cancelada por el usuario.", parse_mode="HTML")
            if os.path.exists(CONFIRMACION_PATH):
                os.remove(CONFIRMACION_PATH)

        else:
            query.edit_message_text("⚠️ Opción no reconocida.", parse_mode="HTML")

    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="manejar_confirmacion")
        query.edit_message_text(text="❌ Error procesando confirmación.")

# ============================================================
# 📝 Manejar mensaje con monto
# ============================================================
def manejar_mensaje(update, context):
    """Recoge respuestas de texto (ej: monto en USDT)."""
    chat_id = update.effective_chat.id
    texto = update.message.text.strip()

    if os.path.exists(CONFIRMACION_PATH):
        try:
            with open(CONFIRMACION_PATH, "r") as f:
                estado = json.load(f)
        except Exception:
            estado = {}

        if estado.get("estado") == "pendiente_monto" and str(estado.get("usuario")) == str(chat_id):
            try:
                monto = float(texto)
                senal = estado.get("senal", {})
                activo = senal.get("activo")
                accion = senal.get("accion")
                precision = senal.get("precision")
                hora_entrada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 🚀 Ejecutar orden en Binance
                mercado = "spot"
                modo_real = True
                res = ejecutar_orden_market(
                    symbol=activo,
                    side=accion.upper(),
                    notional_usd=monto,
                    dry_run=not modo_real,
                    mercado=mercado
                )

                if res.get("success"):
                    context.bot.send_message(chat_id=chat_id, text="✅ Orden ejecutada en Binance.", parse_mode="HTML")
                    order_data = res.get("order", {})
                    fills = order_data.get("fills", [])
                    precio_entrada = float(fills[0]["price"]) if fills else None

                    datos_guardar = {
                        "fecha": hora_entrada,
                        "usuario": chat_id,
                        "activo": activo,
                        "accion": accion,
                        "monto": monto,
                        "tipo": "real" if modo_real else "dry-run",
                        "precision": precision,
                        "conclusion": senal.get("conclusion"),
                        "precio_entrada": precio_entrada,
                        "tp1": senal.get("tp1"),
                        "tp2": senal.get("tp2"),
                        "tp3": senal.get("tp3"),
                        "tp4": senal.get("tp4"),
                        "sl": senal.get("sl"),
                        "duracion": senal.get("duracion"),
                    }

                    guardar_operacion_csv(datos_guardar)
                    guardar_en_base_datos(datos_guardar)
                    context.bot.send_message(chat_id=chat_id, text="📊 Operación registrada en historial.", parse_mode="HTML")
                else:
                    context.bot.send_message(chat_id=chat_id, text=f"❌ Error ejecutando la orden: {res.get('detail')}", parse_mode="HTML")

                os.remove(CONFIRMACION_PATH)
            except ValueError:
                context.bot.send_message(chat_id=chat_id, text="❌ Por favor envía un número válido en USDT.")

# ============================================================
# 🚀 Iniciar bot de Telegram
# ============================================================
def iniciar_bot_telegram():
    """Arranca el listener de Telegram (comandos + callbacks)."""
    if not TELEGRAM_BOT_TOKEN:
        log_error("⚠️ TELEGRAM_BOT_TOKEN no configurado.", archivo="telegram_client.py", funcion="iniciar_bot_telegram")
        return
    try:
        updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
        updater.dispatcher.add_handler(CallbackQueryHandler(manejar_confirmacion))
        updater.dispatcher.add_handler(CommandHandler("prediccion", manejar_prediccion))
        updater.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, manejar_mensaje))
        updater.start_polling()
        print("🤖 Bot de Telegram escuchando comandos...")
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="iniciar_bot_telegram")

# ============================================================
# 🔮 Ejemplo de comando: /prediccion
# ============================================================
def manejar_prediccion(update, context):
    """Muestra activos con mayor precisión IA."""
    chat_id = update.effective_chat.id
    try:
        activos_binance = [a[0] for a in cargar_activos() if a[1].lower() == "binance"]
        mejores = []
        for activo in activos_binance:
            df_raw = obtener_datos_binance(activo, intervalo="5m", limite=150)
            if df_raw.empty:
                continue
            df = normalizar_columnas(df_raw)
            df = agregar_indicadores_tecnicos(df)
            accion_ia = "BUY"
            precision = 0.97
            mejores.append({
                "activo": activo,
                "accion": accion_ia,
                "precision": precision * 100,
                "precio": df["close"].iloc[-1],
                "rsi": df["rsi"].iloc[-1],
                "macd": df["macd"].iloc[-1],
                "macd_signal": df["macd_signal"].iloc[-1],
                "tendencia": tendencia_mercado(df)
            })
        if mejores:
            mejor = sorted(mejores, key=lambda x: x["precision"], reverse=True)[0]
            resumen = f"""🚨 <b>Oportunidad IA</b>
📍 Activo: <b>{mejor['activo']}</b>
📉 Precio: ${mejor['precio']:.2f}
📈 Tendencia: {mejor['tendencia']}
📊 RSI: {mejor['rsi']:.2f} | MACD: {mejor['macd']:.2f}
🤖 Señal IA: <b>{mejor['accion']}</b>
🎯 Precisión: {mejor['precision']:.2f}%
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            context.bot.send_message(chat_id=chat_id, text=resumen, parse_mode="HTML")
        else:
            context.bot.send_message(chat_id=chat_id, text="🤖 No se encontraron oportunidades ≥ 96%.")
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="manejar_prediccion")

# ============================================================
# 📬 Wrapper unificado para compatibilidad con app.py
# ============================================================
def enviar_mensaje_telegram(mensaje: str, chart_path: str = None):
    """Wrapper unificado para enviar mensajes o gráficos a Telegram."""
    try:
        if chart_path:
            return send_telegram_chart(chart_path, caption=mensaje)
        else:
            return send_telegram_alert(mensaje)
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="enviar_mensaje_telegram")
        return False

# ============================================================
# 📡 Enviar señal con confirmación (extendido con estilos)
# ============================================================
def enviar_alerta_con_confirmacion(senal: dict):
    """
    Envía una alerta de trading a Telegram con botones de confirmación,
    emojis y stickers personalizados según la acción.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log_error("Telegram no configurado", archivo="telegram_client.py", funcion="enviar_alerta_con_confirmacion")
        return False

    try:
        # Guardar estado en archivo para manejar la confirmación
        estado = {
            "estado": "pendiente_confirmacion",
            "usuario": TELEGRAM_CHAT_ID,
            "senal": senal
        }
        with open(CONFIRMACION_PATH, "w") as f:
            json.dump(estado, f)

        accion = senal.get("accion", "hold").lower()
        estilo = ACCION_ESTILOS.get(accion, ACCION_ESTILOS["hold"])
        emoji = estilo["emoji"]

        # Construcción del mensaje
        mensaje = f"""{emoji} <b>Oportunidad Detectada</b>
📍 Activo: <b>{senal.get('activo')}</b>
🤖 Señal IA: <b>{senal.get('accion').upper()}</b>
🎯 Precisión: {senal.get('precision',0)*100:.2f}%
📊 Conclusión: {senal.get('conclusion','N/A')}
SL: {senal.get('sl','-')}
TP1: {senal.get('tp1','-')} | TP2: {senal.get('tp2','-')}
TP3: {senal.get('tp3','-')} | TP4: {senal.get('tp4','-')}
⏱️ Duración: {senal.get('duracion','N/A')} min
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        # Botones de Confirmar / Cancelar
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirmar", callback_data="confirmar")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ])

        # Enviar mensaje
        bot_telegram.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=mensaje,
            parse_mode="HTML",
            reply_markup=teclado
        )

        # Enviar sticker según acción
        enviar_sticker_accion(TELEGRAM_CHAT_ID, accion)

        # Si precisión > 90%, mandar también GIF motivador
        if senal.get("precision", 0) >= 0.9:
            enviar_gif_accion(TELEGRAM_CHAT_ID, accion)

        log_info("Señal enviada con confirmación + sticker.", archivo="telegram_client.py", funcion="enviar_alerta_con_confirmacion")
        return True

    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="enviar_alerta_con_confirmacion")
        return False

# ==========================================================
# 📌 Sticker de bienvenida
# ==========================================================
from telegram import Bot
import os

# ⚠️ Usa tu TOKEN de Telegram desde .env o variable de entorno
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None


def enviar_sticker_bienvenida(chat_id: str, sticker_id: str = "CAACAgUAAxkBAAEBwL5kVf5bXk8EXAMPLE") -> bool:
    """
    Envía un sticker de bienvenida a un usuario/grupo en Telegram.
    
    Args:
        chat_id (str): ID del chat o grupo.
        sticker_id (str): ID del sticker (por defecto uno genérico).
    
    Returns:
        bool: True si se envió correctamente, False en caso contrario.
    """
    try:
        if not bot:
            print("⚠️ Bot de Telegram no inicializado. Revisa TELEGRAM_TOKEN.")
            return False
        bot.send_sticker(chat_id=chat_id, sticker=sticker_id)
        return True
    except Exception as e:
        print(f"❌ Error enviando sticker: {e}")
        return False

# ==========================================================
# 🎬 GIF de bienvenida
# ==========================================================
def enviar_gif_bienvenida(chat_id: str, gif_url: str = "https://media.giphy.com/media/3o7aD2saalBwwftBIY/giphy.gif") -> bool:
    """
    Envía un GIF de bienvenida a un usuario/grupo en Telegram.

    Args:
        chat_id (str): ID del chat o grupo.
        gif_url (str): URL del GIF (por defecto uno divertido de Giphy).

    Returns:
        bool: True si se envió correctamente, False en caso contrario.
    """
    try:
        if not bot:
            print("⚠️ Bot de Telegram no inicializado. Revisa TELEGRAM_TOKEN.")
            return False
        bot.send_animation(chat_id=chat_id, animation=gif_url)
        return True
    except Exception as e:
        print(f"❌ Error enviando GIF: {e}")
        return False

# Alias universal para compatibilidad con app.py
def send_telegram_photo(image_buffer_or_path, caption="📊 Análisis"):
    """
    Enviar una foto a Telegram (buffer BytesIO o ruta de archivo).
    Usado como wrapper para app.py (equivalente a send_telegram_chart).
    """
    try:
        if hasattr(image_buffer_or_path, "read"):  # BytesIO
            files = {"photo": image_buffer_or_path}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            requests.post(url, data=data, files=files)
            return True
        elif isinstance(image_buffer_or_path, str) and os.path.exists(image_buffer_or_path):  # Ruta local
            return send_telegram_chart(image_buffer_or_path, caption=caption)
        else:
            log_error("Formato no soportado en send_telegram_photo", archivo="telegram_client.py", funcion="send_telegram_photo")
            return False
    except Exception as e:
        log_error(e, archivo="telegram_client.py", funcion="send_telegram_photo")
        return False
