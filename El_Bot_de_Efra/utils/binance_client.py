# ===== utils/binance_client.py =====
"""
Cliente Binance seguro y helpers para ejecutar órdenes desde la UI.
--------------------------------------------------
✅ Modo dry_run por defecto (no envía órdenes reales hasta que lo habilites).
✅ Calcula cantidad a operar a partir de un notional USD (con validación de precision/stepSize).
✅ Cierra la posición automáticamente tras `duration_min` usando Timer.
✅ Monitorea dinámicamente stop-loss y trailing stop.
✅ Registra automáticamente en logs/historial.csv (via logger_historial).
✅ Corrige desfase horario con Binance usando TIME_OFFSET.
✅ Resincroniza automáticamente cada hora con el servidor Binance.
✅ Al cierre (duration o stop) ejecuta orden contraria en el mismo par (vuelve a USDT).
✅ AHORA: Soporta mercado="spot" y mercado="futuros" (USD-M) en todas las funciones nuevas,
   conservando compatibilidad hacia atrás (si no pasas mercado, usa Spot).
"""

import os
import threading
import time
import requests
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Tuple, Dict, Any

from utils.logger import log_error, logger
from utils.logger_historial import guardar_evento_trade, guardar_evento_stop

# -----------------------
# 🔹 Cargar automáticamente binance.env
# -----------------------
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), "..", "binance.env")
    env_path = os.path.abspath(env_path)
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
        logger.info(f"[BinanceClient] Variables cargadas desde {env_path}")
    else:
        logger.warning(f"[BinanceClient] No se encontró {env_path}, se usará entorno actual")
except Exception as e:
    log_error(e, archivo="utils/binance_client.py", funcion="load_dotenv_auto")

# Cliente oficial Binance
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except Exception:
    Client = None
    BinanceAPIException = Exception

# Cliente Futuros USD-M
try:
    from binance.um_futures import UMFutures
except Exception:
    UMFutures = None  # no rompemos si no está instalado

# 🔑 Leer keys desde variables de entorno
API_KEY = os.getenv("BINANCE_API_KEY") or os.getenv("API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET") or os.getenv("API_SECRET")
MODO_DEMO = os.getenv("MODO_DEMO", "True").lower() == "true"

# 💰 Cantidad por operación en USD (default)
DEFAULT_NOTIONAL_USD = float(os.getenv("BOT_DEFAULT_NOTIONAL_USD", "10.0"))

# ⏳ Tiempo máximo de espera para queries (segundos)
HTTP_TIMEOUT = 15

# ============================================================
# ⏱ Corrección de desfase horario con Binance
# ============================================================
TIME_OFFSET = 0

def sync_time_with_binance():
    """Calcula offset de tiempo contra servidor de Binance (ms)."""
    global TIME_OFFSET
    try:
        resp = requests.get("https://api.binance.com/api/v3/time", timeout=5)
        server_time = int(resp.json().get("serverTime", 0))
        local_time = int(datetime.now().timestamp() * 1000)
        TIME_OFFSET = server_time - local_time
        logger.info(f"[BinanceClient] ⏱ TIME_OFFSET ajustado: {TIME_OFFSET} ms")
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="sync_time_with_binance")
        TIME_OFFSET = 0

def _timestamp() -> int:
    """Retorna timestamp ajustado con TIME_OFFSET (ms)."""
    return int(datetime.now().timestamp() * 1000) + int(TIME_OFFSET)

def _auto_resync_time(interval_sec=3600):
    """Ejecuta sync_time_with_binance cada `interval_sec` segundos (default 1h)."""
    def _loop():
        while True:
            time.sleep(interval_sec)
            try:
                sync_time_with_binance()
            except Exception as e:
                log_error(e, archivo="utils/binance_client.py", funcion="_auto_resync_time")
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

try:
    sync_time_with_binance()
    _auto_resync_time()
except Exception as e:
    log_error(e, archivo="utils/binance_client.py", funcion="inicio_sync_time")

# ============================================================
# 🔧 Clientes Binance (Spot / Futuros)
# ============================================================
def _get_client():
    """(Compat) Devuelve cliente Spot de Binance o lanza error si falta configuración."""
    if Client is None:
        raise RuntimeError("python-binance no está instalado.")
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Faltan BINANCE_API_KEY / BINANCE_API_SECRET en variables de entorno.")
    return Client(API_KEY, API_SECRET, {"timeout": HTTP_TIMEOUT})

def _get_client_spot():
    return _get_client()

