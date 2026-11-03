# ==========================================================
# utils/train_scheduler.py — Actualizador automático de modelos IA
# ==========================================================
# 🧠 Cada 1 hora:
#   - Descarga datos recientes (obtener_datos_con_fallback)
#   - Actualiza modelo LSTM local
#   - Recalibra ensemble híbrido (RF + XGB)
#   - Aplica dynamic_confidence_boost
#   - Guarda resultados y logs
# ----------------------------------------------------------
# Se integra perfectamente con:
#   utils/model_trainer.py
#   utils/logger.py
#   utils.data_fetcher.py
# ==========================================================

import os
import time
import traceback
from datetime import datetime

import pandas as pd

from utils.data_fetcher import obtener_datos_con_fallback
from utils.model_trainer import actualizar_modelos_en_vivo
from utils.logger import log_info, log_error, log_warning


# ==========================================================
# ⚙️ CONFIGURACIÓN GLOBAL
# ==========================================================
ACTIVOS_DEFAULT = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
INTERVALO_MINUTOS = 60  # Cada hora
LOG_FILE = os.path.join("logs", "train_scheduler.log")
os.makedirs("logs", exist_ok=True)


# ==========================================================
# 🕒 Actualización de un activo
# ==========================================================
def actualizar_activo(activo: str):
    """
    Ejecuta una actualización completa del modelo de un activo:
      - obtiene datos recientes
      - llama actualizar_modelos_en_vivo()
    """
    try:
        log_info(f"🔄 Iniciando actualización IA para {activo}", archivo="train_scheduler.py", funcion="actualizar_activo")

        df = obtener_datos_con_fallback(activo, interval="1h", mercado="spot", min_rows=120)
        if df is None or df.empty:
            log_warning(f"⚠️ No se obtuvieron datos recientes para {activo}", archivo="train_scheduler.py", funcion="actualizar_activo")
            return False

        resultado = actualizar_modelos_en_vivo(df, activo=activo, resumen="Actualización horaria automática")

        confianza = resultado.get("confianza", 0)
        boosted = resultado.get("boosted", False)
        consistencia = resultado.get("consistencia", 0)

        log_info(
            f"✅ {activo} actualizado | Confianza={confianza*100:.2f}% | Boosted={boosted} | Consistencia={consistencia:.3f}",
            archivo="train_scheduler.py",
            funcion="actualizar_activo"
        )

        # Guardar pequeño registro en CSV
        df_log = pd.DataFrame([{
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "activo": activo,
            "confianza": confianza,
            "boosted": boosted,
            "consistencia": consistencia
        }])
        df_log.to_csv(LOG_FILE, mode="a", index=False, header=not os.path.exists(LOG_FILE))

        return True
    except Exception as e:
        log_error(f"Error actualizando {activo}: {e}\n{traceback.format_exc()}", archivo="train_scheduler.py", funcion="actualizar_activo")
        return False


# ==========================================================
# ⏰ Bucle principal del scheduler
# ==========================================================
def ejecutar_scheduler():
    """
    Bucle continuo que actualiza los modelos cada hora.
    Puede ejecutarse en background o como servicio.
    """
    log_info("🚀 Iniciando Train Scheduler (1h interval)", archivo="train_scheduler.py", funcion="ejecutar_scheduler")

    while True:
        try:
            for activo in ACTIVOS_DEFAULT:
                actualizar_activo(activo)

            log_info(f"🕒 Esperando {INTERVALO_MINUTOS} minutos para la próxima iteración...", archivo="train_scheduler.py", funcion="ejecutar_scheduler")
            time.sleep(INTERVALO_MINUTOS * 60)
        except KeyboardInterrupt:
            log_warning("⛔ Train Scheduler detenido manualmente", archivo="train_scheduler.py", funcion="ejecutar_scheduler")
            break
        except Exception as e:
            log_error(f"Error general en scheduler: {e}\n{traceback.format_exc()}", archivo="train_scheduler.py", funcion="ejecutar_scheduler")
            time.sleep(60)  # Espera corta antes de reintentar


from utils.auto_learning import auto_retrain_models

# Autoaprendizaje semanal (domingo 03:00 UTC)
scheduler.add_job(
    lambda: auto_retrain_models("GEN"),
    "cron",
    day_of_week="sun",
    hour=3,
    minute=0,
    id="auto_learning_job",
    replace_existing=True
)


# ==========================================================
# 🧩 Ejecutar directamente si se llama este archivo
# ==========================================================
if __name__ == "__main__":
    ejecutar_scheduler()
