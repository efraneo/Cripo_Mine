# ===== utils/init.py =====
"""
🚀 Script de inicialización del bot
-----------------------------------
Se asegura de que la estructura mínima del proyecto esté lista:
- logs/historial.csv con columnas unificadas
- logs/operaciones.csv con formato estándar
- binance.env cargado correctamente
- carpeta modelos_entrenados creada
"""

import os
import csv
from pathlib import Path

# 🔹 Importar logger si está disponible
try:
    from utils.logger import logger, log_error
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("init")

    def log_error(e, archivo, funcion):  # fallback si no existe utils/logger
        logger.error(f"[{archivo}] {funcion} | {e}")


# ============================================================
# 📂 Verificar historial
# ============================================================
def verificar_historial():
    """
    Crea/migra logs/historial.csv con columnas unificadas.
    """
    try:
        from utils import logger_historial as lh
        lh._asegurar_historial()
        logger.info("✅ Historial verificado correctamente.")
    except Exception as e:
        log_error(e, archivo="utils/init.py", funcion="verificar_historial")


# ============================================================
# 📂 Verificar operaciones
# ============================================================
def verificar_operaciones():
    """
    Crea logs/operaciones.csv con cabecera estándar si no existe.
    """
    try:
        operaciones_path = Path("logs/operaciones.csv")
        operaciones_path.parent.mkdir(exist_ok=True)

        if not operaciones_path.exists():
            columnas = [
                "timestamp","usuario","activo","accion","precision","precio_ref","monto",
                "tp1","tp2","tp3","tp4","sl",
                "tipo","resultado","comentario"
            ]
            with open(operaciones_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columnas)
            logger.info(f"✅ operaciones.csv creado en {operaciones_path.resolve()}")
        else:
            logger.info("ℹ️ operaciones.csv ya existe, no se modifica.")
    except Exception as e:
        log_error(e, archivo="utils/init.py", funcion="verificar_operaciones")


# ============================================================
# 🔑 Verificar credenciales de Binance
# ============================================================
def verificar_binance_env():
    """
    Comprueba que binance.env exista y que las claves estén disponibles.
    """
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parent.parent / "binance.env"
        if env_path.exists():
            load_dotenv(env_path)
            logger.info(f"✅ binance.env cargado desde {env_path}")
        else:
            logger.warning(f"⚠ No se encontró {env_path}, se usará entorno actual")

        api_key = os.getenv("BINANCE_API_KEY") or os.getenv("API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("API_SECRET")

        if not api_key or not api_secret:
            logger.warning("⚠ No se encontraron credenciales BINANCE_API_KEY/BINANCE_API_SECRET.")
        else:
            logger.info("🔑 Claves Binance detectadas en entorno.")
    except Exception as e:
        log_error(e, archivo="utils/init.py", funcion="verificar_binance_env")


# ============================================================
# 📦 Verificar carpeta de modelos
# ============================================================
def verificar_modelos():
    """
    Crea carpeta modelos_entrenados si no existe.
    """
    try:
        modelos_dir = Path("modelos_entrenados")
        modelos_dir.mkdir(exist_ok=True)
        logger.info(f"✅ Carpeta de modelos lista en {modelos_dir.resolve()}")
    except Exception as e:
        log_error(e, archivo="utils/init.py", funcion="verificar_modelos")


# ============================================================
# 🚀 Función principal de inicialización
# ============================================================
def inicializar_bot():
    """
    Ejecuta todas las verificaciones previas al inicio del bot.
    """
    logger.info("🔄 Iniciando verificación del entorno del bot...")
    verificar_historial()
    verificar_operaciones()   # <-- Nuevo
    verificar_binance_env()
    verificar_modelos()
    logger.info("🚀 Bot inicializado correctamente y listo para ejecutar.")


# ============================================================
# 📌 Ejecutar automáticamente si se llama directo
# ============================================================
if __name__ == "__main__":
    inicializar_bot()
