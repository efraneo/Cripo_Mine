import streamlit as st
import database as db
from datetime import datetime

# Inicializar Base de Datos
db.init_db()

# Configuración de página
st.set_page_config(page_title="AI Bet Generator", page_icon="🤖", layout="wide")

def main():
    # Si no está logueado, mostrar pantalla de login/registro
    if 'logged_in' not in st.session_state or not st.session_state.logged_in:
        import auth
        auth.show_auth()
        return

    user = st.session_state.user
    perfil = user[8] # Índice de 'perfil' en la BD
    fecha_final_str = user[7] # Índice de 'fecha_final'
    estado = user[11] # Índice de 'estado'

    # Verificar membresía (si no es admin y la fecha final ya pasó)
    if perfil != 'administrador' and fecha_final_str != 'NA':
        try:
            fecha_final = datetime.strptime(fecha_final_str, "%Y-%m-%d")
            if datetime.now() > fecha_final and user[12] == 'gratis': # user[12] = membresia
                import payment
                st.sidebar.button("Cerrar Sesión", on_click=logout)
                payment.show_payment()
                return
        except:
            pass # Si la fecha está mal, dejamos pasar por ahora

    # Menú lateral
    st.sidebar.title(f"👋 Hola, {user[2]}")
    if st.sidebar.button("🚪 Cerrar Sesión"):
        logout()

    # Lógica de visualización según perfil
    if perfil == 'administrador':
        import dashboard
        import betting_app
        
        tab1, tab2 = st.tabs(["📊 Panel Admin", "🤖 Bot de Apuestas"])
        with tab1:
            dashboard.show_dashboard()
        with tab2:
            betting_app.show_betting_app()
    else:
        import betting_app
        import payment
        
        tab1, tab2 = st.tabs(["🤖 Bot de Apuestas", "💳 Mi Suscripción"])
        with tab1:
            betting_app.show_betting_app()
        with tab2:
            payment.show_payment()

def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()

if __name__ == "__main__":
    main()
