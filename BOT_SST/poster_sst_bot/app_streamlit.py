from __future__ import annotations

import streamlit as st

from poster_sst_bot.chatbot import PosterSSTChatbot
from poster_sst_bot.excel_exporter import build_workbook
from poster_sst_bot.schema import ACCIONES_COLUMNS, FIVE_WHY_COLUMNS, HALLAZGOS_COLUMNS, POSTER_FIELDS
from poster_sst_bot.seed_data import default_state
from poster_sst_bot.storage import load_state, save_state


st.set_page_config(page_title="Bot Poster SST", layout="wide")


def get_state():
    if "poster_sst_state" not in st.session_state:
        st.session_state.poster_sst_state = load_state()
        if not st.session_state.poster_sst_state.poster:
            st.session_state.poster_sst_state = default_state()
    return st.session_state.poster_sst_state


state = get_state()
bot = PosterSSTChatbot(state)

st.title("Bot Poster SST")
st.caption("Captura poster, hallazgos, acciones de mejora, 5 Por Que y genera Excel para graficas y predicciones.")

with st.sidebar:
    st.header("WhatsApp")
    st.write("Numero guia configurado:")
    st.code("3186146023")
    st.write("Webhook local:")
    st.code("uvicorn poster_sst_bot.whatsapp_webhook:app --host 0.0.0.0 --port 8001")
    st.write("URL Streamlit:")
    st.code("streamlit run poster_sst_bot/app_streamlit.py")
    if st.button("Guardar estado"):
        save_state(state)
        st.success("Estado guardado.")
    if st.button("Restaurar datos del poster"):
        st.session_state.poster_sst_state = default_state()
        st.rerun()

tab_chat, tab_poster, tab_hallazgos, tab_acciones, tab_five, tab_export = st.tabs(
    ["Chat", "Poster", "Hallazgos", "Acciones", "5 Por Que", "Excel"]
)

with tab_chat:
    if "poster_sst_messages" not in st.session_state:
        st.session_state.poster_sst_messages = [{"role": "assistant", "content": bot.welcome()}]
    for msg in st.session_state.poster_sst_messages:
        st.chat_message(msg["role"]).write(msg["content"])
    prompt = st.chat_input("Escribe menu, poster, hallazgo, accion, 5 por que, resumen o exportar")
    if prompt:
        st.session_state.poster_sst_messages.append({"role": "user", "content": prompt})
        reply = bot.handle(prompt)
        if "excel" in prompt.lower() or "export" in prompt.lower():
            save_state(state)
            output = build_workbook(state)
            reply = f"{reply}\n\nExcel generado: {output}"
        st.session_state.poster_sst_messages.append({"role": "assistant", "content": reply})
        save_state(state)
        st.rerun()

with tab_poster:
    st.subheader("Informacion del poster")
    for key, label in POSTER_FIELDS:
        if key in {"resumen", "problema", "objetivo_general", "metodologia"}:
            state.poster[key] = st.text_area(label, value=state.poster.get(key, ""), height=100)
        else:
            state.poster[key] = st.text_input(label, value=state.poster.get(key, ""))

with tab_hallazgos:
    st.subheader("Control de hallazgos SST")
    with st.form("hallazgo_form", clear_on_submit=True):
        cols = st.columns(3)
        values = {}
        for i, column in enumerate(HALLAZGOS_COLUMNS):
            values[column] = cols[i % 3].text_input(column)
        if st.form_submit_button("Agregar hallazgo"):
            state.hallazgos.append(values)
            save_state(state)
            st.success("Hallazgo agregado.")
    st.dataframe(state.hallazgos, use_container_width=True)

with tab_acciones:
    st.subheader("Matriz acciones de mejora SST")
    with st.form("accion_form", clear_on_submit=True):
        cols = st.columns(3)
        values = {}
        for i, column in enumerate(ACCIONES_COLUMNS):
            values[column] = cols[i % 3].text_input(column)
        if st.form_submit_button("Agregar accion"):
            state.acciones.append(values)
            save_state(state)
            st.success("Accion agregada.")
    st.dataframe(state.acciones, use_container_width=True)

with tab_five:
    st.subheader("Analisis 5 Por Que")
    with st.form("five_form", clear_on_submit=True):
        values = {}
        for column in FIVE_WHY_COLUMNS:
            values[column] = st.text_area(column, height=68) if "POR QUE" in column else st.text_input(column)
        if st.form_submit_button("Agregar 5 Por Que"):
            state.five_why.append(values)
            save_state(state)
            st.success("Analisis agregado.")
    st.dataframe(state.five_why, use_container_width=True)

with tab_export:
    st.subheader("Generar Excel estructurado")
    st.write(bot.summary())
    ready = state.is_ready_for_export()
    if not ready:
        st.warning("Faltan campos minimos: titulo, autor, resumen u objetivo general.")
    if st.button("Generar Excel", disabled=not ready):
        save_state(state)
        output = build_workbook(state)
        st.success("Excel generado.")
        st.markdown(f"[Abrir Excel generado]({output.as_posix()})")
        with output.open("rb") as fh:
            st.download_button(
                "Descargar Excel",
                data=fh,
                file_name=output.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
