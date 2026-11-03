# ==============================================================================
# ARCHIVO 1: BOT DE TRADING DE VELAS JAPONESAS
# ==============================================================================
import os 
from dotenv import load_dotenv 
import streamlit as st 
import pandas as pd 
from binance.client import Client 
from binance.enums import * 
import plotly.graph_objects as go 

# Configuración de página
st.set_page_config(page_title="Bot Trading Velas", page_icon="📈", layout="wide")
st.title("📈 Bot Trading Automático: Velas + Stop Loss 2%")

# Cargar API Keys
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = None

if API_KEY and API_SECRET:
    try:
        # testnet=True es dinero ficticio. Cámbialo a False para dinero real.
        client = Client(API_KEY, API_SECRET, testnet=True)
        st.sidebar.success("✅ API Binance Conectada (Testnet)")
    except Exception as e:
        st.sidebar.error(f"Error de conexión: {e}")
else:
    st.sidebar.warning("⚠️ Revisa el archivo claves_bot.env")

# Configuración lateral
st.sidebar.header("⚙️ Configuración del Bot")
symbol = st.sidebar.selectbox("Par a operar:", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
cantidad_usdt = st.sidebar.number_input("Cantidad a operar (en USDT):", min_value=10.0, value=20.0, step=5.0)

# Función para descargar velas
def get_klines(symbol, interval="5m", limit=100):
    public_client = Client()
    klines = public_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    data = pd.DataFrame(klines, columns=[
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 
        'CloseTime', 'QuoteVolume', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'
    ])
    data['OpenTime'] = pd.to_datetime(data['OpenTime'], unit='ms')
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        data[col] = data[col].astype(float)
    return data

# Motor de patrones
def analizar_patrones(df):
    v1 = df.iloc[-3] 
    v2 = df.iloc[-2]
    v3 = df.iloc[-1] 
    patron = "Sin patrón claro"
    senal = "Mantener / Esperar"
    color = "gray"
    
    cuerpo = abs(v3['Close'] - v3['Open'])
    rango_total = v3['High'] - v3['Low']
    mecha_inf = min(v3['Open'], v3['Close']) - v3['Low']
    mecha_sup = v3['High'] - max(v3['Open'], v3['Close'])
    
    if rango_total > 0 and mecha_inf > (2 * cuerpo) and mecha_sup < cuerpo:
        if (v1['Close'] - v3['Open']) < 0: 
            patron = "Martillo (Hammer)"; senal = "COMPRA"; color = "green"
        else: 
            patron = "Hombre Colgado"; senal = "VENTA"; color = "red"
    elif v2['Close'] < v2['Open'] and v3['Close'] > v3['Open'] and v3['Close'] > v2['Open'] and v3['Open'] < v2['Close']:
        patron = "Envolvente Alcista"; senal = "COMPRA"; color = "green"
    elif v2['Close'] > v2['Open'] and v3['Close'] < v3['Open'] and v3['Close'] < v2['Open'] and v3['Open'] > v2['Close']:
        patron = "Envolvente Bajista"; senal = "VENTA"; color = "red"

    return patron, senal, color

# Función de ejecución real
def ejecutar_orden_real(senal, precio_actual):
    try:
        if senal == "COMPRA":
            cantidad_crypto = round(float(cantidad_usdt / precio_actual), 5)
            client.order_market_buy(symbol=symbol, quantity=cantidad_crypto)
            st.success(f"✅ ORDEN DE COMPRA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            
            precio_stop_loss = precio_actual * 0.98
            st.info(f"🛡️ Colocando Stop Loss en: {precio_stop_loss:.2f} (-2%)")
            
            client.create_order(
                symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC, quantity=cantidad_crypto,
                stopPrice=round(precio_stop_loss, 2), price=round(precio_stop_loss * 0.99, 2)
            )
            st.success("🛡️ Stop Loss colocado correctamente en el mercado.")
            
        elif senal == "VENTA":
            balance = client.get_asset_balance(asset=symbol.replace('USDT',''))
            if balance and float(balance['free']) > 0:
                cantidad_crypto = round(float(balance['free']), 5)
                client.order_market_sell(symbol=symbol, quantity=cantidad_crypto)
                st.success(f"✅ ORDEN DE VENTA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            else:
                st.warning("⚠️ Señal de VENTA, pero no tienes saldo del activo para vender en Spot.")
    except Exception as e:
        st.error(f"❌ Error al ejecutar orden real: {e}")

# Interfaz principal
if st.sidebar.button("🔄 Analizar y Operar"):
    df = get_klines(symbol, interval="5m", limit=100)
    if df is not None:
        patron, senal, color = analizar_patrones(df)
        precio_actual = df.iloc[-1]['Close']
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"<div style='background-color:{color}; padding:20px; border-radius:10px; text-align:center; color:white; font-size:24px; font-weight:bold;'>{senal}</div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Patrón detectado:** {patron}")
            st.markdown(f"**Precio de cierre actual:** `{precio_actual}` USD")
        
        if senal in ["COMPRA", "VENTA"]:
            if client is not None:
                st.warning(f"🚀 Ejecutando orden automática ({senal})...")
                ejecutar_orden_real(senal, precio_actual)
            else:
                st.error("❌ No hay conexión con Binance API.")
        else:
            st.info("ℹ️ No hay señal fuerte. El bot no hará nada.")

        st.markdown("---")
        st.markdown(f"### 📊 Gráfico de {symbol} (Tiempo: 5m)")
        fig = go.Figure(data=[go.Candlestick(
            x=df['OpenTime'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            increasing_line_color='green', decreasing_line_color='red'
        )])
        fig.add_vrect(x0=df.iloc[-3]['OpenTime'], x1=df.iloc[-1]['OpenTime'], fillcolor="yellow", opacity=0.2, layer="below", line_width=0)
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)# ==============================================================================
# ARCHIVO 1: BOT DE TRADING DE VELAS JAPONESAS
# ==============================================================================
import os 
from dotenv import load_dotenv 
import streamlit as st 
import pandas as pd 
from binance.client import Client 
from binance.enums import * 
import plotly.graph_objects as go 

# Configuración de página
st.set_page_config(page_title="Bot Trading Velas", page_icon="📈", layout="wide")
st.title("📈 Bot Trading Automático: Velas + Stop Loss 2%")

# Cargar API Keys
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = None

if API_KEY and API_SECRET:
    try:
        # testnet=True es dinero ficticio. Cámbialo a False para dinero real.
        client = Client(API_KEY, API_SECRET, testnet=True)
        st.sidebar.success("✅ API Binance Conectada (Testnet)")
    except Exception as e:
        st.sidebar.error(f"Error de conexión: {e}")
else:
    st.sidebar.warning("⚠️ Revisa el archivo claves_bot.env")

# Configuración lateral
st.sidebar.header("⚙️ Configuración del Bot")
symbol = st.sidebar.selectbox("Par a operar:", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
cantidad_usdt = st.sidebar.number_input("Cantidad a operar (en USDT):", min_value=10.0, value=20.0, step=5.0)

# Función para descargar velas
def get_klines(symbol, interval="5m", limit=100):
    public_client = Client()
    klines = public_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    data = pd.DataFrame(klines, columns=[
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 
        'CloseTime', 'QuoteVolume', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'
    ])
    data['OpenTime'] = pd.to_datetime(data['OpenTime'], unit='ms')
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        data[col] = data[col].astype(float)
    return data

# Motor de patrones
def analizar_patrones(df):
    v1 = df.iloc[-3] 
    v2 = df.iloc[-2]
    v3 = df.iloc[-1] 
    patron = "Sin patrón claro"
    senal = "Mantener / Esperar"
    color = "gray"
    
    cuerpo = abs(v3['Close'] - v3['Open'])
    rango_total = v3['High'] - v3['Low']
    mecha_inf = min(v3['Open'], v3['Close']) - v3['Low']
    mecha_sup = v3['High'] - max(v3['Open'], v3['Close'])
    
    if rango_total > 0 and mecha_inf > (2 * cuerpo) and mecha_sup < cuerpo:
        if (v1['Close'] - v3['Open']) < 0: 
            patron = "Martillo (Hammer)"; senal = "COMPRA"; color = "green"
        else: 
            patron = "Hombre Colgado"; senal = "VENTA"; color = "red"
    elif v2['Close'] < v2['Open'] and v3['Close'] > v3['Open'] and v3['Close'] > v2['Open'] and v3['Open'] < v2['Close']:
        patron = "Envolvente Alcista"; senal = "COMPRA"; color = "green"
    elif v2['Close'] > v2['Open'] and v3['Close'] < v3['Open'] and v3['Close'] < v2['Open'] and v3['Open'] > v2['Close']:
        patron = "Envolvente Bajista"; senal = "VENTA"; color = "red"

    return patron, senal, color

# Función de ejecución real
def ejecutar_orden_real(senal, precio_actual):
    try:
        if senal == "COMPRA":
            cantidad_crypto = round(float(cantidad_usdt / precio_actual), 5)
            client.order_market_buy(symbol=symbol, quantity=cantidad_crypto)
            st.success(f"✅ ORDEN DE COMPRA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            
            precio_stop_loss = precio_actual * 0.98
            st.info(f"🛡️ Colocando Stop Loss en: {precio_stop_loss:.2f} (-2%)")
            
            client.create_order(
                symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC, quantity=cantidad_crypto,
                stopPrice=round(precio_stop_loss, 2), price=round(precio_stop_loss * 0.99, 2)
            )
            st.success("🛡️ Stop Loss colocado correctamente en el mercado.")
            
        elif senal == "VENTA":
            balance = client.get_asset_balance(asset=symbol.replace('USDT',''))
            if balance and float(balance['free']) > 0:
                cantidad_crypto = round(float(balance['free']), 5)
                client.order_market_sell(symbol=symbol, quantity=cantidad_crypto)
                st.success(f"✅ ORDEN DE VENTA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            else:
                st.warning("⚠️ Señal de VENTA, pero no tienes saldo del activo para vender en Spot.")
    except Exception as e:
        st.error(f"❌ Error al ejecutar orden real: {e}")

# Interfaz principal
if st.sidebar.button("🔄 Analizar y Operar"):
    df = get_klines(symbol, interval="5m", limit=100)
    if df is not None:
        patron, senal, color = analizar_patrones(df)
        precio_actual = df.iloc[-1]['Close']
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"<div style='background-color:{color}; padding:20px; border-radius:10px; text-align:center; color:white; font-size:24px; font-weight:bold;'>{senal}</div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Patrón detectado:** {patron}")
            st.markdown(f"**Precio de cierre actual:** `{precio_actual}` USD")
        
        if senal in ["COMPRA", "VENTA"]:
            if client is not None:
                st.warning(f"🚀 Ejecutando orden automática ({senal})...")
                ejecutar_orden_real(senal, precio_actual)
            else:
                st.error("❌ No hay conexión con Binance API.")
        else:
            st.info("ℹ️ No hay señal fuerte. El bot no hará nada.")

        st.markdown("---")
        st.markdown(f"### 📊 Gráfico de {symbol} (Tiempo: 5m)")
        fig = go.Figure(data=[go.Candlestick(
            x=df['OpenTime'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            increasing_line_color='green', decreasing_line_color='red'
        )])
        fig.add_vrect(x0=df.iloc[-3]['OpenTime'], x1=df.iloc[-1]['OpenTime'], fillcolor="yellow", opacity=0.2, layer="below", line_width=0)
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)# ==============================================================================
# ARCHIVO 1: BOT DE TRADING DE VELAS JAPONESAS
# ==============================================================================
import os 
from dotenv import load_dotenv 
import streamlit as st 
import pandas as pd 
from binance.client import Client 
from binance.enums import * 
import plotly.graph_objects as go 

# Configuración de página
st.set_page_config(page_title="Bot Trading Velas", page_icon="📈", layout="wide")
st.title("📈 Bot Trading Automático: Velas + Stop Loss 2%")

# Cargar API Keys
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = None

if API_KEY and API_SECRET:
    try:
        # testnet=True es dinero ficticio. Cámbialo a False para dinero real.
        client = Client(API_KEY, API_SECRET, testnet=True)
        st.sidebar.success("✅ API Binance Conectada (Testnet)")
    except Exception as e:
        st.sidebar.error(f"Error de conexión: {e}")
else:
    st.sidebar.warning("⚠️ Revisa el archivo claves_bot.env")

# Configuración lateral
st.sidebar.header("⚙️ Configuración del Bot")
symbol = st.sidebar.selectbox("Par a operar:", ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"])
cantidad_usdt = st.sidebar.number_input("Cantidad a operar (en USDT):", min_value=10.0, value=20.0, step=5.0)

# Función para descargar velas
def get_klines(symbol, interval="5m", limit=100):
    public_client = Client()
    klines = public_client.get_klines(symbol=symbol, interval=interval, limit=limit)
    data = pd.DataFrame(klines, columns=[
        'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume', 
        'CloseTime', 'QuoteVolume', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'
    ])
    data['OpenTime'] = pd.to_datetime(data['OpenTime'], unit='ms')
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        data[col] = data[col].astype(float)
    return data

# Motor de patrones
def analizar_patrones(df):
    v1 = df.iloc[-3] 
    v2 = df.iloc[-2]
    v3 = df.iloc[-1] 
    patron = "Sin patrón claro"
    senal = "Mantener / Esperar"
    color = "gray"
    
    cuerpo = abs(v3['Close'] - v3['Open'])
    rango_total = v3['High'] - v3['Low']
    mecha_inf = min(v3['Open'], v3['Close']) - v3['Low']
    mecha_sup = v3['High'] - max(v3['Open'], v3['Close'])
    
    if rango_total > 0 and mecha_inf > (2 * cuerpo) and mecha_sup < cuerpo:
        if (v1['Close'] - v3['Open']) < 0: 
            patron = "Martillo (Hammer)"; senal = "COMPRA"; color = "green"
        else: 
            patron = "Hombre Colgado"; senal = "VENTA"; color = "red"
    elif v2['Close'] < v2['Open'] and v3['Close'] > v3['Open'] and v3['Close'] > v2['Open'] and v3['Open'] < v2['Close']:
        patron = "Envolvente Alcista"; senal = "COMPRA"; color = "green"
    elif v2['Close'] > v2['Open'] and v3['Close'] < v3['Open'] and v3['Close'] < v2['Open'] and v3['Open'] > v2['Close']:
        patron = "Envolvente Bajista"; senal = "VENTA"; color = "red"

    return patron, senal, color

# Función de ejecución real
def ejecutar_orden_real(senal, precio_actual):
    try:
        if senal == "COMPRA":
            cantidad_crypto = round(float(cantidad_usdt / precio_actual), 5)
            client.order_market_buy(symbol=symbol, quantity=cantidad_crypto)
            st.success(f"✅ ORDEN DE COMPRA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            
            precio_stop_loss = precio_actual * 0.98
            st.info(f"🛡️ Colocando Stop Loss en: {precio_stop_loss:.2f} (-2%)")
            
            client.create_order(
                symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=TIME_IN_FORCE_GTC, quantity=cantidad_crypto,
                stopPrice=round(precio_stop_loss, 2), price=round(precio_stop_loss * 0.99, 2)
            )
            st.success("🛡️ Stop Loss colocado correctamente en el mercado.")
            
        elif senal == "VENTA":
            balance = client.get_asset_balance(asset=symbol.replace('USDT',''))
            if balance and float(balance['free']) > 0:
                cantidad_crypto = round(float(balance['free']), 5)
                client.order_market_sell(symbol=symbol, quantity=cantidad_crypto)
                st.success(f"✅ ORDEN DE VENTA EJECUTADA: {cantidad_crypto} {symbol.replace('USDT','')}")
            else:
                st.warning("⚠️ Señal de VENTA, pero no tienes saldo del activo para vender en Spot.")
    except Exception as e:
        st.error(f"❌ Error al ejecutar orden real: {e}")

# Interfaz principal
if st.sidebar.button("🔄 Analizar y Operar"):
    df = get_klines(symbol, interval="5m", limit=100)
    if df is not None:
        patron, senal, color = analizar_patrones(df)
        precio_actual = df.iloc[-1]['Close']
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"<div style='background-color:{color}; padding:20px; border-radius:10px; text-align:center; color:white; font-size:24px; font-weight:bold;'>{senal}</div>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Patrón detectado:** {patron}")
            st.markdown(f"**Precio de cierre actual:** `{precio_actual}` USD")
        
        if senal in ["COMPRA", "VENTA"]:
            if client is not None:
                st.warning(f"🚀 Ejecutando orden automática ({senal})...")
                ejecutar_orden_real(senal, precio_actual)
            else:
                st.error("❌ No hay conexión con Binance API.")
        else:
            st.info("ℹ️ No hay señal fuerte. El bot no hará nada.")

        st.markdown("---")
        st.markdown(f"### 📊 Gráfico de {symbol} (Tiempo: 5m)")
        fig = go.Figure(data=[go.Candlestick(
            x=df['OpenTime'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            increasing_line_color='green', decreasing_line_color='red'
        )])
        fig.add_vrect(x0=df.iloc[-3]['OpenTime'], x1=df.iloc[-1]['OpenTime'], fillcolor="yellow", opacity=0.2, layer="below", line_width=0)
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)
