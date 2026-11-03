# ===== trading_bot.py =====
# ==========================================================
# 📦 TradingBot — Motor principal de análisis multi-activos
# ==========================================================
# - Multi-fuente: Binance, AlphaVantage, TwelveData, Yahoo, CSV...
# - Fallback robusto: si una fuente falla, pasa a la siguiente.
# - Añade indicadores técnicos, detección de patrones, Fibonacci.
# - Integra con módulo de trading para ejecutar/monitorear órdenes.
# - Devuelve estructura compatible con la UI (app.py).
# - Muy tolerante a errores: intenta no romper la importación.
# ==========================================================

import os
import re
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

import pandas as pd
import numpy as np

# Logger local (usa utils.logger si está disponible)
try:
    from utils.logger import log_info, log_error, log_warning
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | [trading_bot] %(message)s")
    _logger = logging.getLogger("trading_bot")
    def log_info(msg, **kw): _logger.info(msg)
    def log_error(msg, **kw): _logger.error(msg)
    def log_warning(msg, **kw): _logger.warning(msg)

# Intentar importar helpers opcionales (no romper si faltan)
try:
    from utils.modelo import entrenar_y_predecir, leer_activos_por_categoria
except Exception as e:
    entrenar_y_predecir = None
    leer_activos_por_categoria = None
    log_warning(f"utils.modelo no disponible: {e}")

try:
    from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
except Exception as e:
    agregar_indicadores_tecnicos = None
    tendencia_mercado = None
    log_warning(f"utils.indicadores_tecnicos no disponible: {e}")

try:
    # Preferir generar_grafico_velas (plotly) — graficos.py puede implementar alias
    from utils.graficos import generar_grafico_velas, graficar_velas_con_senal
except Exception as e:
    generar_grafico_velas = None
    graficar_velas_con_senal = None
    log_warning(f"utils.graficos no disponible: {e}")

# Fibonacci & patrones (si existen)
try:
    from fibonacci import detectar_niveles_fibonacci
except Exception as e:
    detectar_niveles_fibonacci = None
    log_warning(f"fibonacci.py no disponible: {e}")

try:
    from patrones_velas import detectar_patrones_velas
except Exception as e:
    detectar_patrones_velas = None
    log_warning(f"patrones_velas no disponible: {e}")


