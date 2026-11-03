# ==============================================================================
# 🚀 BOT CRIPTO PRO - DASHBOARD UNIFICADO (TRADING + MINERÍA)
# ==============================================================================
import os
import time
import math
import random
import hashlib
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *

# --- CONFIGURACIÓN INICIAL DE STREAMLIT ---
st.set_page_config(page_title="Bot Cripto PRO", page_icon="🚀", layout="wide")

# --- CARGA DE CREDENCIALES Y CONEXIÓN ---
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# Inicializar cliente en cache de Streamlit para no reconectar en cada recarga
@st.cache_resource
def conectar_binance(real: bool):
    if not API_KEY or not API_SECRET:
        return None
    try:
        cliente = Client(API_KEY, API_SECRET, testnet=not real)
        # Sincronizar tiempo
        server_time = cliente.get_server_time()
        local_time = int(time.time() * 1000)
        cliente.timestamp_offset = server_time['serverTime'] - local_time
        return cliente
    except Exception as e:
        st.error(f"Error de conexión Binance: {e}")
        return None

# --- FUNCIONES HELPER PRO ---
def obtener_step_size(cliente, symbol):
    """Obtiene la precisión de decimales permitida para el par (Ej: BTC=0.001, SOL=0.01)"""
    try:
        info = cliente.get_symbol_info(symbol)
        step_size = float(info['filters'][2]['stepSize'])
        # Calcular decimales basados en el step size
        precision = int(round(-math.log(step_size, 10), 0))
        return step_size, precision
    except:
        return 0.001, 3 # Fallback

def formatear_cantidad(cantidad, step_size):
    """Redondea la cantidad al múltiplo correcto requerido por Binance"""
    return math.floor(cantidad / step_size) * step_size

# --- INTERFAZ DE USUARIO ---
st.title("🚀 Bot Cripto PRO Dashboard")
st.markdown("Panel unificado de Trading Automático y Minería.")

# Selector de entorno en la barra lateral
st.sidebar.header("⚙️ Conexión Binance")
entorno_real = st.sidebar.checkbox("⚠️ Usar RED REAL (Desmarcar para Testnet)", value=False)
client = conectar_binance(entorno_real)

if client:
    st.sidebar.success(f"✅ Conectado a Binance ({'RED REAL' if entorno_real else 'TESTNET'})")
else:
    st.sidebar.error("❌ Revisa el archivo claves_bot.env")

# --- PESTAÑAS DEL DASHBOARD ---
tab1, tab2, tab3 = st.tabs([
    "💰 Micro-Ganancias (Scalping)", 
    "📈 Trading Velas + Stop Loss", 
    "⛏️ Estación de Minería PRO"
])

