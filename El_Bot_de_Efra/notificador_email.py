# notificador_email.py

import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from utils.logger import log_error

# ============================== 🔐 CARGA DE CONFIGURACIÓN ==============================

# Carga las variables desde el archivo de entorno
load_dotenv("clave_correo.env")

EMAIL_REMITENTE = os.getenv("CORREO_ORIGEN")
EMAIL_PASSWORD = os.getenv("CLAVE_CORREO")
EMAIL_SMTP = os.getenv("SERVIDOR_SMTP", "smtp.gmail.com")
EMAIL_PUERTO = int(os.getenv("PUERTO_SMTP", 587))
EMAIL_ADMIN = os.getenv("CORREO_ADMIN")


# ============================== 📧 ENVÍO DE EMAIL ==============================

def enviar_email(destino, asunto, cuerpo):
    """
    Envía un correo electrónico a un destinatario específico.
    """
    try:
        msg = EmailMessage()
        msg.set_content(cuerpo)
        msg["Subject"] = asunto
        msg["From"] = EMAIL_REMITENTE
        msg["To"] = destino

        with smtplib.SMTP(EMAIL_SMTP, EMAIL_PUERTO) as server:
            server.starttls()
            server.login(EMAIL_REMITENTE, EMAIL_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email enviado a {destino}")
        return True

    except Exception as e:
        log_error(e, archivo="notificador_email.py", funcion="enviar_email")
        print(f"❌ Error al enviar email: {e}")
        return False


# ============================== 📤 ALIAS PARA COMPATIBILIDAD ==============================

# Esto permite usar 'enviar_correo' en lugar de 'enviar_email' sin modificar otros archivos
enviar_correo = enviar_email
