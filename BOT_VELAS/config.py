# ==============================================================================
# CONFIG.PY - Constantes, API Keys, Estado Inicial y Helpers Base
# ==============================================================================
import os
import time
from dotenv import load_dotenv

# ─── Constantes del Sistema ───────────────────────────────────────────────────
ACTIVOS_ANALIZAR = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

# ─── Estados por Defecto ──────────────────────────────────────────────────────
DEFAULT_STATES = {
    'ganancia_total_realizada': 0.0, 'ganancia_flotante': 0.0, 'comprado': False,
    'precio_compra': 0.0, 'cantidad_comprada': 0.0, 'monto_invertido_operacion': 0.0,
    'max_precio_alcanzado': 0.0, 'break_even_activado': False, 'activo_seleccionado': "BTCUSDT",
    'mejor_puntaje': 0, 'logs_auditoria': ["[AUDIT] Sistema Mutante v2.0 Iniciado..."],
    'bot_activo': False, 'accion_actual': "⏸️ BOT DETENIDO", 'flash_venta': False,
    'saldo_spot_usd': 0.0, 'saldo_usdt_libre': 0.0, 'capital_bot_actual': 0.0,
    'patron_actual': ("NEUTRO", "Esperando análisis..."), 'sesion_mercado': "Cerrada",
    'top_trader_consensus': "Ninguno", 'top_trader_time': 0.0,
    'ultimo_ciclo_ts': 0.0, 'api_keys': {},
    'modo_inversion': 'DEMO',
    # ✅ NUEVO: Estados para simulación DEMO local
    'es_demo': False,
    'demo_usdt_virtual': 0.0,
    'demo_cripto_virtual': 0.0,
}

# ─── Cargar API Keys ──────────────────────────────────────────────────────────
def cargar_api_keys():
    """Carga las API keys del archivo .env y las devuelve como dict"""
    load_dotenv("claves_bot.env")
    return {
        'BINANCE_API_KEY': os.getenv("BINANCE_API_KEY"),
        'BINANCE_API_SECRET': os.getenv("BINANCE_API_SECRET"),
        'GROQ_API_KEY': os.getenv("GROQ_API_KEY"),
        'OPENAI_API_KEY': os.getenv("OPENAI_API_KEY"),
        'DEEPSEEK_API_KEY': os.getenv("DEEPSEEK_API_KEY"),
        'ZAI_API_KEY': os.getenv("ZAI_API_KEY"),
        'ZAI_BASE_URL': os.getenv("ZAI_BASE_URL", "https://api.z-ai.io/v1/chat/completions"),
        'ZAI_MODEL': os.getenv("ZAI_MODEL", "gpt-4o"),
    }

# ─── Inicializar Estado ──────────────────────────────────────────────────────
def init_estado(ss):
    """Inicializa los valores por defecto en session_state si no existen"""
    for key, val in DEFAULT_STATES.items():
        if key not in ss:
            ss[key] = val

# ─── Helper: Agregar Log ─────────────────────────────────────────────────────
def agregar_log(ss, mensaje):
    """Agrega un mensaje con timestamp al log de auditoría (máx 50)"""
    tiempo = time.strftime('%d/%m/%Y %H:%M:%S', time.localtime())
    ss.logs_auditoria.append(f"[{tiempo}] {mensaje}")
    if len(ss.logs_auditoria) > 50:
        ss.logs_auditoria.pop(0)