# ==============================================================================
# PESTAÑA 1: BOT MICRO-GANANCIAS (SCALPING)
# ==============================================================================
with tab1:
    st.header("💰 Bot de Micro-Ganancias Automáticas (Scalping)")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        symbol_sc = st.selectbox("Par a operar:", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"], key="sc_sym")
    with col_s2:
        inversion_usdt = st.number_input("Capital inicial a usar (USDT):", min_value=10.0, max_value=1000.0, value=15.0, step=5.0, key="sc_inv")

    if 'ganancia_total' not in st.session_state:
        st.session_state.ganancia_total = 0.0
    if 'comprado' not in st.session_state:
        st.session_state.comprado = False
    if 'precio_compra' not in st.session_state:
        st.session_state.precio_compra = 0.0

    metric_ganancia = st.empty()
    metric_estado = st.empty()
    log_box = st.empty()

    if st.button("🚀 INICIAR MOTOR SCALPING", key="start_sc"):
        if client:
            st.warning("⚠️ Bot en marcha. Actualizando cada 5 segundos...")
            placeholder = st.empty()
            
            # Bucle optimizado con st.empty() (No congela la página)
            while True:
                try:
                    log_texto = f"--- Ciclo: {time.strftime('%H:%M:%S')} ---\n"
                    step_size, precision = obtener_step_size(client, symbol_sc)
                    
                    balance = client.get_asset_balance(asset='USDT')
                    saldo_usdt = float(balance['free']) if balance else 0.0
                    
                    if not st.session_state.comprado and saldo_usdt >= 10:
                        precio_actual = float(client.get_symbol_ticker(symbol=symbol_sc)['price'])
                        cantidad = formatear_cantidad(inversion_usdt / precio_actual, step_size)
                        
                        if cantidad > 0:
                            client.order_market_buy(symbol=symbol_sc, quantity=round(cantidad, precision))
                            st.session_state.comprado = True
                            st.session_state.precio_compra = precio_actual
                            log_texto += f"✅ COMPRADO {cantidad} {symbol_sc} a {precio_actual} USDT.\n"
                    
                    elif st.session_state.comprado:
                        precio_actual = float(client.get_symbol_ticker(symbol=symbol_sc)['price'])
                        porcentaje_subida = ((precio_actual - st.session_state.precio_compra) / st.session_state.precio_compra) * 100
                        log_texto += f"Comprado a: {st.session_state.precio_compra} | Actual: {precio_actual} | Subida: {porcentaje_subida:.3f}%\n"
                        
                        if porcentaje_subida >= 0.4:
                            asset_crypto = symbol_sc.replace('USDT','')
                            balance_crypto = client.get_asset_balance(asset=asset_crypto)
                            if balance_crypto and float(balance_crypto['free']) > 0:
                                cantidad_vender = formatear_cantidad(float(balance_crypto['free']), step_size)
                                client.order_market_sell(symbol=symbol_sc, quantity=round(cantidad_vender, precision))
                                
                                ganancia_neta = (inversion_usdt * 0.004) - (inversion_usdt * 0.002)
                                st.session_state.ganancia_total += ganancia_neta
                                st.session_state.comprado = False
                                st.session_state.precio_compra = 0.0
                                log_texto += f"💰 VENDIDO a {precio_actual} USDT. ¡Ganancia +{ganancia_neta:.4f} USDT!\n"

                    # Actualizar UI
                    estado_str = "🟢 EN EL MERCADO" if st.session_state.comprado else "🔵 EN EFECTIVO"
                    metric_ganancia.metric("💎 Ganancia Total", f"{st.session_state.ganancia_total:.4f} USDT")
                    metric_estado.metric("📊 Estado", estado_str)
                    log_box.code(log_texto)
                    
                except Exception as e:
                    log_box.error(f"Error en ciclo: {e}")
                
                time.sleep(5) # Pausa
        else:
            st.error("Cliente Binance no conectado.")

# ==============================================================================
# PESTAÑA 2: BOT DE VELAS JAPONESAS
# ==============================================================================
with tab2:
    st.header("📈 Bot Trading Automático: Velas + Stop Loss")
    
    symbol_vel = st.selectbox("Par a operar:", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"], key="vel_sym")
    cantidad_usdt_vel = st.number_input("Cantidad a operar (USDT):", min_value=10.0, value=20.0, step=5.0, key="vel_inv")

    @st.cache_data(ttl=60) # Cache de 1 minuto para no saturar la API
    def get_klines(symbol, interval="5m", limit=100):
        public_client = Client()
        klines = public_client.get_klines(symbol=symbol, interval=interval, limit=limit)
        data = pd.DataFrame(klines, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 'CloseTime', 'QuoteVolume', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'])
        data['OpenTime'] = pd.to_datetime(data['OpenTime'], unit='ms')
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            data[col] = data[col].astype(float)
        return data

    def analizar_patrones(df):
        v1 = df.iloc[-3]; v2 = df.iloc[-2]; v3 = df.iloc[-1]
        patron = "Sin patrón claro"; senal = "Mantener / Esperar"; color = "gray"
        cuerpo = abs(v3['Close'] - v3['Open'])
        rango_total = v3['High'] - v3['Low']
        mecha_inf = min(v3['Open'], v3['Close']) - v3['Low']
        mecha_sup = v3['High'] - max(v3['Open'], v3['Close'])
        
        if rango_total > 0 and mecha_inf > (2 * cuerpo) and mecha_sup < cuerpo:
            if (v1['Close'] - v3['Open']) < 0: patron, senal, color = "Martillo (Hammer)", "COMPRA", "green"
            else: patron, senal, color = "Hombre Colgado", "VENTA", "red"
        elif v2['Close'] < v2['Open'] and v3['Close'] > v3['Open'] and v3['Close'] > v2['Open'] and v3['Open'] < v2['Close']:
            patron, senal, color = "Envolvente Alcista", "COMPRA", "green"
        elif v2['Close'] > v2['Open'] and v3['Close'] < v3['Open'] and v3['Close'] < v2['Open'] and v3['Open'] > v2['Close']:
            patron, senal, color = "Envolvente Bajista", "VENTA", "red"
        return patron, senal, color

    if st.button("🔄 Analizar y Operar Velas", key="start_vel"):
        if client:
            with st.spinner('Analizando mercado...'):
                df = get_klines(symbol_vel, interval="5m", limit=100)
                patron, senal, color = analizar_patrones(df)
                precio_actual = df.iloc[-1]['Close']
                
                st.markdown(f"<div style='background-color:{color}; padding:20px; border-radius:10px; text-align:center; color:white; font-size:24px; font-weight:bold;'>{senal}</div>", unsafe_allow_html=True)
                st.write(f"**Patrón detectado:** {patron} | **Precio:** `{precio_actual}` USD")

                if senal in ["COMPRA", "VENTA"]:
                    step_size, precision = obtener_step_size(client, symbol_vel)
                    try:
                        if senal == "COMPRA":
                            cantidad_crypto = formatear_cantidad(cantidad_usdt_vel / precio_actual, step_size)
                            client.order_market_buy(symbol=symbol_vel, quantity=round(cantidad_crypto, precision))
                            st.success(f"✅ COMPRA EJECUTADA: {round(cantidad_crypto, precision)} {symbol_vel}")
                            
                            sl_precio = precio_actual * 0.98
                            client.create_order(symbol=symbol_vel, side=SIDE_SELL, type=ORDER_TYPE_STOP_LOSS_LIMIT, timeInForce=TIME_IN_FORCE_GTC, quantity=round(cantidad_crypto, precision), stopPrice=round(sl_precio, 2), price=round(sl_precio * 0.99, 2))
                            st.info(f"🛡️ Stop Loss colocado en: {sl_precio:.2f} (-2%)")
                        
                        elif senal == "VENTA":
                            asset = symbol_vel.replace('USDT','')
                            bal = client.get_asset_balance(asset=asset)
                            if bal and float(bal['free']) > 0:
                                cantidad_vender = formatear_cantidad(float(bal['free']), step_size)
                                client.order_market_sell(symbol=symbol_vel, quantity=round(cantidad_vender, precision))
                                st.success(f"✅ VENTA EJECUTADA: {round(cantidad_vender, precision)} {symbol_vel}")
                            else:
                                st.warning("⚠️ Señal de venta, pero no tienes saldo.")
                    except Exception as e:
                        st.error(f"Error orden: {e}")

                # Graficar
                fig = go.Figure(data=[go.Candlestick(x=df['OpenTime'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], increasing_line_color='green', decreasing_line_color='red')])
                fig.add_vrect(x0=df.iloc[-3]['OpenTime'], x1=df.iloc[-1]['OpenTime'], fillcolor="yellow", opacity=0.2, layer="below", line_width=0)
                fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("Cliente Binance no conectado.")

# ==============================================================================
# PESTAÑA 3: MINERÍA PRO
# ==============================================================================
with tab3:
    st.header("⛏️ Estación de Minería Cripto PRO")
    
    tab_min1, tab_min2 = st.tabs(["💰 Staking Real (Binance)", "🧮 Simulador PoW (CPU)"])
    
    with tab_min1:
        st.markdown("**Minería real sin hardware:** Pon tus criptos a trabajar en Binance Staking/Savings.")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            asset = st.selectbox("Cripto a Stakear:", ["USDT", "BTC", "ETH", "BNB"], key="stake_sym")
            monto = st.number_input(f"Monto de {asset} a invertir:", min_value=0.0, value=10.0, step=1.0, key="stake_amt")
            
            if st.button("🚀 Iniciar Staking", key="stake_btn"):
                if client and monto > 0:
                    st.success(f"✅ Proceso enviado. En red real, transferiría {monto} {asset} a Flexible Savings.")
                    st.info("Nota: La automatización de Savings requiere IDs de productos específicos de Binance. Esto es una simulación de la interfaz.")
                else:
                    st.error("Revisa conexión o monto.")
        with col_m2:
            st.info("""
            **Tasas de Interés Anuales (APY) Aprox:**
            * USDT: 5% - 10% anual
            * BTC: 0.5% - 2% anual
            * BNB: 1% - 5% anual
            """)

    with tab_min2:
        st.markdown("**Simulador de Proof-of-Work:** Así es como Bitcoin mina bloques de verdad.")
        if 'saldo_minado' not in st.session_state:
            st.session_state.saldo_minado = 0.0
            
        dificultad = st.slider("Dificultad (Nº de Ceros):", min_value=1, max_value=5, value=2)
        st.metric("💎 Saldo Simulado", f"{st.session_state.saldo_minado:.4f} BTC")
        
        if st.button("⛏️ Minar Bloque", key="pow_btn"):
            log_area = st.empty()
            progreso = st.progress(0)
            recompensa = 0.0005
            max_intentos = 100000
            
            for i in range(max_intentos):
                bloque = str(random.random()) + str(time.time())
                hash_r = hashlib.sha256(bloque.encode()).hexdigest()
                
                if hash_r.startswith("0" * dificultad):
                    st.session_state.saldo_minado += recompensa
                    log_area.success(f"🎉 ¡BLOQUE MINADO! Hash: `{hash_r}`\nIntentos: {i+1}\nRecompensa: +{recompensa} BTC")
                    progreso.progress(100)
                    st.balloons()
                    break
                
                if i % 500 == 0:
                    log_area.info(f"⛏️ Minando... Intento #{i}\nHash actual: `{hash_r}`")
                    progreso.progress(int((i / max_intentos) * 100))
                    time.sleep(0.01)
            else:
                log_area.error("❌ No se encontró bloque. Prueba con menos dificultad.")
