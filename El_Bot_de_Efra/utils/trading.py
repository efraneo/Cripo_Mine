# ==========================================================
# utils/trading.py — TradingExecutor mejorado con IA y métricas
# ==========================================================
import threading
import time
import math
import os
import requests
import hmac
import hashlib
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any

# Binance SDK
try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException, BinanceOrderException
except Exception:
    BinanceClient = None
    BinanceAPIException = Exception
    BinanceOrderException = Exception

# Logger
try:
    from utils.logger import log_info, log_error, log_warning
except Exception:
    import logging
    log = logging.getLogger("utils.trading")
    logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s")
    def log_info(msg, archivo=None, funcion=None): log.info(f"{archivo or ''} {funcion or ''} - {msg}")
    def log_error(msg, archivo=None, funcion=None): log.exception(f"{archivo or ''} {funcion or ''} - {msg}")
    def log_warning(msg, archivo=None, funcion=None): log.warning(f"{archivo or ''} {funcion or ''} - {msg}")


class TradingExecutor:
    """Ejecución y monitoreo seguro con IA integrada."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, dry_run: bool = True):
        self.dry_run = bool(dry_run)
        self._lock = threading.RLock()
        self._comp_threads: Dict[str, Dict[str, Any]] = {}
        self.client = None
        self._time_offset = 0
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")

        self._base_spot = "https://api.binance.com"
        self._base_futures = "https://fapi.binance.com"

        if not self.dry_run:
            if BinanceClient is None:
                log_warning("Binance client no disponible. Forzando dry_run.", archivo="trading.py", funcion="__init__")
                self.dry_run = True
            else:
                try:
                    self.client = BinanceClient(self.api_key, self.api_secret)
                    try:
                        server_time = self.client.get_server_time()
                        if isinstance(server_time, dict) and "serverTime" in server_time:
                            local_time = int(time.time() * 1000)
                            offset = int(server_time["serverTime"]) - local_time
                            self._time_offset = offset
                            setattr(self.client, "timestamp_offset", offset)
                            log_info(f"🕒 Offset Binance aplicado: {offset} ms", archivo="trading.py", funcion="__init__")
                    except Exception as e:
                        log_warning(f"No se pudo sincronizar hora con Binance: {e}", archivo="trading.py", funcion="__init__")
                    log_info("✅ Cliente Binance inicializado (modo REAL)", archivo="trading.py", funcion="__init__")
                except Exception as e:
                    log_error(e, archivo="trading.py", funcion="__init__")
                    self.client = None
                    self.dry_run = True
        else:
            log_info("⚙️ Modo DEMO activo (dry_run)", archivo="trading.py", funcion="__init__")


    # ------------------------------
    # Sincronización y fallbacks firmados
    # ------------------------------
    def _ensure_time_sync(self) -> bool:
        """
        Intenta obtener serverTime de Binance y guardar offset en ms en self._time_offset.
        Devuelve True si tuvo éxito.
        """
        try:
            r = requests.get(f"{self._base_spot}/api/v3/time", timeout=5)
            r.raise_for_status()
            server_time = r.json().get("serverTime")
            if server_time:
                self._time_offset = int(server_time) - int(time.time() * 1000)
                # aplicar al cliente si es posible
                try:
                    setattr(self.client, "timestamp_offset", self._time_offset)
                except Exception:
                    pass
                log_info(f"🕒 Compensación de tiempo aplicada: {self._time_offset} ms",
                         archivo="trading.py", funcion="_ensure_time_sync")
                return True
        except Exception as e:
            log_warning(f"No se pudo sincronizar serverTime: {e}", archivo="trading.py", funcion="_ensure_time_sync")
        return False

    def _signed_order_market(self, api_key: str, api_secret: str, symbol: str, side: str, quantity: str, base: str = None) -> Optional[dict]:
        """
        Envia una orden MARKET firmada directamente por HTTP (fallback cuando python-binance falla por -1021).
        Retorna dict de la respuesta o lanza excepción si falla.
        """
        try:
            base = base or self._base_spot
            # obtener serverTime
            r = requests.get(f"{base}/api/v3/time", timeout=10)
            r.raise_for_status()
            stime = r.json().get("serverTime")
            if not stime:
                raise Exception("No serverTime recibido")

            ts = int(stime)
            # construir query (MARKET)
            params = f"symbol={symbol}&side={side}&type=MARKET&quantity={quantity}&timestamp={ts}&recvWindow=5000"
            signature = hmac.new(api_secret.encode("utf-8"), params.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"{base}/api/v3/order?{params}&signature={signature}"
            headers = {"X-MBX-APIKEY": api_key}
            r2 = requests.post(url, headers=headers, timeout=15)
            r2.raise_for_status()
            return r2.json()
        except Exception as e:
            log_error(e, archivo="trading.py", funcion="_signed_order_market")
            raise

    def _signed_account_request(self, api_key: str, api_secret: str, asset: str = "USDT", base: str = None) -> Optional[float]:
        """
        Realiza petición GET /api/v3/account firmada usando serverTime.
        Retorna el balance 'free' del asset o None.
        """
        try:
            base = base or self._base_spot
            r = requests.get(f"{base}/api/v3/time", timeout=10)
            r.raise_for_status()
            stime = r.json().get("serverTime")
            if not stime:
                return None
            ts = int(stime)
            params = f"timestamp={ts}&recvWindow=5000"
            signature = hmac.new(api_secret.encode("utf-8"), params.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"{base}/api/v3/account?{params}&signature={signature}"
            headers = {"X-MBX-APIKEY": api_key}
            r2 = requests.get(url, headers=headers, timeout=10)
            r2.raise_for_status()
            data = r2.json()
            for b in data.get("balances", []):
                if b.get("asset") == asset:
                    return float(b.get("free", 0))
        except Exception as e:
            log_error(e, archivo="trading.py", funcion="_signed_account_request")
        return None

    # ------------------------------
    # Utils: cantidad, precio, rules
    # ------------------------------
    def _round_quantity(self, qty: float, precision: int = 6) -> float:
        try:
            q = Decimal(str(qty)).quantize(Decimal(10) ** -precision, rounding=ROUND_DOWN)
            return float(q)
        except Exception:
            return round(qty, precision)

    def _get_precio(self, symbol: str) -> Optional[float]:
        try:
            if self.dry_run or not self.client:
                import random
                base = 100.0
                p = round(base + random.uniform(-2, 2), 6)
                return float(p)
            if hasattr(self.client, "get_symbol_ticker"):
                res = self.client.get_symbol_ticker(symbol=symbol)
                price = None
                if isinstance(res, dict):
                    price = res.get("price") or res.get("lastPrice")
                elif hasattr(res, "get"):
                    price = res.get("price")
                return float(price)
            elif hasattr(self.client, "ticker_price"):
                res = self.client.ticker_price(symbol=symbol)
                return float(res["price"])
            else:
                if hasattr(self.client, "get_avg_price"):
                    res = self.client.get_avg_price(symbol=symbol)
                    return float(res.get("price"))
        except Exception as e:
            log_error(e, archivo="trading.py", funcion="_get_precio")
        return None

    def _get_symbol_info_safe(self, symbol: str) -> dict:
        try:
            if not self.client:
                return {}
            info = self.client.get_symbol_info(symbol) or {}
            return info
        except Exception as e:
            log_warning(f"No se pudo obtener symbol_info para {symbol}: {e}",
                        archivo="trading.py", funcion="_get_symbol_info_safe")
            return {}

    def _get_min_notional(self, symbol: str) -> Optional[float]:
        try:
            info = self._get_symbol_info_safe(symbol)
            for f in info.get("filters", []):
                ft = str(f.get("filterType", "")).upper()
                if ft in ("MIN_NOTIONAL", "NOTIONAL"):
                    v = f.get("minNotional") or f.get("notional")
                    if v is not None:
                        try:
                            return float(v)
                        except Exception:
                            try:
                                return float(str(v).replace(",", "."))
                            except Exception:
                                return None
            return None
        except Exception as e:
            log_warning(f"Error extrayendo min_notional para {symbol}: {e}",
                        archivo="trading.py", funcion="_get_min_notional")
            return None

    def _get_lot_rules(self, symbol: str):
        from decimal import Decimal
        try:
            info = self._get_symbol_info_safe(symbol)
            for f in info.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    step_size = f.get("stepSize")
                    min_qty = f.get("minQty")
                    try:
                        step_d = Decimal(str(step_size)) if step_size is not None else None
                    except Exception:
                        step_d = None
                    try:
                        minq_d = Decimal(str(min_qty)) if min_qty is not None else None
                    except Exception:
                        minq_d = None
                    return step_d, minq_d
        except Exception as e:
            log_warning(f"Error extrayendo lot rules para {symbol}: {e}",
                        archivo="trading.py", funcion="_get_lot_rules")
        return None, None

  # ==========================================================
    # ✅ Nuevo: Obtener balance
    # ==========================================================
    def get_balance(self, asset: str = "USDT") -> Optional[float]:
        """Obtiene el balance disponible del activo."""
        try:
            if self.dry_run:
                return 100.0
            if self.client:
                bal = self.client.get_asset_balance(asset=asset)
                if isinstance(bal, dict):
                    return float(bal.get("free", 0))
            return None
        except Exception as e:
            log_error(e, archivo="trading.py", funcion="get_balance")
            return None



    # ------------------------------
    # Ejecutar orden de mercado y monitorear (Optimizado con métricas IA y Telegram)
    # ------------------------------
    def ejecutar_y_monitorear(
        self,
        symbol: str,
        side: str,
        notional_usd: float = 50.0,
        stop_loss_pct: float = 2.0,
        take_profit_pct: float = 1.5,
        trail_pct: float = 0.8,
        duracion_min: int = 10,
        sleep_interval: float = 5.0,
        precision: float = 0.0,
    ) -> dict:
        """
        Ejecuta una orden de mercado y la monitorea en tiempo real.
        Mejoras IA:
         ✅ Registro de precisión IA y confianza.
         ✅ Notificaciones enriquecidas a Telegram.
         ✅ Validación dinámica de saldo, minNotional, timestamp, y reglas de lote.
         ✅ Métricas actualizadas en Streamlit (capital, PnL, winrate).
        """
        from decimal import Decimal, ROUND_DOWN
        from datetime import datetime, timedelta
        import time, requests

        try:
            from binance.exceptions import BinanceAPIException, BinanceOrderException
        except Exception:
            BinanceAPIException = Exception
            BinanceOrderException = Exception

        # ------------------------------
        # Estructura inicial del resultado
        # ------------------------------
        resultado = {
            "success": False,
            "symbol": symbol,
            "side": (side or "").upper(),
            "entry_price": None,
            "exit_price": None,
            "pnl_pct": 0.0,
            "reason": None,
            "detalle": {},
            "capital_final": None,
            "converted_to_usdt": False,
            "precision": precision,
            "abort": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # ------------------------------
        # Función de notificación segura a Telegram
        # ------------------------------
        def notify_telegram_safe(text: str):
            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(text)
            except Exception:
                pass

        # ------------------------------
        # Etapa 1: Validaciones previas y preparación
        # ------------------------------
        try:
            with self._lock:
                side_norm = (side or "").upper()

                # Validar señal
                if side_norm not in ("BUY", "SELL"):
                    msg = f"📌 Señal '{side_norm}' recibida para {symbol} → No se ejecutará (HOLD)"
                    log_info(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                    try:
                        import streamlit as st
                        st.info(msg)
                    except Exception:
                        pass
                    resultado["reason"] = "HOLD / no execution"
                    resultado["success"] = True
                    return resultado

                log_info(f"📌 Ejecutando orden {side_norm} {symbol} (monto={notional_usd:.2f} USDT) | Confianza IA={precision*100:.2f}%",
                         archivo="trading.py", funcion="ejecutar_y_monitorear")

                # Obtener precio actual del mercado
                precio = self._get_precio(symbol)
                if precio is None:
                    resultado["reason"] = "No se pudo obtener precio actual"
                    try:
                        import streamlit as st
                        st.error("❌ No se pudo obtener el precio actual del mercado.")
                    except Exception:
                        pass
                    return resultado

                # Validar saldo disponible
                try:
                    balance_usdt = float(self.get_balance("USDT") or 0.0)
                    if balance_usdt < float(notional_usd):
                        msg = f"⚠️ Saldo insuficiente: disponible {balance_usdt:.4f} USDT, requerido {notional_usd:.4f} USDT"
                        log_warning(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                        notify_telegram_safe(f"⚠️ <b>Saldo insuficiente</b>\n💰 Disponible: {balance_usdt:.4f} USDT\n🔸 Requerido: {notional_usd:.4f} USDT\n⛔ Símbolo: {symbol}")
                        try:
                            import streamlit as st
                            st.error(msg)
                        except Exception:
                            pass
                        resultado["reason"] = msg
                        resultado["abort"] = True
                        resultado["success"] = False
                        return resultado
                except Exception as e_bal:
                    log_warning(f"No se pudo verificar balance USDT: {e_bal}",
                                archivo="trading.py", funcion="ejecutar_y_monitorear")

                # Validar minNotional
                min_notional = None
                try:
                    if self.client:
                        min_notional = self._get_min_notional(symbol)
                except Exception:
                    min_notional = None

                if min_notional is not None and float(notional_usd) < float(min_notional):
                    msg = (f"Notional {notional_usd:.8f} USDT < minNotional {min_notional:.8f} USDT (symbol={symbol})")
                    log_warning(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                    try:
                        import streamlit as st
                        st.error(msg)
                    except Exception:
                        pass
                    notify_telegram_safe(f"⚠️ <b>Notional insuficiente</b>\n🪙 {symbol}\n🔹 Enviado: {notional_usd:.8f} USDT\n🔸 Mínimo: {min_notional:.8f} USDT")
                    resultado["reason"] = msg
                    resultado["abort"] = True
                    resultado["success"] = False
                    return resultado


                # ------------------------------
                # 1️⃣ Ejecutar orden inicial
                # ------------------------------
                resultado["entry_price"] = precio
                cantidad_str = None

                try:
                    from decimal import Decimal
                    cantidad_est = Decimal(str(notional_usd)) / Decimal(str(precio))
                    step_size, min_qty = None, None
                    if self.client:
                        step_size, min_qty = self._get_lot_rules(symbol)

                    # Ajuste a stepSize
                    if step_size and step_size > 0:
                        precision_qty = max(0, -step_size.as_tuple().exponent)
                        quant = Decimal(10) ** -precision_qty
                        cantidad_trunc = (cantidad_est // step_size) * step_size
                        cantidad_q = cantidad_trunc.quantize(quant, rounding=ROUND_DOWN)
                        cantidad_str = format(cantidad_q, 'f')
                    else:
                        cantidad_str = f"{float(cantidad_est):.6f}"

                    # Validar minQty
                    if min_qty and Decimal(cantidad_str) < min_qty:
                        msg = f"Cantidad {cantidad_str} < minQty {min_qty} (symbol={symbol})"
                        log_warning(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                        try:
                            import streamlit as st
                            st.warning(msg)
                        except Exception:
                            pass
                        resultado["reason"] = msg
                        resultado["abort"] = True
                        return resultado
                except Exception as e:
                    log_warning(f"No se pudo ajustar cantidad a reglas Binance: {e}",
                                archivo="trading.py", funcion="ejecutar_y_monitorear")
                    cantidad_str = f"{round(notional_usd / precio, 6):.6f}"

                resultado["detalle"]["cantidad"] = cantidad_str

                # ------------------------------
                # 2️⃣ Envío de orden de mercado
                # ------------------------------
                if self.dry_run:
                    log_info(f"[SIMULADO] Orden {side_norm} {cantidad_str} {symbol} a {precio}",
                             archivo="trading.py", funcion="ejecutar_y_monitorear")
                    resultado["detalle"]["orden_inicial"] = {
                        "simulated": True, "precio": precio, "cantidad": cantidad_str
                    }
                else:
                    try:
                        # preferir método order_market
                        if hasattr(self.client, "order_market"):
                            orden = self.client.order_market(symbol=symbol, side=side_norm, quantity=cantidad_str)
                        else:
                            orden = self.client.create_order(symbol=symbol, side=side_norm, type="MARKET", quantity=cantidad_str)

                        resultado["detalle"]["orden_inicial"] = orden

                        # extraer price de fills
                        try:
                            fills = orden.get("fills") or []
                            if fills and len(fills) > 0:
                                p = fills[0].get("price")
                                if p:
                                    resultado["entry_price"] = float(p)
                        except Exception:
                            pass

                        log_info(f"✅ Orden ejecutada correctamente: {orden}",
                                 archivo="trading.py", funcion="ejecutar_y_monitorear")

                        # Notificación Telegram enriquecida
                        mensaje_exec = (
                            f"🚀 <b>Orden ejecutada</b>\n"
                            f"📌 Activo: <b>{symbol}</b>\n"
                            f"🧭 Dirección: <b>{side_norm}</b>\n"
                            f"💵 Monto: <b>{notional_usd:.2f} USDT</b>\n"
                            f"📊 Cantidad: <b>{cantidad_str}</b>\n"
                            f"🤖 Confianza IA: <b>{precision*100:.2f}%</b>\n"
                            f"🕒 Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        notify_telegram_safe(mensaje_exec)

                    except (BinanceAPIException, BinanceOrderException) as e:
                        err_text = str(e)
                        code = getattr(e, "code", None)
                        if (isinstance(code, int) and code == -1013) or ("NOTIONAL" in err_text.upper()):
                            msg = f"❌ Error NOTIONAL al enviar orden: {err_text}"
                            log_error(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                            resultado["reason"] = msg
                            resultado["abort"] = True
                            return resultado
                        if (isinstance(code, int) and code == -2010) or ("INSUFFICIENT" in err_text.upper()):
                            msg = f"❌ Saldo insuficiente en Binance: {err_text}"
                            log_error(msg, archivo="trading.py", funcion="ejecutar_y_monitorear")
                            notify_telegram_safe(msg)
                            try:
                                import streamlit as st
                                st.error(msg)
                            except Exception:
                                pass
                            resultado["reason"] = msg
                            resultado["abort"] = True
                            return resultado
                        if (isinstance(code, int) and code == -1021) or ("timestamp" in err_text.lower()):
                            log_warning("⚠️ Desfase de tiempo (-1021), reintentando con sincronización...",
                                        archivo="trading.py", funcion="ejecutar_y_monitorear")
                            synced = self._ensure_time_sync()
                            if synced:
                                try:
                                    if hasattr(self.client, "order_market"):
                                        orden = self.client.order_market(symbol=symbol, side=side_norm, quantity=cantidad_str)
                                    else:
                                        orden = self.client.create_order(symbol=symbol, side=side_norm, type="MARKET", quantity=cantidad_str)
                                    resultado["detalle"]["orden_inicial"] = orden
                                except Exception as e2:
                                    log_error(f"Fallo tras sincronizar: {e2}",
                                              archivo="trading.py", funcion="ejecutar_y_monitorear")
                                    resultado["reason"] = str(e2)
                                    return resultado
                        else:
                            log_error(e, archivo="trading.py", funcion="ejecutar_y_monitorear")
                            resultado["reason"] = f"Error Binance: {err_text}"
                            return resultado

                # ------------------------------
                # 3️⃣ Monitoreo de posición en tiempo real
                # ------------------------------
                expiracion = datetime.now() + timedelta(minutes=duracion_min)
                mejor_precio = resultado.get("entry_price") or precio
                pnl_pct = 0.0

                while datetime.now() < expiracion:
                    time.sleep(sleep_interval)
                    precio_act = self._get_precio(symbol)
                    if precio_act is None:
                        continue

                    try:
                        entrada = float(resultado.get("entry_price") or precio)
                        if side_norm == "BUY":
                            pnl_pct = ((precio_act - entrada) / entrada) * 100.0
                        else:
                            pnl_pct = ((entrada - precio_act) / entrada) * 100.0
                    except Exception:
                        pnl_pct = 0.0

                    resultado["pnl_pct"] = round(pnl_pct, 4)
                    resultado["detalle"]["precio_actual"] = precio_act

                    # Actualizar mejor precio para trailing
                    if (side_norm == "BUY" and precio_act > mejor_precio) or \
                       (side_norm == "SELL" and precio_act < mejor_precio):
                        mejor_precio = precio_act

                    # Stop Loss
                    if pnl_pct <= -abs(stop_loss_pct):
                        resultado["exit_price"] = precio_act
                        resultado["reason"] = f"Stop Loss (-{stop_loss_pct}%)"
                        break

                    # Take Profit
                    if pnl_pct >= abs(take_profit_pct):
                        resultado["exit_price"] = precio_act
                        resultado["reason"] = f"Take Profit (+{take_profit_pct}%)"
                        break

                    # Trailing Stop
                    try:
                        if side_norm == "BUY":
                            trail_trigger = mejor_precio * (1.0 - trail_pct / 100.0)
                            if precio_act <= trail_trigger:
                                resultado["exit_price"] = precio_act
                                resultado["reason"] = "Trailing Stop"
                                break
                        else:
                            trail_trigger = mejor_precio * (1.0 + trail_pct / 100.0)
                            if precio_act >= trail_trigger:
                                resultado["exit_price"] = precio_act
                                resultado["reason"] = "Trailing Stop"
                                break
                    except Exception:
                        pass

                # Si no se definió exit_price → expiración
                if resultado.get("exit_price") is None:
                    resultado["exit_price"] = self._get_precio(symbol)
                    resultado["reason"] = "Expiración por tiempo"


                # ============================
                # 3) Orden de cierre (opuesto)
                # ============================
                if self.dry_run:
                    try:
                        import streamlit as st
                        st.info(f"[SIMULADO] Cierre {side_norm} {symbol} en {resultado['exit_price']}")
                    except Exception:
                        pass
                else:
                    try:
                        side_opuesto = "SELL" if side_norm == "BUY" else "BUY"
                        orden_cierre = None
                        try:
                            if hasattr(self.client, "order_market"):
                                orden_cierre = self.client.order_market(symbol=symbol, side=side_opuesto, quantity=cantidad_str)
                            else:
                                orden_cierre = self.client.create_order(
                                    symbol=symbol, side=side_opuesto, type="MARKET", quantity=cantidad_str
                                )
                        except BinanceAPIException as e_close:
                            err_text = str(e_close)
                            code = getattr(e_close, "code", None)
                            if (isinstance(code, int) and code == -1021) or ("timestamp" in err_text.lower()) or ("Timestamp" in err_text):
                                log_warning("⚠️ Desfase de tiempo detectado al cerrar (-1021). Reintentando...", archivo="trading.py", funcion="ejecutar_y_monitorear")
                                synced = self._ensure_time_sync()
                                if synced:
                                    try:
                                        if hasattr(self.client, "order_market"):
                                            orden_cierre = self.client.order_market(symbol=symbol, side=side_opuesto, quantity=cantidad_str)
                                        else:
                                            orden_cierre = self.client.create_order(symbol=symbol, side=side_opuesto, type="MARKET", quantity=cantidad_str)
                                    except Exception:
                                        # fallback firmado
                                        api_key = self.api_key or os.getenv("BINANCE_API_KEY")
                                        api_secret = self.api_secret or os.getenv("BINANCE_API_SECRET")
                                        if api_key and api_secret:
                                            orden_cierre = self._signed_order_market(api_key, api_secret, symbol, side_opuesto, cantidad_str)
                                        else:
                                            raise
                                else:
                                    api_key = self.api_key or os.getenv("BINANCE_API_KEY")
                                    api_secret = self.api_secret or os.getenv("BINANCE_API_SECRET")
                                    if api_key and api_secret:
                                        orden_cierre = self._signed_order_market(api_key, api_secret, symbol, side_opuesto, cantidad_str)
                                    else:
                                        raise
                            else:
                                raise

                        resultado["detalle"]["orden_cierre"] = orden_cierre

                        # intentar extraer price del cierre
                        try:
                            fills_close = orden_cierre.get("fills") or []
                            if fills_close and isinstance(fills_close, (list, tuple)) and len(fills_close) > 0:
                                pclose = fills_close[0].get("price")
                                if pclose:
                                    resultado["exit_price"] = float(pclose)
                        except Exception:
                            pass

                        log_info(f"✅ Orden de cierre ejecutada: {resultado['detalle'].get('orden_cierre')}",
                                 archivo="trading.py", funcion="ejecutar_y_monitorear")

                    except (BinanceAPIException, BinanceOrderException) as e:
                        log_error(e, archivo="trading.py", funcion="ejecutar_y_monitorear_cierre")
                        resultado["reason"] = f"Error cierre Binance: {e}"
                        resultado["success"] = False
                        return resultado

                # ============================
                # 4) Calcular PnL final
                # ============================
                try:
                    entry = float(resultado["entry_price"])
                    exitp = float(resultado["exit_price"])
                    if side_norm == "BUY":
                        pnl_final = ((exitp - entry) / entry) * 100.0
                    else:
                        pnl_final = ((entry - exitp) / entry) * 100.0
                    resultado["pnl_pct"] = round(pnl_final, 4)
                    resultado["success"] = True

                    # Mensajes en UI / Telegram con resumen
                    try:
                        import streamlit as st
                        st.success(f"✅ Operación completada ({symbol}) — PnL: {pnl_final:.2f}% ({resultado['reason']})")
                    except Exception:
                        pass

                    resumen_mensaje = (
                        f"✅ <b>Operación completada</b>\n"
                        f"📌 Activo: <b>{symbol}</b>\n"
                        f"🧭 Dirección: <b>{side_norm}</b>\n"
                        f"💵 Monto: <b>{notional_usdt:.2f} USDT</b>\n"
                        f"📈 Entry: <b>{entry:.8f}</b>\n"
                        f"📉 Exit: <b>{exitp:.8f}</b>\n"
                        f"📊 PnL: <b>{pnl_final:.2f}%</b>\n"
                        f"🤖 Confianza IA: <b>{precision*100:.2f}%</b>\n"
                        f"🕒 Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"🔖 Reason: {resultado.get('reason')}"
                    )
                    notify_telegram_safe(resumen_mensaje)

                except Exception as e:
                    log_error(e, archivo="trading.py", funcion="ejecutar_y_monitorear_calc")
                    resultado["success"] = False

                # ============================
                # 5) Conversión final a USDT (si corresponde) y capital final
                # ============================
                try:
                    if not self.dry_run and self.client:
                        # Determinar quote asset (suponiendo 'USDT' o sufijo)
                        quote_asset = "USDT" if symbol.endswith("USDT") else symbol[-4:]
                        base_asset = symbol.replace(quote_asset, "")

                        if base_asset and base_asset != "USDT":
                            try:
                                balance = self.get_balance(base_asset)
                                if balance and float(balance) > 0:
                                    sell_qty = self._round_quantity(balance, precision=6)
                                    sell_qty_str = f"{sell_qty:.6f}".rstrip('0').rstrip('.') if sell_qty is not None else None
                                    try:
                                        orden_convert = self.client.order_market(symbol=f"{base_asset}USDT", side="SELL", quantity=sell_qty_str)
                                        resultado["detalle"]["orden_convert"] = orden_convert
                                        resultado["converted_to_usdt"] = True
                                        log_info(f"🔄 Convertido {sell_qty_str} {base_asset} → USDT",
                                                 archivo="trading.py", funcion="ejecutar_y_monitorear")
                                    except Exception as e_conv:
                                        log_warning(f"No se pudo ejecutar conversión a USDT: {e_conv}",
                                                    archivo="trading.py", funcion="ejecutar_y_monitorear")
                            except Exception as e_balance_conv:
                                log_warning(f"Error comprobando balance para conversión: {e_balance_conv}",
                                            archivo="trading.py", funcion="ejecutar_y_monitorear")

                        # Obtener capital final en USDT
                        try:
                            capital_final = self.get_balance("USDT")
                            resultado["capital_final"] = capital_final
                        except Exception as e_cap:
                            log_warning(f"No se pudo obtener capital final USDT: {e_cap}",
                                        archivo="trading.py", funcion="ejecutar_y_monitorear")
                except Exception as e:
                    log_warning(f"No se pudo convertir a USDT / obtener capital final: {e}",
                                archivo="trading.py", funcion="ejecutar_y_monitorear")

                # ============================
                # 6) Actualizar métricas en memoria para UI (si aplica)
                # ============================
                try:
                    # actualizar métricas de inversión compuesta en session_state (si se usa Streamlit)
                    try:
                        import streamlit as st
                        metricas = st.session_state.get("metricas_inversion", {}) or {}
                        # valores básicos a mantener/crear
                        metricas.setdefault("capital_inicial", metricas.get("capital_inicial", resultado.get("capital_final") or 0.0))
                        metricas["capital_actual"] = resultado.get("capital_final", metricas.get("capital_actual", metricas["capital_inicial"]))
                        metricas["mejor_capital"] = max(metricas.get("mejor_capital", metricas["capital_actual"]), metricas["capital_actual"])
                        # ganancia pct desde capital_inicial
                        try:
                            ci = float(metricas.get("capital_inicial", 0.0))
                            ca = float(metricas.get("capital_actual", 0.0))
                            metricas["ganancia_pct"] = round(((ca - ci) / (ci + 1e-12)) * 100.0, 4) if ci > 0 else 0.0
                        except Exception:
                            metricas["ganancia_pct"] = metricas.get("ganancia_pct", 0.0)

                        metricas["estado"] = "última_ok" if resultado.get("success") else metricas.get("estado", "N/A")
                        st.session_state["metricas_inversion"] = metricas
                    except Exception:
                        pass
                except Exception:
                    pass

                return resultado

        except Exception as e:
            log_error(e, archivo="trading.py", funcion="ejecutar_y_monitorear")
            resultado["reason"] = str(e)
            resultado["success"] = False
            try:
                import streamlit as st
                st.error(f"❌ Error inesperado: {e}")
            except Exception:
                pass
            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(f"❌ <b>Error crítico en ejecutar_y_monitorear</b>\n{e}")
            except Exception:
                pass
            return resultado


 # ==========================================================
    # 🧮 Inversión compuesta
    # ==========================================================
    def iniciar_inversion_compuesta(
        self,
        symbol: str,
        side: str = "BUY",
        monto_inicial: float = 5.0,
        stop_drawdown_pct: float = 2.0,
        usuario: str = "desconocido",
        sleep_interval: float = 30.0,
        max_cycles: int = 999,
    ) -> str:
        """Inicia inversión compuesta en background."""
        try:
            uid = f"{usuario}__{symbol}__{int(time.time())}"
            state = {
                "symbol": symbol,
                "side": side.upper(),
                "capital_actual": float(monto_inicial),
                "capital_inicial": float(monto_inicial),
                "mejor_capital": float(monto_inicial),
                "estado": "iniciada",
                "stop_drawdown_pct": float(stop_drawdown_pct),
                "stop_flag": False,
                "cycles": 0,
                "max_cycles": int(max_cycles),
                "started_at": datetime.now().isoformat(),
                "usuario": usuario,
                "confianza_ia": 0.0,
                "accion_ia": "HOLD"
            }

            self._comp_threads[uid] = state
            th = threading.Thread(target=self._loop, args=(uid, sleep_interval), daemon=True)
            state["thread"] = th
            th.start()

            log_info(f"🧩 Inversión compuesta iniciada -> {uid}", archivo="trading.py", funcion="iniciar_inversion_compuesta")

            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(
                    f"🧩 <b>Inversión compuesta iniciada</b>\n"
                    f"👤 Usuario: <b>{usuario}</b>\n"
                    f"📊 Activo: <b>{symbol}</b>\n"
                    f"🧭 Dirección inicial: <b>{side.upper()}</b>\n"
                    f"💵 Monto inicial: <b>{monto_inicial:.2f} USDT</b>\n"
                    f"⛔ Stop Drawdown: <b>{stop_drawdown_pct:.2f}%</b>"
                )
            except Exception:
                pass

            return uid

        except Exception as e:
            log_error(e, archivo="trading.py", funcion="iniciar_inversion_compuesta")
            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(f"❌ <b>Error al iniciar inversión compuesta:</b> {e}")
            except Exception:
                pass
            raise

    # ==========================================================
    # 🔁 Bucle de inversión compuesta
    # ==========================================================
    def _loop(self, uid: str, sleep_interval: float = 30.0):
        """Ejecuta ciclos de inversión + IA + Telegram."""
        try:
            state = self._comp_threads.get(uid)
            if not state:
                return

            from utils.modelo import predecir_senal
            from utils.data_fetcher import obtener_datos_con_fallback

            try:
                from telegram_alertas import send_telegram_alert
            except Exception:
                send_telegram_alert = None

            symbol = state["symbol"]
            side = state["side"]
            stop_drawdown = float(state["stop_drawdown_pct"])
            mejor_capital = state["mejor_capital"]

            while not state.get("stop_flag") and state["cycles"] < state["max_cycles"]:
                notional = float(state["capital_actual"])

                # 🧠 Evaluar IA
                df = obtener_datos_con_fallback(symbol, interval="1h", mercado="spot", min_rows=200)
                accion, confianza, _, _, _ = predecir_senal(df, activo=symbol, pasos=20, futuros=5)
                state["accion_ia"] = accion.upper()
                state["confianza_ia"] = round(confianza, 4)

                res = self.ejecutar_y_monitorear(
                    symbol=symbol,
                    side=accion.upper() if accion != "hold" else side,
                    notional_usd=notional,
                    stop_loss_pct=stop_drawdown,
                    take_profit_pct=1.0,
                    trail_pct=0.5,
                    duracion_min=10,
                    sleep_interval=5.0
                )

                state["cycles"] += 1
                pnl_pct = res.get("pnl_pct", 0.0) if isinstance(res, dict) else 0.0
                pnl_amount = state["capital_actual"] * (pnl_pct / 100)
                state["capital_actual"] = round(max(0.0, state["capital_actual"] + pnl_amount), 8)

                if state["capital_actual"] > mejor_capital:
                    mejor_capital = state["capital_actual"]
                    state["mejor_capital"] = mejor_capital

                drawdown_pct = (1.0 - (state["capital_actual"] / mejor_capital)) * 100 if mejor_capital > 0 else 0
                state["estado"] = f"ciclo_{state['cycles']} pnl={pnl_pct:.2f}% capital={state['capital_actual']:.4f}"

                log_info(f"[{uid}] ciclo={state['cycles']} | pnl={pnl_pct:.2f}% | confianza={confianza:.2%} | capital={state['capital_actual']}", archivo="trading.py", funcion="_loop")

                if send_telegram_alert and (state["cycles"] % 3 == 0 or abs(pnl_pct) > 1):
                    send_telegram_alert(
                        f"🔁 <b>Ciclo {state['cycles']}</b>\n"
                        f"📊 Activo: <b>{symbol}</b>\n"
                        f"🤖 Señal IA: <b>{accion.upper()}</b>\n"
                        f"💡 Confianza: <b>{confianza*100:.2f}%</b>\n"
                        f"💰 Capital: <b>{state['capital_actual']:.4f} USDT</b>\n"
                        f"📈 PnL: <b>{pnl_pct:.2f}%</b>\n"
                        f"📉 Drawdown: <b>{drawdown_pct:.2f}%</b>"
                    )

                if drawdown_pct >= stop_drawdown or state["capital_actual"] <= 0:
                    state["stop_flag"] = True
                    motivo = "drawdown" if drawdown_pct >= stop_drawdown else "capital agotado"
                    log_warning(f"[{uid}] Detenido por {motivo}", archivo="trading.py", funcion="_loop")
                    if send_telegram_alert:
                        send_telegram_alert(f"🛑 <b>Detenido por {motivo}</b>\nID: {uid}")
                    break

                time.sleep(sleep_interval)

            log_info(f"[{uid}] Loop finalizado. Estado: {state.get('estado')}", archivo="trading.py", funcion="_loop")
            if send_telegram_alert:
                send_telegram_alert(f"✅ <b>Inversión finalizada</b>\nID: {uid}\nEstado: {state.get('estado')}")

        except Exception as e:
            log_error(e, archivo="trading.py", funcion="_loop")
            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(f"❌ <b>Error en loop:</b> {e}")
            except Exception:
                pass


    def stop_inversion_compuesta(self, uid: str):
        """
        Marca flag para detener la inversión compuesta identificada por uid.
        Envía notificación visual y a Telegram.
        """
        try:
            if uid in self._comp_threads:
                self._comp_threads[uid]["stop_flag"] = True
                self._comp_threads[uid]["estado"] = "detenido_por_usuario"

                msg = f"🛑 Stop solicitado para inversión {uid}"
                log_info(msg, archivo="trading.py", funcion="stop_inversion_compuesta")
                try:
                    import streamlit as st
                    st.warning(msg)
                except Exception:
                    pass
                try:
                    from telegram_alertas import send_telegram_alert
                    send_telegram_alert(f"🛑 <b>Inversión detenida manualmente</b>\nID: <b>{uid}</b>")
                except Exception:
                    pass

        except Exception as e:
            log_error(e, archivo="trading.py", funcion="stop_inversion_compuesta")
            try:
                from telegram_alertas import send_telegram_alert
                send_telegram_alert(f"⚠️ <b>Error al detener inversión:</b> {e}")
            except Exception:
                pass




# ------------------------------
# Ejecución directa (básica) con executor
# ------------------------------
def ejecutar_orden_segura_basico(
    activo: str,
    accion: str,
    monto: float,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.05,
    usuario: str = "desconocido",
    executor=None
) -> dict:
    """
    Ejecuta una orden de mercado segura en Binance (o en modo demo).
    Retorna un diccionario con los datos de la operación.
    """
    try:
        if executor is None:
            executor = TradingExecutor(dry_run=True)

        precio = executor._get_precio(activo)
        if precio is None:
            raise Exception("No se pudo obtener precio del activo")

        cantidad = executor._round_quantity(monto / precio, precision=6)

        resultado = {
            "success": False,
            "activo": activo,
            "accion": accion.upper(),
            "monto": float(monto),
            "precio_entrada": float(precio),
            "cantidad": float(cantidad),
            "hora_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario": usuario,
            "stop_loss_pct": stop_loss_pct * 100,
            "take_profit_pct": take_profit_pct * 100,
            "detalle": {}
        }

        if executor.dry_run:
            log_info(f"[SIMULADO] {accion.upper()} {cantidad} {activo} @ {precio} (monto={monto} USDT)",
                     archivo="trading.py", funcion="ejecutar_orden_segura_basico")
            resultado["success"] = True
            return resultado

        try:
            if hasattr(executor.client, "order_market"):
                orden = executor.client.order_market(symbol=activo, side=accion.upper(), quantity=cantidad)
            elif hasattr(executor.client, "create_order"):
                orden = executor.client.create_order(symbol=activo, side=accion.upper(), type="MARKET", quantity=cantidad)
            else:
                orden = executor.client.order(symbol=activo, side=accion.upper(), type="MARKET", quantity=cantidad)

            log_info(f"✅ Orden ejecutada: {orden}", archivo="trading.py", funcion="ejecutar_orden_segura_basico")
            resultado["success"] = True
            resultado["detalle"]["orden"] = orden
            return resultado

        except (BinanceAPIException, BinanceOrderException) as e:
            log_error(e, archivo="trading.py", funcion="ejecutar_orden_segura_basico_binance")
            resultado["reason"] = f"Error Binance: {e}"
            return resultado

    except Exception as e:
        log_error(e, archivo="trading.py", funcion="ejecutar_orden_segura_basico")
        return {
            "success": False,
            "activo": activo,
            "accion": accion.upper(),
            "monto": monto,
            "precio_entrada": None,
            "cantidad": None,
            "hora_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario": usuario,
            "stop_loss_pct": stop_loss_pct * 100,
            "take_profit_pct": take_profit_pct * 100,
            "reason": str(e)
        }

# ------------------------------
# Wrapper para compatibilidad con app.py
# ------------------------------
def ejecutar_orden_segura(
    activo: str,
    accion: str,
    monto: float = 5.0,
    stop_loss_pct: float = 2.0,
    take_profit_pct: float = 5.0,
    usuario: str = "desconocido",
    dry_run: bool = True,
    precision: float = None  # Confianza IA
) -> dict:
    try:
        api_key = None
        api_secret = None
        from os import getenv
        if not dry_run:
            api_key = getenv("BINANCE_API_KEY")
            api_secret = getenv("BINANCE_API_SECRET")

        executor = TradingExecutor(api_key=api_key, api_secret=api_secret, dry_run=dry_run)
        side = "BUY" if accion.lower().startswith(("comp", "buy")) else "SELL"

        resultado = executor.ejecutar_y_monitorear(
            symbol=activo,
            side=side,
            notional_usd=float(monto),
            stop_loss_pct=float(stop_loss_pct),
            take_profit_pct=float(take_profit_pct),
            trail_pct=0.5,
            duracion_min=30,
            sleep_interval=5.0,
            precision=(precision if precision is not None else 0.0)
        )

        # Notificación a Telegram centralizada aquí
        try:
            from telegram_alertas import send_telegram_alert
            hora_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            mensaje = (
                f"🚀 <b>Orden enviada</b>\n"
                f"👤 Usuario: <b>{usuario}</b>\n"
                f"📌 Activo: <b>{activo}</b>\n"
                f"🧭 Dirección: <b>{accion.upper()}</b>\n"
                f"💵 Monto: <b>{monto:.2f} USDT</b>\n"
            )
            if precision is not None:
                mensaje += f"🤖 Confianza IA: <b>{precision*100:.2f}%</b>\n"
            mensaje += (
                f"🕒 Hora: {hora_local}\n"
                f"🎯 Stop Loss: {stop_loss_pct:.2f}%\n"
                f"🎯 Take Profit: {take_profit_pct:.2f}%"
            )
            send_telegram_alert(mensaje)
        except Exception as e:
            log_warning(f"No se pudo enviar notificación a Telegram: {e}", archivo="trading.py", funcion="ejecutar_orden_segura")

        return resultado

    except Exception as e:
        log_error(e, archivo="trading.py", funcion="ejecutar_orden_segura")
        return {"success": False, "reason": str(e)}

# ==========================================================
# utils/trading.py — Fin del archivo
# ==========================================================
