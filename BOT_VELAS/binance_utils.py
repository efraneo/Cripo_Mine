# ==============================================================================
# BINANCE_UTILS.PY - Conexión, Saldos, Formato, Top Traders, Simulación DEMO
# ==============================================================================
import time
import math
import requests
from collections import Counter
from binance.client import Client
from binance.exceptions import BinanceAPIException
import streamlit as st

# ─── Conexión a Binance RED REAL (Cacheada) ────────────────────────────────
@st.cache_resource
def conectar_binance_real(api_key, api_secret):
    """Conecta a Binance RED REAL con sincronización de tiempo"""
    try:
        cliente = Client(api_key, api_secret, testnet=False)
        server_time = cliente.get_server_time()
        local_time = int(time.time() * 1000)
        cliente.timestamp_offset = server_time['serverTime'] - local_time
        return cliente, None
    except Exception as e:
        return None, str(e)

def init_connection(ss):
    """Inicializa la conexión: DEMO usa cliente público, REAL usa keys"""
    keys = ss.api_keys
    es_demo = (ss.get('modo_inversion', 'DEMO') == 'DEMO')
    ss['es_demo'] = es_demo

    if es_demo:
        # ✅ MODO DEMO: Cliente público SIN autenticación (solo lee precios)
        try:
            public_client = Client()
            ss['client'] = public_client
            return public_client, None, True
        except Exception as e:
            return None, str(e), True
    else:
        # MODO REAL: Cliente con API keys
        api_key = keys.get('BINANCE_API_KEY')
        api_secret = keys.get('BINANCE_API_SECRET')
        if api_key and api_secret:
            client, error = conectar_binance_real(api_key, api_secret)
            ss['client'] = client
            return client, error, False
        ss['client'] = None
        return None, "Sin API Keys", False

# ─── Formato de Cantidades ────────────────────────────────────────────────────
def obtener_step_size(client, symbol):
    """Obtiene el step size y precision de un símbolo"""
    try:
        info = client.get_symbol_info(symbol)
        for filtro in info['filters']:
            if filtro['filterType'] == 'LOT_SIZE':
                step = float(filtro['stepSize'])
                precision = int(round(-math.log(step, 10), 0))
                return step, precision
    except: pass
    return 0.001, 3

def formatear_cantidad(cantidad, step_size):
    """Ajusta cantidad al step size de Binance"""
    return math.floor(cantidad / step_size) * step_size

# ─── Saldos Spot (REAL vs DEMO) ────────────────────────────────────────────
def actualizar_saldo_spot(ss):
    """Actualiza saldos: real usa API, demo usa saldo virtual"""
    client = ss.get('client')
    if not client: return

    if ss.get('es_demo'):
        # ✅ DEMO: Saldo virtual
        ss.saldo_spot_usd = ss.get('demo_usdt_virtual', 0.0)
        ss.saldo_usdt_libre = ss.get('demo_usdt_virtual', 0.0)
    else:
        # REAL: Consultar API
        try:
            total_usd, usdt_libre = 0.0, 0.0
            account = client.get_account()
            for balance in account['balances']:
                asset, free, locked = balance['asset'], float(balance['free']), float(balance['locked'])
                amount = free + locked
                if amount > 0:
                    if asset == 'USDT':
                        total_usd += amount; usdt_libre = free
                    else:
                        try:
                            precio = float(client.get_symbol_ticker(symbol=f"{asset}USDT")['price'])
                            total_usd += amount * precio
                        except: pass
            ss.saldo_spot_usd = total_usd
            ss.saldo_usdt_libre = usdt_libre
        except Exception as e:
            from config import agregar_log
            agregar_log(ss, f"Error saldo: {e}")

