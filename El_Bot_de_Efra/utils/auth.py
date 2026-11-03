# utils/auth.py
# ==========================================================
# Gestión de usuarios y sesiones (control IP, aprobaciones
# de admins, límites diarios de acceso, migraciones).
# ==========================================================

import os
import sqlite3
import bcrypt
import logging
import pandas as pd
from datetime import datetime, timedelta, date
import socket
import typing
from utils.security import cifrar, descifrar

# utils/auth.py (añadir al inicio, cerca de otros imports)
try:
    from utils.db import leer_activos_por_categoria as leer_activos_por_categoria_db
    def leer_activos_por_categoria():
        return leer_activos_por_categoria_db()
except Exception:
    def leer_activos_por_categoria():
        return ({"Top": ["BTCUSDT", "ETHUSDT"]}, ["BTCUSDT", "ETHUSDT"])


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "usuarios.db")

_logger = logging.getLogger("utils.auth")
if not _logger.handlers:
    handler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | [auth] %(message)s")
    handler.setFormatter(fmt)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)


def _get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ----------------------------------------------------------
# Migraciones
# ----------------------------------------------------------
def _ensure_tables_and_columns():
    """Crea/actualiza tablas y columnas necesarias (usuarios, sesiones, historial_sesiones, ip_requests, ip_autorizadas)."""
    try:
        conn = _get_connection()
        cur = conn.cursor()

        # Tabla usuarios base
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                clave TEXT NOT NULL,
                nombre TEXT,
                correo TEXT,
                es_admin INTEGER DEFAULT 0,
                ver_senales INTEGER DEFAULT 1,
                usar_ia INTEGER DEFAULT 1,
                ver_historial INTEGER DEFAULT 1,
                ver_backtesting INTEGER DEFAULT 0,
                estado TEXT DEFAULT 'activo',
                creado_en TEXT
            )
        """)

        # Revisar columnas existentes
        cur.execute("PRAGMA table_info(usuarios)")
        cols = [r["name"] for r in cur.fetchall()]

        # Extras
        extras = {
            "estado_actual": "TEXT DEFAULT 'habilitado'",
            "ganancias_periodo": "TEXT DEFAULT ''",
            "ip_autorizada": "TEXT DEFAULT ''",
            "clave1_binance": "TEXT DEFAULT ''",
            "clave2_binance": "TEXT DEFAULT ''",
            "cambio_clave": "INTEGER DEFAULT 0",
            "celular": "TEXT DEFAULT ''",
            "fecha_nacimiento": "TEXT DEFAULT ''",
            "firma_tratamiento_datos": "BLOB",
            # 🔹 nuevas columnas para compatibilidad
            "estado_ip": "TEXT DEFAULT 'pendiente'",
            "ip_aprobada": "TEXT DEFAULT ''",
            "duracion_acumulada_seg": "INTEGER DEFAULT 0",
            "fecha_acumulada": "TEXT DEFAULT ''"
        }
        for col, typ in extras.items():
            if col not in cols:
                try:
                    cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {typ}")
                    _logger.info(f"➕ Migración: añadida columna '{col}' en usuarios")
                except Exception:
                    _logger.warning(f"No se pudo añadir columna '{col}' (quizá ya existe)")

        # Tabla sesiones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                ip TEXT,
                inicio TEXT,
                ultimo_ping TEXT,
                activo INTEGER DEFAULT 1,
                duracion_acumulada_seg INTEGER DEFAULT 0,
                fecha_acumulada TEXT DEFAULT '',
                FOREIGN KEY(usuario) REFERENCES usuarios(usuario) ON DELETE CASCADE
            )
        """)

        # Tabla historial de sesiones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS historial_sesiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                inicio TEXT,
                fin TEXT,
                duracion_seg INTEGER,
                fecha TEXT,
                FOREIGN KEY(usuario) REFERENCES usuarios(usuario) ON DELETE CASCADE
            )
        """)

        # Tabla peticiones IP
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ip_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                ip TEXT NOT NULL,
                ts TEXT,
                estado TEXT DEFAULT 'pendiente',
                admin TEXT DEFAULT '',
                nota TEXT DEFAULT ''
            )
        """)

        # Tabla IPs autorizadas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ip_autorizadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                ip TEXT NOT NULL,
                aprobado_por TEXT,
                ts TEXT
            )
        """)

        conn.commit()
        conn.close()
        _logger.info("✅ Esquema DB OK (auth)")
    except Exception as e:
        _logger.error(f"❌ Migraciones DB error: {e}")


def inicializar_db():
    _ensure_tables_and_columns()


def inicializar_tabla_sesiones():
    _ensure_tables_and_columns()


# ----------------------------------------------------------
# Password helpers
# ----------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

# ----------------------------------------------------------
# CRUD usuarios
# ----------------------------------------------------------
def get_user(usuario: str) -> typing.Optional[dict]:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        data = dict(row)

        # Intentar descifrar claves de Binance si existen (no modificar DB)
        try:
            from utils.security import descifrar
            # campos en DB: clave1_binance, clave2_binance
            if data.get("clave1_binance"):
                dec1 = descifrar(data.get("clave1_binance"))
                data["clave1_binance"] = dec1 if dec1 is not None else data.get("clave1_binance")
            if data.get("clave2_binance"):
                dec2 = descifrar(data.get("clave2_binance"))
                data["clave2_binance"] = dec2 if dec2 is not None else data.get("clave2_binance")
        except Exception as e:
            # no rompemos si module security no está disponible
            _logger.warning(f"security.descifrar fallo: {e}")

        return data
    except Exception as e:
        _logger.error(f"❌ get_user error: {e}")
        return None


def listar_usuarios() -> pd.DataFrame:
    try:
        conn = _get_connection()
        df = pd.read_sql_query(
            "SELECT usuario, nombre, correo, es_admin, estado, creado_en, ip_autorizada FROM usuarios",
            conn
        )
        conn.close()
        return df
    except Exception as e:
        _logger.error(f"❌ listar_usuarios error: {e}")
        return pd.DataFrame()


def ensure_user(usuario: str, clave: str = None, **kwargs) -> bool:
    try:
        existing = get_user(usuario)
        conn = _get_connection()
        cur = conn.cursor()

        # Pre-procesar claves Binance: cifrar antes de almacenar
        try:
            from utils.security import cifrar
        except Exception:
            cifrar = None

        # Si vienen claves plain en kwargs -> cifrarlas para almacenarlas
        almacenables = {}
        if "clave1_binance" in kwargs and kwargs.get("clave1_binance") is not None:
            raw1 = kwargs.get("clave1_binance")
            if cifrar:
                almacenables["clave1_binance"] = cifrar(raw1) or raw1
            else:
                almacenables["clave1_binance"] = raw1
            # quitar del kwargs original para evitar doble manejo
            kwargs.pop("clave1_binance", None)

        if "clave2_binance" in kwargs and kwargs.get("clave2_binance") is not None:
            raw2 = kwargs.get("clave2_binance")
            if cifrar:
                almacenables["clave2_binance"] = cifrar(raw2) or raw2
            else:
                almacenables["clave2_binance"] = raw2
            kwargs.pop("clave2_binance", None)

        if existing is None:
            cur.execute("""
                INSERT INTO usuarios (usuario, clave, nombre, correo, es_admin,
                    ver_senales, usar_ia, ver_historial, ver_backtesting,
                    estado, creado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usuario,
                hash_password(clave) if clave else "",
                kwargs.get("nombre", usuario),
                kwargs.get("correo"),
                int(kwargs.get("es_admin", False)),
                int(kwargs.get("ver_senales", True)),
                int(kwargs.get("usar_ia", True)),
                int(kwargs.get("ver_historial", True)),
                int(kwargs.get("ver_backtesting", False)),
                kwargs.get("estado", "activo"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            # Si había claves para almacenar, actualizarlas en la misma transacción
            if almacenables:
                campos = []
                vals = []
                for k, v in almacenables.items():
                    campos.append(f"{k} = ?")
                    vals.append(v)
                vals.append(usuario)
                cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE usuario = ?", tuple(vals))

        else:
            campos, valores = [], []
            if clave is not None:
                campos.append("clave = ?")
                valores.append(hash_password(clave))
            for k in [
                "nombre", "correo", "es_admin", "ver_senales", "usar_ia",
                "ver_historial", "ver_backtesting", "estado",
                "ip_autorizada", "celular", "fecha_nacimiento"
            ]:
                if k in kwargs:
                    v = int(kwargs[k]) if isinstance(kwargs[k], bool) else kwargs[k]
                    campos.append(f"{k} = ?")
                    valores.append(v)

            # Añadir claves cifradas si vienen
            for k, v in almacenables.items():
                campos.append(f"{k} = ?")
                valores.append(v)

            if campos:
                valores.append(usuario)
                cur.execute(f"UPDATE usuarios SET {', '.join(campos)} WHERE usuario = ?", tuple(valores))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _logger.error(f"❌ ensure_user error: {e}")
        return False


def agregar_usuario(usuario: str, clave: str, rol: str = "user",
                    nombre: str = None, correo: str = None,
                    ip_autorizada: str = "") -> bool:
    try:
        es_admin = True if rol == "admin" else False
        return ensure_user(
            usuario, clave,
            nombre=nombre or usuario,
            correo=correo,
            es_admin=es_admin,
            ver_senales=True,
            usar_ia=True,
            ver_historial=True,
            ver_backtesting=es_admin,
            estado="activo",
            ip_autorizada=ip_autorizada
        )
    except Exception as e:
        _logger.error(f"❌ agregar_usuario error: {e}")
        return False


def eliminar_usuario(usuario: str) -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM usuarios WHERE usuario = ?", (usuario,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _logger.error(f"❌ eliminar_usuario error: {e}")
        return False


# ----------------------------------------------------------
# Bootstrap admin
# ----------------------------------------------------------
from utils.logger import log_info, log_error

def bootstrap_admin(usuario: str = "admin", clave: str = "1234") -> bool:
    try:
        ok = ensure_user(
            usuario, clave,
            nombre="Administrador",
            es_admin=True,
            ver_senales=True,
            usar_ia=True,
            ver_historial=True,
            ver_backtesting=True,
            estado="activo"
        )
        if ok:
            log_info(f"✅ bootstrap_admin listo para usuario={usuario}",
                     archivo="auth.py", funcion="bootstrap_admin")
        else:
            log_error("⚠️ ensure_user devolvió False en bootstrap_admin",
                      archivo="auth.py", funcion="bootstrap_admin")
        return ok
    except Exception as e:
        log_error(e, archivo="auth.py", funcion="bootstrap_admin")
        return False


# ----------------------------------------------------------
# Login con control IP y tiempo
# ----------------------------------------------------------
def _get_today_seconds_for_user(usuario: str) -> int:
    """Devuelve segundos ya usados hoy por el usuario."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        hoy = date.today().strftime("%Y-%m-%d")
        cur.execute("SELECT duracion_acumulada_seg, fecha_acumulada FROM sesiones WHERE usuario = ?", (usuario,))
        row = cur.fetchone()
        conn.close()
        if row and row["fecha_acumulada"] == hoy:
            return int(row["duracion_acumulada_seg"] or 0)
        return 0
    except Exception as e:
        _logger.error(f"Error get_today_seconds_for_user: {e}")
        return 0


def login_usuario(usuario: str, clave: str, ip_actual: str = None) -> dict:
    """
    Verifica credenciales y condiciones de acceso.
    Retorna dict con datos o con {"error": motivo}.
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT usuario, nombre, clave, es_admin, ip_autorizada, estado
            FROM usuarios WHERE usuario = ?
        """, (usuario,))
        row = cur.fetchone()
        conn.close()

        if not row:
            _logger.warning(f"Usuario no encontrado: {usuario}")
            return {"error": "usuario_no_existe"}

        db_usuario = row["usuario"]
        db_nombre = row["nombre"] or db_usuario
        db_clave = row["clave"]
        es_admin = bool(row["es_admin"])
        ip_aut = row["ip_autorizada"] if "ip_autorizada" in row.keys() else ""
        estado = row["estado"]

        # Estado
        if estado.lower() != "activo":
            return {"error": "usuario_inhabilitado"}

        # Validar clave
        try:
            pass_valid = bcrypt.checkpw(clave.encode("utf-8"), db_clave.encode("utf-8"))
        except Exception:
            pass_valid = (clave == db_clave)

        if not pass_valid:
            return {"error": "clave_incorrecta"}

        # Admin → acceso directo
        if es_admin:
            return {
                "usuario": db_usuario,
                "nombre": db_nombre,
                "es_admin": True,
                "ip_ok": True
            }

        # IP autorizada
        if ip_aut:
            if not ip_actual:
                return {"error": "ip_no_detectada"}
            if ip_aut != ip_actual:
                return {"error": "ip_no_autorizada", "ip_autorizada": ip_aut}
        else:
            return {"error": "ip_pendiente_autorizacion"}

        # Tiempo diario (2h = 7200 seg)
        usados = _get_today_seconds_for_user(db_usuario)
        if usados >= 2 * 3600:
            return {"error": "tiempo_excedido", "usados_seg": usados}

        # OK
        return {
            "usuario": db_usuario,
            "nombre": db_nombre,
            "es_admin": False,
            "ip_ok": True,
            "usados_seg": usados
        }

    except Exception as e:
        _logger.error(e)
        return {"error": "error_interno"}


# ----------------------------------------------------------
# Gestión de solicitudes IP
# ----------------------------------------------------------
def request_ip_access(usuario: str, ip: str) -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO ip_requests (usuario, ip, ts, estado) VALUES (?, ?, ?, 'pendiente')",
                    (usuario, ip, ts))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _logger.error(f"Error request_ip_access: {e}")
        return False


def list_pending_ip_requests() -> list:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, usuario, ip, ts FROM ip_requests WHERE estado = 'pendiente'")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        _logger.error(f"Error list_pending_ip_requests: {e}")
        return []


def approve_ip_request(request_id: int, admin_usuario: str) -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT usuario, ip FROM ip_requests WHERE id = ? AND estado = 'pendiente'", (request_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return False
        usuario = row["usuario"]
        ip = row["ip"]

        # Límite de 10 usuarios distintos
        cur.execute("SELECT COUNT(DISTINCT usuario) AS c FROM ip_autorizadas")
        c = cur.fetchone()["c"]
        if int(c) >= 10:
            cur.execute("UPDATE ip_requests SET estado = 'denegada', admin = ?, nota = ? WHERE id = ?",
                        (admin_usuario, "Límite 10 usuarios alcanzado", request_id))
            conn.commit()
            conn.close()
            return False

        # Insertar y actualizar
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO ip_autorizadas (usuario, ip, aprobado_por, ts) VALUES (?, ?, ?, ?)",
                    (usuario, ip, admin_usuario, ts))
        cur.execute("UPDATE usuarios SET ip_autorizada = ? WHERE usuario = ?", (ip, usuario))
        cur.execute("UPDATE ip_requests SET estado = 'aprobada', admin = ? WHERE id = ?", (admin_usuario, request_id))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _logger.error(f"Error approve_ip_request: {e}")
        return False


def deny_ip_request(request_id: int, admin_usuario: str, nota: str = "") -> bool:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE ip_requests SET estado = 'denegada', admin = ?, nota = ? WHERE id = ?",
                    (admin_usuario, nota, request_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        _logger.error(f"Error deny_ip_request: {e}")
        return False

# ----------------------------------------------------------
# Registrar / actualizar sesiones
# ----------------------------------------------------------
def registrar_sesion(usuario: str, ip: str = "desconocida"):
    """Registra inicio de sesión o mantiene sesión activa."""
    try:
        conn = _get_connection()
        cur = conn.cursor()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT id FROM sesiones WHERE usuario = ?", (usuario,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE sesiones SET ultimo_ping = ?, ip = ?, activo = 1
                WHERE usuario = ?
            """, (ahora, ip, usuario))
        else:
            cur.execute("""
                INSERT INTO sesiones
                (usuario, ip, inicio, ultimo_ping, activo, duracion_acumulada_seg, fecha_acumulada)
                VALUES (?, ?, ?, ?, 1, 0, '')
            """, (usuario, ip, ahora, ahora))
        conn.commit()
        conn.close()

        # 🔔 Notificación Telegram de login
        try:
            from telegram_alertas import send_telegram_alert
            mensaje = (
                f"✅ <b>Inicio de sesión</b>\n"
                f"👤 Usuario: <b>{usuario}</b>\n"
                f"🕒 Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🌐 IP: {ip}"
            )
            send_telegram_alert(mensaje)

            # Opcional: gráfico login
            try:
                from telegram_alertas import send_plot_login
                send_plot_login(usuario)
            except Exception as e:
                _logger.warning(f"No se pudo enviar gráfico login: {e}")
        except Exception as e:
            _logger.warning(f"No se pudo enviar alerta Telegram login: {e}")

    except Exception as e:
        _logger.error(f"❌ registrar_sesion error: {e}")


def actualizar_ping(usuario: str):
    try:
        conn = _get_connection()
        cur = conn.cursor()
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE sesiones SET ultimo_ping = ? WHERE usuario = ?", (ahora, usuario))
        conn.commit()
        conn.close()
    except Exception as e:
        _logger.error(f"❌ actualizar_ping error: {e}")


# ----------------------------------------------------------
# Cerrar sesión con cálculo de duración acumulada
# ----------------------------------------------------------
def cerrar_sesion(usuario: str):
    """
    Cierra sesión del usuario:
    - Calcula duración desde inicio hasta ahora (seguro con hora internet).
    - Actualiza duracion_acumulada_seg diario en usuarios.
    - Guarda registro en historial_sesiones.
    - Marca sesión como inactiva.
    Retorna: (duracion_sesion_seg, acumulado_hoy_seg, restante_seg)
    """
    try:
        conn = _get_connection()
        cur = conn.cursor()

        # Hora segura (internet, fallback UTC)
        ahora = get_internet_time()
        hoy = ahora.strftime("%Y-%m-%d")

        # Buscar sesión activa
        cur.execute("SELECT inicio FROM sesiones WHERE usuario = ? AND activo = 1", (usuario,))
        row = cur.fetchone()
        if not row or not row["inicio"]:
            conn.close()
            return 0, 0, 0  # nada que cerrar

        inicio = datetime.strptime(row["inicio"], "%Y-%m-%d %H:%M:%S")
        duracion_seg = int((ahora - inicio).total_seconds())

        # Reset acumulado si el día cambió
        cur.execute("SELECT duracion_acumulada_seg, fecha_acumulada FROM usuarios WHERE usuario = ?", (usuario,))
        urow = cur.fetchone()
        acumulado = 0
        if urow:
            if urow["fecha_acumulada"] != hoy:
                acumulado = 0
            else:
                acumulado = int(urow["duracion_acumulada_seg"] or 0)

        acumulado += duracion_seg

        # Guardar acumulado
        cur.execute("""
            UPDATE usuarios
            SET duracion_acumulada_seg = ?, fecha_acumulada = ?
            WHERE usuario = ?
        """, (acumulado, hoy, usuario))

        # Guardar historial
        cur.execute("""
            INSERT INTO historial_sesiones (usuario, inicio, fin, duracion_seg, fecha)
            VALUES (?, ?, ?, ?, ?)
        """, (usuario, row["inicio"], ahora.strftime("%Y-%m-%d %H:%M:%S"), duracion_seg, hoy))

        # Marcar sesión inactiva
        cur.execute("UPDATE sesiones SET activo = 0 WHERE usuario = ?", (usuario,))

        conn.commit()
        conn.close()

        _logger.info(f"✅ Sesión cerrada: {usuario}, sesión={duracion_seg}s, acumulado={acumulado}s")
        return duracion_seg, acumulado, max(0, 7200 - acumulado)  # seg
    except Exception as e:
        _logger.error(f"❌ cerrar_sesion error: {e}")
        return 0, 0, 0


def listar_sesiones_activas() -> pd.DataFrame:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(sesiones)")
        scols = [r["name"] for r in cur.fetchall()]

        base_query = "SELECT usuario, ip, inicio"
        if "ultimo_ping" in scols:
            base_query += ", ultimo_ping"
        base_query += " FROM sesiones WHERE activo = 1"

        df = pd.read_sql_query(base_query, conn)
        conn.close()

        # Si no hay sesiones activas → devolver lista de usuarios activos
        if df.empty:
            users = pd.read_sql_query(
                "SELECT usuario, correo, es_admin, estado FROM usuarios",
                _get_connection()
            )
            users["ip"] = ""
            users["inicio"] = ""
            users["ultimo_ping"] = ""
            return users[["usuario", "ip", "inicio", "ultimo_ping"]]

        return df
    except Exception as e:
        _logger.error(f"❌ listar_sesiones_activas error: {e}")
        return pd.DataFrame()


# ----------------------------------------------------------
# Obtener permisos
# ----------------------------------------------------------
def obtener_permisos(usuario: str) -> dict:
    try:
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT es_admin, ver_senales, usar_ia, ver_historial, ver_backtesting
            FROM usuarios WHERE usuario = ?
        """, (usuario,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return {}

        return {
            "es_admin": bool(row["es_admin"]),
            "ver_senales": bool(row["ver_senales"]),
            "usar_ia": bool(row["usar_ia"]),
            "ver_historial": bool(row["ver_historial"]),
            "ver_backtesting": bool(row["ver_backtesting"]),
        }
    except Exception as e:
        log_error(e, archivo="auth.py", funcion="obtener_permisos")
        return {}


# ----------------------------------------------------------
# Actualizar clave
# ----------------------------------------------------------
def actualizar_clave(usuario: str, nueva_clave: str) -> bool:
    try:
        hashed = hash_password(nueva_clave)
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE usuarios
            SET clave = ?, cambio_clave = cambio_clave + 1
            WHERE usuario = ?
        """, (hashed, usuario))
        conn.commit()
        conn.close()
        log_info(f"Clave actualizada: {usuario}", archivo="auth.py", funcion="actualizar_clave")
        return True
    except Exception as e:
        log_error(e, archivo="auth.py", funcion="actualizar_clave")
        return False



