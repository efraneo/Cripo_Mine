# telegram_alertas.py
import os
import json
import requests
from datetime import datetime
import pandas as pd

from config_loader import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import log_error
from utils.comun import cargar_activos, obtener_datos_binance, normalizar_columnas
from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
# ❌ Import diferido de procesar_senal para evitar circular import
from notificador_email import enviar_email

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

# ============================================================
# 📌 Estado de confirmación compartido con Streamlit
# ============================================================
CONFIRMACION_PATH = "estado_confirmacion.json"

def guardar_confirmacion(senal):
    """Guarda la confirmación de operación para que Streamlit pueda leerla."""
    try:
        with open(CONFIRMACION_PATH, "w", encoding="utf-8") as f:
            json.dump(senal, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="guardar_confirmacion")

def leer_confirmacion():
    """Lee la confirmación guardada (si existe)."""
    if not os.path.exists(CONFIRMACION_PATH):
        return None
    try:
        with open(CONFIRMACION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="leer_confirmacion")
        return None

# ============================================================
# 📨 Enviar mensaje con texto
# ============================================================
def send_telegram_alert(mensaje, botones=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Token o Chat ID de Telegram no configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': mensaje,
        'parse_mode': 'HTML'
    }
    if botones:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": b["texto"], "url": b["url"]}] for b in botones]
        }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="send_telegram_alert")

# ============================================================ 
# 🖼️ Enviar imagen (gráfico)
# ============================================================
def send_telegram_chart(imagen_path, caption='📊 Análisis Técnico'):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    if not os.path.exists(imagen_path):
        return

    import requests
    from requests.exceptions import ConnectionError, Timeout

    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'
    try:
        with open(imagen_path, 'rb') as img:
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            files = {'photo': img}
            # ✅ Timeout y manejo de errores de conexión robusto
            requests.post(url, data=data, files=files, timeout=10)
    except (ConnectionError, Timeout) as e_net:
        log_warning(f"⚠️ Error conexión Telegram (imagen): {e_net}",
                    archivo="telegram_alertas.py", funcion="send_telegram_chart")
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="send_telegram_chart")

# ============================================================
# 🖼️ Alias para enviar gráficos
# ============================================================
def enviar_imagen_telegram(ruta_imagen, mensaje="📊 Gráfico"):
    if os.path.exists(ruta_imagen):
        send_telegram_chart(ruta_imagen, caption=mensaje)

# ============================================================
# 🎭 GIF y Stickers de bienvenida
# ============================================================
def enviar_gif_bienvenida(chat_id=None):
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    gif_path = "media/bienvenida.gif"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAnimation"
    try:
        if os.path.exists(gif_path):
            with open(gif_path, "rb") as gif:
                files = {"animation": gif}
                data = {
                    "chat_id": chat_id,
                    "caption": "🎉 ¡Bienvenido a El Bot de Efra!",
                    "parse_mode": "HTML"
                }
                requests.post(url, files=files, data=data)
        else:
            # 📌 Enviar un GIF desde URL si no existe el archivo local
            gif_url = "https://media.giphy.com/media/QBd2kLB5qDmysEXre9/giphy.gif"
            requests.post(url, data={"chat_id": chat_id, "animation": gif_url})
        return True
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="enviar_gif_bienvenida")
        return False

def enviar_sticker_bienvenida(chat_id=None):
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    sticker_id = "CAACAgIAAxkBAAEIB2JkQFj2X7jzv7vM0ZpLwWzB1Z3qCwACAgADVp29CkWzw7E1ai-jNgQ"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendSticker"
    try:
        requests.post(url, data={"chat_id": chat_id, "sticker": sticker_id})
        return True
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="enviar_sticker_bienvenida")
        return False

# Alias para compatibilidad
enviar_telegram = send_telegram_alert

