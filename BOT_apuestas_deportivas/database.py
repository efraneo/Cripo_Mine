"""
Persistencia del Bot de Apuestas con DOBLE backend:
  • Supabase (Postgres) — si existen los secrets SUPABASE_URL y SUPABASE_KEY.
    Recomendado en producción (Streamlit Cloud: el disco se borra en cada redeploy).
    Esquema: SUPABASE_SCHEMA.sql
  • SQLite local (bot_ad.db) — respaldo para desarrollo/local (sin secrets).

API pública idéntica para ambos backends (ver usos en auth/betting_app/dashboard).
"""
import sqlite3
import hashlib
import hmac
import os
import requests
from datetime import datetime, timedelta

DB_NAME = "bot_ad.db"

PBKDF2_ITERATIONS = 200_000

USER_COLS = ["id", "identificacion", "usuario", "clave", "correo", "fecha_nacimiento",
             "fecha_inicio", "fecha_final", "perfil", "numero_ingresos",
             "analisis_realizados", "estado", "membresia"]
PICK_COLS = ["id", "ts", "evento_id", "sport_key", "deporte", "evento", "empieza",
             "mercado", "market_key", "seleccion", "seleccion_raw", "linea", "cuota",
             "casa", "prob_modelo", "edge", "kelly_frac", "riesgo", "origen",
             "usuario", "resultado", "closing_odds", "clv"]


def _secret(key, default=None):
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        try:
            return os.environ.get(key, default)
        except Exception:
            return default


# ---------------------------------------------------------------------------
# SUPABASE (PostgREST) — configuración y helper
# ---------------------------------------------------------------------------

def _supabase_config():
    try:
        url = _secret("SUPABASE_URL")
        key = _secret("SUPABASE_KEY")
    except Exception:
        url = key = None
    if url and key:
        url = str(url).strip().rstrip("/")
        key = str(key).strip()
        if url.startswith("http"):
            return url, key
    return None, None


def storage_mode():
    return "supabase" if _supabase_config()[0] else "sqlite"


def _sb(method, path, params=None, json_body=None, prefer=None, timeout=20):
    url, key = _supabase_config()
    if not url:
        raise RuntimeError("Supabase no configurado (SUPABASE_URL / SUPABASE_KEY)")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    return requests.request(method, f"{url}/rest/v1/{path}", params=params,
                            json=json_body, headers=headers, timeout=timeout)


def _sb_missing_table(response):
    if response is None:
        return False
    text = response.text.lower() if hasattr(response, "text") else ""
    return response.status_code in (404, 406) and ("pgrst205" in text or "relation" in text or "does not exist" in text)


_tables_state = None


def storage_status():
    """'sqlite' | 'supabase' | 'supabase-missing-tables'"""
    global _tables_state
    if storage_mode() != "supabase":
        return "sqlite"
    if _tables_state is None:
        try:
            r = _sb("GET", "users", params={"select": "id", "limit": 1})
            _tables_state = "supabase" if r.status_code == 200 else "supabase-missing-tables"
        except Exception:
            _tables_state = "supabase-missing-tables"
    return _tables_state


def _user_from_dict(d):
    if not d:
        return None
    return tuple(d.get(c) for c in USER_COLS)


def _pick_from_dict(d):
    return tuple(d.get(c) for c in PICK_COLS)


def _sqlite_connect():
    return sqlite3.connect(DB_NAME)


# ---------------------------------------------------------------------------
# Inicialización / siembra del admin
# ---------------------------------------------------------------------------