def _get_client_futuros():
    """Devuelve cliente de Futuros USD-M, si está disponible."""
    if UMFutures is None:
        raise RuntimeError("python-binance (UMFutures) no está disponible para Futuros.")
    if not API_KEY or not API_SECRET:
        raise RuntimeError("Faltan BINANCE_API_KEY / BINANCE_API_SECRET en variables de entorno.")
    # Nota: UMFutures ya maneja los timestamps; no hace falta pasar TIME_OFFSET
    return UMFutures(key=API_KEY, secret=API_SECRET)

# ============================================================
# 🔎 Wrapper con resync automático (Spot)
# ============================================================
def _call_with_resync(func, *args, retries: int = 1, **kwargs):
    """Envuelve llamadas y reintenta si hay desfase (-1021) (Spot)."""
    try:
        return func(*args, **kwargs)
    except BinanceAPIException as e:
        if getattr(e, "code", None) == -1021 and retries > 0:
            logger.warning("[BinanceClient] ⚠️ Timestamp desfasado, resincronizando TIME_OFFSET...")
            sync_time_with_binance()
            return _call_with_resync(func, *args, retries=retries - 1, **kwargs)
        raise
    except Exception:
        raise

# ============================================================
# 🔧 Obtener último precio de un símbolo
# ============================================================
def _get_price_for_symbol(symbol: str, mercado: str = "spot") -> Optional[float]:
    """Obtiene el último precio ticker (Spot o Futuros USD-M)."""
    mercado = (mercado or "spot").lower()
    try:
        if mercado == "futuros":
            client_f = _get_client_futuros()
            data = client_f.ticker_price(symbol=symbol)  # {'symbol': 'BTCUSDT', 'price': '...'}
            price = float(data.get("price"))
        else:
            client = _get_client_spot()
            ticker = _call_with_resync(client.get_symbol_ticker, symbol=symbol)
            price = float(ticker.get("price"))
        if price <= 0:
            return None
        return price
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="_get_price_for_symbol")
        return None

# ============================================================
# 📐 Ajuste de cantidad según LOT_SIZE (Spot/Futuros)
# ============================================================
def _get_symbol_info(symbol: str, mercado: str = "spot") -> Dict[str, Any]:
    try:
        if (mercado or "spot").lower() == "futuros":
            c = _get_client_futuros()
            info = c.exchange_info()  # grande
            # Buscar el símbolo
            sym = next((s for s in info.get("symbols", []) if s.get("symbol") == symbol), None)
            return sym or {}
        else:
            c = _get_client_spot()
            return _call_with_resync(c.get_symbol_info, symbol)
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="_get_symbol_info")
        return {}

def ajustar_cantidad(symbol: str, cantidad: float, client=None, mercado: str = "spot") -> float:
    """
    Ajusta la cantidad a los filtros de Binance (stepSize, minQty).
    Evita error -1100 'Illegal characters in parameter quantity'.
    Soporta Spot y Futuros USD-M.
    """
    try:
        info = _get_symbol_info(symbol, mercado=mercado)
        filters = info.get("filters", [])
        lot_size = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), None)
        if not lot_size:
            return float(cantidad)

        step_size = Decimal(lot_size["stepSize"])
        min_qty = Decimal(lot_size["minQty"])
        cant_decimal = Decimal(str(cantidad))

        ajustada = (cant_decimal // step_size) * step_size
        ajustada = ajustada.quantize(step_size, rounding=ROUND_DOWN)

        if ajustada < min_qty:
            logger.error(f"[BinanceClient] ❌ Cantidad {ajustada} < minQty {min_qty} para {symbol} ({mercado})")
            raise ValueError(f"Cantidad {ajustada} < minQty {min_qty} para {symbol}")

        return float(f"{ajustada:f}")  # ✅ str plano sin notación científica
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="ajustar_cantidad")
        return float(cantidad)

# ============================================================
# 📐 Cálculo de cantidad a operar (Spot/Futuros)
# ============================================================
def calcular_quantity_from_notional(symbol: str, notional_usd: float = DEFAULT_NOTIONAL_USD, mercado: str = "spot") -> float:
    """Calcula la cantidad a operar dado un monto notional en USD (ya ajustado a LOT_SIZE)."""
    price = _get_price_for_symbol(symbol, mercado=mercado)
    if not price or price == 0:
        raise RuntimeError(f"No se pudo obtener precio para {symbol} ({mercado})")
    qty = float(notional_usd) / price
    return ajustar_cantidad(symbol, qty, mercado=mercado)

