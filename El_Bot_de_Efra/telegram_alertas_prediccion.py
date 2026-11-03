# telegram_alertas_prediccion.py
# ==========================================================
# 📲 Envío de resúmenes de predicción a Telegram + Historial
# ----------------------------------------------------------
# - Señal final (BUY/SELL/HOLD)
# - Score, confianza, votos por metodología
# - Stop Loss, Take Profits y horas de análisis
# - Guardado en historial de análisis en session_state
# ==========================================================

from typing import Dict, Any, List
from telegram_alertas import send_telegram_alert
from datetime import datetime
import streamlit as st


def enviar_resumen_prediccion(
    activo: str,
    resultado: Dict[str, Any],
    usuario: str = "desconocido",
    stop_loss: float = None,
    take_profits: List[float] = None,
    hora_analisis: datetime = None,
    hora_prediccion: datetime = None,
):
    """
    Envía un resumen a Telegram y lo guarda en historial (st.session_state).
    """

    try:
        senal = resultado.get("senal", "HOLD")
        score = resultado.get("score", 0.0)
        confianza = resultado.get("confianza", 0.0)
        votos = resultado.get("votos", {})
        resumen_metodos: List[str] = resultado.get("resumen", [])

        # Stop loss y TPs
        sl_txt = f"{stop_loss:.4f}" if stop_loss else "N/A"
        tp_txt = (
            ", ".join([f"{tp:.4f}" for tp in take_profits]) if take_profits else "N/A"
        )

        # Horas
        hora_analisis = hora_analisis or datetime.now()
        hora_prediccion = hora_prediccion or (hora_analisis)

        # Construir mensaje
        mensaje = f"""
📊 <b>Resultado del análisis</b>
👤 Usuario: <b>{usuario}</b>
📌 Activo: <b>{activo}</b>
🧭 Señal final: <b>{senal}</b>
⚖️ Score: <b>{score:.4f}</b>
🤖 Confianza global: <b>{confianza*100:.2f}%</b>

📈 Votos:
  🟢 BUY: {votos.get("BUY",0)}
  🔴 SELL: {votos.get("SELL",0)}
  ⚪ HOLD: {votos.get("HOLD",0)}

🧾 Resumen metodologías:
{chr(10).join(["- " + r for r in resumen_metodos[:8]])}
{"... (+"+str(len(resumen_metodos)-8)+" más)" if len(resumen_metodos) > 8 else ""}

🎯 Take Profits: {tp_txt}
📉 Stop Loss: {sl_txt}

🕒 Hora análisis: {hora_analisis.strftime("%Y-%m-%d %H:%M:%S")}
🕒 Entrada sugerida (+5min): {hora_prediccion.strftime("%Y-%m-%d %H:%M:%S")}
"""

        # 🚀 Enviar a Telegram
        send_telegram_alert(mensaje)

        # 📝 Guardar en historial
        if "historial_analisis" not in st.session_state:
            st.session_state["historial_analisis"] = []

        st.session_state["historial_analisis"].append(
            {
                "activo": activo,
                "usuario": usuario,
                "senal": senal,
                "score": score,
                "confianza": confianza,
                "votos": votos,
                "stop_loss": stop_loss,
                "take_profits": take_profits,
                "hora_analisis": hora_analisis,
                "hora_prediccion": hora_prediccion,
                "resumen": resumen_metodos,
                "timestamp": datetime.now(),
            }
        )

    except Exception as e:
        print(f"[ERROR] No se pudo enviar resumen de predicción a Telegram: {e}")
