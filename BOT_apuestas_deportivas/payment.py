import streamlit as st
import database as db
from datetime import datetime

def show_payment():
    st.title("💳 Suscripción Premium")
    st.write("Tu periodo de prueba de 3 días está activo o ha terminado. ¡Suscríbete para seguir rompiendo las casas de apuestas!")
    
    with st.form("pse_payment"):
        st.subheader("Simulador de Pago PSE")
        nombre = st.text_input("Nombre completo titutar")
        banco = st.selectbox("Selecciona tu banco", ["Bancolombia", "Davivienda", "Banco de Bogotá", "Nequi"])
        monto = "$50.000 COP (1 Mes de Acceso)"
        st.info(f"Monto a pagar: {monto}")
        submit = st.form_submit_button("Pagar con PSE")
        
        if submit:
            identificacion = st.session_state.user[1]
            db.update_membership(identificacion, days=30)
            st.success("¡Pago exitoso! Tu membresía ha sido activada por 30 días.")
            st.session_state.user = db.get_user_by_id(identificacion) # Refrescar sesión
            st.rerun()import streamlit as st
import database as db
from datetime import datetime

def show_payment():
    st.title("💳 Suscripción Premium")
    st.write("Tu periodo de prueba de 3 días está activo o ha terminado. ¡Suscríbete para seguir rompiendo las casas de apuestas!")
    
    with st.form("pse_payment"):
        st.subheader("Simulador de Pago PSE")
        nombre = st.text_input("Nombre completo titutar")
        banco = st.selectbox("Selecciona tu banco", ["Bancolombia", "Davivienda", "Banco de Bogotá", "Nequi"])
        monto = "$50.000 COP (1 Mes de Acceso)"
        st.info(f"Monto a pagar: {monto}")
        submit = st.form_submit_button("Pagar con PSE")
        
        if submit:
            identificacion = st.session_state.user[1]
            db.update_membership(identificacion, days=30)
            st.success("¡Pago exitoso! Tu membresía ha sido activada por 30 días.")
            st.session_state.user = db.get_user_by_id(identificacion) # Refrescar sesión
            st.rerun()