class TradingBot:
    """
    Clase principal que orquesta:
    - descarga de datos (multi-fuentes)
    - cálculo de indicadores
    - predicción IA (si está disponible)
    - generación de gráficos
    - retorno de resultados para UI
    """

    def __init__(self):
        # Intentar inicializar cliente Binance si hay credenciales
        self.client = None
        try:
            from binance.client import Client
            key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_API_SECRET")
            if key and secret:
                self.client = Client(api_key=key, api_secret=secret)
                log_info("Binance client inicializado (siempre comprueba credenciales).")
            else:
                log_info("Binance API keys no encontradas — client no inicializado.")
        except Exception as e:
            log_warning(f"No se inicializó cliente Binance: {e}")
            self.client = None

        # Cargar catálogo de activos si existe función util
        self.activos_por_categoria = {}
        self.mercado_symbols = {}
        if leer_activos_por_categoria:
            try:
                self.activos_por_categoria, self.mercado_symbols = leer_activos_por_categoria("activos.csv")
            except Exception as e:
                log_warning(f"leer_activos_por_categoria falló: {e}")

        # Exponer modelo si está disponible
        self.entrenar_y_predecir = entrenar_y_predecir

        # Estado interno
        self.bot_activo = False
        self.simbolos_en_tiempo_real = []

    # -------------------------
    # Utilidades internas
    # -------------------------
    def _ensure_datetime_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Asegura que el DataFrame tenga índice DatetimeIndex y columnas mínimas.
        """
        if df is None:
            return pd.DataFrame()
        try:
            # columnas mínimas
            cols = [c.lower() for c in df.columns]
            # Normalizar nombres comunes
            rename_map = {}
            for c in df.columns:
                lc = c.lower()
                if lc in ["date", "fecha", "datetime", "time", "timestamp"]:
                    rename_map[c] = "fecha"
            if rename_map:
                df = df.rename(columns=rename_map)

            # Si hay columna 'fecha' y no es índice, ponerla como índice
            if "fecha" in df.columns and not isinstance(df.index, pd.DatetimeIndex):
                df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
                df = df.set_index("fecha")
            # Si índice no es DatetimeIndex, intentar inferir
            if not isinstance(df.index, pd.DatetimeIndex):
                try:
                    df.index = pd.to_datetime(df.index)
                except Exception:
                    # fallback: crear índice con rango
                    df.index = pd.to_datetime(df.index, errors="coerce")
            # Drop filas con índice NaT
            if isinstance(df.index, pd.DatetimeIndex):
                df = df[~df.index.isna()]
            # Asegurar columnas OHLCV estén presentes (si no, crear NaNs)
            for c in ["open", "high", "low", "close", "volume"]:
                if c not in df.columns:
                    df[c] = np.nan
            # Convertir tipos numéricos
            for c in ["open", "high", "low", "close", "volume"]:
                try:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                except Exception:
                    pass
            return df
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="_ensure_datetime_index")
            return pd.DataFrame()

    # -------------------------
    # Buscar activo en catálogo
    # -------------------------
    def buscar_activo(self, nombre_o_simbolo: str) -> Optional[Dict[str, str]]:
        """
        Busca un activo por nombre o símbolo:
        1) Busca en el catálogo cargado (activos.csv → self.activos_por_categoria).
        2) Si no existe, busca en lista unificada cargar_activos().
        Retorna dict con {"simbolo": ..., "mercado": ...} o None.
        """
        try:
            target = str(nombre_o_simbolo).strip().upper()

            # 1) Buscar en catálogo pre-cargado (si existe)
            if getattr(self, "activos_por_categoria", None):
                for categoria, simbolos in self.activos_por_categoria.items():
                    for simbolo in simbolos:
                        if str(simbolo).strip().upper() == target:
                            return {
                                "simbolo": simbolo,
                                "mercado": self.mercado_symbols.get(simbolo, "desconocido")
                            }

            # 2) Buscar en lista robusta de activos (CSV, BD o Binance)
            try:
                from trading_bot import cargar_activos
                activos = cargar_activos()
                if target in activos:
                    return {"simbolo": target, "mercado": "desconocido"}
            except Exception as e:
                log_warning(f"⚠️ buscar_activo fallback cargar_activos falló: {e}", archivo="trading_bot.py", funcion="buscar_activo")

            return None
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="buscar_activo")
            return None

    # ============================================================
    # 📡 Métodos de obtención de datos (individuales)
    # Cada método devuelve DataFrame con índice DatetimeIndex y columnas
    # open, high, low, close, volume (en minúsculas).
    # ============================================================
    def obtener_datos_binance(self, symbol: str, interval: str = "1m", limit: int = 500) -> pd.DataFrame:
        try:
            if not self.client:
                return pd.DataFrame()
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
            if not klines:
                return pd.DataFrame()
            df = pd.DataFrame(klines, columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base", "taker_buy_quote", "ignore"
            ])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
            df = df.set_index("timestamp")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return self._ensure_datetime_index(df[["open", "high", "low", "close", "volume"]])
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="obtener_datos_binance")
            return pd.DataFrame()

    def obtener_datos_alphavantage(self, symbol: str, interval: str = "1min", limit: int = 500) -> pd.DataFrame:
        try:
            key = os.getenv("ALPHAVANTAGE_API_KEY")
            if not key:
                return pd.DataFrame()
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TIME_SERIES_INTRADAY&symbol={symbol}&interval={interval}"
                f"&apikey={key}&outputsize=compact"
            )
            r = requests.get(url, timeout=15)
            data = r.json()
            ts_key = next((k for k in data.keys() if "Time Series" in k), None)
            if not ts_key:
                return pd.DataFrame()
            values = data.get(ts_key, {})
            df = pd.DataFrame.from_dict(values, orient="index")
            df.columns = ["open", "high", "low", "close", "volume"]
            df = df.astype(float)
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)
            return self._ensure_datetime_index(df)
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="obtener_datos_alphavantage")
            return pd.DataFrame()

    def obtener_datos_twelvedata(self, symbol: str, interval: str = "1m", limit: int = 500) -> pd.DataFrame:
        try:
            key = os.getenv("TWELVEDATA_API_KEY")
            if not key:
                return pd.DataFrame()
            url = (
                f"https://api.twelvedata.com/time_series?"
                f"symbol={symbol}&interval={interval}&apikey={key}"
                f"&outputsize={limit}&format=JSON"
            )
            r = requests.get(url, timeout=15)
            data = r.json().get("values", [])
            if not data:
                return pd.DataFrame()
            df = pd.DataFrame(data)
            df.columns = [c.lower() for c in df.columns]
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
                df = df.set_index("datetime")
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df.sort_index(inplace=True)
            return self._ensure_datetime_index(df)
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="obtener_datos_twelvedata")
            return pd.DataFrame()

    def obtener_datos_yahoo(self, symbol: str, period: str = "1mo", interval: str = "1h") -> pd.DataFrame:
        try:
            import yfinance as yf
            yf_symbol = symbol if not symbol.upper().endswith("USDT") else symbol.replace("USDT", "-USD")
            max_period = "7d" if interval == "1m" else period
            df = yf.download(yf_symbol, period=max_period, interval=interval, progress=False)

            if df is None or df.empty:
                return pd.DataFrame()
            df.rename(columns=str.lower, inplace=True)
            return self._ensure_datetime_index(df[["open", "high", "low", "close", "volume"]])
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="obtener_datos_yahoo")
            return pd.DataFrame()

    def obtener_datos_csv(self, symbol: str) -> pd.DataFrame:
        try:
            posibles = [
                f"datos_alpha/{symbol}_alpha.csv",
                f"datos_twelve/{symbol}_twelve.csv",
                f"data_historica/{symbol}.csv",
                f"csv/{symbol}.csv"
            ]
            for p in posibles:
                if os.path.exists(p):
                    df = pd.read_csv(p, index_col=0, parse_dates=True, encoding="utf-8", on_bad_lines="skip")
                    df.rename(columns=str.lower, inplace=True)
                    return self._ensure_datetime_index(df)
            return pd.DataFrame()
        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="obtener_datos_csv")
            return pd.DataFrame()

    # Alias para compatibilidad (alguna versión usó otro nombre)
    def obtener_datos_con_fallback_alias(self, *args, **kwargs):
        return self.obtener_datos_con_fallback(*args, **kwargs)

    # ============================================================
    # 📡 Fallback maestro (intenta múltiples fuentes en orden)
    # ============================================================
    def obtener_datos_con_fallback(self, symbol: str, interval: str = "1m", limit: int = 500) -> pd.DataFrame:
        """
        Intenta obtener datos OHLCV de múltiples fuentes en orden:
        Binance -> AlphaVantage -> TwelveData -> Yahoo -> CSV local.
        Devuelve DataFrame vacío si no encuentra nada.
        """
        errores = []

        # Priorizar Binance si está inicializado
        try:
            df = self.obtener_datos_binance(symbol, interval=interval, limit=limit)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            errores.append(f"Binance: {e}")

        # AlphaVantage
        try:
            df = self.obtener_datos_alphavantage(symbol, interval=interval, limit=limit)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            errores.append(f"AlphaVantage: {e}")

        # TwelveData
        try:
            df = self.obtener_datos_twelvedata(symbol, interval=interval, limit=limit)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            errores.append(f"TwelveData: {e}")

        # Yahoo
        try:
            df = self.obtener_datos_yahoo(symbol, period="1mo", interval=interval)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            errores.append(f"Yahoo: {e}")

        # CSV local (último recurso)
        try:
            df = self.obtener_datos_csv(symbol)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            errores.append(f"CSV local: {e}")

        log_error(f"No se pudo obtener datos para {symbol} | Errores acumulados: {errores}", archivo="trading_bot.py", funcion="obtener_datos_con_fallback")
        return pd.DataFrame()

    # ============================================================
    # 📊 Método principal: Análisis completo del activo
    # ============================================================
    def analizar(self, symbol: str, ejecutar_orden: bool = False) -> Optional[Dict[str, Any]]:
        """
        Ejecuta análisis técnico + IA sobre 'symbol' y devuelve
        un diccionario con resultados apto para la UI.

        Retorna None si falla.
        También envía un resumen + gráfico a Telegram (1 solo mensaje).
        """
        try:
            # ============================================================
            # 1) Normalizar símbolo usando catálogo
            # ============================================================
            try:
                info_activo = self.buscar_activo(symbol)
            except Exception:
                info_activo = None
            symbol_use = info_activo.get("simbolo", symbol) if info_activo else symbol

            # ============================================================
            # 2) Obtener datos (con fallback)
            # ============================================================
            df = self.obtener_datos_con_fallback(symbol_use, interval="1m", limit=500)
            if df is None or df.empty or len(df) < 6:
                log_warning(f"⚠️ Datos insuficientes para {symbol_use}")
                return None

            # ============================================================
            # 3) Asegurar índice de tiempo y columnas
            # ============================================================
            df = self._ensure_datetime_index(df)

            # ============================================================
            # 4) Añadir indicadores técnicos
            # ============================================================
            if agregar_indicadores_tecnicos:
                try:
                    df = agregar_indicadores_tecnicos(df)
                except Exception as e:
                    log_warning(f"⚠️ agregar_indicadores_tecnicos falló: {e}")

            # ============================================================
            # 5) Tendencia de mercado
            # ============================================================
            try:
                tendencia = tendencia_mercado(df) if tendencia_mercado else None
            except Exception:
                tendencia = None

            # ============================================================
            # 6) Predicción IA
            # ============================================================
            action, acc = "hold", 0.0
            try:
                if self.entrenar_y_predecir:
                    res = self.entrenar_y_predecir(df)
                    if isinstance(res, tuple) and len(res) >= 2:
                        action, acc = res[0], float(res[1])
                    elif isinstance(res, dict):
                        action = res.get("accion", "hold")
                        acc = float(res.get("precision", 0.0))
            except Exception as e:
                log_warning(f"⚠️ entrenar_y_predecir falló: {e}")

            # ============================================================
            # 7) Niveles de Fibonacci
            # ============================================================
            niveles_raw, niveles_numericos = [], []
            try:
                if detectar_niveles_fibonacci:
                    niveles_raw = detectar_niveles_fibonacci(df)
                if isinstance(niveles_raw, (dict, list)):
                    for v in (niveles_raw.values() if isinstance(niveles_raw, dict) else niveles_raw):
                        try:
                            if isinstance(v, (int, float)):
                                niveles_numericos.append(float(v))
                            elif isinstance(v, str):
                                m = re.search(r"([-+]?\d+[\.\,]?\d*)", v)
                                if m:
                                    niveles_numericos.append(float(m.group(1).replace(",", ".")))
                        except Exception:
                            pass
            except Exception as e:
                log_warning(f"⚠️ detectar_niveles_fibonacci falló: {e}")

            # ============================================================
            # 8) Patrones de velas
            # ============================================================
            patrones = []
            try:
                if detectar_patrones_velas:
                    patrones = detectar_patrones_velas(df)
            except Exception as e:
                log_warning(f"⚠️ detectar_patrones_velas falló: {e}")

            # ============================================================
            # 9) Generar gráfico
            # ============================================================
            grafico_fig = None
            try:
                from utils.graficos import graficar_velas_con_senal
                grafico_fig = graficar_velas_con_senal(df, activo=symbol_use, accion=action)
            except Exception as e:
                log_warning(f"⚠️ Error generando gráfico: {e}")

            # ============================================================
            # 10) Guardar historial
            # ============================================================
            try:
                from utils.logger_historial import guardar_log
                guardar_log(
                    prediccion=action,
                    precision=acc,
                    rsi=df["rsi"].iloc[-1] if "rsi" in df.columns else None,
                    macd=df["macd"].iloc[-1] if "macd" in df.columns else None,
                    volumen=df["volume"].iloc[-1] if "volume" in df.columns else None,
                    tendencia=tendencia,
                    activo=symbol_use,
                    origen="TradingBot.analizar"
                )
            except Exception:
                pass

            # ============================================================
            # 11) Ejecutar orden (opcional)
            # ============================================================
            if ejecutar_orden:
                try:
                    from utils.trading import TradingExecutor
                    executor = TradingExecutor(
                        api_key=os.getenv("BINANCE_API_KEY"),
                        api_secret=os.getenv("BINANCE_API_SECRET"),
                        dry_run=False
                    )
                    executor.ejecutar_y_monitorear(
                        symbol=symbol_use,
                        side=action.upper(),
                        notional_usd=50,
                        stop_loss_pct=2.0,
                        take_profit_pct=1.5,
                        trail_pct=0.8,
                        duracion_min=30
                    )
                except Exception as e:
                    log_warning(f"⚠️ ejecución de orden falló: {e}")

            # ============================================================
            # 12) Ajustar índice a hora local
            # ============================================================
            try:
                df.index = pd.to_datetime(df.index, utc=True)
                df.index = df.index.tz_convert("America/Bogota")
            except Exception:
                pass

            # ============================================================
            # 13) Duración estimada con ATR (acotada 5–30 min)
            # ============================================================
            duracion_estimada = 15  # valor por defecto
            try:
                if "high" in df.columns and "low" in df.columns and "close" in df.columns:
                    atr = (df["high"] - df["low"]).rolling(window=14).mean().iloc[-1]
                    precio = df["close"].iloc[-1]
                    if atr and precio:
                        ratio = max(1, precio / atr)
                        duracion_estimada = int(min(30, max(5, ratio // 5)))
            except Exception as e:
                log_warning(f"No se pudo calcular duración estimada: {e}", archivo="trading_bot.py", funcion="analizar")

            # ============================================================
            # 14) Confianza ajustada
            # ============================================================
            try:
                from utils.graficos import calcular_confianza_mejorada
                acc = calcular_confianza_mejorada(acc, df)
            except Exception as e:
                log_warning(f"⚠️ calcular_confianza_mejorada falló: {e}")

            # ============================================================
            # 15) Construir retorno
            # ============================================================
            try:
                df.index = pd.to_datetime(df.index, utc=True)
                df.index = df.index.tz_convert("America/Bogota")
            except Exception:
                pass

            hora_estimada = df.index[-1].to_pydatetime() if len(df.index) else None

            retorno = {
                "accion": action if action else "hold",
                "precision": acc if acc is not None else 0.0,
                "tendencia": tendencia,
                "df": df,
                "grafico": grafico_fig,
                "niveles_raw": niveles_raw,
                "niveles_numericos": niveles_numericos,
                "patrones": patrones,
                "rsi": df["rsi"].iloc[-1] if "rsi" in df.columns else None,
                "macd": df["macd"].iloc[-1] if "macd" in df.columns else None,
                "volumen": df["volume"].iloc[-1] if "volume" in df.columns else None,
                "hora_entrada_estimada": hora_estimada,
                "duracion_estimada_min": duracion_estimada,
                "tps": niveles_numericos[:4] if niveles_numericos else [],
                "stop_loss_price": None if not niveles_numericos else niveles_numericos[-1]
            }

            # ============================================================
            # 16) Enviar resumen + gráfico a Telegram (UN SOLO mensaje)
            # ============================================================
            try:
                from utils.graficos import enviar_grafico_telegram

                # Formato bonito para TP1..TP4
                tps = retorno.get("tps", [])
                tp_lines = []
                for i, tp in enumerate(tps[:4], start=1):
                    tp_lines.append(f"TP{i}: {tp:.2f}")
                tp_text = "\n".join(tp_lines) if tp_lines else "N/A"

                # Patrones de velas
                patrones_text = ", ".join(retorno.get("patrones", [])) if retorno.get("patrones") else "Ninguno"

                resumen = f"""
