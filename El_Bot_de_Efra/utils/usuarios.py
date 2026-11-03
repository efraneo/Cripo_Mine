# utils/usuarios.py
import os
import re
import sqlite3
import hashlib
from typing import Dict, Any, Optional

try:
    import pandas as pd
except Exception:
    pd = None  # Para que no falle si este módulo se usa sin pandas

# Ruta del DB (en el directorio raíz del proyecto)
DB_PATH = os.path.join(os.getcwd(), "usuarios.db")

# ---------- Utilidades internas ----------

def _is_sha256_hex(s: str) -> bool:
    if not isinstance(s, str):
        return False
    return bool(re.fullmatch(r"[A-Fa-f0-9]{64}", s or ""))

def _sha256(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    return sqlite3.connect(DB_PATH)

# ---------- Bootstrap / esquema ----------

def crear_tabla_si_no_existe():
    con = _conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario TEXT PRIMARY KEY,
            clave   TEXT NOT NULL,
            nombre  TEXT,
            correo  TEXT,
            es_admin INTEGER DEFAULT 0,
            ver_senales INTEGER DEFAULT 0,
            usar_ia INTEGER DEFAULT 0,
            ver_historial INTEGER DEFAULT 0,
            ver_backtesting INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'activo'
        )
    """)
    con.commit()
    con.close()

def _str2bool(x) -> int:
    if isinstance(x, bool):
        return 1 if x else 0
    if x is None:
        return 0
    s = str(x).strip().lower()
    return 1 if s in ("1","true","t","yes","y","si","sí") else 0

def _estado_norm(x) -> str:
    s = str(x or "").strip().lower()
    return "activo" if s in ("activo","active","1","true","si","sí","yes","y") else "inactivo"

def seed_desde_csv(csv_path: str = "claves.csv", forzar_hash: bool = True) -> int:
    """
    Carga/actualiza usuarios desde claves.csv.
    Columnas esperadas: usuario,clave,nombre,correo,es_admin,ver_senales,usar_ia,ver_historial,ver_backtesting,estado
    - forzar_hash=True -> guarda todas las claves como SHA256.
    Devuelve la cantidad de filas procesadas.
    """
    if pd is None:
        return 0
    if not os.path.exists(csv_path):
        return 0

    df = pd.read_csv(csv_path, dtype=str).fillna("")
    req = ["usuario","clave","nombre","correo","es_admin","ver_senales","usar_ia","ver_historial","ver_backtesting","estado"]
    for col in req:
        if col not in df.columns:
            # Si faltan columnas, completa con valores por defecto
            if col == "estado":
                df[col] = "activo"
            elif col in ("es_admin","ver_senales","usar_ia","ver_historial","ver_backtesting"):
                df[col] = "0"
            else:
                df[col] = ""

    con = _conn()
    cur = con.cursor()

    n = 0
    for _, r in df.iterrows():
        usuario = str(r["usuario"]).strip()
        if not usuario:
            continue
        clave_file = str(r["clave"]).strip()
        if forzar_hash:
            clave_db = _sha256(clave_file)
        else:
            # Mantener como esté en el CSV
            clave_db = clave_file if _is_sha256_hex(clave_file) else clave_file

        nombre = str(r["nombre"]).strip()
        correo = str(r["correo"]).strip()
        es_admin        = _str2bool(r["es_admin"])
        ver_senales     = _str2bool(r["ver_senales"])
        usar_ia         = _str2bool(r["usar_ia"])
        ver_historial   = _str2bool(r["ver_historial"])
        ver_backtesting = _str2bool(r["ver_backtesting"])
        estado          = _estado_norm(r["estado"])

        cur.execute("""
            INSERT INTO usuarios (usuario, clave, nombre, correo, es_admin, ver_senales, usar_ia, ver_historial, ver_backtesting, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(usuario) DO UPDATE SET
                clave=excluded.clave,
                nombre=excluded.nombre,
                correo=excluded.correo,
                es_admin=excluded.es_admin,
                ver_senales=excluded.ver_senales,
                usar_ia=excluded.usar_ia,
                ver_historial=excluded.ver_historial,
                ver_backtesting=excluded.ver_backtesting,
                estado=excluded.estado
        """, (usuario, clave_db, nombre, correo, es_admin, ver_senales, usar_ia, ver_historial, ver_backtesting, estado))
        n += 1

    con.commit()
    con.close()
    return n

def migrar_passwords_a_sha256():
    """
    Si encuentra claves en texto plano, las migra a SHA256.
    No rompe si ya están en SHA256.
    """
    con = _conn()
    cur = con.cursor()
    cur.execute("SELECT usuario, clave FROM usuarios")
    rows = cur.fetchall()
    for usuario, clave in rows:
        if not _is_sha256_hex(clave):
            cur.execute("UPDATE usuarios SET clave=? WHERE usuario=?", (_sha256(clave), usuario))
    con.commit()
    con.close()

def ensure_db_bootstrap(csv_path: str = "claves.csv"):
    crear_tabla_si_no_existe()
    # Si la tabla está vacía y existe claves.csv, sembrar:
    con = _conn()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM usuarios")
    count = cur.fetchone()[0]
    con.close()
    if count == 0 and os.path.exists(csv_path):
        seed_desde_csv(csv_path, forzar_hash=True)
    # En cualquier caso, garantiza claves con SHA:
    migrar_passwords_a_sha256()

# ---------- API pública para la app ----------

def verificar_usuario(usuario: str, clave: str) -> bool:
    """
    Devuelve True si el usuario existe (estado='activo') y la clave coincide.
    Soporta DB con hash SHA256 o texto plano (compatibilidad), pero migra a SHA en bootstrap.
    """
    usuario = str(usuario or "").strip()
    if not usuario:
        return False

    try:
        con = _conn()
        cur = con.cursor()
        cur.execute("SELECT clave, estado FROM usuarios WHERE usuario=?", (usuario,))
        row = cur.fetchone()
        con.close()
        if not row:
            return False
        clave_guardada, estado = row[0], (row[1] or "inactivo").lower().strip()
        if estado != "activo":
            return False

        clave_input_hash = _sha256(clave or "")
        if _is_sha256_hex(clave_guardada):
            # Comparar hash con hash
            return clave_guardada.lower() == clave_input_hash.lower()
        else:
            # Compatibilidad: comparar texto plano
            return (clave_guardada == (clave or ""))
    except Exception:
        return False

def obtener_permisos(usuario: str) -> Dict[str, Any]:
    permisos = {
        "es_admin": False,
        "ver_senales": False,
        "usar_ia": False,
        "ver_historial": False,
        "ver_backtesting": False,
    }
    try:
        con = _conn()
        cur = con.cursor()
        cur.execute("""
            SELECT es_admin, ver_senales, usar_ia, ver_historial, ver_backtesting
            FROM usuarios WHERE usuario=?
        """, (str(usuario).strip(),))
        row = cur.fetchone()
        con.close()
        if row:
            permisos = {
                "es_admin": bool(row[0]),
                "ver_senales": bool(row[1]),
                "usar_ia": bool(row[2]),
                "ver_historial": bool(row[3]),
                "ver_backtesting": bool(row[4]),
            }
    except Exception:
        pass
    return permisos

def obtener_nombre(usuario: str) -> str:
    try:
        con = _conn()
        cur = con.cursor()
        cur.execute("SELECT nombre FROM usuarios WHERE usuario=?", (str(usuario).strip(),))
        row = cur.fetchone()
        con.close()
        return row[0] if row and row[0] else str(usuario)
    except Exception:
        return str(usuario)

def estado_usuario(usuario: str) -> str:
    try:
        con = _conn()
        cur = con.cursor()
        cur.execute("SELECT estado FROM usuarios WHERE usuario=?", (str(usuario).strip(),))
        row = cur.fetchone()
        con.close()
        return (row[0] or "inactivo") if row else "inactivo"
    except Exception:
        return "inactivo"
