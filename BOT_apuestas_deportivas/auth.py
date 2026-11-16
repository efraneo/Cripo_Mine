import streamlit as st
import database as db
import email_sender
import random
from datetime import datetime

def show_auth():
    st.markdown("<h1 style='text-align: center;'>🔒 Acceso al Bot Premium</h1>", unsafe_allow_html=True)
    
    if 'auth_view' not in st.session_state:
        st.session_state.auth_view = 'login'
    if 'recovery_code' not in st.session_state:
        st.session_state.recovery_code = None
    if 'recovery_user_id' not in st.session_state:
        st.session_state.recovery_user_id = None

    if st.session_state.auth_view == 'login':
        show_login()
    elif st.session_state.auth_view == 'register':
        show_register()
    elif st.session_state.auth_view == 'forgot':
        show_forgot_password()
    elif st.session_state.auth_view == 'reset':
        show_reset_password()

def show_login():
    st.write("Por favor, inicia sesión para continuar.")
    with st.form("login_form"):
        usuario = st.text_input("Usuario")
        clave = st.text_input("Clave", type="password")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            user = db.verify_login(usuario, clave)
            if user:
                if user[11] == 'pendiente': st.warning("Tu cuenta está en espera de aprobación por el Administrador.")
                elif user[11] == 'rechazado': st.error("Tu cuenta ha sido rechazada.")
                elif user[11] == 'aprobado':
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    db.update_login_stats(usuario)
                    st.rerun()
            else: st.error("Usuario o clave incorrectos.")
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    if col1.button("📝 ¿Quieres registrarte?"):
        st.session_state.auth_view = 'register'; st.rerun()
    if col2.button("🔑 ¿Olvidaste tu clave?"):
        st.session_state.auth_view = 'forgot'; st.rerun()

def show_register():
    st.subheader("Registro (3 Días Gratis)")
    with st.form("register_form"):
        identificacion = st.text_input("Identificación (Cédula)")
        usuario = st.text_input("Usuario deseado")
        correo = st.text_input("Correo electrónico")
        fecha_nac = st.date_input("Fecha de Nacimiento", min_value=datetime(1950, 1, 1)).strftime("%Y-%m-%d")
        clave = st.text_input("Crea una clave", type="password")
        submit = st.form_submit_button("Registrarme")
        
        if submit:
            if db.register_user(identificacion, usuario, clave, correo, fecha_nac):
                st.success("¡Registro exitoso! Tienes 3 días de prueba. El administrador debe aprobar tu cuenta.")
                st.session_state.auth_view = 'login'; st.rerun()
            else: st.error("El usuario o identificación ya existe.")
    
    if st.button("⬅️ Volver a Iniciar Sesión"):
        st.session_state.auth_view = 'login'; st.rerun()

def show_forgot_password():
    st.subheader("Recuperar Clave")
    st.write("Ingresa tu Identificación y Usuario. Te enviaremos un código a tu correo registrado.")
    with st.form("forgot_form"):
        identificacion = st.text_input("Identificación")
        usuario = st.text_input("Usuario")
        submit = st.form_submit_button("Enviar Código")
        
        if submit:
            correo = db.get_email_by_user_id(identificacion, usuario)
            if correo:
                code = str(random.randint(100000, 999999))
                st.session_state.recovery_code = code
                st.session_state.recovery_user_id = identificacion
                if email_sender.send_recovery_email(correo, code):
                    st.success("Se ha enviado un código de verificación a tu correo.")
                    st.session_state.auth_view = 'reset'; st.rerun()
                else:
                    st.error("Error al enviar el correo. Contacta al administrador.")
            else:
                st.error("No se encontró un usuario con esa combinación de Identificación y Usuario.")
    
    if st.button("⬅️ Volver a Iniciar Sesión"):
        st.session_state.auth_view = 'login'; st.rerun()

def show_reset_password():
    st.subheader("Restablecer Clave")
    with st.form("reset_form"):
        code_input = st.text_input("Código de verificación (enviado a tu correo)")
        new_pass = st.text_input("Nueva clave", type="password")
        confirm_pass = st.text_input("Confirma tu nueva clave", type="password")
        submit = st.form_submit_button("Cambiar Clave")
        
        if submit:
            if code_input == st.session_state.recovery_code:
                if new_pass == confirm_pass:
                    db.update_password(st.session_state.recovery_user_id, new_pass)
                    st.success("¡Clave actualizada exitosamente! Por favor inicia sesión.")
                    st.session_state.auth_view = 'login'
                    st.session_state.recovery_code = None
                    st.session_state.recovery_user_id = None
                    st.rerun()
                else:
                    st.error("Las claves no coinciden.")
            else:
                st.error("El código de verificación es incorrecto.")
    
    if st.button("⬅️ Volver"):
        st.session_state.auth_view = 'login'; st.rerun()