def init_db():
    if storage_status() == "supabase":
        _ensure_admin_supabase()
        return
    if storage_status() == "supabase-missing-tables":
        return  # La app mostrará las instrucciones para correr SUPABASE_SCHEMA.sql
    # ---------- SQLite ----------
    conn = _sqlite_connect()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identificacion TEXT UNIQUE, usuario TEXT UNIQUE, clave TEXT, correo TEXT,
        fecha_nacimiento TEXT, fecha_inicio TEXT, fecha_final TEXT, perfil TEXT,
        numero_ingresos INTEGER DEFAULT 0, analisis_realizados INTEGER DEFAULT 0,
        estado TEXT DEFAULT 'pendiente', membresia TEXT DEFAULT 'gratis'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        evento_id TEXT, sport_key TEXT, deporte TEXT, evento TEXT, empieza TEXT,
        mercado TEXT, market_key TEXT, seleccion TEXT, seleccion_raw TEXT, linea REAL,
        cuota REAL, casa TEXT, prob_modelo REAL, edge REAL, kelly_frac REAL,
        riesgo TEXT, origen TEXT DEFAULT 'ia', usuario TEXT,
        resultado TEXT DEFAULT 'pendiente', closing_odds REAL, clv REAL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS login_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        usuario TEXT, identificacion TEXT, es_master INTEGER DEFAULT 0,
        evento TEXT DEFAULT 'login', detalle TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_evento ON picks(evento_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_resultado ON picks(resultado)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_ts ON picks(ts)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_login_history_ts ON login_history(ts)')
    c.execute("SELECT * FROM users WHERE usuario='dasb1512'")
    if not c.fetchone():
        admin_pw = _secret("admin_password", "1234567890")
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute('''INSERT INTO users
            (identificacion, usuario, clave, correo, fecha_nacimiento, fecha_inicio, fecha_final, perfil, numero_ingresos, estado, membresia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('8642239', 'dasb1512', hash_password(admin_pw), 'efraneo@gmail.com', '1976-09-19', today, 'NA', 'administrador', 0, 'aprobado', 'paga'))
        conn.commit()
    conn.close()


def _ensure_admin_supabase():
    try:
        r = _sb("GET", "users", params={"usuario": "eq.dasb1512", "select": "id"})
        if r.status_code == 200 and r.json():
            return
        admin_pw = _secret("admin_password", "1234567890")
        today = datetime.now().strftime("%Y-%m-%d")
        payload = {
            "identificacion": "8642239", "usuario": "dasb1512", "clave": hash_password(admin_pw),
            "correo": "efraneo@gmail.com", "fecha_nacimiento": "1976-09-19",
            "fecha_inicio": today, "fecha_final": "NA", "perfil": "administrador",
            "numero_ingresos": 0, "estado": "aprobado", "membresia": "paga",
        }
        _sb("POST", "users", json_body=payload, prefer="return=minimal")
    except Exception:
        pass  # La siembra no debe tumbar la app


# ---------------------------------------------------------------------------
# Contraseñas: PBKDF2 con migración desde SHA256
# ---------------------------------------------------------------------------

def hash_password(password):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def _verify_pbkdf2(stored, password):
    try:
        _, iter_s, salt_hex, hash_hex = stored.split("$", 3)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iter_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def verify_password(stored, password):
    if stored and stored.startswith("pbkdf2$"):
        return _verify_pbkdf2(stored, password)
    return bool(stored) and hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())


def _rehash_if_legacy(stored, password):
    return None if (stored or "").startswith("pbkdf2$") else hash_password(password)


# ---------------------------------------------------------------------------
# Acceso maestro (Secrets USUARIO_MASTER / CLAVE_MASTER) — no toca la BD
# ---------------------------------------------------------------------------

def master_credentials_configured():
    try:
        u = _secret("USUARIO_MASTER")
        p = _secret("CLAVE_MASTER")
        return bool(u and str(u).strip()) and bool(p and str(p))
    except Exception:
        return False


def master_status():
    try:
        u = _secret("USUARIO_MASTER")
        p = _secret("CLAVE_MASTER")
        u_ok = bool(u and str(u).strip())
        p_ok = bool(p and str(p))
        return {"configured": u_ok and p_ok, "usuario_set": u_ok, "clave_set": p_ok,
                "usuario_len": len(str(u)) if u is not None else 0,
                "clave_len": len(str(p)) if p is not None else 0}
    except Exception:
        return {"configured": False, "usuario_set": False, "clave_set": False,
                "usuario_len": 0, "clave_len": 0}


def verify_master_login(usuario, clave):
    try:
        if not master_credentials_configured():
            return None
        mu = str(_secret("USUARIO_MASTER")).strip()
        mp = str(_secret("CLAVE_MASTER"))
        user_in = (usuario or "").strip()
        clave_in = clave or ""
        ok_user = hmac.compare_digest(mu.encode("utf-8"), user_in.encode("utf-8"))
        ok_pass = hmac.compare_digest(mp.encode("utf-8"), clave_in.encode("utf-8"))
        if ok_user and ok_pass:
            today = datetime.now().strftime("%Y-%m-%d")
            return (0, "MASTER", mu, "", "", "1970-01-01", today, "NA",
                    "administrador", 0, 0, "aprobado", "paga")
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Historial de ingresos (visible solo para el MASTER)
# ---------------------------------------------------------------------------

def log_login_event(usuario, identificacion=None, es_master=False, evento="login", detalle=None):
    try:
        if storage_status() == "supabase":
            _sb("POST", "login_history",
                json_body={"usuario": usuario, "identificacion": identificacion,
                           "es_master": bool(es_master), "evento": evento, "detalle": detalle},
                prefer="return=minimal")
            return
        if storage_status() == "supabase-missing-tables":
            return
        conn = _sqlite_connect()
        c = conn.cursor()
        c.execute('INSERT INTO login_history (usuario, identificacion, es_master, evento, detalle) VALUES (?, ?, ?, ?, ?)',
                  (usuario, identificacion, 1 if es_master else 0, evento, detalle))
        conn.commit(); conn.close()
    except Exception:
        pass  # el historial jamás debe impedir un login


def get_login_history(limit=100):
    out = []
    try:
        if storage_status() == "supabase":
            r = _sb("GET", "login_history",
                    params={"select": "ts,usuario,identificacion,es_master,evento,detalle",
                            "order": "ts.desc", "limit": limit})
            if r.status_code != 200:
                return []
            return r.json()
        if storage_status() == "sqlite":
            conn = _sqlite_connect()
            c = conn.cursor()
            c.execute('SELECT ts, usuario, identificacion, es_master, evento, detalle FROM login_history ORDER BY ts DESC LIMIT ?', (limit,))
            for row in c.fetchall():
                out.append({"ts": row[0], "usuario": row[1], "identificacion": row[2],
                            "es_master": bool(row[3]), "evento": row[4], "detalle": row[5]})
            conn.close()
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Usuarios — CRUD completo (el MASTER lo administra desde el panel)
# ---------------------------------------------------------------------------

def register_user(identificacion, usuario, clave, correo, fecha_nac):
    if storage_status() == "supabase-missing-tables":
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    end_trial = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    payload = {
        "identificacion": identificacion, "usuario": usuario, "clave": hash_password(clave),
        "correo": correo, "fecha_nacimiento": fecha_nac, "fecha_inicio": today,
        "fecha_final": end_trial, "perfil": "usuario", "estado": "pendiente", "membresia": "gratis",
    }
    if storage_status() == "supabase":
        try:
            r = _sb("POST", "users", json_body=payload, prefer="return=minimal")
            return r.status_code in (200, 201)
        except Exception:
            return False
    conn = _sqlite_connect(); c = conn.cursor()
    try:
        c.execute('''INSERT INTO users
            (identificacion, usuario, clave, correo, fecha_nacimiento, fecha_inicio, fecha_final, perfil, estado, membresia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (identificacion, usuario, payload["clave"], correo, fecha_nac, today, end_trial, 'usuario', 'pendiente', 'gratis'))
        conn.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def create_user(identificacion, usuario, clave, correo, fecha_nac="", perfil="usuario",
                estado="aprobado", membresia="paga", fecha_final="NA"):
    if storage_status() == "supabase-missing-tables":
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "identificacion": identificacion, "usuario": usuario, "clave": hash_password(clave),
        "correo": correo, "fecha_nacimiento": fecha_nac, "fecha_inicio": today,
        "fecha_final": fecha_final, "perfil": perfil, "estado": estado, "membresia": membresia,
    }
    if storage_status() == "supabase":
        try:
            r = _sb("POST", "users", json_body=payload, prefer="return=minimal")
            return r.status_code in (200, 201)
        except Exception:
            return False
    conn = _sqlite_connect(); c = conn.cursor()
    try:
        c.execute('''INSERT INTO users
            (identificacion, usuario, clave, correo, fecha_nacimiento, fecha_inicio, fecha_final, perfil, estado, membresia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (identificacion, usuario, payload["clave"], correo, fecha_nac, today, fecha_final, perfil, estado, membresia))
        conn.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_login(usuario, clave):
    if storage_status() == "supabase":
        try:
            r = _sb("GET", "users", params={"usuario": f"eq.{usuario}", "select": "*", "limit": 1})
            if r.status_code != 200:
                return None
            rows = r.json()
            if not rows:
                return None
            user = rows[0]
            stored = user.get("clave", "")
            if not verify_password(stored, clave):
                return None
            new_hash = _rehash_if_legacy(stored, clave)
            if new_hash:
                try:
                    _sb("PATCH", "users", params={"usuario": f"eq.{usuario}"},
                        json_body={"clave": new_hash}, prefer="return=minimal")
                except Exception:
                    pass
            return _user_from_dict(user)
        except Exception:
            return None
    if storage_status() == "supabase-missing-tables":
        return None
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE usuario=?", (usuario,))
    user = c.fetchone()
    if not user:
        conn.close(); return None
    stored = user[3]
    if not verify_password(stored, clave):
        conn.close(); return None
    new_hash = _rehash_if_legacy(stored, clave)
    if new_hash:
        try:
            c.execute("UPDATE users SET clave=? WHERE usuario=?", (new_hash, usuario))
            conn.commit()
        except Exception:
            pass
    conn.close(); return user


def get_email_by_user_id(identificacion, usuario):
    if storage_status() == "supabase":
        r = _sb("GET", "users", params={"identificacion": f"eq.{identificacion}",
                                        "usuario": f"eq.{usuario}", "select": "correo", "limit": 1})
        if r.status_code == 200:
            rows = r.json()
            return rows[0].get("correo") if rows else None
        return None
    if storage_status() == "supabase-missing-tables":
        return None
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT correo FROM users WHERE identificacion=? AND usuario=?", (identificacion, usuario))
    result = c.fetchone(); conn.close()
    return result[0] if result else None


def update_password(identificacion, new_password):
    set_user_password(identificacion, new_password)


def set_user_password(identificacion, new_password):
    hashed = hash_password(new_password)
    if storage_status() == "supabase":
        _sb("PATCH", "users", params={"identificacion": f"eq.{identificacion}"},
            json_body={"clave": hashed}, prefer="return=minimal")
        return
    if storage_status() == "supabase-missing-tables":
        return
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("UPDATE users SET clave=? WHERE identificacion=?", (hashed, identificacion))
    conn.commit(); conn.close()


def _bump_counter(usuario, column):
    if storage_status() == "supabase":
        try:
            r = _sb("GET", "users", params={"usuario": f"eq.{usuario}", "select": column, "limit": 1})
            rows = r.json() if r.status_code == 200 else []
            current = (rows[0].get(column) or 0) if rows else 0
            _sb("PATCH", "users", params={"usuario": f"eq.{usuario}"},
                json_body={column: current + 1}, prefer="return=minimal")
        except Exception:
            pass
        return
    if storage_status() == "supabase-missing-tables":
        return
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute(f"UPDATE users SET {column} = {column} + 1 WHERE usuario=?", (usuario,))
    conn.commit(); conn.close()


def update_login_stats(usuario):
    _bump_counter(usuario, "numero_ingresos")


def increment_analysis(usuario):
    _bump_counter(usuario, "analisis_realizados")


def get_all_users():
    """Proyección fija: identificacion, usuario, correo, fecha_inicio, fecha_final,
    perfil, numero_ingresos, analisis_realizados, estado, membresia"""
    cols = "identificacion,usuario,correo,fecha_inicio,fecha_final,perfil,numero_ingresos,analisis_realizados,estado,membresia"
    if storage_status() == "supabase":
        try:
            r = _sb("GET", "users", params={"select": cols, "order": "fecha_inicio"})
            if r.status_code != 200:
                return []
            return [tuple(row.get(c) for c in cols.split(",")) for row in r.json()]
        except Exception:
            return []
    if storage_status() == "supabase-missing-tables":
        return []
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT identificacion, usuario, correo, fecha_inicio, fecha_final, perfil, numero_ingresos, analisis_realizados, estado, membresia FROM users")
    users = c.fetchall(); conn.close(); return users


def approve_user(identificacion, approve=True):
    update_user_fields(identificacion, {"estado": "aprobado" if approve else "rechazado"})


def update_membership(identificacion, days=30):
    if storage_status() == "supabase":
        end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        _sb("PATCH", "users", params={"identificacion": f"eq.{identificacion}"},
            json_body={"membresia": "paga", "fecha_final": end, "estado": "aprobado"},
            prefer="return=minimal")
        return
    if storage_status() == "supabase-missing-tables":
        return
    conn = _sqlite_connect(); c = conn.cursor()
    new_end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("UPDATE users SET membresia='paga', fecha_final=?, estado='aprobado' WHERE identificacion=?", (new_end, identificacion))
    conn.commit(); conn.close()


def extend_membership(identificacion, extra_days=7):
    """Extiende la membresía N días DESDE HOY o desde el vencimiento, lo que sea mayor."""
    today = datetime.now()
    if storage_status() == "supabase":
        r = _sb("GET", "users", params={"identificacion": f"eq.{identificacion}", "select": "fecha_final", "limit": 1})
        base = today
        if r.status_code == 200 and r.json():
            raw = r.json()[0].get("fecha_final") or ""
            try:
                parsed = datetime.strptime(raw, "%Y-%m-%d")
                if parsed > today:
                    base = parsed
            except (ValueError, TypeError):
                pass
        new_end = (base + timedelta(days=extra_days)).strftime("%Y-%m-%d")
        _sb("PATCH", "users", params={"identificacion": f"eq.{identificacion}"},
            json_body={"membresia": "paga", "fecha_final": new_end, "estado": "aprobado"},
            prefer="return=minimal")
        return new_end
    if storage_status() == "supabase-missing-tables":
        return None
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT fecha_final FROM users WHERE identificacion=?", (identificacion,))
    row = c.fetchone()
    base = today
    if row and row[0] and row[0] != "NA":
        try:
            parsed = datetime.strptime(row[0], "%Y-%m-%d")
            if parsed > today:
                base = parsed
        except (ValueError, TypeError):
            pass
    new_end = (base + timedelta(days=extra_days)).strftime("%Y-%m-%d")
    c.execute("UPDATE users SET membresia='paga', fecha_final=?, estado='aprobado' WHERE identificacion=?", (new_end, identificacion))
    conn.commit(); conn.close()
    return new_end


def get_user_by_id(identificacion):
    if storage_status() == "supabase":
        try:
            r = _sb("GET", "users", params={"identificacion": f"eq.{identificacion}", "select": "*", "limit": 1})
            rows = r.json() if r.status_code == 200 else []
            return _user_from_dict(rows[0]) if rows else None
        except Exception:
            return None
    if storage_status() == "supabase-missing-tables":
        return None
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE identificacion=?", (identificacion,))
    user = c.fetchone(); conn.close(); return user


def update_user_fields(identificacion, fields):
    """CRUD del master: actualiza SOLO campos permitidos (nunca 'clave' ni 'id' directamente)."""
    allowed = {"identificacion", "usuario", "correo", "fecha_nacimiento", "fecha_inicio",
               "fecha_final", "perfil", "numero_ingresos", "analisis_realizados",
               "estado", "membresia"}
    clean = {k: v for k, v in (fields or {}).items() if k in allowed}
    if not clean:
        return False
    if storage_status() == "supabase":
        r = _sb("PATCH", "users", params={"identificacion": f"eq.{identificacion}"},
                json_body=clean, prefer="return=minimal")
        return r.status_code in (200, 204)
    if storage_status() == "supabase-missing-tables":
        return False
    conn = _sqlite_connect(); c = conn.cursor()
    sets = ", ".join(f"{k}=?" for k in clean)
    c.execute(f"UPDATE users SET {sets} WHERE identificacion=?", (*clean.values(), identificacion))
    conn.commit(); conn.close()
    return True


def delete_user(identificacion):
    if storage_status() == "supabase":
        r = _sb("DELETE", "users", params={"identificacion": f"eq.{identificacion}"},
                prefer="return=minimal")
        return r.status_code in (200, 204)
    if storage_status() == "supabase-missing-tables":
        return False
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("DELETE FROM users WHERE identificacion=?", (identificacion,))
    conn.commit(); conn.close()
    return True


# ---------------------------------------------------------------------------
# PICKS — registro y métricas
# ---------------------------------------------------------------------------

def save_pick(pick):
    if storage_status() == "supabase-missing-tables":
        return
    if storage_status() == "supabase":
        payload = {k: pick.get(k) for k in
                   ["evento_id", "sport_key", "deporte", "evento", "empieza", "mercado",
                    "market_key", "seleccion", "seleccion_raw", "linea", "cuota", "casa",
                    "prob_modelo", "edge", "kelly_frac", "riesgo", "origen", "usuario"]}
        _sb("POST", "picks", json_body=payload, prefer="return=minimal")
        return
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute('''INSERT INTO picks
        (evento_id, sport_key, deporte, evento, empieza, mercado, market_key, seleccion,
         seleccion_raw, linea, cuota, casa, prob_modelo, edge, kelly_frac, riesgo, origen, usuario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (pick.get("evento_id"), pick.get("sport_key"), pick.get("deporte"), pick.get("evento"),
         pick.get("empieza"), pick.get("mercado"), pick.get("market_key"), pick.get("seleccion"),
         pick.get("seleccion_raw"), pick.get("linea"), pick.get("cuota"), pick.get("casa"),
         pick.get("prob_modelo"), pick.get("edge"), pick.get("kelly_frac"),
         pick.get("riesgo"), pick.get("origen", "ia"), pick.get("usuario")))
    conn.commit(); conn.close()


def get_pending_picks():
    if storage_status() == "supabase":
        r = _sb("GET", "picks", params={"select": ",".join(PICK_COLS),
                                        "resultado": "eq.pendiente", "order": "empieza"})
        if r.status_code != 200:
            return []
        return [_pick_from_dict(d) for d in r.json()]
    if storage_status() == "supabase-missing-tables":
        return []
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute("SELECT * FROM picks WHERE resultado='pendiente' ORDER BY empieza")
    rows = c.fetchall(); conn.close(); return rows


def settle_pick(pick_id, resultado, closing_odds=None):
    clv = None
    if closing_odds:
        if storage_status() == "supabase":
            r = _sb("GET", "picks", params={"id": f"eq.{pick_id}", "select": "cuota", "limit": 1})
            rows = r.json() if r.status_code == 200 else []
            cuota = rows[0].get("cuota") if rows else None
        else:
            conn = _sqlite_connect(); c = conn.cursor()
            c.execute('SELECT cuota FROM picks WHERE id=?', (pick_id,))
            row = c.fetchone(); conn.close()
            cuota = row[0] if row else None
        if cuota and closing_odds > 0:
            clv = round((cuota - closing_odds) / closing_odds, 4)
    body = {"resultado": resultado}
    if closing_odds is not None:
        body["closing_odds"] = closing_odds
    if clv is not None:
        body["clv"] = clv
    if storage_status() == "supabase":
        _sb("PATCH", "picks", params={"id": f"eq.{pick_id}"}, json_body=body, prefer="return=minimal")
        return
    if storage_status() == "supabase-missing-tables":
        return
    conn = _sqlite_connect(); c = conn.cursor()
    c.execute('UPDATE picks SET resultado=?, closing_odds=COALESCE(?, closing_odds), clv=COALESCE(?, clv) WHERE id=?',
              (resultado, closing_odds, clv, pick_id))
    conn.commit(); conn.close()


def grade_h2h_pick(seleccion_raw, home_team, away_team, home_score, away_score):
    def norm(s):
        return (s or "").strip().lower()

    if home_score > away_score:
        winner = home_team
    elif away_score > home_score:
        winner = away_team
    else:
        winner = "draw"

    pick = norm(seleccion_raw)
    if pick in ("draw", "empate", "x"):
        return "ganada" if winner.lower() == "draw" else "perdida"
    return "ganada" if pick == norm(winner) else "perdida"


def grade_totals_pick(seleccion_raw, linea, home_score, away_score):
    total = (home_score or 0) + (away_score or 0)
    raw = (seleccion_raw or "").strip().lower()
    if raw.startswith("over") or raw.startswith("más") or raw.startswith("mayor"):
        if total == linea:
            return "void"
        return "ganada" if total > linea else "perdida"
    if raw.startswith("under") or raw.startswith("menos") or raw.startswith("menor"):
        if total == linea:
            return "void"
        return "ganada" if total < linea else "perdida"
    return None


def autograde_picks(scores_by_event):
    pending = get_pending_picks()
    graded = 0
    for row in pending:
        (pid, ts, evento_id, sport_key, deporte, evento, empieza, mercado, market_key,
         seleccion, seleccion_raw, linea, cuota, casa, prob_modelo, edge, kelly_frac,
         riesgo, origen, usuario, resultado, closing_odds, clv) = row
        sc = scores_by_event.get(evento_id)
        if not sc:
            continue
        hs, a_s = sc.get("home_score"), sc.get("away_score")
        if hs is None or a_s is None:
            continue
        result = None
        mk = (market_key or "").lower()
        if mk in ("h2h", "1x2", "moneyline"):
            result = grade_h2h_pick(seleccion_raw, sc.get("home"), sc.get("away"), hs, a_s)
        elif mk == "totals":
            result = grade_totals_pick(seleccion_raw, linea if linea is not None else 2.5, hs, a_s)
        if result:
            settle_pick(pid, result)
            graded += 1
    return graded


def get_pick_stats(days=90, usuario=None):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = []
    if storage_status() == "supabase":
        params = {"select": "cuota,prob_modelo,resultado,clv,riesgo,deporte,market_key",
                  "resultado": "in.(ganada,perdida,void)",
                  "ts": f"gte.{since}T00:00:00Z"}
        if usuario:
            params["usuario"] = f"eq.{usuario}"
        try:
            r = _sb("GET", "picks", params=params)
            if r.status_code == 200:
                rows = [(d.get("cuota"), d.get("prob_modelo"), d.get("resultado"), d.get("clv"),
                         d.get("riesgo"), d.get("deporte"), d.get("market_key")) for d in r.json()]
        except Exception:
            rows = []
    elif storage_status() == "sqlite":
        q = ("SELECT cuota, prob_modelo, resultado, clv, riesgo, deporte, market_key "
             "FROM picks WHERE date(ts) >= ? AND resultado IN ('ganada','perdida','void')")
        params = [since]
        if usuario:
            q += " AND usuario = ?"
            params.append(usuario)
        conn = _sqlite_connect(); c = conn.cursor()
        c.execute(q, params)
        rows = c.fetchall(); conn.close()

    settled = [r for r in rows if r[2] in ("ganada", "perdida")]
    voids = sum(1 for r in rows if r[2] == "void")
    wins = sum(1 for r in settled if r[2] == "ganada")
    n = len(settled)
    with_cuota = [r for r in settled if r[0] and r[0] > 0]
    staked = sum(1.0 for _ in with_cuota)
    ret = sum(r[0] for r in with_cuota if r[2] == "ganada")
    roi = ((ret - staked) / staked * 100) if staked else 0.0
    hit = (wins / n * 100) if n else 0.0

    probs = [r[1] for r in settled if r[1] is not None]
    brier = None
    if probs:
        outcomes = [1 if r[2] == "ganada" else 0 for r in settled if r[1] is not None]
        brier = round(sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs), 4)

    clvs = [r[3] for r in rows if r[3] is not None]
    avg_clv = round(sum(clvs) / len(clvs), 4) if clvs else None

    def breakout(idx):
        groups = {}
        for r in settled:
            groups.setdefault(r[idx] or "?", []).append(r)
        out = {}
        for k, g in groups.items():
            w = sum(1 for x in g if x[2] == "ganada")
            g_cuota = [x for x in g if x[0] and x[0] > 0]
            st = float(len(g_cuota))
            rt = sum(x[0] for x in g_cuota if x[2] == "ganada")
            out[k] = {"n": len(g), "acierto_pct": round(w / len(g) * 100, 1),
                      "roi_pct": round((rt - st) / st * 100, 1) if st else None}
        return out

    return {
        "n_liquidados": n,
        "aciertos": wins,
        "acierto_pct": round(hit, 1),
        "roi_pct": round(roi, 2),
        "brier": brier,
        "avg_clv": avg_clv,
        "voids": voids,
        "por_riesgo": breakout(4),
        "por_deporte": breakout(5),
        "por_mercado": breakout(6),
    }


def get_recent_picks(limit=30, usuario=None):
    if storage_status() == "supabase":
        params = {"select": ",".join(PICK_COLS), "order": "id.desc", "limit": limit}
        if usuario:
            params["usuario"] = f"eq.{usuario}"
        try:
            r = _sb("GET", "picks", params=params)
            return [_pick_from_dict(d) for d in r.json()] if r.status_code == 200 else []
        except Exception:
            return []
    if storage_status() == "sqlite-missing-tables" or storage_status() == "supabase-missing-tables":
        return []
    conn = _sqlite_connect(); c = conn.cursor()
    if usuario:
        c.execute('SELECT * FROM picks WHERE usuario=? ORDER BY id DESC LIMIT ?', (usuario, limit))
    else:
        c.execute('SELECT * FROM picks ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall(); conn.close(); return rows
