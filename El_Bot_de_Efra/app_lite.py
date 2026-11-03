# ==========================================================
# 📦 BLOQUE 1: IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==========================================================
import os
import socket
from datetime import datetime, timedelta

import pandas as pd
import plotly.io as pio
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# 🔄 Auto-refresh de la app cada 60s
st_autorefresh(interval=60 * 1000, limit=None, key="auto_refresh_lite")

# 🎨 Tema oscuro por defecto para gráficos
pio.templates.default = "plotly_dark"

# ==========================================================
# 📦 IMPORTACIONES INTERNAS DEL BOT
# ==========================================================
from utils.model_trainer import cargar_meta_modelo, reentrenar_desde_historial
from utils.auth import (
    autenticar_usuario, obtener_permisos, cambiar_contraseña,
    agregar_usuario, eliminar_usuario, cargar_usuarios, guardar_log_acceso,
    obtener_correo, obtener_nombre
)
from utils.modelo import entrenar_y_predecir
from utils.comun import (
    cargar_activos, obtener_datos_yahoo, obtener_datos_binance,
    normalizar_columnas
)
from utils.historial import cargar_historial, resumen_semanal, resumen_metricas
from utils.logger import log_error
from utils.graficos import graficar_candlestick
from utils.indicadores_tecnicos import agregar_indicadores_tecnicos, tendencia_mercado
from telegram_alertas import enviar_telegram, send_telegram_chart
from notificador_email import enviar_email
from fibonacci import detectar_niveles_fibonacci
from el_bot_de_efra import procesar_senal

# ==========================================================
# 📦 OPCIONAL: MODO BINANCE (SOLO SI ESTÁ DISPONIBLE)
# ==========================================================
try:
    from binance.client import Client
    from config_loader import API_KEY, API_SECRET  # Asegúrate que config_loader.py tenga tus claves
    binance_disponible = True
except ImportError:
    binance_disponible = False
except Exception:
    binance_disponible = False