# ============================================================
# 🚀 Ejecución de órdenes (Spot/Futuros con MIN_NOTIONAL)
# ============================================================
def ejecutar_orden_market(symbol: str, side: str, quantity: float = None,
                          notional_usd: float = None, dry_run: bool = True,
                          mercado: str = "spot") -> Dict[str, Any]:
    """
    Ejecuta orden de mercado ajustando LOT_SIZE y cumpliendo MIN_NOTIONAL.
    Args:
      symbol: e.g., 'BTCUSDT'
      side: 'BUY' | 'SELL'
      quantity: opcional, si no se pasa se calcula desde notional_usd
      notional_usd: monto en USDT (por defecto DEFAULT_NOTIONAL_USD)
      dry_run: si True o si MODO_DEMO=True, no envía orden real
      mercado: 'spot' (default) | 'futuros' (USD-M)
    """
    side = side.upper()
    mercado = (mercado or "spot").lower()
    if side not in ("BUY", "SELL"):
        return {"success": False, "detail": "side inválido (use 'BUY' o 'SELL')", "order": None}

    try:
        # 1) Calcular qty base
        if quantity is None:
            notional = float(notional_usd) if notional_usd is not None else DEFAULT_NOTIONAL_USD
            quantity = calcular_quantity_from_notional(symbol, notional, mercado=mercado)
        else:
            quantity = ajustar_cantidad(symbol, quantity, mercado=mercado)

        # 2) Filtros (LOT_SIZE y MIN_NOTIONAL/NOTIONAL)
        info = _get_symbol_info(symbol, mercado=mercado)
        filters = info.get("filters", [])

        lot = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), {})
        step_size = Decimal(lot.get("stepSize", "0.000001"))
        dec_qty = Decimal(str(quantity))
        dec_qty = (dec_qty // step_size) * step_size  # round down a múltiplo de step
        quantity = float(dec_qty)  # ya ajustado

        # 3) Cumplir MIN_NOTIONAL/NOTIONAL
        min_notional = None
        price = _get_price_for_symbol(symbol, mercado=mercado) or 0.0
        for f in filters:
            if f.get("filterType") in ("MIN_NOTIONAL", "NOTIONAL"):
                # Futuros puede traer 'notional' o 'minNotional' según versión
                min_notional = float(f.get("minNotional") or f.get("notional") or 0.0)
                break
        if min_notional and price > 0:
            current_notional = quantity * price
            if current_notional < min_notional:
                needed_qty = (Decimal(str(min_notional)) / Decimal(str(price)))
                needed_qty = (needed_qty // step_size) * step_size
                quantity = float(needed_qty)
                if quantity * price < min_notional:
                    quantity = float(needed_qty + step_size)

        quantity_str = format(quantity, "f")
        logger.info(f"[BinanceClient] 🚀 Orden {mercado.upper()} {side} {symbol} qty={quantity_str} dry_run={dry_run or MODO_DEMO}")

        # 👉 respeto a MODO_DEMO global
        effective_dry_run = dry_run or MODO_DEMO

        if effective_dry_run:
            return {
                "success": True,
                "detail": "dry_run - orden simulada" + (" (MODO_DEMO)" if MODO_DEMO and not dry_run else ""),
                "order": {
                    "symbol": symbol, "side": side, "type": "MARKET",
                    "quantity": quantity, "status": "SIMULATED",
                    "fills": [{"price": price, "qty": quantity}],
                    "timestamp": datetime.utcnow().isoformat(),
                    "mercado": mercado
                }
            }

        if mercado == "futuros":
            # USD-M Futures
            c = _get_client_futuros()
            order = c.new_order(symbol=symbol, side=side, type="MARKET", quantity=quantity_str)
        else:
            # Spot
            c = _get_client_spot()
            order = _call_with_resync(
                c.create_order,
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=quantity_str,
                timestamp=_timestamp()
            )
        return {"success": True, "detail": "Orden enviada", "order": order}

    except BinanceAPIException as e:
        log_error(e, archivo="utils/binance_client.py", funcion="ejecutar_orden_market")
        return {"success": False, "detail": str(e), "order": None}
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="ejecutar_orden_market")
        return {"success": False, "detail": str(e), "order": None}

# ============================================================
# 💰 Saldo disponible (Spot/Futuros)
# ============================================================
def obtener_saldo_disponible(asset: str = "USDT", usuario: Optional[str] = None, es_admin: bool = False,
                             mercado: str = "spot") -> Tuple[float, float, bool]:
    """Obtiene el saldo disponible para un activo específico.
    return: (saldo_real, maximo_permitido, saldo_bajo)
    Soporta Spot y Futuros USD-M.
    """
    saldo_real = 0.0
    mercado = (mercado or "spot").lower()
    try:
        if mercado == "futuros":
            c = _get_client_futuros()
            balances = c.balance()  # lista de dicts
            for b in balances or []:
                if b.get("asset") == asset.upper():
                    # 'availableBalance' es el disponible en USD-M
                    saldo_real = float(b.get("availableBalance", 0.0))
                    break
        else:
            c = _get_client_spot()
            account_info = _call_with_resync(c.get_account)
            for b in account_info.get("balances", []):
                if b["asset"] == asset.upper():
                    saldo_real = float(b.get("free", 0.0))
                    break
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="obtener_saldo_disponible")
        return 0.0, 0.0, True

    if saldo_real < 5.0:
        return saldo_real, 0.0, True
    maximo_permitido = saldo_real if es_admin else min(10.0, saldo_real)
    return saldo_real, maximo_permitido, saldo_real < 5.0

