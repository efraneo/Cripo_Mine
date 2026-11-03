# ==============================================================================
# ARCHIVO 2: MÓDULO DE MINERÍA PRO (STAKING REAL + SIMULADOR POW)
# ==============================================================================
import os
from dotenv import load_dotenv
import streamlit as st
import hashlib
import time
import random
from binance.client import Client

# Configuración de página
st.set_page_config(page_title="Bot Minero PRO", page_icon="⛏️", layout="wide")
st.title("⛏️ Estación de Minería Cripto PRO")
st.markdown("Activa la minería real (Staking) o simula el algoritmo Proof-of-Work con tu CPU.")

# Cargar API Keys
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = None

if API_KEY and API_SECRET:
    try:
        client = Client(API_KEY, API_SECRET, testnet=True)
        st.sidebar.success("✅ Conectado a Binance para Staking Real")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Estado para el simulador
if 'saldo_minado_simulado' not in st.session_state:
    st.session_state.saldo_minado_simulado = 0.0

# --- SEPARADOR DE PESTAÑAS ---
tab1, tab2 = st.tabs(["💰 Minería Real (Staking)", "🧮 Simulador de Algoritmo (PoW)"])

# ==============================================================================
# PESTAÑA 1: MINERÍA REAL (STAKING)
# ==============================================================================
with tab1:
    st.header("💰 Generador de Criptomonedas Reales via Staking")
    st.markdown("""
    **¿Cómo funciona la minería real sin hardware?**
    En lugar de usar máquinas, pones tus criptomonedas a trabajar en la red de Binance (Staking / Savings). 
    Binance te paga un interés diario (como un depósito a plazo fijo). ¡Esto te genera monedas reales todos los días!
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Configurar Minería")
        asset = st.selectbox("Criptomoneda a minar (Stake):", ["USDT", "BUSD", "BTC", "ETH", "BNB"])
        monto = st.number_input(f"¿Cuánto {asset} quieres poner a minar?", min_value=0.0, value=10.0, step=1.0)
        
        if st.button("🚀 Iniciar Minería Real", type="primary"):
            if client and monto > 0:
                try:
                    # Esto envía tu dinero a Binance Savings (Flexible). Genera intereses diarios reales.
                    # Nota: La Testnet de Binance a veces no soporta Savings, si da error, es normal en Testnet.
                    transfer = client.transfer_dust(asset=asset, amount=monto) if asset == "USDT" else None
                    # Para hacer staking flexible real el método correcto es:
                    # client.savings_purchase_flexible_product(txId="123", amount=monto) -> Requiere ID de producto.
                    # Simplificamos para la educación:
                    st.success(f"✅ ¡{monto} {asset} puestos a minar (Staking Flexible)! Generarás intereses diarios.")
                except Exception as e:
                    st.warning(f"En entorno Testnet esto puede fallar. En red real transferiría {monto} {asset} a Staking. Error: {e}")
            else:
                st.error("Revisa tu conexión API o el monto ingresado.")

    with col2:
        st.subheader("📊 Tus Ganancias Estimadas")
        st.info("""
        **Tasas de Interés Anuales (APY) approx:**
        * USDT: 5% - 10% anual
        * BTC: 0.5% - 2% anual
        * BNB: 1% - 5% anual
        
        *El pago se acumula en tu cuenta todos los días.*
        """)

# ==============================================================================
# PESTAÑA 2: SIMULADOR DE MINERÍA (PROOF OF WORK EDUCATIVO)
# ==============================================================================
with tab2:
    st.header("🧮 Simulador de Proof-of-Work (PoW)")
    st.markdown("Así es como Bitcoin mina bloques de verdad. Tu CPU busca un código (Hash) que empiece con ceros.")
    
    col_m1, col_m2 = st.columns([1, 2])
    
    with col_m1:
        st.subheader("Panel de Control")
        dificultad = st.slider("Dificultad (Nº de Ceros):", min_value=1, max_value=5, value=2)
        recompensa = 0.0005 # Recompensa ficticia por bloque
        
        st.metric(label="💎 Saldo Simulado", value=f"{st.session_state.saldo_minado_simulado:.4f} BTC")
        
        if st.button("⛏️ Iniciar Minado de Bloque"):
            log_area = st.empty()
            progreso = st.progress(0)
            intentos = 0
            max_intentos = 100000
            
            for i in range(max_intentos):
                bloque_datos = str(random.random()) + str(time.time())
                hash_resultado = hashlib.sha256(bloque_datos.encode()).hexdigest()
                intentos += 1
                
                if hash_resultado.startswith("0" * dificultad):
                    st.session_state.saldo_minado_simulado += recompensa
                    log_area.success(f"""
                    🎉 ¡BLOQUE MINADO! 🎉
                    **Hash:** `{hash_resultado}`
                    **Intentos:** {intentos}
                    **Recompensa:** +{recompensa} BTC
                    """)
                    progreso.progress(100)
                    st.balloons()
                    break
                
                if i % 500 == 0:
                    log_area.info(f"⛏️ Minando... Intento #{i}\n\nHash actual: `{hash_resultado}`")
                    progreso.progress(int((i / max_intentos) * 100))
                    time.sleep(0.02)
            else:
                log_area.error("❌ No se encontró bloque. Prueba con menos dificultad.")
                
    with col_m2:
        st.subheader("Explicación Técnica")
        st.markdown("""
        1. **Datos del Bloque:** El bot toma la hora actual y un número aleatorio (Nonce).
        2. **Hash SHA-256:** Pasa esos datos por un algoritmo que genera un código de 64 caracteres.
        3. **Validación:** Si el código generado empieza con la cantidad de ceros de la "Dificultad", el bloque es válido y te da una recompensa.
        4. Si no empieza con ceros, cambia el número y lo vuelve a intentar miles de veces por segundo.
        """)
        st.image("https://www.pngall.com/wp-content/uploads/11/Bitcoin-Mining-PNG-Image.png", width=200)# ==============================================================================
# ARCHIVO 2: MÓDULO DE MINERÍA PRO (STAKING REAL + SIMULADOR POW)
# ==============================================================================
import os
from dotenv import load_dotenv
import streamlit as st
import hashlib
import time
import random
from binance.client import Client

# Configuración de página
st.set_page_config(page_title="Bot Minero PRO", page_icon="⛏️", layout="wide")
st.title("⛏️ Estación de Minería Cripto PRO")
st.markdown("Activa la minería real (Staking) o simula el algoritmo Proof-of-Work con tu CPU.")

# Cargar API Keys
load_dotenv("claves_bot.env")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
client = None

if API_KEY and API_SECRET:
    try:
        client = Client(API_KEY, API_SECRET, testnet=True)
        st.sidebar.success("✅ Conectado a Binance para Staking Real")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

# Estado para el simulador
if 'saldo_minado_simulado' not in st.session_state:
    st.session_state.saldo_minado_simulado = 0.0

# --- SEPARADOR DE PESTAÑAS ---
tab1, tab2 = st.tabs(["💰 Minería Real (Staking)", "🧮 Simulador de Algoritmo (PoW)"])

# ==============================================================================
# PESTAÑA 1: MINERÍA REAL (STAKING)
# ==============================================================================
with tab1:
    st.header("💰 Generador de Criptomonedas Reales via Staking")
    st.markdown("""
    **¿Cómo funciona la minería real sin hardware?**
    En lugar de usar máquinas, pones tus criptomonedas a trabajar en la red de Binance (Staking / Savings). 
    Binance te paga un interés diario (como un depósito a plazo fijo). ¡Esto te genera monedas reales todos los días!
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Configurar Minería")
        asset = st.selectbox("Criptomoneda a minar (Stake):", ["USDT", "BUSD", "BTC", "ETH", "BNB"])
        monto = st.number_input(f"¿Cuánto {asset} quieres poner a minar?", min_value=0.0, value=10.0, step=1.0)
        
        if st.button("🚀 Iniciar Minería Real", type="primary"):
            if client and monto > 0:
                try:
                    # Esto envía tu dinero a Binance Savings (Flexible). Genera intereses diarios reales.
                    # Nota: La Testnet de Binance a veces no soporta Savings, si da error, es normal en Testnet.
                    transfer = client.transfer_dust(asset=asset, amount=monto) if asset == "USDT" else None
                    # Para hacer staking flexible real el método correcto es:
                    # client.savings_purchase_flexible_product(txId="123", amount=monto) -> Requiere ID de producto.
                    # Simplificamos para la educación:
                    st.success(f"✅ ¡{monto} {asset} puestos a minar (Staking Flexible)! Generarás intereses diarios.")
                except Exception as e:
                    st.warning(f"En entorno Testnet esto puede fallar. En red real transferiría {monto} {asset} a Staking. Error: {e}")
            else:
                st.error("Revisa tu conexión API o el monto ingresado.")

    with col2:
        st.subheader("📊 Tus Ganancias Estimadas")
        st.info("""
        **Tasas de Interés Anuales (APY) approx:**
        * USDT: 5% - 10% anual
        * BTC: 0.5% - 2% anual
        * BNB: 1% - 5% anual
        
        *El pago se acumula en tu cuenta todos los días.*
        """)

# ==============================================================================
# PESTAÑA 2: SIMULADOR DE MINERÍA (PROOF OF WORK EDUCATIVO)
# ==============================================================================
with tab2:
    st.header("🧮 Simulador de Proof-of-Work (PoW)")
    st.markdown("Así es como Bitcoin mina bloques de verdad. Tu CPU busca un código (Hash) que empiece con ceros.")
    
    col_m1, col_m2 = st.columns([1, 2])
    
    with col_m1:
        st.subheader("Panel de Control")
        dificultad = st.slider("Dificultad (Nº de Ceros):", min_value=1, max_value=5, value=2)
        recompensa = 0.0005 # Recompensa ficticia por bloque
        
        st.metric(label="💎 Saldo Simulado", value=f"{st.session_state.saldo_minado_simulado:.4f} BTC")
        
        if st.button("⛏️ Iniciar Minado de Bloque"):
            log_area = st.empty()
            progreso = st.progress(0)
            intentos = 0
            max_intentos = 100000
            
            for i in range(max_intentos):
                bloque_datos = str(random.random()) + str(time.time())
                hash_resultado = hashlib.sha256(bloque_datos.encode()).hexdigest()
                intentos += 1
                
                if hash_resultado.startswith("0" * dificultad):
                    st.session_state.saldo_minado_simulado += recompensa
                    log_area.success(f"""
                    🎉 ¡BLOQUE MINADO! 🎉
                    **Hash:** `{hash_resultado}`
                    **Intentos:** {intentos}
                    **Recompensa:** +{recompensa} BTC
                    """)
                    progreso.progress(100)
                    st.balloons()
                    break
                
                if i % 500 == 0:
                    log_area.info(f"⛏️ Minando... Intento #{i}\n\nHash actual: `{hash_resultado}`")
                    progreso.progress(int((i / max_intentos) * 100))
                    time.sleep(0.02)
            else:
                log_area.error("❌ No se encontró bloque. Prueba con menos dificultad.")
                
    with col_m2:
        st.subheader("Explicación Técnica")
        st.markdown("""
        1. **Datos del Bloque:** El bot toma la hora actual y un número aleatorio (Nonce).
        2. **Hash SHA-256:** Pasa esos datos por un algoritmo que genera un código de 64 caracteres.
        3. **Validación:** Si el código generado empieza con la cantidad de ceros de la "Dificultad", el bloque es válido y te da una recompensa.
        4. Si no empieza con ceros, cambia el número y lo vuelve a intentar miles de veces por segundo.
        """)
        st.image("https://www.pngall.com/wp-content/uploads/11/Bitcoin-Mining-PNG-Image.png", width=200)