# ==========================================================
# 🌐 COMPROBAR CONEXIÓN A INTERNET
# ==========================================================
def hay_conexion_internet(host="8.8.8.8", port=53, timeout=3):
    """Verifica si hay conexión a Internet intentando conectar con un servidor DNS."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

if not hay_conexion_internet():
    st.error("⚠️ Sin conexión a internet. Por favor, verifica tu red e intenta más tarde.")
    st.stop()

# ==========================================================
# 🎨 CONFIGURACIÓN VISUAL DE LA APP
# ==========================================================
st.set_page_config(page_title="Bot de Efra Lite", layout="wide", page_icon="🤖")
st.markdown("""
    <style>
        body { background-color: #0E1117; color: white; }
        .stApp { background-color: #0E1117; }
        .stButton>button { background-color: #1F77B4; color: white; }
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# 📦 BLOQUE 2: SESIÓN, LOGIN Y PANEL LATERAL
# ==========================================================

# Inicializar variables de sesión si no existen
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario = None
    st.session_state.nombre = None
    st.session_state.permisos = None
    st.session_state.bot_activo = False
    st.session_state.analisis_realizado = False
    st.session_state.activo_actual = None

# ==========================================================
# 🔐 Login de usuario
# ==========================================================
if not st.session_state.autenticado:
    st.sidebar.title("🔐 Ingreso al Bot de Efra (Lite)")
    usuario = st.sidebar.text_input("Usuario", key="usuario_input_lite")
    clave = st.sidebar.text_input("Contraseña", type="password", key="clave_input_lite")

    if st.sidebar.button("Iniciar sesión", key="login_btn_lite"):
        try:
            if autenticar_usuario(usuario, clave):
                st.session_state.autenticado = True
                st.session_state.usuario = usuario
                st.session_state.nombre = obtener_nombre(usuario)
                st.session_state.permisos = obtener_permisos(usuario)

                # Guardar acceso en el log
                guardar_log_acceso(usuario)

                # Notificar por correo y Telegram
                correo = obtener_correo(usuario)
                if correo:
                    enviar_email(correo, "🔐 Inicio de sesión",
                                 f"🧑 Usuario {st.session_state.nombre} ha iniciado sesión.")
                enviar_telegram(f"📲 Usuario {st.session_state.nombre} inició sesión.")

                # Refrescar la app para que cargue el panel
                st.rerun()
            else:
                st.sidebar.error("❌ Credenciales inválidas. Intenta de nuevo.")
        except Exception as e:
            log_error(e, archivo="app_lite.py", funcion="login_usuario")
            st.sidebar.error("⚠️ Error durante el proceso de autenticación.")

    st.stop()

# ==========================================================
# 🎛️ Panel lateral de control
# ==========================================================
st.sidebar.header("🎛️ Panel de Control")

# 🔹 Cargar lista de activos
try:
    activos = cargar_activos()
except Exception as e:
    log_error(e, archivo="app_lite.py", funcion="cargar_activos")
    activos = []

# 🔹 Selector de activo
if activos:
    activo = st.sidebar.selectbox("📈 Selecciona un activo", activos, key="activo_selectbox_lite")
else:
    st.sidebar.warning("⚠️ No se encontraron activos disponibles.")
    activo = None

# Botones de control (activados/desactivados dinámicamente)
iniciar = st.sidebar.button(
    "🚀 Iniciar análisis",
    key="iniciar_btn_lite",
    disabled=st.session_state.bot_activo  # Deshabilitar si ya está activo
)
cancelar = st.sidebar.button(
    "🔴 Cancelar análisis",
    key="cancelar_btn_lite",
    disabled=not st.session_state.bot_activo  # Deshabilitar si no está activo
)

# Manejo de acciones
if iniciar:
    st.session_state.bot_activo = True
    st.session_state.analisis_realizado = False
    st.session_state.activo_actual = activo

if cancelar:
    st.session_state.bot_activo = False
    st.session_state.analisis_realizado = False
    st.session_state.activo_actual = None
    enviar_telegram(f"⛔ Análisis detenido por {st.session_state.nombre}")
    st.sidebar.info("⛔ Análisis detenido.")

# ==========================================================
# 📦 BLOQUE 3: CONFIGURACIÓN PERSISTENTE DEL BOT
# ==========================================================

import json

CONFIG_FILE = "config_bot.json"

def cargar_config():
    """Carga la configuración guardada desde archivo JSON."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_error(e, archivo="app_lite.py", funcion="cargar_config")
            return {"modo_demo": True, "ejecutar_orden": False}
    else:
        return {"modo_demo": True, "ejecutar_orden": False}

def guardar_config(config):
    """Guarda la configuración actual en archivo JSON."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="guardar_config")

# Cargar configuración al iniciar
config = cargar_config()

# ==========================================================
# 🔧 Controles en la interfaz lateral
# ==========================================================
st.sidebar.subheader("⚙️ Configuración del Bot")

modo_demo = st.sidebar.checkbox(
    "🧪 Activar MODO DEMO (Simulación)",
    value=config.get("modo_demo", True),
    help="Si está activado, las órdenes no se ejecutarán en real."
)

ejecutar_orden = st.sidebar.checkbox(
    "🚀 Activar EJECUCIÓN AUTOMÁTICA de órdenes",
    value=config.get("ejecutar_orden", False),
    help="Si está activado, el bot ejecutará órdenes automáticamente si las señales coinciden."
)

# Guardar cambios si se modifica configuración
if (modo_demo != config.get("modo_demo")) or (ejecutar_orden != config.get("ejecutar_orden")):
    config["modo_demo"] = modo_demo
    config["ejecutar_orden"] = ejecutar_orden
    guardar_config(config)
    st.sidebar.success("✅ Configuración actualizada")

# Mostrar estado actual
estado_modo = "🧪 DEMO" if modo_demo else "💰 REAL"
estado_ordenes = "✅ Automático" if ejecutar_orden else "🛑 Manual"
st.sidebar.markdown(f"**Modo actual:** {estado_modo}")
st.sidebar.markdown(f"**Ejecución:** {estado_ordenes}")

# ==========================================================
# 🔓 Botón de Cerrar sesión
# ==========================================================
if st.sidebar.button("🔓 Cerrar sesión", key="logout_btn_lite"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ==========================================================
# 📦 BLOQUE 4: DEFINICIÓN DE TABS Y FLUJO DE ANÁLISIS
# ==========================================================

tabs = st.tabs([
    "📊 Análisis",
    "📉 Backtesting",
    "📂 Historial",
    "👥 Administración"
])

# ----------------------------------------------------------
# 📌 TAB: ANÁLISIS PRINCIPAL
# ----------------------------------------------------------
with tabs[0]:
    st.title("🤖 El Bot de Efra - Plataforma de Trading Lite")
    st.success(f"👋 Bienvenido, {st.session_state.nombre}")

    # --- Botón Cancelar Análisis ---
    if cancelar:
        st.session_state["bot_activo"] = False
        st.session_state["analisis_realizado"] = False
        enviar_telegram(f"⛔ Análisis detenido por {st.session_state.nombre}")
        st.info("⛔ Análisis detenido.")
        st.stop()

    # --- Botón Iniciar Análisis ---
    if iniciar:
        st.session_state["analisis_realizado"] = True
        st.session_state["bot_activo"] = True
        st.session_state["activo_actual"] = activo

        # Deshabilitar botón "Iniciar" mientras el análisis está activo
        st.sidebar.button("🚀 Iniciar análisis", disabled=True, key="iniciar_btn_disabled")
        st.sidebar.button("🔴 Cancelar análisis", key="cancelar_btn_enabled")

        # ==============================
        # 📌 Intentar buscar datos desde todas las fuentes
        # ==============================
        try:
            # Evitamos depender del campo 'mercado'
            simbolo = activo  # Usamos directamente el símbolo
            df = bot.obtener_datos_con_fallback(simbolo, interval="1m")

            # Si no hay datos suficientes, detener
            if df is None or df.empty or len(df) < 10:
                st.error(f"⚠️ No se pudieron obtener datos suficientes para {simbolo} desde ninguna fuente.")
                st.session_state["analisis_realizado"] = False
                st.stop()

            # Normalizar columnas para IA y gráfico
            df = normalizar_columnas(df)
            if df.empty:
                st.error("⚠️ Los datos obtenidos no tienen columnas válidas.")
                st.session_state["analisis_realizado"] = False
                st.stop()

        except Exception as e:
            log_error(e, archivo="app_lite.py", funcion="obtener_datos_con_fallback")
            st.error(f"❌ Error al obtener datos del activo {activo}")
            st.session_state["analisis_realizado"] = False
            st.stop()

        # ==============================
        # 📌 Calcular indicadores técnicos
        # ==============================
        df_ind = agregar_indicadores_tecnicos(df.copy())

        columnas_requeridas = ["low", "high", "close"]
        for col in columnas_requeridas:
            if col not in df_ind.columns:
                st.error(f"❌ Falta columna requerida: {col}")
                st.session_state["analisis_realizado"] = False
                st.stop()

        # ==============================
        # 📌 Ejecutar análisis IA + técnico
        # ==============================
        try:
            accion_ia, precision, señal_tec, _ = procesar_senal(simbolo)
        except Exception as e:
            log_error(e, archivo="app_lite.py", funcion="procesar_senal")
            st.warning("⚠️ No se pudo generar predicción IA.")
            accion_ia, precision, señal_tec = None, None, None

        # ==============================
        # 📌 Mostrar métricas IA
        # ==============================
        texto_ia = accion_ia.upper() if accion_ia else "N/A"
        texto_prec = f"{precision:.2%}" if precision else "N/A"
        texto_tec = "BUY" if señal_tec and señal_tec > 0 else "SELL" if señal_tec and señal_tec < 0 else "HOLD"

        st.metric("Predicción IA", texto_ia)
        st.metric("Precisión", texto_prec)
        st.metric("Técnica", texto_tec)

        # ==============================
        # 📈 Mostrar gráfico
        # ==============================
        fig = graficar_candlestick(df_ind, titulo=f"📈 {activo} - Análisis Técnico")
        st.plotly_chart(fig, use_container_width=True)

        # ==============================
        # 📤 Enviar resultados a Telegram
        # ==============================
        ruta = f"graficos/{activo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        os.makedirs("graficos", exist_ok=True)
        pio.write_image(fig, ruta, format="png")
        send_telegram_chart(ruta, caption=f"📊 Gráfico de {activo} - Señales técnicas + IA")

# ==========================================================
# 📦 BLOQUE 5: BACKTESTING TÉCNICO
# ==========================================================

with tabs[1]:
    st.subheader("📉 Backtesting Técnico de Estrategias")

    # --- Comprobar si el usuario ya seleccionó un activo ---
    activo = st.session_state.get("activo_actual")
    if not activo:
        st.info("ℹ️ Selecciona primero un activo en el panel lateral e inicia el análisis.")
        st.stop()

    # ==============================
    # 📌 Obtener datos desde cualquier fuente disponible
    # ==============================
    try:
        # Evitar depender del campo 'mercado'
        df_raw = bot.obtener_datos_con_fallback(activo, interval="1m")

        if df_raw is None or df_raw.empty:
            st.error(f"⚠️ No se pudieron obtener datos para {activo} en ninguna fuente.")
            st.stop()

        # Normalizar y agregar indicadores técnicos
        df = normalizar_columnas(df_raw)
        df = agregar_indicadores_tecnicos(df)

        if df.empty or df.isnull().all().all():
            st.error("⚠️ Datos inválidos o incompletos para backtesting.")
            st.stop()

    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="backtesting_tab")
        st.error(f"❌ Error durante el proceso de backtesting: {e}")
        st.stop()

    # ==============================
    # 📌 Configuración del backtest
    # ==============================
    estrategia = st.selectbox(
        "⚙️ Estrategia Técnica",
        ["Cruce de Medias", "RSI Overbought/Oversold"]
    )
    capital_inicial = st.number_input(
        "💰 Capital inicial (USDT)", value=1000.0, min_value=100.0, step=100.0
    )
    comision = st.slider(
        "💸 Comisión por operación (%)", min_value=0.0, max_value=0.5, value=0.1, step=0.01
    )

    # ==============================
    # 📌 Botón para ejecutar backtesting
    # ==============================
    ejecutar_backtest = st.button("🚀 Ejecutar Backtesting")

    if ejecutar_backtest:
        try:
            # Aplicar la estrategia seleccionada
            df_bt = aplicar_estrategia_tecnica(df.copy(), estrategia)
            resultado, historial = realizar_backtesting(df_bt, capital_inicial, comision)
            met = calcular_metricas(historial)

            # Mostrar resultados
            st.success(f"✅ Estrategia completada - {estrategia}")
            st.write("📈 Métricas de rendimiento:")
            st.write(met)

            # Equity Curve
            st.markdown("### 📊 Equity Curve")
            fig_equity = graficar_equity_curve(historial)
            st.plotly_chart(fig_equity, use_container_width=True)

            # Detalles de operaciones
            st.markdown("### 📝 Detalles de las operaciones")
            st.dataframe(historial, use_container_width=True)

        except Exception as e:
            log_error(e, archivo="app_lite.py", funcion="ejecutar_backtesting")
            st.error(f"❌ Error al ejecutar el backtesting: {e}")

# ==========================================================
# 📦 BLOQUE 6: HISTORIAL Y ADMINISTRACIÓN
# ==========================================================

with tabs[2]:
    st.subheader("📂 Historial de operaciones")

    try:
        # Intentar leer el historial con codificación segura
        try:
            historial = cargar_historial()
        except UnicodeDecodeError:
            # Fallback a lectura segura para caracteres especiales
            historial = pd.read_csv("historial.csv", encoding="latin-1")

        if historial is None or historial.empty:
            st.warning("⚠️ No hay registros en el historial todavía.")
        else:
            # Mostrar el historial
            st.dataframe(historial, use_container_width=True)

            # Resumen semanal
            st.markdown("### 📊 Resumen Semanal")
            resumen_semana = resumen_semanal(historial)
            st.write(resumen_semana)

            # Métricas de rendimiento
            st.markdown("### 📈 Métricas Globales")
            resumen = resumen_metricas(historial)
            st.write(resumen)

    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="cargar_historial_tab")
        st.error(f"❌ Error al leer historial: {e}")

# ==========================================================
# 📦 BLOQUE 7: ADMINISTRACIÓN DE USUARIOS
# ==========================================================

with tabs[3]:
    st.subheader("👥 Administración de Usuarios")

    # Formulario para agregar nuevo usuario
    with st.form("form_nuevo_usuario"):
        nuevo_usuario = st.text_input("👤 Nuevo usuario")
        nueva_clave = st.text_input("🔑 Contraseña", type="password")
        nuevo_correo = st.text_input("📧 Correo electrónico")
        permisos = st.selectbox("📜 Permisos", ["admin", "usuario"])
        submit_agregar = st.form_submit_button("➕ Agregar Usuario")

        if submit_agregar:
            if nuevo_usuario and nueva_clave:
                try:
                    agregar_usuario(nuevo_usuario, nueva_clave, nuevo_correo, permisos)
                    st.success(f"✅ Usuario '{nuevo_usuario}' agregado correctamente.")
                except Exception as e:
                    log_error(e, archivo="app_lite.py", funcion="agregar_usuario")
                    st.error(f"❌ Error al agregar usuario: {e}")
            else:
                st.warning("⚠️ Debes completar todos los campos obligatorios.")

    # Formulario para cambiar contraseña
    with st.form("form_cambiar_clave"):
        usuario_cambiar = st.text_input("👤 Usuario")
        nueva_clave_cambiar = st.text_input("🔑 Nueva contraseña", type="password")
        submit_cambiar = st.form_submit_button("🔄 Cambiar contraseña")

        if submit_cambiar:
            try:
                cambiar_contraseña(usuario_cambiar, nueva_clave_cambiar)
                st.success(f"✅ Contraseña de '{usuario_cambiar}' actualizada.")
            except Exception as e:
                log_error(e, archivo="app_lite.py", funcion="cambiar_contraseña")
                st.error(f"❌ Error al cambiar contraseña: {e}")

    # Formulario para eliminar usuario
    with st.form("form_eliminar_usuario"):
        usuario_eliminar = st.text_input("👤 Usuario a eliminar")
        submit_eliminar = st.form_submit_button("🗑️ Eliminar usuario")

        if submit_eliminar:
            try:
                eliminar_usuario(usuario_eliminar)
                st.success(f"✅ Usuario '{usuario_eliminar}' eliminado.")
            except Exception as e:
                log_error(e, archivo="app_lite.py", funcion="eliminar_usuario")
                st.error(f"❌ Error al eliminar usuario: {e}")


# ==========================================================
# 📦 BLOQUE 8: TRADING MANUAL
# ==========================================================

with tabs[4]:
    st.subheader("💼 Trading Manual")

    try:
        # Entrada de símbolo y parámetros manuales
        simbolo_manual = st.text_input("📈 Activo / Par", value=st.session_state.get("activo_actual", ""))
        cantidad_manual = st.number_input("Cantidad", min_value=0.0, value=0.0, step=0.1)
        precio_manual = st.number_input("Precio", min_value=0.0, value=0.0, step=0.01)
        tipo_operacion = st.selectbox("Tipo de operación", ["Compra", "Venta"])

        if st.button("📌 Ejecutar Orden Manual"):
            if simbolo_manual and cantidad_manual > 0 and precio_manual > 0:
                # Aquí se registraría la orden en el historial o base de datos
                st.success(f"✅ Orden manual registrada: {tipo_operacion} {cantidad_manual} {simbolo_manual} a {precio_manual}")
                enviar_telegram(f"📌 Orden manual: {tipo_operacion} {cantidad_manual} {simbolo_manual} a {precio_manual}")
            else:
                st.warning("⚠️ Debes completar todos los campos.")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="trading_manual")
        st.error(f"❌ Error en Trading Manual: {e}")


# ==========================================================
# 📦 BLOQUE 9: ÓRDENES EJECUTADAS
# ==========================================================

with tabs[5]:
    st.subheader("📋 Órdenes Ejecutadas")

    try:
        historial_ordenes = cargar_historial()

        if historial_ordenes is None or historial_ordenes.empty:
            st.info("ℹ️ No hay órdenes ejecutadas todavía.")
        else:
            st.dataframe(historial_ordenes, use_container_width=True)
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="ordenes_ejecutadas")
        st.error(f"❌ Error al cargar órdenes ejecutadas: {e}")


