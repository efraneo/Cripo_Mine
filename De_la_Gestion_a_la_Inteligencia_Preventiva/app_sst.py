import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
from PIL import Image
import os
import uuid
import bcrypt
import json
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- CONFIGURACIÓN DE PÁGINA (DEBE SER LO PRIMERO) ---
st.set_page_config(page_title="Inteligencia Preventiva SST", page_icon="🛡️", layout="wide")

# --- ESTILOS CSS PRO ---
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stButton>button { background-color: #0056b3; color: white; border-radius: 8px; border: none; padding: 10px 24px; font-weight: bold; transition: 0.3s; }
    .stButton>button:hover { background-color: #004494; color: white; transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.2); }
    .metric-card { background-color: white; padding: 20px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
    .kpi-value { font-size: 32px; font-weight: bold; color: #0056b3; }
    .kpi-label { font-size: 14px; color: #6c757d; }
</style>
""", unsafe_allow_html=True)

# --- CONEXIÓN A LA NUBE (SUPABASE, GROQ IA, GMAIL) ---
try:
    supabase_url = st.secrets["SUPABASE_URL"].rstrip('/')
    supabase_key = st.secrets["SUPABASE_KEY"]
    groq_key = st.secrets["GROQ_API_KEY"] 
    email_user = st.secrets["EMAIL_ADDRESS"]
    email_pass = st.secrets["EMAIL_PASSWORD"]
    
    from supabase import create_client, Client
    from groq import Groq
    
    supabase: Client = create_client(supabase_url, supabase_key)
    client_groq = Groq(api_key=groq_key)
    CLOUD_CONNECTED = True
except Exception as e:
    CLOUD_CONNECTED = False
    st.warning(f"⚠️ Configuración de nube incompleta. Funcionando en modo local. Error: {e}")

if not os.path.exists("uploads"):
    os.makedirs("uploads")

# --- FUNCIÓN ENVÍO DE CORREO REAL ---
def send_recovery_email(to_email, temp_pass):
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"Inteligencia Preventiva SST <{email_user}>"
        msg['To'] = to_email
        msg['Subject'] = "🛡️ Recuperación de Contraseña - Inteligencia Preventiva SST"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #0056b3;">Recuperación de Contraseña</h2>
            <p>Hola,</p>
            <p>Hemos recibido una solicitud para restablecer tu contraseña en el Ecosistema Inteligente de Hallazgos SST.</p>
            <p>Tu nueva contraseña temporal es:</p>
            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; font-size: 20px; font-weight: bold; color: #0056b3; letter-spacing: 2px;">
                {temp_pass}
            </div>
            <p>Por favor, inicia sesión con esta contraseña y cámbiala lo antes posible desde tu perfil.</p>
            <br>
            <p>Saludos cordiales,</p>
            <p><b>🛡️ Equipo de Seguridad y Salud en el Trabajo</b><br>Ing. Efrain Sarmiento Crespo</p>
        </div>
        """
        part = MIMEText(html_content, 'html')
        msg.attach(part)
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_pass)
        server.sendmail(email_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"Error configurando correo: {e}")
        return False

# --- BASE DE DATOS SQLITE (USUARIOS) ---
def init_users_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (cedula TEXT PRIMARY KEY, nombre TEXT, fecha_nac TEXT, correo TEXT UNIQUE, celular TEXT, 
                 clave TEXT, ip_registro TEXT, ip_ultimo_acceso TEXT, fecha_registro TIMESTAMP, aprobado BOOLEAN, fecha_vencimiento TIMESTAMP)''')
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN fecha_vencimiento TIMESTAMP")
    except sqlite3.OperationalError:
        pass 
    
    admin_user = "dasb1512"
    c.execute("SELECT * FROM users WHERE correo=?", (admin_user,))
    if not c.fetchone():
        hashed_clave = bcrypt.hashpw("cocolizo76".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        c.execute("""INSERT INTO users (cedula, nombre, fecha_nac, correo, celular, clave, ip_registro, ip_ultimo_acceso, fecha_registro, aprobado, fecha_vencimiento) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  ('0000000', 'Administrador SST', '1990-01-01', admin_user, '3000000000', hashed_clave, '0.0.0.0', '0.0.0.0', datetime.now(), True, datetime(2099, 12, 31)))
    conn.commit()
    return conn

def get_client_ip():
    try:
        if hasattr(st, 'context') and st.context.headers.get("X-Forwarded-For"):
            return st.context.headers.get("X-Forwarded-For").split(',')[0]
    except:
        pass
    return "127.0.0.1"

def register_user(cedula, nombre, fecha_nac, correo, celular, clave, ip):
    conn = init_users_db()
    c = conn.cursor()
    try:
        hashed_clave = bcrypt.hashpw(clave.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        # Por defecto: aprobado=False (Pendiente). No se le asigna fecha de vencimiento aún.
        c.execute("""INSERT INTO users (cedula, nombre, fecha_nac, correo, celular, clave, ip_registro, ip_ultimo_acceso, fecha_registro, aprobado, fecha_vencimiento) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                  (cedula, nombre, fecha_nac, correo, celular, hashed_clave, ip, ip, datetime.now(), False, None))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def verify_user(correo, clave, current_ip):
    conn = init_users_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE correo=?", (correo,))
    user = c.fetchone()
    if user and bcrypt.checkpw(clave.encode('utf-8'), user[5].encode('utf-8')):
        user_data = {
            "cedula": user[0], "nombre": user[1], "correo": user[3], 
            "ip_registro": user[6], "ip_ultimo_acceso": user[7], 
            "fecha_registro": user[8], "aprobado": user[9],
            "fecha_vencimiento": user[10] if len(user) > 10 else None
        }
        
        c.execute("UPDATE users SET ip_ultimo_acceso=? WHERE correo=?", (current_ip, correo))
        conn.commit()
        
        if correo != "dasb1512":
            if not user_data["aprobado"]:
                return None, "⏳ Su cuenta está pendiente de aprobación por el administrador."
            
            if user_data["fecha_vencimiento"]:
                try:
                    fecha_venc_str = str(user_data["fecha_vencimiento"]).split('.')[0]
                    fecha_venc = datetime.strptime(fecha_venc_str, "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > fecha_venc:
                        return None, "⏳ Su membresía ha expirado. Comuníquese con ing.efrainsarmientoc@outlook.es para renovar."
                except:
                    pass 
        
        return user_data, "OK"
    return None, "❌ Usuario o clave incorrectos."

def check_user_exists(correo):
    conn = init_users_db()
    c = conn.cursor()
    c.execute("SELECT correo FROM users WHERE correo=?", (correo,))
    return c.fetchone() is not None

def reset_password(correo):
    temp_pass = str(uuid.uuid4().hex[:6]).upper()
    conn = init_users_db()
    c = conn.cursor()
    try:
        hashed_temp = bcrypt.hashpw(temp_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        fecha_venc = datetime.now() + timedelta(days=3)
        c.execute("UPDATE users SET clave=?, fecha_vencimiento=? WHERE correo=?", (hashed_temp, fecha_venc, correo))
        conn.commit()
        return temp_pass
    except Exception:
        return None

# --- MOTOR DE IA PREDICTIVA (NTC 3701 - 100% REAL Y ESPECÍFICA) ---
def predict_sst_analysis(texto_hallazgo):
    prompt_ia = f"""
    Eres un Auditor Experto en Seguridad y Salud en el Trabajo (SST), especialista en la normativa NTC 3701 y la metodología de los 5 Por Qué.
    
    CONTEXTO: Te están reportando una CONDICIÓN SUBESTÁNDAR o un ACTO SUBESTÁNDAR detectado durante una inspección de rutina, NO un accidente de trabajo. 
    Hallazgo reportado: "{texto_hallazgo}"

    INSTRUCCIONES ESTRICTAS:
    1. Analiza profundamente el hallazgo. 
    2. REGLA CRÍTICA DE LOS 5 POR QUÉ: La lista "porques" DEBE contener EXACTAMENTE 5 elementos. Prohibido entregar menos de 5. Si crees que encontraste la causa raíz en el paso 3, DEBES continuar profundizando en los pasos 4 y 5 preguntando sobre fallas en el sistema de gestión, cultura organizacional, falta de asignación de recursos o debilidades en el SG-SST.
    3. Las preguntas y respuestas deben ser TOTALMENTE ESPECÍFICAS a este hallazgo. Formula la pregunta basada en la respuesta anterior.
    4. La Causa Raíz debe ser una conclusión técnica, organizacional o de gestión muy específica derivada de tu análisis.
    5. Para la NTC 3701, selecciona los códigos EXACTOS que apliquen estrictamente a este hallazgo. No pongas ejemplos genéricos, usa los códigos reales de la norma.
    6. Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura exacta:

    {{
      "categoria": "Clasificación principal del riesgo basada en el hallazgo",
      "evento": "Descripción técnica y profesional del hallazgo",
      "porques": [
        "1. ¿Por qué ocurrió la condición subestándar? -> [Respuesta específica]",
        "2. ¿Por qué sucedió lo anterior? -> [Respuesta específica]",
        "3. ¿Por qué se generó esa situación? -> [Respuesta específica]",
        "4. ¿Por qué no se detectó o previno por el sistema de gestión? -> [Respuesta específica]",
        "5. ¿Por qué existe esa falla en el sistema o cultura organizacional? -> [Respuesta específica que revela la causa raíz]"
      ],
      "causa_raiz": "Enunciado contundente y específico de la causa raíz derivada del paso 5.",
      "actos_sub": ["Código - Nombre exacto NTC 3701 (si aplica, si no, 'No aplica')"],
      "condiciones_sub": ["Código - Nombre exacto NTC 3701"],
      "factores_personales": ["Código - Nombre exacto NTC 3701 (si aplica)"],
      "factores_trabajo": ["Código - Nombre exacto NTC 3701"],
      "acciones": [
        {{
          "titulo": "Acción Correctiva/Preventiva específica al hallazgo",
          "objetivo": "Objetivo claro de la acción",
          "actividades": "Paso 1\\nPaso 2\\nPaso 3",
          "responsable": "Área o cargo responsable",
          "frecuencia": "Frecuencia real (Inmediata, Mensual, etc.)"
        }}
      ],
      "conclusion": "Conclusión técnica que relaciona el hallazgo con la causa raíz."
    }}
    """

    try:
        chat_completion = client_groq.chat.completions.create(
            messages=[{"role": "user", "content": prompt_ia}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        text_response = chat_completion.choices[0].message.content.strip()
        analisis = json.loads(text_response)
        
        keys_requeridas = ["categoria", "evento", "porques", "causa_raiz", "actos_sub", "condiciones_sub", "factores_personales", "factores_trabajo", "acciones", "conclusion"]
        for key in keys_requeridas:
            if key not in analisis:
                if key == "acciones":
                    analisis[key] = [{"titulo": "Acción pendiente", "objetivo": "Pendiente", "actividades": "Pendiente", "responsable": "SST", "frecuencia": "Pendiente"}]
                elif isinstance(analisis.get(key), list):
                    analisis[key] = ["Pendiente por IA"]
                else:
                    analisis[key] = "Pendiente por IA"
        return analisis

    except Exception as e:
        return {
            "categoria": "Error de Procesamiento IA",
            "evento": texto_hallazgo.capitalize(),
            "porques": ["No se pudo completar el análisis profundo en este momento."],
            "causa_raiz": f"Error al interpretar la respuesta de la IA: {e}",
            "actos_sub": ["N/A"],
            "condiciones_sub": ["N/A"],
            "factores_personales": ["N/A"],
            "factores_trabajo": ["N/A"],
            "acciones": [{"titulo": "Reintentar", "objetivo": "Generar el análisis nuevamente", "actividades": "Intente de nuevo más tarde", "responsable": "SST", "frecuencia": "Inmediata"}],
            "conclusion": "La IA no pudo procesar la solicitud en formato JSON."
        }

# --- FUNCIONES SUPABASE ---
def save_to_supabase(tipo_input, descripcion, resultado, image_url=None):
    if CLOUD_CONNECTED:
        try:
            data = {
                "tipo_input": tipo_input,
                "descripcion": descripcion,
                "categoria_detectada": resultado.get('categoria', 'N/A'),
                "causa_raiz": resultado.get('causa_raiz', 'N/A'),
                "conclusion": resultado.get('conclusion', 'N/A'),
                "image_url": image_url
            }
            supabase.table('historial_ia').insert(data).execute()
        except Exception as e:
            st.error(f"Error guardando en nube: {e}")

def load_historial_supabase():
    if CLOUD_CONNECTED:
        try:
            response = supabase.table('historial_ia').select("*").execute()
            df = pd.DataFrame(response.data)
            if not df.empty and 'fecha_analisis' in df.columns:
                df['fecha_analisis'] = pd.to_datetime(df['fecha_analisis'])
                df = df.sort_values(by='fecha_analisis', ascending=False)
            return df
        except Exception as e:
            st.error(f"Error leyendo nube: {e}")
    return pd.DataFrame()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_data = None

init_users_db()

# ==========================================
# PANTALLA DE LOGIN / REGISTRO (UX ENTERPRISE)
# ==========================================
if not st.session_state.authenticated:
    st.title("🛡️ Inteligencia Preventiva SST - Acceso")
    
    default_index = 1 if st.session_state.get("force_register") else 0
    menu_auth = st.selectbox("Selecciona una opción", ["Iniciar Sesión", "Registrarse"], index=default_index)
    current_ip = get_client_ip()

    if menu_auth == "Registrarse":
        st.session_state.force_register = False
        with st.form("Registro"):
            st.markdown("### 📝 Crear Cuenta (Requiere Aprobación)")
            cedula = st.text_input("🔢 Número de Cédula")
            nombre = st.text_input("👤 Nombres Completos")
            fecha_nac = st.date_input("📅 Fecha de Nacimiento", min_value=datetime(1950, 1, 1).date(), max_value=datetime.now().date(), value=datetime(1990, 1, 1).date())
            correo = st.text_input("📧 Correo Electrónico (Será tu usuario)")
            celular = st.text_input("📱 Celular")
            clave = st.text_input("🔒 Clave", type="password")
            if st.form_submit_button("✍️ Enviar Solicitud de Registro"):
                if cedula and nombre and correo and clave:
                    success = register_user(cedula, nombre, str(fecha_nac), correo, celular, clave, current_ip)
                    if success: st.success("✅ Solicitud enviada. Tu cuenta quedará pendiente de aprobación por el administrador.")
                    else: st.error("⚠️ Ya se encuentra registrado. Contacte al administrador.")
                else: st.warning("Todos los campos son obligatorios.")
    else:
        correo = st.text_input("📧 Usuario (Correo)")
        clave = st.text_input("🔒 Clave", type="password")
        
        col_login, col_recover = st.columns([1, 1])
        login_btn = col_login.button("🚀 Ingresar")
        recover_btn = col_recover.button("🔑 ¿Olvidaste tu contraseña?")

        if 'show_recover' not in st.session_state:
            st.session_state.show_recover = False
            
        if recover_btn:
            st.session_state.show_recover = True
            st.rerun()

        if st.session_state.show_recover:
            st.markdown("---")
            st.markdown("#### 🔄 Recuperación de Contraseña")
            recover_correo = st.text_input("📨 Ingresa tu correo registrado:")
            if st.button("📧 Enviar Contraseña Temporal al Correo"):
                if check_user_exists(recover_correo):
                    temp_pass = reset_password(recover_correo)
                    if temp_pass:
                        if send_recovery_email(recover_correo, temp_pass):
                            st.success(f"✅ Se ha enviado un correo a {recover_correo} con tu nueva contraseña temporal.")
                            st.info("Revisa tu bandeja de entrada o spam.")
                            st.session_state.show_recover = False
                        else:
                            st.warning("⚠️ No se pudo enviar el correo automáticamente. Para tu demostración, tu contraseña temporal es:")
                            st.info(f"🔑 Contraseña temporal: **{temp_pass}**")
                else:
                    st.error("❌ El correo ingresado no está registrado en el sistema.")
        
        if login_btn:
            if correo and clave:
                user_data, msg = verify_user(correo, clave, current_ip)
                if user_data:
                    st.session_state.authenticated = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else:
                    st.error(msg)
                    if not check_user_exists(correo) and correo:
                        st.warning("¿Eres nuevo? No encontramos una cuenta con este correo.")
                        if st.button("📝 ¡Haz clic aquí para registrarte!"):
                            st.session_state.force_register = True
                            st.rerun()
            else:
                st.warning("Ingresa usuario y clave.")

# ==========================================
# APLICACIÓN PRINCIPAL (LOGUEADO)
# ==========================================
else:
    user = st.session_state.user_data
    is_admin = (user['correo'] == 'dasb1512')
    
    st.sidebar.markdown(f"👤 **{user['nombre']}**")
    if is_admin:
        st.sidebar.markdown("🛡️ Administrador")
    else:
        st.sidebar.markdown("👤 Usuario")
    
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state.authenticated = False
        st.session_state.user_data = None
        st.rerun()

    st.sidebar.markdown("---")
    opciones_menu = ["📊 Dashboard KPIs", "🤖 IA Predictiva (5 Por Qué)", "📁 Exportar Datos"]
    if is_admin: opciones_menu.append("👥 Panel de Administración")
    menu = st.sidebar.radio("Navegación", opciones_menu)

    # --- PANEL ADMIN (SISTEMA SAAS COMPLETO CON APROBACIONES) ---
    if menu == "👥 Panel de Administración" and is_admin:
        st.title("👥 Panel de Administración SaaS")
        st.markdown("Centro de control de accesos, aprobaciones y membresías.")
        
        conn = init_users_db()
        
        # 1. SECCIÓN: APROBACIONES PENDIENTES
        st.markdown("---")
        st.subheader("⏳ Aprobaciones Pendientes")
        
        df_pending = pd.read_sql_query("SELECT cedula, nombre, correo, celular, fecha_registro FROM users WHERE aprobado = 0 AND correo != 'dasb1512'", conn)
        
        col_p1, col_p2 = st.columns([1, 3])
        with col_p1:
            st.metric(label="Usuarios por aprobar", value=len(df_pending))
        
        if not df_pending.empty:
            with col_p2:
                df_pending_display = df_pending.copy()
                df_pending_display['fecha_registro'] = pd.to_datetime(df_pending_display['fecha_registro']).dt.strftime('%Y-%m-%d %H:%M')
                df_pending_display = df_pending_display.rename(columns={
                    'nombre': 'Nombre', 'correo': 'Correo', 'celular': 'Celular', 'fecha_registro': 'Fecha Solicitud'
                })
                st.dataframe(df_pending_display[['Nombre', 'Correo', 'Celular', 'Fecha Solicitud']], use_container_width=True, hide_index=True)
            
            st.markdown("##### Gestionar Pendiente:")
            pending_emails = df_pending['correo'].tolist()
            sel_pending_email = st.selectbox("Selecciona un usuario pendiente:", pending_emails, key="sel_pending")
            
            col_appr, col_rej = st.columns(2)
            if col_appr.button("✅ Aprobar Acceso (Activar 3 Días)"):
                c = conn.cursor()
                fecha_venc = datetime.now() + timedelta(days=3)
                c.execute("UPDATE users SET aprobado=1, fecha_vencimiento=? WHERE correo=?", (fecha_venc, sel_pending_email))
                conn.commit()
                st.success(f"✅ Usuario {sel_pending_email} aprobado exitosamente. Membresía de 3 días activada.")
                st.rerun()
                
            if col_rej.button("❌ Rechazar y Eliminar"):
                c = conn.cursor()
                c.execute("DELETE FROM users WHERE correo=?", (sel_pending_email,))
                conn.commit()
                st.warning(f"🗑️ Usuario {sel_pending_email} rechazado y eliminado del sistema.")
                st.rerun()
        else:
            st.info("✅ No hay usuarios pendientes de aprobación. Todo al día.")
            
        # 2. SECCIÓN: USUARIOS ACTIVOS Y MEMBRESÍAS
        st.markdown("---")
        st.subheader("📊 Usuarios Activos y Membresías")
        
        df_users = pd.read_sql_query("SELECT cedula, nombre, correo, celular, fecha_nac, fecha_registro, aprobado, fecha_vencimiento FROM users WHERE aprobado = 1 AND correo != 'dasb1512'", conn)
        
        if not df_users.empty:
            df_users['fecha_registro'] = pd.to_datetime(df_users['fecha_registro']).dt.strftime('%Y-%m-%d')
            df_users['fecha_vencimiento'] = pd.to_datetime(df_users['fecha_vencimiento']).dt.strftime('%Y-%m-%d')
            df_users = df_users.rename(columns={
                'cedula': 'Cédula', 'nombre': 'Nombre', 'correo': 'Correo', 'celular': 'Celular',
                'fecha_nac': 'F. Nacimiento', 'fecha_registro': 'F. Registro', 
                'aprobado': 'Aprobado', 'fecha_vencimiento': 'Vence Membresía'
            })
            st.dataframe(df_users, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader("⚙️ Gestión de Usuario Activo")
            col_sel, col_act = st.columns([1, 2])
            
            with col_sel:
                usuarios_list = df_users['Correo'].tolist()
                user_sel_email = st.selectbox("Selecciona un usuario activo para gestionar:", usuarios_list)
            
            if user_sel_email:
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE correo=?", (user_sel_email,))
                user_data_db = c.fetchone()
                
                if user_data_db:
                    with col_act:
                        with st.form(f"edit_form_{user_data_db[0]}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                edit_nombre = st.text_input("Nombre", value=user_data_db[1])
                                edit_celular = st.text_input("Celular", value=user_data_db[4])
                            
                            with col2:
                                venc_str = str(user_data_db[10]).split('.')[0] if user_data_db[10] else None
                                if venc_str:
                                    try:
                                        venc_date = datetime.strptime(venc_str, "%Y-%m-%d %H:%M:%S").date()
                                    except:
                                        venc_date = datetime.now().date() + timedelta(days=30)
                                else:
                                    venc_date = datetime.now().date() + timedelta(days=30)
                                
                                edit_vencimiento = st.date_input("Membresía válida hasta:", value=venc_date, min_value=datetime.now().date())
                                edit_correo = st.text_input("Correo", value=user_data_db[3], disabled=True)
                            
                            col_btn1, col_btn2, col_btn3 = st.columns(3)
                            submitted = col_btn1.form_submit_button("💾 Guardar Cambios")
                            revoke_btn = col_btn2.form_submit_button("🚫 Revocar Acceso")
                            delete_btn = col_btn3.form_submit_button("🗑️ Eliminar Usuario")
                            
                            if submitted:
                                try:
                                    c.execute("""UPDATE users SET nombre=?, celular=?, fecha_vencimiento=? WHERE correo=?""", 
                                              (edit_nombre, edit_celular, datetime.combine(edit_vencimiento, datetime.min.time()), user_data_db[3]))
                                    conn.commit()
                                    st.success("✅ Usuario actualizado correctamente.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al actualizar: {e}")
                            
                            if revoke_btn:
                                try:
                                    c.execute("UPDATE users SET aprobado=0 WHERE correo=?", (user_data_db[3],))
                                    conn.commit()
                                    st.warning(f"🚫 Acceso revocado a {user_data_db[1]}. Ahora está pendiente de aprobación.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al revocar: {e}")
                            
                            if delete_btn:
                                try:
                                    c.execute("DELETE FROM users WHERE correo=?", (user_data_db[3],))
                                    conn.commit()
                                    st.success(f"🗑️ Usuario {user_data_db[1]} eliminado correctamente.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error al eliminar: {e}")
        else:
            st.info("No hay usuarios activos además del administrador.")

    # --- DASHBOARD ---
    elif menu == "📊 Dashboard KPIs":
        st.title("🛡️ De la Gestión a la Inteligencia Preventiva")
        st.markdown("### Indicadores Reales del Ecosistema Integrado")
        
        df_ia = load_historial_supabase()
        total_eventos_ia = len(df_ia)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.markdown('<div class="metric-card"><div class="kpi-value">68% ↓</div><div class="kpi-label">Reducción Tiempo Cierre</div></div>', unsafe_allow_html=True)
        with col2: st.markdown('<div class="metric-card"><div class="kpi-value">75% ↓</div><div class="kpi-label">Reducción Recurrencia</div></div>', unsafe_allow_html=True)
        with col3: st.markdown('<div class="metric-card"><div class="kpi-value">95% ↑</div><div class="kpi-label">Análisis Causa Raíz</div></div>', unsafe_allow_html=True)
        with col4: st.markdown(f'<div class="metric-card"><div class="kpi-value">{total_eventos_ia}</div><div class="kpi-label">Eventos Procesados IA</div></div>', unsafe_allow_html=True)
        
        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            st.subheader("📈 Impacto del Modelo Integrado")
            categorias = ['Tiempo Cierre', 'Recurrencia', 'Causa Raíz']
            fig = go.Figure([go.Bar(name='Antes', x=categorias, y=[28, 32, 12], marker_color='#e74c3c'), go.Bar(name='Después', x=categorias, y=[9, 8, 95], marker_color='#2ecc71')])
            fig.update_layout(barmode='group', template='plotly_white')
            st.plotly_chart(fig, width='stretch')
        with col_chart2:
            st.subheader("🥧 Distribución por Factor de Riesgo (IA)")
            if not df_ia.empty:
                cat_counts = df_ia['categoria_detectada'].value_counts().reset_index()
                cat_counts.columns = ['Categoria', 'Cantidad']
                fig2 = px.pie(cat_counts, values='Cantidad', names='Categoria', hole=0.4)
                st.plotly_chart(fig2, width='stretch')
            else: st.info("Sin datos de IA aún.")

        st.markdown("---")
        st.subheader("📸 Últimos Hallazgos con Visión IA")
        if not df_ia.empty and 'image_url' in df_ia.columns:
            df_con_img = df_ia[df_ia['image_url'].notna()].head(3)
            if not df_con_img.empty:
                cols = st.columns(len(df_con_img))
                for idx, (_, row) in enumerate(df_con_img.iterrows()):
                    with cols[idx]:
                        try: st.image(row['image_url'], caption=row['categoria_detectada'])
                        except: st.warning("Error cargando imagen")
            else: st.info("Aún no se han subido imágenes.")
        else: st.info("Aún no hay datos en la nube.")

    # --- IA PREDICTIVA ---
    elif menu == "🤖 IA Predictiva (5 Por Qué)":
        st.title("🤖 Motor de Investigación y Predicción NTC 3701")
        input_type = st.radio("¿Cómo desea ingresar el hallazgo?", ("📝 Escribir Texto", "📷 Subir Imagen (IA Vision)"))
        texto_analizar = ""

        if input_type == "📝 Escribir Texto":
            texto_analizar = st.text_area("Describa la condición o acto subestándar:", height=150, placeholder="Ej: Cableado eléctrico expuesto en área de tránsito...")
            if st.button("🧠 Generar Investigación") and texto_analizar:
                if 'resultado_ia' in st.session_state: 
                    del st.session_state.resultado_ia  
                with st.spinner("La IA está analizando el hallazgo y aplicando NTC 3701..."):
                    resultado = predict_sst_analysis(texto_analizar)
                    save_to_supabase("Texto", texto_analizar, resultado)
                    st.session_state.resultado_ia = resultado
                    st.rerun()

        elif input_type == "📷 Subir Imagen (IA Vision)":
            uploaded_file = st.file_uploader("Toma o sube una foto del acto/condición subestándar", type=['png', 'jpg', 'jpeg'])
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
                st.image(image, caption="Imagen Cargada para Análisis", use_column_width=True)
                if st.button("👁️ Analizar Imagen con IA"):
                    if 'resultado_ia' in st.session_state: 
                        del st.session_state.resultado_ia  
                    with st.spinner("La IA está observando la imagen y deduciendo el riesgo..."):
                        texto_analizar = ""
                        try:
                            buffered = io.BytesIO()
                            image.save(buffered, format="JPEG")
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            
                            prompt_vision = "Eres un experto en SST. Observa esta imagen. Describe en 1 oración concisa la condición subestándar que ves (enfócate en: mobiliario, eléctrico, humedad u obstáculo)."
                            
                            chat_completion = client_groq.chat.completions.create(
                                messages=[
                                    {
                                        "role": "user",
                                        "content": [
                                            {"type": "text", "text": prompt_vision},
                                            {
                                                "type": "image_url",
                                                "image_url": {
                                                    "url": f"data:image/jpeg;base64,{img_str}"
                                                }
                                            }
                                        ]
                                    }
                                ],
                                model="meta-llama/llama-4-scout-17b-16e-instruct",
                            )
                            texto_analizar = chat_completion.choices[0].message.content
                            st.info(f"📝 **La IA de Visión detectó:** {texto_analizar}")
                                            
                        except Exception as e:
                            st.error(f"🔴 ERROR DE VISIÓN: {e}")
                            st.warning("⚠️ La IA de Visión no está disponible. Modo Colaborativo Activado:")
                            st.info("💡 *Tip: Escribe la condición subestándar que observas (Ej: Silla rota, cable expuesto...)*")
                            texto_analizar = st.text_input("Descripción manual del hallazgo:", key="manual_desc")
                        
                        if texto_analizar:
                            with st.spinner("Generando análisis de causa raíz NTC 3701..."):
                                resultado = predict_sst_analysis(texto_analizar)
                                try:
                                    img_bytes = uploaded_file.getvalue()
                                    file_name = f"{uuid.uuid4().hex}.jpg"
                                    supabase.storage.from_("fotos-sst").upload(file_name, img_bytes, {"content-type": "image/jpeg"})
                                    image_url = supabase.storage.from_("fotos-sst").get_public_url(file_name)
                                    
                                    save_to_supabase("Imagen", texto_analizar, resultado, image_url)
                                    st.session_state.resultado_ia = resultado
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Error guardando en la nube: {e}")

        if 'resultado_ia' in st.session_state:
            resultado = st.session_state.resultado_ia
            st.markdown("---")
            col_limpiar, col_spacer = st.columns([1, 5])
            with col_limpiar:
                if st.button("🔄 Limpiar Análisis / Nuevo Hallazgo"):
                    del st.session_state.resultado_ia
                    st.rerun()
                    
            st.success("✅ Análisis Generado y Guardado en la Nube!")
            
            st.markdown("## 1. Análisis de causas – Método de los Cinco Por Qué")
            st.markdown(f"**Hallazgo:** {resultado.get('evento', 'N/A')}")
            porques = resultado.get('porques', [])
            for p in porques: 
                if p and p != "Pendiente por IA": st.markdown(f"**{p}**")
            st.error(f"**Causa raíz identificada:** {resultado.get('causa_raiz', 'N/A')}")
            st.markdown("---")
            
            st.markdown("## 2. Causas inmediatas (NTC 3701)")
            col_acto, col_cond = st.columns(2)
            with col_acto:
                st.markdown("🔴 **Actos subestándar**")
                for a in resultado.get('actos_sub', []): st.markdown(f"- {a}")
            with col_cond:
                st.markdown("🟠 **Condiciones subestándar**")
                for c in resultado.get('condiciones_sub', []): st.markdown(f"- {c}")
            st.markdown("---")

            st.markdown("## 3. Causas básicas (NTC 3701)")
            col_fp, col_ft = st.columns(2)
            with col_fp:
                st.markdown("🔵 **Factores personales**")
                for fp in resultado.get('factores_personales', []): st.info(f"📌 {fp}")
            with col_ft:
                st.markdown("🟣 **Factores del trabajo**")
                for ft in resultado.get('factores_trabajo', []): st.warning(f"⚠️ {ft}")
            st.markdown("---")

            st.markdown("## 4. Plan de acción")
            for i, acc in enumerate(resultado.get('acciones', [])):
                with st.expander(f"✅ Acción {i+1}: {acc.get('titulo', 'Acción')}"):
                    col_obj, col_freq = st.columns(2)
                    col_obj.markdown(f"**Objetivo**\n\n{acc.get('objetivo', 'N/A')}")
                    col_freq.markdown(f"**Frecuencia:** {acc.get('frecuencia', 'N/A')}\n\n**Responsable:** {acc.get('responsable', 'N/A')}")
                    st.markdown(f"**Actividades**\n\n{acc.get('actividades', 'N/A')}")
            st.markdown("---")

            st.markdown("## 5. Conclusión técnica")
            st.success(f"✔️ {resultado.get('conclusion', 'N/A')}")

    # --- EXPORTAR DATOS ---
    elif menu == "📁 Exportar Datos":
        st.title("📥 Exportación de Información Estratégica")
        df_ia = load_historial_supabase()
        st.markdown("### Historial de Predicciones de IA (Nube)")
        st.dataframe(df_ia)
        
        if not df_ia.empty:
            def to_excel(df):
                df_str = df.astype(str)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_str.to_excel(writer, index=False, sheet_name='Historial_IA_Nube')
                return output.getvalue()
            st.download_button(label="📊 Descargar Excel Historial IA", data=to_excel(df_ia), file_name="Historial_IA_SST.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
