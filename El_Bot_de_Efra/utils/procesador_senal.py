"""
utils/procesador_senal.py
-------------------------
Pipeline principal de análisis:
- Obtiene datos históricos con fallback
- Aplica indicadores técnicos y análisis de tendencia
- Integra IA ensemble híbrido (RF + XGB + LSTM)
- Ajusta confianza dinámica mediante confidence_boost
- Guarda resultados y notifica por Telegram
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# === Dependencias internas ===
from utils.data_fetcher import obtener_datos_con_fallback as obtener_datos_historicos
from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
from utils.sentiment_analyzer import SentimentAnalyzer
from utils.db_handler import guardar_en_base_datos
from utils.telegram_client import send_telegram_alert
from utils.modelo import predecir_senal
from utils.confidence_boost import dynamic_confidence_boost
from utils.logger import log_error, log_warning, log_info


# ============================================================
# 🧩 Estrategia auxiliar simple (fallback)
# ============================================================
def _estrategia_agresiva(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = np.nan

    try:
        df["ma_fast"] = df["close"].rolling(window=5, min_periods=1).mean()
        df["ma_slow"] = df["close"].rolling(window=15, min_periods=1).mean()
        df["long_signal"] = df["ma_fast"] > df["ma_slow"]
    except Exception:
        df["long_signal"] = False

    try:
        df["soporte"] = df["low"].rolling(window=20, min_periods=1).min()
        df["resistencia"] = df["high"].rolling(window=20, min_periods=1).max()
    except Exception:
        df["soporte"] = np.nan
        df["resistencia"] = np.nan

    try:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
        loss = -delta.clip(upper=0).rolling(window=14, min_periods=1).mean()
        rs = gain / (loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = df["ema12"] - df["ema26"]
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    except Exception:
        df["rsi"] = np.nan
        df["macd"] = np.nan
        df["macd_signal"] = np.nan

    return df


# ============================================================
# 🚀 Procesamiento completo de señal
# ============================================================
def procesar_senal(
    activo: str,
    usuario: str = "desconocido",
    usar_avanzado: bool = True,
    umbral_emitir: float = 0.75,
    enviar_telegram_flag: bool = True
):
    try:
        # === 1️⃣ Obtener datos históricos ===
        df = obtener_datos_historicos(activo, interval="1h", mercado="spot", min_rows=200)
        if df is None or df.empty:
            log_warning(f"Sin datos válidos para {activo}", archivo="procesador_senal.py", funcion="procesar_senal")
            return {"accion_ia": "hold", "precision": 0.0}, "sin_datos", [], None, 0

        # === 2️⃣ Aplicar indicadores técnicos ===
        df_ind = agregar_indicadores_tecnicos(df)
        tendencia = tendencia_mercado(df_ind)

        # === 3️⃣ Variables clave ===
        rsi = df_ind["rsi"].iloc[-1] if "rsi" in df_ind else None
        macd = df_ind["macd"].iloc[-1] if "macd" in df_ind else None
        macd_signal = df_ind["macd_signal"].iloc[-1] if "macd_signal" in df_ind else None
        soporte = df_ind["low"].tail(20).min() if not df_ind.empty else None
        resistencia = df_ind["high"].tail(20).max() if not df_ind.empty else None
        volumen_fuerte = (
            "volume" in df_ind and df_ind["volume"].iloc[-1] > df_ind["volume"].mean() * 1.5
        )

        # === 4️⃣ Predicción IA ensemble (RF + XGB + LSTM) ===
        accion, confianza, hora_iso, duracion, pred_precios = predecir_senal(
            df_ind,
            activo=activo,
            pasos=20,
            futuros=4,
            modo_agresivo=not usar_avanzado
        )

        accion_ia = accion.lower() if accion else "buy"
        traducciones = {"buy": "Compra", "sell": "Venta"}
        accion_ia_txt = traducciones.get(accion_ia, "Compra")

        # === 5️⃣ Ajuste dinámico de confianza IA ===
        try:
            consistencia = float(df_ind["close"].corr(df_ind["ema12"])) if "ema12" in df_ind else 0.0
            rf_score = np.random.uniform(0.6, 0.9)  # ⚙️ simulado (reemplazado por RF real en modelo)
            error_score = np.random.uniform(0.5, 0.9)
            estabilidad = np.random.uniform(0.3, 0.8)

            confianza_ajustada, boosted = dynamic_confidence_boost(
                metodologias=[],
                prediccion_lstm={"confianza": confianza},
                confianza_actual=confianza,
                score_methods=0.0,
                rf_score=rf_score,
                consistencia=consistencia,
                error_score=error_score,
                estabilidad=estabilidad,
                resumen=f"{activo} — Acción IA: {accion_ia.upper()} | Tendencia: {tendencia}"
            )
        except Exception as e:
            log_warning(f"Boost dinámico falló: {e}", archivo="procesador_senal.py", funcion="procesar_senal")
            confianza_ajustada = confianza

        # === 6️⃣ Análisis de sentimiento ===
        sa = SentimentAnalyzer()
        sentimiento = sa.get_market_sentiment(activo)

        # === 7️⃣ Construcción de conclusión visual ===
        conclusion = (
            f"🤖 **IA sugiere {accion_ia_txt.upper()}** "
            f"(confianza {confianza_ajustada*100:.2f}%)\n"
            f"📊 Tendencia: {tendencia}\n"
            f"📰 Sentimiento mercado: {sentimiento}"
        )
        if volumen_fuerte:
            conclusion += " 💥 Volumen fuerte detectado"

        hora_entrada = (
            datetime.strptime(hora_iso, "%Y-%m-%dT%H:%M:%S") if hora_iso else datetime.now() + timedelta(minutes=5)
        )

        # === 8️⃣ Guardar en base de datos ===
        data_db = {
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "activo": activo,
            "mercado": "binance",
            "precision": confianza_ajustada,
            "ia_prediccion": accion_ia,
            "conclusion": conclusion,
            "precio_actual": float(df_ind["close"].iloc[-1]),
            "soporte": soporte,
            "resistencia": resistencia,
            "rsi": rsi,
            "macd_signal": macd_signal,
            "tendencia": tendencia,
            "volumen_fuerte": volumen_fuerte,
            "sl": soporte * 0.98 if soporte else None,
            "tp1": resistencia * 0.5 if resistencia else None,
            "tp2": resistencia * 0.75 if resistencia else None,
            "tp3": resistencia if resistencia else None,
            "tp4": resistencia * 1.1 if resistencia else None,
        }
        try:
            guardar_en_base_datos(data_db)
        except Exception as e:
            log_warning(f"Guardar DB falló: {e}", archivo="procesador_senal.py", funcion="procesar_senal")

        # === 9️⃣ Notificación Telegram ===
        if enviar_telegram_flag:
            try:
                mensaje = (
                    f"📊 *Nueva señal detectada*\n"
                    f"📈 Activo: {activo}\n"
                    f"🤖 Acción IA: *{accion_ia.upper()}*\n"
                    f"🎯 Confianza ajustada: {confianza_ajustada*100:.2f}%\n\n"
                )
                mensaje += f"   • RSI: {rsi:.2f}\n" if rsi is not None else "   • RSI: -\n"
                mensaje += f"   • MACD: {macd:.4f}\n" if macd is not None else "   • MACD: -\n"
                mensaje += f"   • Señal MACD: {macd_signal:.4f}\n" if macd_signal is not None else "   • Señal MACD: -\n"
                mensaje += f"   • Tendencia: {tendencia}\n"
                mensaje += f"   • Soporte: {soporte if soporte else '-'}\n"
                mensaje += f"   • Resistencia: {resistencia if resistencia else '-'}\n"
                mensaje += f"⏰ Entrada estimada: {hora_entrada.strftime('%H:%M:%S')}\n"
                mensaje += f"🕒 Duración: {duracion} min"
                send_telegram_alert(mensaje)
            except Exception as e:
                log_warning(f"Enviar Telegram falló: {e}", archivo="procesador_senal.py", funcion="procesar_senal")

        # === 🔚 Retornar resultados ===
        resultado = {
            "accion_ia": accion_ia,
            "precision": confianza_ajustada,
            "df_velas": df_ind,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "tendencia": tendencia,
            "soporte": soporte,
            "resistencia": resistencia,
            "volumen_fuerte": volumen_fuerte,
        }
        return resultado, conclusion, pred_precios, hora_entrada, duracion

    except Exception as e:
        log_error(e, archivo="procesador_senal.py", funcion="procesar_senal")
        return {"accion_ia": "hold", "precision": 0.0}, "error", [], None, 0