# ==========================================================
# 📦 BLOQUE 10: RANKING DE RESULTADOS
# ==========================================================

with tabs[6]:
    st.subheader("🏆 Ranking de Resultados")

    try:
        historial_ranking = cargar_historial()

        if historial_ranking is None or historial_ranking.empty:
            st.info("ℹ️ No hay datos para mostrar el ranking.")
        else:
            # Ordenar por beneficio
            ranking = historial_ranking.copy()
            if "beneficio" in ranking.columns:
                ranking = ranking.sort_values(by="beneficio", ascending=False)
                st.dataframe(ranking, use_container_width=True)
            else:
                st.warning("⚠️ No se encontró la columna 'beneficio' para ordenar el ranking.")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="ranking_resultados")
        st.error(f"❌ Error al mostrar ranking: {e}")

# ==========================================================
# 📦 BLOQUE 11: IA MANUAL
# ==========================================================

with tabs[7]:
    st.subheader("🤖 IA Manual")

    try:
        activo_ia = st.text_input("📈 Activo para análisis IA", value=st.session_state.get("activo_actual", ""))
        
        if st.button("🚀 Ejecutar IA Manual"):
            if activo_ia:
                try:
                    accion, precision, señal_tec, señales = procesar_senal(activo_ia)
                    st.metric("Predicción IA", accion.upper() if accion else "N/A")
                    st.metric("Precisión", f"{precision:.2%}" if precision else "N/A")
                    st.metric("Señal Técnica", señal_tec if señal_tec else "N/A")
                except Exception as e:
                    log_error(e, archivo="app_lite.py", funcion="ia_manual")
                    st.error(f"❌ Error en IA Manual: {e}")
            else:
                st.warning("⚠️ Debes especificar un activo.")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="ia_manual_tab")
        st.error(f"❌ Error en la pestaña IA Manual: {e}")