# ============================================================
# 📊 Predicción IA desde comando Telegram
# ============================================================
def manejar_prediccion(update, context):
    from utils.procesador_senal import procesar_senal

    chat_id = update.effective_chat.id
    usuario = update.effective_user.username or "admin"
    try:
        activos_binance = [a[0] for a in cargar_activos() if a[1].lower() == "binance"]
        intervalos = ["1m", "3m", "5m"]
        mejores = []
        for activo in activos_binance:
            for intv in intervalos:
                try:
                    df_raw = obtener_datos_binance(activo, intervalo=intv, limite=150)
                    if df_raw.empty:
                        continue
                    df = normalizar_columnas(df_raw)
                    df = agregar_indicadores_tecnicos(df)
                    accion_ia, precision, señal_tec, señales = procesar_senal(activo)

                    if precision and precision >= 0.96:
                        mejores.append({
                            "activo": activo,
                            "intervalo": intv,
                            "accion": accion_ia.upper(),
                            "precision": precision * 100,  # ✅ ahora en porcentaje real
                            "precio": df["close"].iloc[-1],
                            "rsi": df["rsi"].iloc[-1],
                            "macd": df["macd"].iloc[-1],
                            "macd_signal": df["macd_signal"].iloc[-1],
                            "señal_tec": "BUY" if señal_tec > 0 else "SELL" if señal_tec < 0 else "HOLD",
                            "tendencia": tendencia_mercado(df)
                        })
                except Exception as e:
                    log_error(e, archivo="telegram_alertas.py", funcion="prediccion_activo")
        if mejores:
            mejor = sorted(mejores, key=lambda x: x["precision"], reverse=True)[0]
            resumen = f"""🚨 <b>Oportunidad Detectada (IA)</b>
📍 Activo: <b>{mejor['activo']}</b>
🕒 Intervalo: {mejor['intervalo']}
📉 Precio: ${mejor['precio']:.2f}
📈 Tendencia: {mejor['tendencia']}
📊 RSI: {mejor['rsi']:.2f}
📊 MACD: {mejor['macd']:.2f}
📍 Señal MACD: {mejor['macd_signal']:.2f}
🧠 Señal IA: <b>{mejor['accion']}</b>
📚 Técnica: <b>{mejor['señal_tec']}</b>
🎯 Precisión IA: {mejor['precision']:.2f}%
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            context.bot.send_message(chat_id=chat_id, text=resumen, parse_mode="HTML")

            # 📊 Intentar enviar gráfico si existe
            grafico_path = f"graficos/{mejor['activo']}_{mejor['intervalo']}.png"
            if os.path.exists(grafico_path):
                send_telegram_chart(grafico_path, caption=f"📊 Gráfico {mejor['activo']} {mejor['intervalo']}")

        else:
            context.bot.send_message(chat_id=chat_id, text="🤖 No se encontraron oportunidades con precisión ≥ 96%.")
    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="manejar_prediccion")

# ============================================================
# 📌 Confirmación de operaciones
# ============================================================
ultima_senal = {}

def enviar_senal_con_confirmacion(activo, accion, hora_entrada, duracion, precision, chat_id=None):
    global ultima_senal
    ultima_senal = {
        "activo": activo,
        "accion": accion,
        "hora_entrada": hora_entrada,
        "duracion": duracion,
        "precision": precision * 100  # ✅ porcentaje real
    }
    if not chat_id:
        chat_id = TELEGRAM_CHAT_ID
    texto = f"""
📢 <b>Señal detectada</b>
📈 Activo: {activo}
🤖 Acción: {accion.upper()} (Precisión: {precision * 100:.2f}%)
⏱ Entrada: {hora_entrada.strftime('%H:%M') if hora_entrada else 'Inmediata'}
⏳ Duración estimada: {duracion} min
"""
    botones = [
        [InlineKeyboardButton("✅ Ejecutar", callback_data="ejecutar_operacion")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar_operacion")]
    ]
    markup = InlineKeyboardMarkup(botones)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "HTML",
        "reply_markup": markup.to_dict()
    }
    try:
        requests.post(url, json=payload)

        # 📊 Intentar enviar gráfico automáticamente
        grafico_path = f"graficos/{activo}.png"
        if os.path.exists(grafico_path):
            send_telegram_chart(grafico_path, caption=f"📊 Gráfico {activo}")

    except Exception as e:
        log_error(e, archivo="telegram_alertas.py", funcion="enviar_senal_con_confirmacion")

def manejar_confirmacion(update, context):
    query = update.callback_query
    query.answer()
    if query.data == "ejecutar_operacion":
        from el_bot_de_efra import ejecutar_operacion_desde_telegram
        ejecutar_operacion_desde_telegram(ultima_senal)
        guardar_confirmacion({"confirmado": True, "senal": ultima_senal})
        query.edit_message_text("✅ Operación confirmada. Ejecutando...")
    else:
        guardar_confirmacion({"confirmado": False, "senal": ultima_senal})
        query.edit_message_text("❌ Operación cancelada.")

# ============================================================
# 📌 Registrar handlers
# ============================================================
def registrar_handlers(updater):
    updater.dispatcher.add_handler(CallbackQueryHandler(manejar_confirmacion))
    updater.dispatcher.add_handler(CommandHandler("prediccion", manejar_prediccion))

# ============================================================
# 🚀 Iniciar bot de Telegram
# ============================================================
def iniciar_bot_telegram():
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN no configurado.")
        return
    updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
    registrar_handlers(updater)
    updater.start_polling()
    print("🤖 Bot de Telegram escuchando comandos...")
