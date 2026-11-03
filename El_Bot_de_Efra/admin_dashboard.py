# admin_dashboard.py

import streamlit as st
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

# Nuevas importaciones
from config_loader import MODO_DEMO, CLAVE_SECRETA
from telegram_alertas import enviar_resumen_semanal
import plotly.express as px

# Seguridad básica por clave (temporal)
clave_ingresada = st.text_input("🔐 Ingresa tu clave de administrador", type="password")
if clave_ingresada != CLAVE_SECRETA:
    st.warning("🔒 Clave incorrecta.")
    st.stop()

st.title("📊 Panel de administración - Bot de Efra")

# Cargar CSV de historial
if os.path.exists("historial.csv"):
    df = pd.read_csv("logs/historial.csv", parse_dates=["fecha"])
    df.sort_values("fecha", ascending=False, inplace=True)
else:
    st.warning("⚠️ No se encontró historial.")
    st.stop()

# Filtros
col1, col2 = st.columns(2)
symbols = df['activo'].unique().tolist()
symbol = col1.selectbox("Símbolo", ["Todos"] + symbols)

fechas = df['fecha'].dt.date.unique()
fecha_sel = col2.selectbox("Fecha", ["Todas"] + sorted(fechas, reverse=True))

df_filtrado = df.copy()
if symbol != "Todos":
    df_filtrado = df_filtrado[df_filtrado['activo'] == symbol]
if fecha_sel != "Todas":
    df_filtrado = df_filtrado[df_filtrado['fecha'].dt.date == fecha_sel]

st.subheader("📈 Señales recientes")

if not df_filtrado.empty:
    fig = px.scatter(
        df_filtrado,
        x="fecha",
        y="accion",
        color="activo",
        symbol="accion",
        title="Acciones del bot",
        labels={"accion": "Señal"}
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No hay datos para mostrar.")

def convertir_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Historial")
    output.seek(0)
    return output

if not df_filtrado.empty:
    st.download_button("📥 Descargar Excel", convertir_excel(df_filtrado), file_name="historial_filtrado.xlsx")

if st.button("📤 Enviar resumen por Telegram"):
    resumen = f"🧠 Resumen de señales:\n\n"
    resumen += df_filtrado['accion'].value_counts().to_string()
    enviar_resumen_semanal(resumen)
    st.success("Resumen enviado a Telegram.")