# ============================================================
# 🧰 Compatibilidad: get_binance_balance (usado en la UI)
# ============================================================
def get_binance_balance(asset: str = "USDT", mercado: str = "spot") -> float:
    """Alias de compatibilidad para la UI (ahora con mercado)."""
    saldo, _, _ = obtener_saldo_disponible(asset=asset, mercado=mercado)
    return float(saldo)

# ============================================================
# ⏰ Cierre automático por duración (ejecuta orden contraria)
# ============================================================
def schedule_trade_closure(simbolo: str, entry_price: float, action_side: str, duration_min: int,
                           usuario: Optional[str] = None, notional_usd: float = None, dry_run: bool = True,
                           guardar_historial_fn=None, callback_cierre=None, mercado: str = "spot") -> bool:
    """
    Programa un cierre automático tras `duration_min` minutos.
    🔹 Al cerrarse, ejecuta la orden contraria en el mismo par (SELL si fue BUY, BUY si fue SELL)
       para convertir la posición nuevamente a USDT.
    🔹 Guarda evento en historial y permite callback para notificar en app/telegram.
    Soporta Spot/Futuros.
    """
    try:
        duration_sec = max(30, int(duration_min) * 60)
    except Exception:
        duration_sec = 1800

    def _cerrar_y_evaluar():
        try:
            precio_cierre = _get_price_for_symbol(simbolo, mercado=mercado)
            if precio_cierre is None:
                logger.error(f"[BinanceClient] ❌ No se pudo obtener precio de cierre para {simbolo} ({mercado})")
                return

            notional = float(notional_usd) if notional_usd else DEFAULT_NOTIONAL_USD
            entry_qty = notional / float(entry_price) if entry_price else notional / precio_cierre

            # Ejecutar orden contraria
            side_close = "SELL" if str(action_side).upper() == "BUY" else "BUY"
            try:
                entry_qty_ajustada = ajustar_cantidad(simbolo, entry_qty, mercado=mercado)
                cierre_res = ejecutar_orden_market(
                    symbol=simbolo,
                    side=side_close,
                    quantity=entry_qty_ajustada,
                    dry_run=dry_run,
                    mercado=mercado
                )
            except Exception as e:
                log_error(e, archivo="utils/binance_client.py", funcion="schedule_close_ejecutar")
                cierre_res = {"success": False, "detail": str(e), "order": None}

            # Precio salida real
            salida_price = None
            try:
                if cierre_res.get("success") and cierre_res.get("order"):
                    order = cierre_res.get("order")
                    fills = order.get("fills") if isinstance(order, dict) else None
                    if fills and len(fills) > 0:
                        salida_price = float(fills[0].get("price", precio_cierre))
                if salida_price is None:
                    salida_price = _get_price_for_symbol(simbolo, mercado=mercado) or precio_cierre
            except Exception:
                salida_price = _get_price_for_symbol(simbolo, mercado=mercado) or precio_cierre

            # Calcular PnL
            pnl = (salida_price - float(entry_price)) * entry_qty \
                if str(action_side).upper() == "BUY" else (float(entry_price) - salida_price) * entry_qty
            pnl_pct = ((salida_price - float(entry_price)) / float(entry_price) * 100.0) \
                if str(action_side).upper() == "BUY" else ((float(entry_price) - salida_price) / float(entry_price) * 100.0)

            # Guardar historial
            try:
                (guardar_historial_fn or guardar_evento_trade)(
                    usuario=usuario or "N/A",
                    activo=simbolo,
                    accion=str(action_side).lower(),
                    precio_entrada=float(entry_price),
                    precio_salida=float(salida_price),
                    cantidad=entry_qty,
                    pnl=pnl,
                    origen=("BINANCE_AUTO_FUT" if mercado == "futuros" else "BINANCE_AUTO") if not dry_run else "SIMULATED",
                    razon_cierre="duration"
                )
            except Exception as e:
                log_error(e, archivo="utils/binance_client.py", funcion="guardar_evento_trade_schedule")

            logger.info(f"[BinanceClient] ⏰ Cierre automático {simbolo} ({mercado}) | PnL={pnl:.4f} | Pct={pnl_pct:.2f}%")

            # Callback
            try:
                resumen = {
                    "activo": simbolo,
                    "side": action_side,
                    "precio_entrada": float(entry_price),
                    "precio_salida": float(salida_price),
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "motivo": "duration",
                    "mercado": mercado
                }
                if callable(callback_cierre):
                    callback_cierre(resumen)
            except Exception as e:
                log_error(e, archivo="utils/binance_client.py", funcion="callback_cierre_schedule")

        except Exception as e:
            log_error(e, archivo="utils/binance_client.py", funcion="_cerrar_y_evaluar")

    t = threading.Timer(duration_sec, _cerrar_y_evaluar)
    t.daemon = True
    t.start()
    return True

