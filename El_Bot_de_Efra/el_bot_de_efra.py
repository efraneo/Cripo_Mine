# el_bot_de_efra.py — BLOQUE A
# ------------------------------------------------------------
# Imports y configuración general
# ------------------------------------------------------------

import os
import json
import csv
import math
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional

import numpy as np
import pandas as pd

# Utils del proyecto (asegúrate de que existan)
from utils.comun import cargar_activos
from utils.logger import log_error, logger, log_warning
from utils.historial import guardar_historial
from utils.telegram_client import send_telegram_alert  # función que ya usabas
from utils.indicadores_tecnicos import (
    tendencia_mercado,
    detectar_pullback,
    calcular_entrada_ideal
)

# Módulos del bot/backtesting (si existen)
from trading_bot import TradingBot
from backtesting.estrategias import (
    GestorEstrategias,
    EstrategiaCruceMedias,
    EstrategiaRsiMacd,
    EstrategiaVolatilidad
)

# Procesador de señal unificado (puede devolver tuple (resultado, conclusion, pred_precios, hora_entrada, duracion)
# o en algunas versiones dict. Lo manejamos robustamente abajo).
from utils.procesador_senal import procesar_senal  # adaptaremos su uso más abajo

# Para acceder a datos si los helpers directos no están disponibles
from utils.data_fetcher import get_candles_multi, obtener_datos_bin, obtener_datos_yahoo  # wrappers múltiples

# ============================================================
# Constantes / archivo de config
# ============================================================
CONFIG_FILE = "config_bot.json"
LOG_PREFIX = "[el_bot_de_efra]"

# Configura logger básico si no está configurado
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# el_bot_de_efra.py — BLOQUE B
# ------------------------------------------------------------
# Gestión de configuración y helpers auxiliares
# ------------------------------------------------------------

def cargar_config() -> Dict[str, Any]:
    """Carga la configuración persistente; devuelve dict por defecto si no existe."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_warning(f"{LOG_PREFIX} - cargar_config: fallo leyendo config: {e}")
            return {"modo_demo": True, "ejecutar_orden": False}
    return {"modo_demo": True, "ejecutar_orden": False}

def guardar_config(cfg: Dict[str, Any]) -> bool:
    """Guarda configuración en disco (útil si la interfaz cambia opciones)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_error(e, archivo="el_bot_de_efra.py", funcion="guardar_config")
        return False

def safe_obtener_precio_actual(activo: str, intervalo: str = "1m") -> Optional[float]:
    """
    Intenta obtener el último precio disponible usando varios proveedores.
    Devuelve None si no pudo.
    """
    try:
        # 1) intentar obtener desde la función de Binance (si disponible)
        try:
            df = get_candles_multi(activo, interval=intervalo, mercado="spot", min_rows=1, preferred=["binance_spot"])
            if df is not None and not df.empty:
                return float(df["close"].iloc[-1])
        except Exception:
            pass

        # 2) fallback a obtener_datos_bin si existe
        try:
            df2 = obtener_datos_bin(activo, interval="1h", lookback="1d")
            if df2 is not None and not df2.empty:
                return float(df2["close"].iloc[-1])
        except Exception:
            pass

        # 3) último recurso, yahoo
        try:
            df3 = obtener_datos_yahoo(activo, interval="1h", period="2d")
            if df3 is not None and not df3.empty:
                return float(df3["close"].iloc[-1])
        except Exception:
            pass

        return None
    except Exception as e:
        log_error(e, archivo="el_bot_de_efra.py", funcion="safe_obtener_precio_actual")
        return None

# el_bot_de_efra.py — BLOQUE C
# ------------------------------------------------------------
# ejecutar_bot: flujo principal que procesa señales para los activos
# ------------------------------------------------------------

