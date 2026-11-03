# ==========================================================
# utils/telegram_orchestrator.py — PTB v20+ con Binance integrado
# ==========================================================
import threading
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from utils.logger import log_error

# ==========================================================
# Estado global del orquestador
# ==========================================================
_APP: Optional[Application] = None
_THREAD: Optional[threading.Thread] = None
_RUNNING: bool = False

# Cola en memoria de oportunidades pendientes
# {chat_id: { 'op_id': {...} } }
_PENDING: Dict[int, Dict[str, Any]] = {}

# Flujo por chat (esperando monto, etc.)
# {chat_id: {'esperando_monto_de': 'op_id', 'default_monto': 5.0}}
_FLOW: Dict[int, Dict[str, Any]] = {}

# ==========================================================
# Configuración
# ==========================================================
def _load_config():
    import yaml
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg
    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="_load_config")
        return {}

# ==========================================================
# Helpers Async/Sync
# ==========================================================
def _ensure_loop():
    """Devuelve el event loop actual o crea uno nuevo si hace falta."""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

def _run_coro(coro):
    """
    Ejecuta una corutina desde contexto síncrono.
    - Si hay loop corriendo, agenda la tarea (no bloquea).
    - Si no hay loop, crea uno, corre y devuelve el resultado.
    """
    try:
        loop = asyncio.get_running_loop()
        return asyncio.ensure_future(coro)
    except RuntimeError:
        loop = _ensure_loop()
        return loop.run_until_complete(coro)

async def _maybe_run_sync(func, **kwargs):
    """Invoca funciones síncronas desde async sin bloquear (en ThreadPool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(**kwargs))

# ==========================================================
# Handlers básicos
# ==========================================================
async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🤖 Bot listo para confirmar oportunidades. Usa /status para verificar.")
    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="_cmd_start")

async def _cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("✅ Online. Esperando oportunidades…")
    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="_cmd_status")

# ==========================================================
# Handlers de callbacks y ejecución
# ==========================================================
async def _on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja clicks en botones 'Ejecutar' / 'Cancelar'."""
    try:
        query = update.callback_query
        await query.answer()
        action, op_id = query.data.split("|", 1)
        chat_id = query.message.chat.id

        ops = _PENDING.get(chat_id, {})
        op = ops.get(op_id)
        if not op:
            await query.edit_message_text("⚠️ Oportunidad expirada o no encontrada.")
            return

        if action == "cancel":
            del ops[op_id]
            await query.edit_message_text("🛑 Operación cancelada.")
            return

        if action == "exec":
            _FLOW.setdefault(chat_id, {})
            _FLOW[chat_id]["esperando_monto_de"] = op_id
            _FLOW[chat_id]["default_monto"] = 5.0
            await query.edit_message_text("💵 ¿Cuánto deseas invertir (USDT)?\nResponde con un número (ej: 7.5)")
    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="_on_callback")

