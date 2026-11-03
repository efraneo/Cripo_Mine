# ==============================================================================
# UI_COMPONENTES.PY - Banners, Métricas, Gráficos, Logs, Tab Staking
# ==============================================================================
import time
import requests
import pandas as pd
import streamlit as st
from binance.client import Client
import plotly.graph_objects as go

# ─── Métricas Principales ────────────────────────────────────────────────────
def render_metricas(ss):
    """Renderiza las 4 métricas principales del bot"""
    client = ss.get('client')
    valor = 0.0
    if ss.comprado and client:
        try: valor = ss.cantidad_comprada * float(client.get_symbol_ticker(symbol=ss.activo_seleccionado)['price'])
        except: valor = ss.capital_bot_actual
    else: valor = ss.capital_bot_actual

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric(label="💼 Saldo TOTAL Binance", value=f"${ss.saldo_spot_usd:.2f}")
    with col2: st.metric(label="🤖 Valor Bot (Vivo)", value=f"${valor:.2f} USDT")
    with col3: st.metric(label="📈 P&L Flotante", value=f"{ss.ganancia_flotante:+.4f} USDT")
    with col4: st.metric(label="💎 P&L Realizado", value=f"{ss.ganancia_total_realizada:+.4f} USDT")

# ─── Banner Secundario (Estado del Mercado) ──────────────────────────────────
def render_banner_mercado(ss):
    """Renderiza el banner con info de sesión, activo, puntaje"""
    # ✅ FIX: Quitado el countdown que causaba render innecesario
    st.markdown(f"""
        <div style='background:#1E1E1E;padding:12px;border-radius:8px;text-align:center;
                    color:#AAA;margin:10px 0;border:1px solid #333;'>
            Sesión: <b style='color:#FFF'>{ss.sesion_mercado}</b> |
            Activo: <b style='color:#0FA'>{ss.activo_seleccionado}</b> |
            Mejor Puntaje: <b style='color:#FFD700'>{ss.mejor_puntaje} pts</b> |
            Consenso Top: <b style='color:#F0F'>{ss.top_trader_consensus}</b>
        </div>""", unsafe_allow_html=True)

# ─── Banner Principal (Acción del Bot) ───────────────────────────────────────
def render_banner_accion(ss):
    """Renderiza el banner gigante con la acción actual del bot"""
    accion = ss.accion_actual
    colores = {
        "Escaneo": "#007BFF", "DISPARO": "#17A2B8", "EN ": "#28A745",
        "VENTA": "#FFD700", "VENDIENDO": "#FFD700", "COMPRADO": "#28A745",
        "ERROR": "#DC3545", "FONDOS": "#FF6600"
    }
    color = "#808080"
    for key, col in colores.items():
        if key in accion: color = col; break

    st.markdown(f"""
        <div style="background:{color};padding:25px;border-radius:15px;text-align:center;
                    margin:20px 0;box-shadow:0px 4px 15px rgba(0,0,0,0.4);">
            <h2 style="color:white;margin:0;font-weight:bold;text-transform:uppercase;
                       letter-spacing:1px;">{accion}</h2>
        </div>""", unsafe_allow_html=True)

    if ss.flash_venta:
        st.balloons()
        ss.flash_venta = False

# ─── Botones de Control ──────────────────────────────────────────────────────
def render_botones(ss, capital_ini, on_iniciar, on_detener):
    """Renderiza los botones de Iniciar/Detener"""
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🧠 INICIAR BOT (CONSOLIDAR)", type="primary", disabled=ss.bot_activo):
            on_iniciar()
    with col2:
        if st.button("🛑 DETENER BOT", disabled=not ss.bot_activo):
            on_detener()