📊 <b>Análisis completado</b>
💱 Activo: <b>{symbol_use}</b>
🤖 Señal IA: <b>{action.upper()}</b>
🎯 Confianza: {acc:.2%}
📈 Tendencia: {tendencia or 'N/A'}
📉 RSI: {f"{retorno['rsi']:.2f}" if retorno['rsi'] is not None else "N/A"}
📊 MACD: {f"{retorno['macd']:.2f}" if retorno['macd'] is not None else "N/A"}
🎯 Take Profits:
{tp_text}
🕒 Entrada: {retorno['hora_entrada_estimada'] if retorno['hora_entrada_estimada'] else 'N/A'}
⏳ Duración estimada: {retorno['duracion_estimada_min']} min
🕯️ Patrones: {patrones_text}
"""

                # ✅ Enviar gráfico + mensaje en UN SOLO envío
                if grafico_fig:
                    enviar_grafico_telegram(
                        grafico_fig,
                        mensaje=resumen,
                        filename=f"{symbol_use}_analisis.png"
                    )
            except Exception as e:
                log_warning(f"⚠️ No se pudo enviar alerta Telegram: {e}")

            return retorno

        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="analizar")
            return None


    # ============================================================
    # 📊 Analizar activo (versión robusta para app.py)
    # ============================================================
    def analizar_activo(
        self,
        activo: str,
        usar_avanzado: bool = True,
        usar_agresivo: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Analiza un activo usando:
          - Datos OHLCV con fallback (Binance + otras fuentes).
          - Indicadores técnicos (metodologías).
          - Predicción LSTM como voto adicional.
          - Combina señales para decisión final.
        Nunca devuelve HOLD → fuerza BUY o SELL.
        """
        try:
            from utils.metodologias import aplicar_metodologias
            from utils.binance_data import obtener_velas_binance
            from utils.lstm_model import predecir as predecir_lstm
            from utils.prediccion import combinar_senales

            # 1️⃣ Obtener velas recientes
            df = obtener_velas_binance(symbol=activo, interval="1m", limit=200)
            if df is None or df.empty:
                log_warning(
                    f"❌ Sin datos para {activo}",
                    archivo="trading_bot.py",
                    funcion="analizar_activo",
                )
                return None

            # 2️⃣ Predicción LSTM (primero, para pasarla luego a metodologías)
            prediccion_lstm = None
            try:
                prediccion_lstm = predecir_lstm(df, pasos=30, horizonte=5)
            except Exception as e:
                log_warning(
                    f"LSTM falló: {e}",
                    archivo="trading_bot.py",
                    funcion="analizar_activo",
                )

            # 3️⃣ Calcular metodologías técnicas (con conexión IA)
            metodologias = []
            try:
                metodologias = aplicar_metodologias(
                    df,
                    prediccion_lstm=prediccion_lstm,
                    confianza_ia=prediccion_lstm.get("confianza", 0.0) if isinstance(prediccion_lstm, dict) else 0.0,
                    resumen=f"Análisis de {activo}"
                )
            except Exception as e:
                log_warning(
                    f"aplicar_metodologias falló: {e}",
                    archivo="trading_bot.py",
                    funcion="analizar_activo",
                )

            # 4️⃣ Combinar señales (metodologías + LSTM)
            combinado = {}
            senal, confianza = "BUY", 0.5
            try:
                combinado = combinar_senales(
                    metodos=metodologias,
                    prediccion_lstm=prediccion_lstm,
                    peso_lstm=0.55,
                    umbral=0.20,
                    force_threshold=0.70,
                    method_trust_map=None,
                    verbose=False
                )
                senal = combinado.get("senal", "BUY").upper()
                confianza = float(combinado.get("confianza", 0.5))
            except Exception as e:
                log_warning(
                    f"⚠️ combinar_senales falló: {e}",
                    archivo="trading_bot.py",
                    funcion="analizar_activo",
                )

            # ⚡ Nunca devolver HOLD → forzar dirección coherente
            if senal == "HOLD":
                if prediccion_lstm:
                    senal = "BUY" if prediccion_lstm.get("tendencia") == "UP" else "SELL"
                else:
                    senal = "BUY" if confianza < 0.5 else "SELL"

            # 🚀 Aplicar refuerzo dinámico de confianza IA
            try:
                from utils.confidence_boost import dynamic_confidence_boost
                confianza_reforzada, aplicado = dynamic_confidence_boost(
                    metodologias=metodologias,
                    prediccion_lstm=prediccion_lstm,
                    confianza_actual=confianza,
                    resumen=f"{activo} ({senal}) — confianza base {confianza*100:.2f}%"
                )
                if aplicado:
                    confianza = max(confianza, confianza_reforzada)
            except Exception as e:
                log_warning(f"⚠️ dynamic_confidence_boost falló: {e}",
                            archivo="trading_bot.py", funcion="analizar_activo")

            # 🔒 Asegurar confianza mínima visual (evita valores <10%)
            confianza = max(0.15, min(confianza, 0.99))

            # 5️⃣ Stop Loss dinámico
            ultimo_close = float(df["close"].iloc[-1])
            stop_loss = round(ultimo_close * 0.98, 4)

            # 6️⃣ Duración estimada (ATR)
            duracion = 15
            try:
                if "high" in df.columns and "low" in df.columns and "close" in df.columns:
                    atr = (df["high"] - df["low"]).rolling(window=14).mean().iloc[-1]
                    precio = df["close"].iloc[-1]
                    if atr and precio:
                        ratio = max(1, precio / atr)
                        duracion = int(min(30, max(5, ratio // 5)))
            except Exception as e:
                log_warning(
                    f"No se pudo calcular duración estimada: {e}",
                    archivo="trading_bot.py",
                    funcion="analizar_activo",
                )

            # ✅ Construir retorno robusto
            return {
                "activo": activo,
                "df": df,
                "metodologias": metodologias,
                "prediccion_lstm": prediccion_lstm,
                "senal": senal,
                "confianza": round(confianza, 3),
                "stop_loss_price": stop_loss,
                "duracion_estimada_min": duracion,
                "combinado": combinado or {},
            }

        except Exception as e:
            log_error(e, archivo="trading_bot.py", funcion="analizar_activo")
            return None


# ============================================
# LISTAR ACTIVOS
# ============================================

    def listar_activos_catalogo(self) -> List[str]:
        """
        Retorna lista aplanada de símbolos desde el catálogo cargado.
        """
        try:
            symbols = []
            for cat, s in (self.activos_por_categoria or {}).items():
                symbols.extend(s)
            return sorted(list(set(symbols)))
        except Exception as e:
            log_warning(f"listar_activos_catalogo falló: {e}")
            return []