async def _on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captura monto, ejecuta orden en Binance y monitorea con SL/Trailing."""
    try:
        if not update.message:
            return
        chat_id = update.message.chat.id
        flow = _FLOW.get(chat_id, {})
        op_id = flow.get("esperando_monto_de")
        if not op_id:
            return

        # Parseo del monto
        raw = (update.message.text or "").strip().replace(",", ".")
        try:
            monto = float(raw)
            if monto <= 0:
                raise ValueError
        except Exception:
            monto = flow.get("default_monto", 5.0)
            await update.message.reply_text(f"⚠️ Entrada inválida. Usaré {monto} USDT.")

        # Extraer la operación
        op = _PENDING.get(chat_id, {}).pop(op_id, None)
        _FLOW[chat_id].pop("esperando_monto_de", None)
        if not op:
            await update.message.reply_text("⚠️ La oportunidad ya no está disponible.")
            return

        # ======================================================
        # 🔗 Ejecución real en Binance
        # ======================================================
        try:
            from utils.binance_client import ejecutar_orden_market, monitorear_posicion
        except Exception as e:
            log_error(e, archivo="telegram_orchestrator.py", funcion="import_binance_client")
            await update.message.reply_text("❌ No se encontró utils.binance_client. No se pudo ejecutar.")
            return

        cfg = _load_config()
        estrategia = (cfg.get("estrategia") or {})
        stop_loss_pct = float(estrategia.get("stop_loss_pct", -2.0)) / 100.0
        trailing = bool(estrategia.get("trailing", True))
        trailing_step = float(estrategia.get("trailing_step", 1.0)) / 100.0
        trailing_lock = float(estrategia.get("trailing_lock", 0.5)) / 100.0
        trailing_lock_gain = float(estrategia.get("trailing_lock_gain", 0.5)) / 100.0

        symbol = op["activo"]
        side = op["accion"].upper()
        mercado = op.get("mercado", "spot")

        # 1. Ejecutar orden Market
        res = await _maybe_run_sync(
            ejecutar_orden_market,
            symbol=symbol,
            side=side,
            notional_usd=monto,
            dry_run=not op.get("modo_real", False),
            mercado=mercado
        )
        if not res.get("success"):
            await update.message.reply_text(f"❌ Error en orden: {res.get('detail')}")
            return

        # 2. Obtener precio de entrada real
        fills = (res.get("order") or {}).get("fills", [])
        precio_entrada = float(fills[0]["price"]) if fills else None

        # 3. Lanzar monitoreo SL + Trailing
        if precio_entrada:
            await _maybe_run_sync(
                monitorear_posicion,
                symbol=symbol,
                precio_entrada=precio_entrada,
                action_side=side,
                notional_usd=monto,
                max_drawdown=abs(stop_loss_pct),
                trailing_stop=trailing_step if trailing else 0.0,
                trailing_lock=trailing_lock,
                trailing_lock_gain=trailing_lock_gain,
                duration_min=op.get("duracion") or 30,
                dry_run=not op.get("modo_real", False),
                usuario=op.get("usuario") or "telegram"
            )

        # 4. Confirmar al usuario
        await update.message.reply_text(
            f"✅ Orden {side} {symbol} ejecutada por {monto} USDT.\n"
            f"SL: {stop_loss_pct*100:.2f}% | Trailing: {trailing} (+{trailing_step*100:.2f}% step)"
        )

    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="_on_text")

# ==========================================================
# Orquestador principal
# ==========================================================
def _build_app() -> Optional[Application]:
    cfg = _load_config()
    bot_token = (cfg.get("telegram") or {}).get("bot_token")
    if not bot_token:
        log_error("config.yaml -> telegram.bot_token no definido",
                  archivo="telegram_orchestrator.py", funcion="_build_app")
        return None

    app = Application.builder().token(bot_token).build()
    app.add_handler(CommandHandler("start", _cmd_start))
    app.add_handler(CommandHandler("status", _cmd_status))
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    return app

def start_orchestrator():
    """Lanza el bot de Telegram en un hilo de fondo (solo una vez)."""
    global _APP, _THREAD, _RUNNING
    if _RUNNING:
        return
    _APP = _build_app()
    if _APP is None:
        return

    def _target():
        global _RUNNING
        _RUNNING = True
        try:
            _APP.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            log_error(e, archivo="telegram_orchestrator.py", funcion="run_polling")
        finally:
            _RUNNING = False

    _THREAD = threading.Thread(target=_target, name="TG-Orchestrator", daemon=True)
    _THREAD.start()

def notify_opportunity(
    chat_id: int,
    activo: str,
    accion: str,
    precision: float,
    mercado: Optional[str] = None,
    usuario: Optional[str] = None,
    duracion_min: Optional[int] = None,
    modo_real: Optional[bool] = None,
    indicadores: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Envía una alerta de oportunidad con botones Ejecutar/Cancelar.
    """
    try:
        if not _RUNNING:
            start_orchestrator()

        cfg = _load_config()
        bot_token = (cfg.get("telegram") or {}).get("bot_token")
        if not bot_token:
            return False

        bot = Bot(token=bot_token)
        op_id = f"{activo}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        _PENDING.setdefault(chat_id, {})
        _PENDING[chat_id][op_id] = {
            "activo": activo,
            "accion": accion,
            "precision": precision,
            "mercado": mercado,
            "usuario": usuario,
            "duracion": duracion_min,
            "modo_real": modo_real
        }

        ind_txt = ""
        if indicadores:
            try:
                rsi = indicadores.get("rsi")
                macd = indicadores.get("macd")
                tend = indicadores.get("tendencia")
                ind_txt = f"\n📐 RSI: {rsi} | MACD: {macd}\n📊 Tendencia: {tend}"
            except Exception:
                pass

        text = (
            f"🚨 *Oportunidad Detectada*\n"
            f"📈 Activo: *{activo}*\n"
            f"🎯 Acción: *{accion.upper()}*\n"
            f"🤖 Precisión IA: *{precision*100:.2f}%*{ind_txt}\n\n"
            "¿Deseas ejecutar la orden ahora?"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ejecutar", callback_data=f"exec|{op_id}"),
             InlineKeyboardButton("🛑 Cancelar", callback_data=f"cancel|{op_id}")]
        ])

        _run_coro(bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=kb))
        return True
    except Exception as e:
        log_error(e, archivo="telegram_orchestrator.py", funcion="notify_opportunity")
        return False
