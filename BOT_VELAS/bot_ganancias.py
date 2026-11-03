# ==============================================================================
# BOT_GANANCIAS.PY - ORCHESTRATOR PRINCIPAL
# ==============================================================================
import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ─── Imports de Módulos ──────────────────────────────────────────────────────
from config import cargar_api_keys, init_estado, agregar_log
from binance_utils import init_connection, liquidar_todo_a_usdt, actualizar_saldo_spot
from motor_trading import ejecutar_si_corresponde
from ui_componentes import (
    render_metricas, render_banner_mercado, render_banner_accion,
    render_botones, render_grafico, render_logs, render_tab_staking
)

# ─── Configuración de Página ─────────────────────────────────────────────────
st.set_page_config(page_title="Trade Bot de Efra", page_icon="🧠", layout="wide")
st.title("🧠 Mega Bot Mutante (Consejo 4 Dioses IA + Ballenas + Consenso)")
st.markdown("Análisis por OpenAI + Groq + DeepSeek + **Z.ai**. Solo dispara si hay consenso unánime de las 4.")

# ─── Inicialización ──────────────────────────────────────────────────────────
ss = st.session_state
ss.api_keys = cargar_api_keys()
init_estado(ss)

# ─── Selector de Modo de Inversión ──────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.header("🔐 Modo de Inversión")

modo_actual = ss.get('modo_inversion', 'DEMO')
modo_disabled = ss.get('bot_activo', False)

if modo_disabled:
    color_modo = "🟢" if modo_actual == "REAL" else "🟡"
    st.sidebar.info(f"{color_modo} Modo: **{modo_actual}** (Detén el bot para cambiar)")
else:
    modo_seleccionado = st.sidebar.radio(
        "Selecciona antes de iniciar:",
        options=["DEMO", "REAL"],
        index=0 if modo_actual == "DEMO" else 1,
        horizontal=True,
        help="DEMO = Simulación local (dinero ficticio)\nREAL = Red real (dinero real)"
    )
    ss.modo_inversion = modo_seleccionado
    
    if modo_seleccionado == "REAL":
        st.sidebar.error("⚠️ ESTÁS EN RED REAL. Tu dinero está en riesgo.")
    else:
        st.sidebar.success("🟡 Modo DEMO activo. Simulación local sin riesgo.")

st.sidebar.markdown("---")

# ─── Conexión a Binance ─────────────────────────────────────────────────────
client, error, es_demo = init_connection(ss)

if client:
    if es_demo:
        st.sidebar.success("✅ Modo DEMO: Leyendo precios públicos (sin API keys)")
    else:
        st.sidebar.success("✅ Conectado a Binance RED REAL")
elif error and error != "Sin API Keys":
    st.sidebar.error(f"Error: {error}")
else:
    st.sidebar.warning("⚠️ Revisa el archivo claves_bot.env")

# ─── Sidebar: Configuración de Capital ───────────────────────────────────────
st.sidebar.header("💰 Gestión de Capital")
capital_inicial = st.sidebar.number_input("Capital Aislado (USDT):", min_value=10.0, max_value=10000.0, value=10.0, step=5.0)
reinvertir = st.sidebar.checkbox("🔄 Reinvertir Ganancias (Auto-Compound)", value=True)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Configuración Trading")
tp_pct = st.sidebar.slider("🎯 Take Profit (%)", min_value=0.1, max_value=5.0, value=0.5, step=0.1)
sl_pct = st.sidebar.slider("🛡️ Stop Loss (%)", min_value=-5.0, max_value=-0.1, value=-0.5, step=0.1)
intervalo_seg = st.sidebar.slider("⏱️ Intervalo ciclos (seg)", min_value=5, max_value=60, value=10, step=5)

# ─── Callbacks de Botones ────────────────────────────────────────────────────
def on_iniciar():
    if not ss.get('client'):
        st.error("Sin conexión a Binance")
        return

    modo = ss.get('modo_inversion', 'DEMO')
    agregar_log(ss, f"🚀 INICIANDO BOT EN MODO {modo}...")

    # ✅ Si es DEMO, inicializar saldo virtual
    if modo == 'DEMO':
        ss.demo_usdt_virtual = capital_inicial
        ss.demo_cripto_virtual = 0.0
        agregar_log(ss, f"💰 [DEMO] Saldo virtual inicializado: ${capital_inicial:.2f}")

    liquidar_todo_a_usdt(ss)
    time.sleep(1)
    actualizar_saldo_spot(ss)

    if ss.saldo_usdt_libre < capital_inicial:
        st.error(f"Fondos insuficientes. Tienes ${ss.saldo_usdt_libre:.2f}")
    else:
        ss.bot_activo = True
        ss.capital_bot_actual = capital_inicial
        ss.ultimo_ciclo_ts = 0

def on_detener():
    ss.bot_activo = False
    ss.accion_actual = "⏸️ BOT DETENIDO"
    agregar_log(ss, f"🛑 BOT DETENIDO (Modo: {ss.get('modo_inversion', 'DEMO')})")

# ─── Ejecutar Ciclo del Bot (ANTES de la UI) ────────────────────────────────
if ss.get('bot_activo', False) and ss.get('client'):
    ejecutar_si_corresponde(ss, intervalo_seg, tp_pct, sl_pct, capital_inicial, reinvertir)

# ─── Auto-refresh ────────────────────────────────────────────────────────────
if ss.get('bot_activo', False) and ss.get('client'):
    st_autorefresh(
        interval=intervalo_seg * 1000,
        limit=None,
        key="bot_auto_refresh"
    )

# ─── Banner de Modo ──────────────────────────────────────────────────────────
modo = ss.get('modo_inversion', 'DEMO')
if modo == "REAL":
    st.markdown("""
        <div style='background:#8B0000;padding:8px;border-radius:8px;text-align:center;
                    color:#FFF;border:2px solid #FF0000;margin-bottom:10px;'>
            🔴 MODO REAL — DINERO REAL EN JUEGO — Operando en Binance RED REAL
        </div>""", unsafe_allow_html=True)
else:
    st.markdown("""
        <div style='background:#1A5276;padding:8px;border-radius:8px;text-align:center;
                    color:#FFF;border:2px solid #F1C40F;margin-bottom:10px;'>
            🟡 MODO DEMO — SIMULACIÓN LOCAL — Lee precios reales pero no ejecuta operaciones
        </div>""", unsafe_allow_html=True)

# ─── Interfaz Principal: Tabs ───────────────────────────────────────────────
tab1, tab2 = st.tabs(["🤖 Trading Activo Mutante", "💎 Ingresos Pasivos"])

with tab1:
    render_metricas(ss)
    render_banner_mercado(ss)
    render_banner_accion(ss)
    st.markdown("---")
    render_botones(ss, capital_inicial, on_iniciar, on_detener)

    col_chart, col_logs = st.columns([2, 1])
    with col_chart:
        render_grafico(ss, tp_pct, sl_pct)
    with col_logs:
        render_logs(ss)

with tab2:
    render_tab_staking(ss)