def ejecutar_bot(ejecutar_orden: Optional[bool] = None):
    """
    Ejecuta el flujo completo del bot para todos los activos definidos en `cargar_activos`.
    - usa procesar_senal (compatibilidad con versiones que devuelven tuple o dict).
    - reporta por Telegram.
    """
    config = cargar_config()
    ejecutar_auto = ejecutar_orden if ejecutar_orden is not None else config.get("ejecutar_orden", False)

    activos = cargar_activos()  # Se espera lista de tuplas (activo, mercado) o lista simple
    if not activos:
        logger.warning(f"{LOG_PREFIX} No se encontraron activos en la configuración.")
        return

    gestor = GestorEstrategias([
        EstrategiaCruceMedias(),
        EstrategiaRsiMacd(),
        EstrategiaVolatilidad()
    ])

    bot = TradingBot()
    bot.modo_demo = config.get("modo_demo", True)
    bot.ejecutar_orden = ejecutar_auto

    for item in activos:
        try:
            # soporta (activo, mercado) o solo activo string
            if isinstance(item, (list, tuple)) and len(item) >= 1:
                activo = item[0]
                mercado = item[1] if len(item) > 1 else "spot"
            else:
                activo = str(item)
                mercado = "spot"

            # Llamada a procesar_senal: puede retornar tuple o dict
            try:
                salida = procesar_senal(activo, usar_avanzado=True, enviar_telegram_flag=False)
            except TypeError:
                # Si la firma es otra, intenta solo con activo
                salida = procesar_senal(activo)

            # Normalizar salida: dos formatos esperables:
            # 1) (resultado_dict, conclusion, pred_precios, hora_entrada, duracion)
            # 2) resultado_dict (contiene df_velas, precision, accion_ia...)
            resultado = {}
            conclusion = None
            pred_precios = []
            hora_entrada = None
            duracion = 0

            if isinstance(salida, tuple) and len(salida) >= 1:
                # formato tuple detectado
                resultado = salida[0] if len(salida) > 0 else {}
                conclusion = salida[1] if len(salida) > 1 else None
                pred_precios = salida[2] if len(salida) > 2 else []
                hora_entrada = salida[3] if len(salida) > 3 else None
                duracion = salida[4] if len(salida) > 4 else 0
            elif isinstance(salida, dict):
                resultado = salida
                # intentar mapear campos
                conclusion = resultado.get("conclusion") or resultado.get("descripcion") or None
                pred_precios = resultado.get("pred_precios") or resultado.get("predicciones") or []
                hora_entrada = resultado.get("hora_entrada") or resultado.get("entrada_estimada")
                duracion = resultado.get("duracion") or 0
            else:
                # formato inesperado; saltar
                logger.warning(f"{LOG_PREFIX} procesar_senal devolvió tipo inesperado para {activo}: {type(salida)}")
                continue

            # Extraer métricas
            accion_ia = (resultado.get("accion_ia") or resultado.get("accion") or "hold").lower()
            precision = float(resultado.get("precision", 0.0))
            df = resultado.get("df_velas") or resultado.get("df") or pd.DataFrame()

            # Si no hay df o está vacío, intentar obtener velas con orquestador multi
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                logger.info(f"{LOG_PREFIX} No hay velas en procesar_senal para {activo} — intentando obtener con providers.")
                try:
                    # intento con min_rows=120 para operaciones intradiarias; ajusta según necesidad
                    df = get_candles_multi(activo, interval="1m", mercado=mercado, min_rows=120, preferred=["binance_spot"])
                except Exception as e:
                    log_warning(f"{LOG_PREFIX} get_candles_multi fallo para {activo}: {e}")
                    df = pd.DataFrame()

            if df is None or df.empty:
                logger.warning(f"{LOG_PREFIX} ⚠️ No hay datos de velas para {activo}. Se omitirá envío/execution.")
                continue

            # Indicadores y análisis complementario (si quieres puedes añadir más)
            patrones = []
            try:
                patrones = detectar_patrones_velas(df)
            except Exception:
                patrones = []

            niveles = []
            try:
                from fibonacci import detectar_niveles_fibonacci
                niveles = detectar_niveles_fibonacci(df)
            except Exception:
                niveles = []

            tendencia = tendencia_mercado(df)

            precio_actual = float(df["close"].iloc[-1])
            soporte = float(df["low"].rolling(window=5, min_periods=1).min().iloc[-1])
            resistencia = float(df["high"].rolling(window=5, min_periods=1).max().iloc[-1])
            rsi = float(resultado.get("rsi", np.nan)) if resultado.get("rsi") is not None else np.nan
            macd = float(resultado.get("macd", np.nan)) if resultado.get("macd") is not None else np.nan
            macd_signal = float(resultado.get("macd_signal", np.nan)) if resultado.get("macd_signal") is not None else np.nan

            # Envío a Telegram con formato robusto
            fecha = datetime.now()
            mensaje = (
                f"👋 <b>Hola, soy el Bot de Efra</b>\n"
                f"🕒 {fecha.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📌 Activo: {activo} ({mercado.upper()})\n"
                f"📈 Tendencia: {tendencia}\n"
                f"💵 Precio: {precio_actual:.2f}\n"
                f"🟢 Soporte: {soporte:.2f} | 🔴 Resistencia: {resistencia:.2f}\n"
                f"📉 RSI: {rsi:.2f} | MACD: {macd:.2f} | Señal MACD: {macd_signal:.2f}\n"
                f"🕯️ Patrón velas: {', '.join(patrones) if patrones else 'Ninguno'}\n"
                f"📏 Fibonacci: {', '.join(niveles) if niveles else 'N/A'}\n"
            )
            # Entrada ideal si existe
            try:
                tipo_pullback = detectar_pullback(df)
            except Exception:
                tipo_pullback = "no_pullback"

            entrada_info = {}
            try:
                if tipo_pullback != "no_pullback":
                    entrada_info = calcular_entrada_ideal(df, tipo_pullback)
            except Exception:
                entrada_info = {}

            if entrada_info:
                mensaje += f"🎯 Entrada ideal: {entrada_info.get('entrada', 0):.2f} | SL: {entrada_info.get('sl', 0):.2f} | TP: {entrada_info.get('tp', 0):.2f}\n"

            mensaje += (
                f"\n🤖 IA: {accion_ia.upper()} (Precisión: {precision:.2%})\n"
                f"📚 Técnica: {'BUY' if (resultado.get('señal_tec') or resultado.get('signal_tec') or 0) > 0 else 'SELL' if (resultado.get('señal_tec') or resultado.get('signal_tec') or 0) < 0 else 'HOLD'}\n"
                f"📌 Conclusión: {'INVERTIR' if precision >= 0.6 else 'ESPERAR'}\n"
            )
            if hora_entrada:
                try:
                    if isinstance(hora_entrada, str):
                        mensaje += f"⏱ Entrada estimada: {hora_entrada}\n"
                    else:
                        mensaje += f"⏱ Entrada estimada: {hora_entrada.strftime('%H:%M')}\n"
                except Exception:
                    pass
            if duracion:
                mensaje += f"⏳ Duración estimada: {duracion} min\n"

            # Enviar mensaje (si supera umbral mínimo o siempre si quieres)
            try:
                send_telegram_alert(mensaje)
            except Exception as e:
                log_warning(f"{LOG_PREFIX} fallo enviando telegram: {e}")

            # Guardar historial
            try:
                guardar_historial(fecha=datetime.now(), activo=activo, accion=accion_ia, precision=precision, origen="IA")
                # también guardamos la señal técnica si está
                señal_final = resultado.get("señal_tec") or resultado.get("signal_tec") or 0
                guardar_historial(fecha=datetime.now(), activo=activo,
                                  accion="buy" if señal_final > 0 else "sell" if señal_final < 0 else "hold",
                                  origen="Estrategia")
            except Exception as e:
                log_warning(f"{LOG_PREFIX} guardar_historial fallo: {e}")

            # Ejecutar orden si corresponde (modo automático)
            try:
                if bot.ejecutar_orden and tipo_pullback != "no_pullback":
                    if (accion_ia == "buy" and tipo_pullback == "pullback_buy") or \
                       (accion_ia == "sell" and tipo_pullback == "pullback_sell"):
                        bot.place_order(activo.replace("-", ""), accion_ia)
            except Exception as e:
                log_warning(f"{LOG_PREFIX} fallo place_order: {e}")

        except Exception as exc:
            logger.error(f"{LOG_PREFIX} ❌ Error procesando {item}: {exc}")
            log_error(exc, archivo="el_bot_de_efra.py", funcion="ejecutar_bot")