def get_internet_time() -> datetime:
    """Devuelve la hora actual desde internet (worldtimeapi), fallback UTC."""
    
    import requests

    try:
        url = "http://worldtimeapi.org/api/timezone/America/Bogota"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return datetime.fromisoformat(data["datetime"].split(".")[0])
    except Exception as e:
        _logger.warning(f"⚠️ Error obteniendo hora internet, fallback UTC: {e}")
    return datetime.utcnow()


# ----------------------------------------------------------
# Helpers IP cliente
# ----------------------------------------------------------
def _get_client_ip() -> str:
    try:
        xff = os.environ.get("HTTP_X_FORWARDED_FOR") or os.environ.get("X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    except Exception:
        pass
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip and host_ip != "127.0.0.1":
            return host_ip
    except Exception:
        pass
    return "127.0.0.1"


# ----------------------------------------------------------
# Export helpers
# ----------------------------------------------------------
__all__ = [
    "DB_PATH", "inicializar_db", "inicializar_tabla_sesiones",
    "hash_password", "check_password",
    "get_user", "listar_usuarios", "ensure_user", "agregar_usuario", "eliminar_usuario",
    "bootstrap_admin",
    "login_usuario", "obtener_permisos",
    "registrar_sesion", "actualizar_ping", "cerrar_sesion", "listar_sesiones_activas",
    "request_ip_access", "list_pending_ip_requests", "approve_ip_request", "deny_ip_request",
    "_get_client_ip", "actualizar_clave"
]