# ─── Liquidación Total (REAL vs DEMO) ───────────────────────────────────────
def liquidar_todo_a_usdt(ss):
    """Vende todo: real usa API, demo simula"""
    from config import agregar_log
    client = ss.get('client')
    if not client: return

    if ss.get('es_demo'):
        # ✅ DEMO: Simular liquidación (devolver cripto virtual a USDT)
        if ss.get('demo_cripto_virtual', 0.0) > 0:
            precio = float(client.get_symbol_ticker(symbol=ss.activo_seleccionado)['price'])
            valor_cripto = ss.demo_cripto_virtual * precio
            ss.demo_usdt_virtual += valor_cripto
            ss.demo_cripto_virtual = 0.0
            agregar_log(ss, f"🔄 [DEMO] Liquidado cripto virtual por ${valor_cripto:.2f}")
        agregar_log(ss, "✅ [DEMO] LIQUIDACIÓN VIRTUAL COMPLETADA.")
    else:
        # REAL: Ejecutar en Binance
        agregar_log(ss, "🔄 LIQUIDANDO ACTIVOS PARA CONSOLIDAR CAPITAL...")
        try:
            account = client.get_account()
            for balance in account['balances']:
                asset, free_amount = balance['asset'], float(balance['free'])
                if asset != 'USDT' and free_amount > 0:
                    par = f"{asset}USDT"
                    try:
                        info = client.get_symbol_info(par)
                        if not info: continue
                        step, prec = obtener_step_size(client, par)
                        cant = formatear_cantidad(free_amount, step)
                        if cant > 0:
                            client.order_market_sell(symbol=par, quantity=round(cant, prec))
                            time.sleep(0.5)
                    except: pass
            actualizar_saldo_spot(ss)
            agregar_log(ss, "✅ LIQUIDACIÓN COMPLETADA.")
        except Exception as e:
            agregar_log(ss, f"❌ Error en liquidación: {e}")

# ─── ✅ NUEVO: Simular Compra DEMO ──────────────────────────────────────────
def simular_compra_demo(ss, symbol, cantidad, precio):
    """Simula una compra en modo DEMO y devuelve dict estilo orden de Binance"""
    from config import agregar_log
    monto = cantidad * precio
    ss.demo_usdt_virtual -= monto
    ss.demo_cripto_virtual = cantidad
    agregar_log(ss, f"✅ [DEMO] COMPRA SIMULADA: {cantidad} {symbol} @ ${precio}")
    agregar_log(ss, f"   [DEMO] USDT virtual restante: ${ss.demo_usdt_virtual:.2f}")
    return {'executedQty': str(cantidad)}

# ─── ✅ NUEVO: Simular Venta DEMO ──────────────────────────────────────────
def simular_venta_demo(ss, symbol, cantidad, precio):
    """Simula una venta en modo DEMO"""
    from config import agregar_log
    monto = cantidad * precio
    ss.demo_usdt_virtual += monto
    ss.demo_cripto_virtual = 0.0
    agregar_log(ss, f"💰 [DEMO] VENTA SIMULADA: {cantidad} {symbol} @ ${precio}")
    agregar_log(ss, f"   [DEMO] USDT virtual actual: ${ss.demo_usdt_virtual:.2f}")
    return monto

# ─── Consensus Top Traders Binance ───────────────────────────────────────────
def obtener_consensus_top_traders(ss):
    """Obtiene el activo más tradeado por top traders (cacheado 15 min)"""
    from config import ACTIVOS_ANALIZAR
    ahora = time.time()
    if ss.top_trader_consensus != "Ninguno" and (ahora - ss.top_trader_time) < 900:
        return ss.top_trader_consensus
    try:
        url = "https://www.binance.com/bapi/fORS/FUTURE/V1/PUBLIC/FUTURE/LEADERBOARD/GETLEADERBOARDRANK"
        payload = {"isTrader": True, "pageType": "1", "periodType": "MONTHLY"}
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=5.0)
        if resp.json().get('data'):
            simbolos = [t.get('symbol', "") for t in resp.json()['data'][:5] if t.get('symbol')]
            if simbolos:
                contador = Counter(simbolos)
                ganador, veces = contador.most_common(1)[0]
                ss.top_trader_consensus = ganador if veces >= 2 else simbolos[0]
                ss.top_trader_time = ahora
                return ss.top_trader_consensus
    except: pass
    if ss.top_trader_consensus == "Ninguno":
        ss.top_trader_consensus = ACTIVOS_ANALIZAR[0]
    return ss.top_trader_consensus