# el_bot_de_efra.py — BLOQUE D
# ------------------------------------------------------------
# Ejecutar operación desde una señal recibida por Telegram
# ------------------------------------------------------------

def ejecutar_operacion_desde_telegram(senal: Dict[str, Any]):
    """
    Ejecuta una operación a partir de la señal recibida por Telegram.
    Se espera `senal` con keys: activo, accion, precision, opcionalmente sl/tp.
    """
    try:
        bot = TradingBot()

        activo = senal.get("activo")
        accion = senal.get("accion")
        precision = float(senal.get("precision", 0.0))

        if not activo or not accion:
            log_warning(f"{LOG_PREFIX} ejecutar_operacion_desde_telegram: señal inválida {senal}")
            return

        # Parámetros básicos de riesgo (puedes enlazar con config)
        config = cargar_config()
        capital_total = config.get("capital_total", 1000)
        riesgo_pct = config.get("riesgo_pct", 2)  # porcentaje del capital
        precio_actual = safe_obtener_precio_actual(activo) or 0.0
        if precio_actual <= 0:
            log_warning(f"{LOG_PREFIX} No se pudo obtener precio actual para {activo}")
            return

        # SL y TP si vienen por la señal, si no, definimos reglas simples
        sl = senal.get("sl")
        tp = senal.get("tp")
        if sl is None or tp is None:
            if accion.lower() == "buy":
                sl = precio_actual * 0.98
                tp = precio_actual * 1.02
            else:
                sl = precio_actual * 1.02
                tp = precio_actual * 0.98

        riesgo_usdt = capital_total * (riesgo_pct / 100)
        riesgo_por_unidad = abs(precio_actual - sl) if precio_actual != sl else 0.0
        cantidad = (riesgo_usdt / riesgo_por_unidad) if riesgo_por_unidad > 0 else 0.0

        # Ejecutar orden (TradingBot debe implementar abrir_operacion o similar)
        try:
            bot.ejecutar_orden = True
            bot.modo_demo = config.get("modo_demo", True)
            # Normaliza nombre activo si viene con guiones
            symbol_normal = activo.replace("-", "").upper()
            bot.abrir_operacion(symbol_normal, accion, cantidad, sl, tp)
            send_telegram_alert(f"✅ Operación {accion.upper()} ejecutada en {activo} | Cantidad: {cantidad:.4f} | SL: {sl:.2f} | TP: {tp:.2f}")
        except Exception as e:
            log_error(e, archivo="el_bot_de_efra.py", funcion="ejecutar_operacion_desde_telegram")
            send_telegram_alert(f"❌ Falló ejecución operación en {activo}: {e}")

    except Exception as exc:
        log_error(exc, archivo="el_bot_de_efra.py", funcion="ejecutar_operacion_desde_telegram")

# el_bot_de_efra.py — BLOQUE E
# ------------------------------------------------------------
# Instancia global y ejecución directa
# ------------------------------------------------------------

# Instancia global opcional para otros módulos
bot = TradingBot()

def main():
    """
    Punto de entrada para ejecución directa desde consola.
    Ejecuta un ciclo simple para todos los activos cargados.
    """
    try:
        ejecutar_bot(ejecutar_orden=None)
    except Exception as e:
        log_error(e, archivo="el_bot_de_efra.py", funcion="main")
        logger.error(f"{LOG_PREFIX} Error en main: {e}")

if __name__ == "__main__":
    main()
