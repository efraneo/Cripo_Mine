# bot_telegram_listener.py
import os
import time
import traceback
from datetime import datetime
import telebot

from telegram_alertas import enviar_telegram, send_telegram_chart
from utils.comun import normalizar_columnas, cargar_activos, obtener_datos_binance
from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
from el_bot_de_efra import procesar_senal
from config_loader import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import log_error

# === Inicializar Bot ===
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# === Comando /start o /ayuda ===
@bot.message_handler(commands=['start', 'ayuda'])
def send_welcome(message):
    ayuda = """
👋 <b>Bienvenido a El Bot de Efra 🤖</b>

Comandos disponibles:
/start o /ayuda – Muestra esta ayuda
/status – Verifica si el bot está activo
/prediccion – Busca oportunidades actuales de inversión
/creditos – Ver información del autor y colaboradores

📈 ¡Envíame /prediccion para comenzar!
"""
    bot.reply_to(message, ayuda, parse_mode="HTML")

# === Comando /status ===
@bot.message_handler(commands=['status'])
def send_status(message):
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    bot.reply_to(message, f"✅ El Bot de Efra está activo.\n🕒 Hora del sistema: {ahora}")

# === Comando /creditos ===
@bot.message_handler(commands=['creditos'])
def send_credits(message):
    creditos = """
<b>📢 Créditos - El Bot de Efra 🤖</b>

👨‍💻 Desarrollador: @efrain_dev
💡 IA y Estrategia: El equipo de soporte
📦 Librerías: Python, Streamlit, Binance API, Yahoo Finance, Plotly, Scikit-learn, entre otras.
🛡️ Seguridad: Autenticación personalizada y registro de actividad

¡Gracias por usar esta herramienta! 🚀
"""
    bot.send_message(message.chat.id, creditos, parse_mode="HTML")

# === Comando /prediccion ===
@bot.message_handler(commands=['prediccion'])
def handle_prediccion(message):
    try:
        activos_binance = [a[0] for a in cargar_activos() if a[1].lower() == "binance"]
        intervalos = ["1m", "3m", "5m"]
        mejores = []

        for activo in activos_binance:
            for intervalo in intervalos:
                try:
                    df_raw = obtener_datos_binance(activo, intervalo=intervalo, limite=150)
                    if df_raw.empty:
                        continue
                    df = normalizar_columnas(df_raw)
                    df = agregar_indicadores_tecnicos(df)
                    accion_ia, precision, señal_tec, señales = procesar_senal(activo)

                    # ✅ Corrección precisión multiplicada por 100
                    if precision and precision >= 0.96 and accion_ia:
                        mejores.append({
                            "activo": activo,
                            "intervalo": intervalo,
                            "accion": accion_ia.upper(),
                            "precision": precision * 100,  # ahora en porcentaje real
                            "precio": df["close"].iloc[-1],
                            "rsi": df["rsi"].iloc[-1],
                            "macd": df["macd"].iloc[-1],
                            "macd_signal": df["macd_signal"].iloc[-1],
                            "señal_tec": "BUY" if señal_tec > 0 else "SELL" if señal_tec < 0 else "HOLD",
                            "tendencia": tendencia_mercado(df)
                        })
                except Exception as e:
                    log_error(e, archivo="bot_telegram_listener.py", funcion="loop_activos")

        if mejores:
            mejor = sorted(mejores, key=lambda x: x["precision"], reverse=True)[0]

            resumen = f"""🚨 <b>Oportunidad Detectada (IA)</b>
📍 Activo: <b>{mejor['activo']}</b>
🕒 Intervalo: {mejor['intervalo']}
📉 Precio actual: ${mejor['precio']:.2f}
📈 Tendencia: {mejor['tendencia']}

📊 RSI: {mejor['rsi']:.2f}
📊 MACD: {mejor['macd']:.2f}
📍 Señal MACD: {mejor['macd_signal']:.2f}

🧠 Señal IA: <b>{mejor['accion']}</b>
📚 Técnica: <b>{mejor['señal_tec']}</b>
🎯 Precisión IA: {mejor['precision']:.2f}%

📌 Recomendación: <b>{"INVIERTE" if mejor["accion"] == mejor["señal_tec"] else "NO INVERTIR"}</b>
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=resumen, parse_mode="HTML")

            # 📊 Enviar gráfico si existe imagen generada
            grafico_path = f"graficos/{mejor['activo']}_{mejor['intervalo']}.png"
            if os.path.exists(grafico_path):
                send_telegram_chart(grafico_path, caption=f"📊 Gráfico {mejor['activo']} {mejor['intervalo']}")

        else:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="⚠️ No se detectaron oportunidades con precisión ≥ 96%.", parse_mode="HTML")

    except Exception as e:
        log_error(e, archivo="bot_telegram_listener.py", funcion="handle_prediccion")
        traceback.print_exc()
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="❌ Error procesando la predicción IA.", parse_mode="HTML")

# === Loop del bot Telegram ===
if __name__ == "__main__":
    print("🤖 Bot de Telegram escuchando comandos...")
    try:
        bot.infinity_polling()
    except Exception as e:
        log_error(e, archivo="bot_telegram_listener.py", funcion="main")