# ============================================================
# 🛡 Monitoreo dinámico (stop-loss + trailing stop + duración)
# ============================================================
def monitorear_posicion(symbol: str, precio_entrada: float, action_side: str = "BUY", notional_usd: float = None,
                        max_drawdown: float = 0.02, trailing_stop: float = 0.01, duration_min: int = None,
                        dry_run: bool = True, usuario: Optional[str] = None, callback_cierre=None,
                        mercado: str = "spot") -> bool:
    """
    Monitorea en segundo plano (stop-loss + trailing stop + duración).
    Soporta Spot/Futuros.
    """
    try:
        mercado = (mercado or "spot").lower()
        notional = float(notional_usd) if notional_usd else DEFAULT_NOTIONAL_USD
        entry_price = float(precio_entrada)
        if entry_price <= 0:
            logger.error(f"[BinanceClient] ❌ Precio entrada inválido {symbol}: {entry_price}")
            return False

        entry_qty = notional / entry_price
        start_time = time.time()

        stop_price = entry_price * (1 - max_drawdown if action_side.upper() == "BUY" else 1 + max_drawdown)
        peak_price = entry_price

        def _monitor():
            nonlocal stop_price, peak_price
            while True:
                time.sleep(10)
                precio_actual = _get_price_for_symbol(symbol, mercado=mercado)
                if not precio_actual:
                    continue

                # Actualizar trailing stop
                if action_side.upper() == "BUY" and precio_actual > peak_price:
                    peak_price = precio_actual
                    stop_price = max(stop_price, peak_price * (1 - trailing_stop))
                elif action_side.upper() == "SELL" and precio_actual < peak_price:
                    peak_price = precio_actual
                    stop_price = min(stop_price, peak_price * (1 + trailing_stop))

                # Cierre por stop
                if (action_side.upper() == "BUY" and precio_actual <= stop_price) or \
                   (action_side.upper() == "SELL" and precio_actual >= stop_price):
                    try:
                        side_close = "SELL" if action_side.upper() == "BUY" else "BUY"
                        entry_qty_ajustada = ajustar_cantidad(symbol, entry_qty, mercado=mercado)
                        cierre_res = ejecutar_orden_market(
                            symbol=symbol,
                            side=side_close,
                            quantity=entry_qty_ajustada,
                            dry_run=dry_run,
                            mercado=mercado
                        )
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="monitoreo_close_stop")
                        cierre_res = {"success": False, "detail": str(e), "order": None}

                    salida_price = precio_actual
                    try:
                        if cierre_res.get("success") and cierre_res.get("order"):
                            fills = cierre_res["order"].get("fills")
                            if fills and len(fills) > 0:
                                salida_price = float(fills[0].get("price", precio_actual))
                    except Exception:
                        pass

                    pnl = (salida_price - entry_price) * entry_qty if action_side.upper() == "BUY" else (entry_price - salida_price) * entry_qty
                    pnl_pct = ((salida_price - entry_price) / entry_price * 100.0) if action_side.upper() == "BUY" else ((entry_price - salida_price) / entry_price * 100.0)

                    # Guardar evento stop
                    try:
                        razon = "trailing_stop" if (action_side.upper() == "BUY" and abs(salida_price - peak_price) / peak_price <= trailing_stop) or \
                                              (action_side.upper() == "SELL" and abs(salida_price - peak_price) / peak_price <= trailing_stop) else "max_drawdown"
                        guardar_evento_stop(
                            usuario=usuario or "N/A",
                            activo=symbol,
                            accion=action_side.lower(),
                            entry_price=entry_price,
                            stop_price=salida_price,
                            pnl=pnl,
                            razon=razon,
                            origen=("BINANCE_MONITOR_FUT" if mercado == "futuros" else "BINANCE_MONITOR") if not dry_run else "SIMULATED"
                        )
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="guardar_evento_stop_monitoreo")

                    logger.info(f"[BinanceClient] 🚨 Stop ejecutado {symbol} ({mercado}) | PnL={pnl:.4f} | Pct={pnl_pct:.2f}%")

                    # Callback
                    try:
                        resumen = {
                            "activo": symbol,
                            "side": action_side,
                            "precio_entrada": entry_price,
                            "precio_salida": salida_price,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "motivo": "stop_loss",
                            "mercado": mercado
                        }
                        if callable(callback_cierre):
                            callback_cierre(resumen)
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="callback_cierre_monitor")

                    break

                # Cierre por duración
                if duration_min and (time.time() - start_time) >= duration_min * 60:
                    try:
                        side_close = "SELL" if action_side.upper() == "BUY" else "BUY"
                        entry_qty_ajustada = ajustar_cantidad(symbol, entry_qty, mercado=mercado)
                        cierre_res = ejecutar_orden_market(
                            symbol=symbol,
                            side=side_close,
                            quantity=entry_qty_ajustada,
                            dry_run=dry_run,
                            mercado=mercado
                        )
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="monitoreo_close_duration")
                        cierre_res = {"success": False, "detail": str(e), "order": None}

                    salida_price = _get_price_for_symbol(symbol, mercado=mercado) or precio_actual
                    try:
                        if cierre_res.get("success") and cierre_res.get("order"):
                            fills = cierre_res["order"].get("fills")
                            if fills and len(fills) > 0:
                                salida_price = float(fills[0].get("price", salida_price))
                    except Exception:
                        pass

                    pnl = (salida_price - entry_price) * entry_qty if action_side.upper() == "BUY" else (entry_price - salida_price) * entry_qty
                    pnl_pct = ((salida_price - entry_price) / entry_price * 100.0) if action_side.upper() == "BUY" else ((entry_price - salida_price) / entry_price * 100.0)

                    try:
                        guardar_evento_stop(
                            usuario=usuario or "N/A",
                            activo=symbol,
                            accion=action_side.lower(),
                            entry_price=entry_price,
                            stop_price=salida_price,
                            pnl=pnl,
                            razon="duration_limit",
                            origen=("BINANCE_MONITOR_FUT" if mercado == "futuros" else "BINANCE_MONITOR") if not dry_run else "SIMULATED"
                        )
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="guardar_evento_stop_duration")

                    logger.info(f"[BinanceClient] ⏰ Duración alcanzada {symbol} ({mercado}) | PnL={pnl:.4f} | Pct={pnl_pct:.2f}%")

                    try:
                        resumen = {
                            "activo": symbol,
                            "side": action_side,
                            "precio_entrada": entry_price,
                            "precio_salida": salida_price,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "motivo": "duration_limit",
                            "mercado": mercado
                        }
                        if callable(callback_cierre):
                            callback_cierre(resumen)
                    except Exception as e:
                        log_error(e, archivo="utils/binance_client.py", funcion="callback_cierre_duration")

                    break

        t = threading.Thread(target=_monitor, daemon=True)
        t.start()
        return True

    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="monitorear_posicion")
        return False

# ============================================================
# 🧩 Helpers auxiliares (stubs seguros)
# ============================================================
def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def get_symbol_info_cached(symbol: str) -> Dict[str, Any]:
    """Stub compatible: consulta directa (sin caché persistente)."""
    try:
        client = _get_client_spot()
        return _call_with_resync(client.get_symbol_info, symbol)
    except Exception as e:
        log_error(e, archivo="utils/binance_client.py", funcion="get_symbol_info_cached")
        return {}

def get_latest_price(symbol: str) -> Optional[float]:
    """Alias: precio último (Spot por compatibilidad)."""
    return _get_price_for_symbol(symbol, mercado="spot")

