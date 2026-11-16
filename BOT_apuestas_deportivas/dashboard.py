import streamlit as st
import pandas as pd
import plotly.express as px
import database as db

def show_dashboard():
    st.title("📊 Dashboard Administrador")
    st.write(f"Bienvenido, **{st.session_state.user[2]}** (Administrador)")
    
    users = db.get_all_users()
    df = pd.DataFrame(users, columns=['Identificación', 'Usuario', 'Correo', 'F. Inicio', 'F. Final', 'Perfil', 'Ingresos', 'Análisis', 'Estado', 'Membresía'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Usuarios", len(df))
    col2.metric("Usuarios Aprobados", len(df[df['Estado'] == 'aprobado']))
    col3.metric("Pendientes / Rechazados", len(df[df['Estado'] != 'aprobado']))
    
    st.divider()
    
    # Gráfica de Torta
    st.subheader("Distribución de Usuarios Registrados vs Aprobados")
    pie_data = df['Estado'].value_counts().reset_index()
    pie_data.columns = ['Estado', 'Cantidad']
    fig = px.pie(pie_data, values='Cantidad', names='Estado', title='Estado de Registros', hole=0.4)
    st.plotly_chart(fig, use_container_width=True)
    
    st.divider()
    
    # Gestión de usuarios
    st.subheader("⚙️ Gestión de Usuarios")
    st.dataframe(df, use_container_width=True)
    
    st.subheader("Aprobar / Rechazar Usuarios")
    pending_users = df[df['Estado'] == 'pendiente']['Identificación'].tolist()
    if pending_users:
        selected_id = st.selectbox("Selecciona usuario pendiente", pending_users)
        c1, c2 = st.columns(2)
        if c1.button("✅ Aprobar Usuario"):
            db.approve_user(selected_id, True)
            st.success("Usuario aprobado.")
            st.rerun()
        if c2.button("❌ Rechazar Usuario"):
            db.approve_user(selected_id, False)
            st.warning("Usuario rechazado.")
            st.rerun()
    else:
        st.info("No hay usuarios pendientes.")
        
    st.divider()
    st.subheader("👑 Top 5 Usuarios (Más Análisis)")
    top_users = df.sort_values(by='Análisis', ascending=False).head(5)
    st.dataframe(top_users[['Usuario', 'Ingresos', 'Análisis']], use_container_width=True)