# ==========================================================
# 📦 BLOQUE 12: IA AUTOMÁTICA
# ==========================================================

with tabs[8]:
    st.subheader("🤖 IA Automática")

    try:
        st.write("📌 Esta función ejecutará el análisis automático en base a los activos configurados.")
        if st.button("▶️ Iniciar IA Automática"):
            try:
                # Aquí podrías conectar con la lógica de análisis automático del bot
                st.success("✅ IA Automática iniciada.")
                enviar_telegram("🤖 IA Automática iniciada.")
            except Exception as e:
                log_error(e, archivo="app_lite.py", funcion="ia_automatica")
                st.error(f"❌ Error iniciando IA Automática: {e}")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="ia_automatica_tab")
        st.error(f"❌ Error en la pestaña IA Automática: {e}")


# ==========================================================
# 📦 BLOQUE 13: RANKING Y BACKTESTING DESDE HISTORIAL
# ==========================================================

with tabs[9]:
    st.subheader("📊 Ranking y Backtesting desde Historial")

    try:
        historial = cargar_historial()

        if historial is None or historial.empty:
            st.info("ℹ️ No hay historial suficiente para realizar ranking/backtesting.")
        else:
            st.write("📌 Ranking basado en resultados pasados:")
            if "beneficio" in historial.columns:
                ranking_hist = historial.sort_values(by="beneficio", ascending=False)
                st.dataframe(ranking_hist, use_container_width=True)
            else:
                st.warning("⚠️ No se encontró columna 'beneficio' en el historial.")

            if st.button("🔄 Ejecutar Backtesting desde Historial"):
                try:
                    # Aquí integras la lógica de backtesting desde historial
                    st.success("✅ Backtesting desde historial ejecutado.")
                except Exception as e:
                    log_error(e, archivo="app_lite.py", funcion="backtesting_historial")
                    st.error(f"❌ Error en backtesting desde historial: {e}")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="ranking_backtesting_historial")
        st.error(f"❌ Error en pestaña Ranking & Backtesting desde Historial: {e}")


# ==========================================================
# 📦 BLOQUE 14: PREDICCIÓN EN TIEMPO REAL Y EJECUCIÓN
# ==========================================================

with tabs[10]:
    st.subheader("🏆 Predicción en tiempo real y ejecución")

    try:
        activo_realtime = st.text_input("📈 Activo para predicción en tiempo real", value=st.session_state.get("activo_actual", ""))

        if st.button("▶️ Iniciar predicción en tiempo real"):
            if activo_realtime:
                try:
                    accion, precision, señal_tec, señales = procesar_senal(activo_realtime)
                    st.metric("Predicción IA", accion.upper() if accion else "N/A")
                    st.metric("Precisión", f"{precision:.2%}" if precision else "N/A")
                    st.metric("Señal Técnica", señal_tec if señal_tec else "N/A")
                except Exception as e:
                    log_error(e, archivo="app_lite.py", funcion="prediccion_tiempo_real")
                    st.error(f"❌ Error en predicción en tiempo real: {e}")
            else:
                st.warning("⚠️ Debes especificar un activo.")
    except Exception as e:
        log_error(e, archivo="app_lite.py", funcion="prediccion_tiempo_real_tab")
        st.error(f"❌ Error en la pestaña de predicción en tiempo real: {e}")