# ─── Gráfico de Velas Pro ────────────────────────────────────────────────────
# ─── Reemplaza la función render_grafico en ui_componentes.py ───────────────
def render_grafico(ss, tp_pct, sl_pct):
    """Renderiza gráfico + Muestra las velas japonesas detectadas"""
    señal, nombre = ss.patron_actual
    
    # ✅ NUEVO: Mostrar velas japonesas si hay datos
    # Esto usa el último análisis del estado si existe
    patron_str = f"🕵️ **Análisis:** {nombre}"
    if señal == "COMPRA": st.success(patron_str)
    elif señal == "VENTA": st.error(patron_str)
    else: st.info(patron_str)

    st.subheader(f"📊 Velas + Volumen + EMA — {ss.activo_seleccionado}")
    try:
        pub = Client()
        klines = pub.get_klines(symbol=ss.activo_seleccionado, interval="1m", limit=50)
        df = pd.DataFrame(klines, columns=['Time','Open','High','Low','Close','Volume','CT','QAV','Trades','TBB','TBQ','I'])
        df['Time'] = pd.to_datetime(df['Time'], unit='ms', utc=True).dt.tz_convert('America/Bogota')
        for c in ['Open','High','Low','Close','Volume']: df[c] = df[c].astype(float)
        df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

        # ✅ NUEVO: Detectar patrones en tiempo real para mostrarlos debajo del gráfico
        from analisis_tecnico import detectar_16_patrones
        patrones_actuales = detectar_16_patrones(df)
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['Time'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Velas', increasing_line_color='#00FF00', decreasing_line_color='#FF0000'))
        fig.add_trace(go.Scatter(x=df['Time'], y=df['EMA_9'], mode='lines', name='EMA 9', line=dict(color='#FFD700', width=1.5)))
        fig.add_trace(go.Scatter(x=df['Time'], y=df['EMA_21'], mode='lines', name='EMA 21', line=dict(color='#00FFFF', width=1.5)))
        colores_vol = ['#00FF00' if r['Close'] >= r['Open'] else '#FF0000' for _, r in df.iterrows()]
        fig.add_trace(go.Bar(x=df['Time'], y=df['Volume'], name='Vol', marker_color=colores_vol, opacity=0.4, yaxis='y2'))

        if ss.comprado:
            pc = ss.precio_compra
            fig.add_hline(y=pc, line_dash="dash", line_color="yellow", annotation_text="BE")
            fig.add_hline(y=pc*(1+tp_pct/100), line_dash="dot", line_color="green", annotation_text="TP")
            fig.add_hline(y=pc*(1+sl_pct/100), line_dash="dot", line_color="red", annotation_text="SL")

        fig.update_layout(template="plotly_dark", height=550, xaxis_rangeslider_visible=False, yaxis=dict(side='left'), yaxis2=dict(overlaying='y', side='right', showgrid=False, rangemode='tozero'))
        st.plotly_chart(fig, use_container_width=True)
        
        # ✅ NUEVO: Tarjeta Visual de Patrones Japoneses
        if patrones_actuales and patrones_actuales[0] != "Ninguno (Sin patrón claro)":
            patrones_html = " | ".join(patrones_actuales)
            st.markdown(f"""
                <div style='background:#1C1C1C; padding:15px; border-radius:10px; border: 1px solid #FFD700; margin-top:10px;'>
                    <p style='color:#FFD700; margin:0; font-weight:bold; font-size:16px;'>🇯🇵 Patrones Japoneses Detectados en Tiempo Real:</p>
                    <p style='color:#FFFFFF; margin:5px 0 0 0; font-size:18px;'>{patrones_html}</p>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div style='background:#1C1C1C; padding:15px; border-radius:10px; border: 1px solid #333; margin-top:10px;'>
                    <p style='color:#888; margin:0;'>🇯🇵 Escaneando velas... (Esperando patrón claro de los 16)</p>
                </div>
            """, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Error gráfico: {e}")

# ─── Panel de Logs ───────────────────────────────────────────────────────────
def render_logs(ss):
    """Renderiza el panel de auditoría con logs invertidos"""
    st.subheader("🕵️ Panel de Auditoría")
    st.code("\n".join(ss.logs_auditoria[::-1]), language='bash')

# ─── Tab Staking ─────────────────────────────────────────────────────────────
def render_tab_staking(ss):
    """Renderiza la pestaña de ingresos pasivos / staking"""
    st.title("💎 Ingresos Pasivos (Staking / Binance Earn)")
    st.markdown("Analiza productos de alto rendimiento (APR) para que tu cripto trabaje.")
    st.info("Dual Investment: Depositas USDT y eliges precio. Si sube, ganas hasta 200% APR.")
    client = ss.get('client')
    if not client:
        st.warning("Conecta tu API Key para ver Staking.")
        return
    try:
        with st.spinner("Obteniendo productos de Earn..."):
            url = "https://www.binance.com/bapi/lending/union/interestHistorical?size=10&type=1&status=1"
            hdrs = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
            resp = requests.get(url, headers=hdrs, timeout=5.0)
            if resp.status_code == 200 and resp.json().get('data'):
                df = pd.DataFrame(resp.json()['data'])
                cols = [c for c in df.columns if c in ['asset','apy','minPurchaseAmount','status']]
                if cols:
                    df = df[cols]
                    df['apy'] = pd.to_numeric(df['apy'], errors='coerce')
                    df['minPurchaseAmount'] = pd.to_numeric(df['minPurchaseAmount'], errors='coerce')
                    df = df[(df['apy'] > 0.1) & (df['status'] == 'PURCHASING')]
                    df = df.sort_values('apy', ascending=False).head(15)
                    if len(df) > 0:
                        st.success(f"✅ {len(df)} productos con mejor APY:")
                        for _, row in df.iterrows():
                            a, apy, mn = row['asset'], row['apy'], row['minPurchaseAmount']
                            c1, c2 = st.columns([3, 1])
                            with c1: st.write(f"**{a}** - APY: `{apy}%` - Mín: `{mn} {a}`")
                            with c2:
                                if st.button(f"Suscribir {a}", key=f"sub_{a}"):
                                    st.warning("Requiere integrar API de Savings en Binance.")
                    else: st.warning("No se encontraron productos activos.")
            else: st.error("Binance bloqueó el scrapeo temporalmente.")
    except Exception as e: st.error(f"Error: {e}")
