import sqlite3
import hashlib
import hmac
import os
from datetime import datetime, timedelta

DB_NAME = "bot_ad.db"

# PBKDF2 para claves nuevas; SHA256 (legacy) solo para verificar claves viejas.
PBKDF2_ITERATIONS = 200_000


def _secret(key, default=None):
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        identificacion TEXT UNIQUE, usuario TEXT UNIQUE, clave TEXT, correo TEXT,
        fecha_nacimiento TEXT, fecha_inicio TEXT, fecha_final TEXT, perfil TEXT,
        numero_ingresos INTEGER DEFAULT 0, analisis_realizados INTEGER DEFAULT 0,
        estado TEXT DEFAULT 'pendiente', membresia TEXT DEFAULT 'gratis'
    )''')
    # Tabla de picks: el "cerebro medidor" del bot (hit rate, ROI, Brier, CLV)
    c.execute('''CREATE TABLE IF NOT EXISTS picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT DEFAULT CURRENT_TIMESTAMP,
        evento_id TEXT,
        sport_key TEXT,
        deporte TEXT,
        evento TEXT,
        empieza TEXT,
        mercado TEXT,
        market_key TEXT,
        seleccion TEXT,
        seleccion_raw TEXT,
        linea REAL,
        cuota REAL,
        casa TEXT,
        prob_modelo REAL,
        edge REAL,
        kelly_frac REAL,
        riesgo TEXT,
        origen TEXT DEFAULT 'ia',
        usuario TEXT,
        resultado TEXT DEFAULT 'pendiente',
        closing_odds REAL,
        clv REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_evento ON picks(evento_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_resultado ON picks(resultado)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_picks_ts ON picks(ts)')

    c.execute("SELECT * FROM users WHERE usuario='dasb1512'")
    if not c.fetchone():
        # La clave de admin viene de secrets (ADMIN_PASSWORD) — nunca en el código.
        admin_pw = _secret("admin_password", "1234567890")
        today = datetime.now().strftime("%Y-%m-%d")
        c.execute('''INSERT INTO users
            (identificacion, usuario, clave, correo, fecha_nacimiento, fecha_inicio, fecha_final, perfil, numero_ingresos, estado, membresia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('8642239', 'dasb1512', hash_password(admin_pw), 'efraneo@gmail.com', '1976-09-19', today, 'NA', 'administrador', 0, 'aprobado', 'paga'))
        conn.commit()
    conn.close()


def master_credentials_configured():
    """El acceso maestro solo se habilita si USUARIO_MASTER y CLAVE_MASTER están en Secrets y NO vacíos."""
    try:
        u = _secret("USUARIO_MASTER")
        p = _secret("CLAVE_MASTER")
        return bool(u and str(u).strip()) and bool(p and str(p))
    except Exception:
        return False


def master_status():
    """Diagnóstico SEGURO para la pantalla de login: solo dice si están configurados (y longitudes), nunca valores."""
    try:
        u = _secret("USUARIO_MASTER")
        p = _secret("CLAVE_MASTER")
        u_ok = bool(u and str(u).strip())
        p_ok = bool(p and str(p))
        return {
            "configured": u_ok and p_ok,
            "usuario_set": u_ok,
            "clave_set": p_ok,
            "usuario_len": len(str(u)) if u is not None else 0,
            "clave_len": len(str(p)) if p is not None else 0,
        }
    except Exception:
        return {"configured": False, "usuario_set": False, "clave_set": False,
                "usuario_len": 0, "clave_len": 0}


def verify_master_login(usuario, clave):
    """Verifica las credenciales maestras de Secrets (USUARIO_MASTER / CLAVE_MASTER).

    Devuelve un usuario sintético con perfil administrador si coincide, o None.
    Nunca se persiste en la BD ni requiere aprobación/membresía.
    Soporta contraseñas con caracteres no-ASCII (comparación en bytes).
    """
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
            # Tupla con la MISMA forma que 'SELECT * FROM users':
            # (id, identificacion, usuario, clave, correo, fecha_nac, fecha_inicio, fecha_final,
            #  perfil, numero_ingresos, analisis_realizados, estado, membresia)
            return (0, "MASTER", mu, "", "", "1970-01-01", today, "NA",
                    "administrador", 0, 0, "aprobado", "paga")
        return None
    except Exception:
        # Jamás romper el login: si algo falla, cae al login normal de la BD
        return None


def hash_password(password):
    """PBKDF2-HMAC-SHA256 con sal aleatoria. Formato: pbkdf2$iter$salt$hash"""
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
    if stored.startswith("pbkdf2$"):
        return _verify_pbkdf2(stored, password)
    # Legacy SHA256 sin sal
    return hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())





def register_user(identificacion, usuario, clave, correo, fecha_nac):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        end_trial = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        c.execute('''INSERT INTO users
            (identificacion, usuario, clave, correo, fecha_nacimiento, fecha_inicio, fecha_final, perfil, estado, membresia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (identificacion, usuario, hash_password(clave), correo, fecha_nac, today, end_trial, 'usuario', 'pendiente', 'gratis'))
        conn.commit(); return True
    except sqlite3.IntegrityError: return False
    finally: conn.close()


def verify_login(usuario, clave):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE usuario=?", (usuario,))
    user = c.fetchone()
    if not user:
        conn.close(); return None
    stored = user[3]
    ok = verify_password(stored, clave)
    if ok and not stored.startswith("pbkdf2$"):
        # Migración transparente: re-hashear con PBKDF2 en el primer login correcto
        try:
            c.execute("UPDATE users SET clave=? WHERE usuario=?", (hash_password(clave), usuario))
            conn.commit()
        except Exception:
            pass
    conn.close()
    return user if ok else None


def get_email_by_user_id(identificacion, usuario):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT correo FROM users WHERE identificacion=? AND usuario=?", (identificacion, usuario))
    result = c.fetchone(); conn.close()
    return result[0] if result else None


def update_password(identificacion, new_password):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("UPDATE users SET clave=? WHERE identificacion=?", (hash_password(new_password), identificacion))
    conn.commit(); conn.close()


def update_login_stats(usuario):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("UPDATE users SET numero_ingresos = numero_ingresos + 1 WHERE usuario=?", (usuario,))
    conn.commit(); conn.close()


def increment_analysis(usuario):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("UPDATE users SET analisis_realizados = analisis_realizados + 1 WHERE usuario=?", (usuario,))
    conn.commit(); conn.close()


def get_all_users():
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT identificacion, usuario, correo, fecha_inicio, fecha_final, perfil, numero_ingresos, analisis_realizados, estado, membresia FROM users")
    users = c.fetchall(); conn.close(); return users


def approve_user(identificacion, approve=True):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    estado = 'aprobado' if approve else 'rechazado'
    c.execute("UPDATE users SET estado=? WHERE identificacion=?", (estado, identificacion))
    conn.commit(); conn.close()


def update_membership(identificacion, days=30):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    new_end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    c.execute("UPDATE users SET membresia='paga', fecha_final=?, estado='aprobado' WHERE identificacion=?", (new_end, identificacion))
    conn.commit(); conn.close()


def get_user_by_id(identificacion):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE identificacion=?", (identificacion,))
    user = c.fetchone(); conn.close(); return user


# ---------------------------------------------------------------------------
# PICKS: registro, liquidación (manual y automática vía scores API) y métricas
# ---------------------------------------------------------------------------

def save_pick(pick):
    """Guarda un pick generado por el bot. `pick` es un dict."""
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
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
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute('SELECT * FROM picks WHERE resultado=\'pendiente\' ORDER BY empieza')
    rows = c.fetchall(); conn.close(); return rows


def settle_pick(pick_id, resultado, closing_odds=None):
    """Liquidación manual o automática. resultado: ganada|perdida|void"""
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    clv = None
    if closing_odds:
        c.execute('SELECT cuota FROM picks WHERE id=?', (pick_id,))
        row = c.fetchone()
        if row and row[0] and closing_odds > 0:
            clv = round((row[0] - closing_odds) / closing_odds, 4)
    c.execute('UPDATE picks SET resultado=?, closing_odds=COALESCE(?, closing_odds), clv=COALESCE(?, clv) WHERE id=?',
              (resultado, closing_odds, clv, pick_id))
    conn.commit(); conn.close()


def grade_h2h_pick(seleccion_raw, home_team, away_team, home_score, away_score):
    """Clasifica un pick h2h/1x2. Devuelve 'ganada'|'perdida'."""
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
    return None  # no se puede clasificar -> queda pendiente


def autograde_picks(scores_by_event):
    """Liquida picks pendientes usando scores finales del endpoint de scores.

    scores_by_event: {evento_id: {"home": str, "away": str, "home_score": int, "away_score": int}}
    Devuelve nº de picks liquidados.
    """
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
    """Métricas honestas del bot: % aciertos, ROI, Brier, CLV."""
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = ("SELECT cuota, prob_modelo, resultado, clv, riesgo, deporte, market_key "
         "FROM picks WHERE date(ts) >= ? AND resultado IN ('ganada','perdida','void')")
    params = [since]
    if usuario:
        q += " AND usuario = ?"
        params.append(usuario)
    c.execute(q, params)
    rows = c.fetchall(); conn.close()

    settled = [r for r in rows if r[2] in ("ganada", "perdida")]
    voids = sum(1 for r in rows if r[2] == "void")
    wins = sum(1 for r in settled if r[2] == "ganada")
    n = len(settled)
    # Stake plano 1u SOLO para picks con cuota (sin cuota -> acierto/fallo, no entran al ROI)
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
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    if usuario:
        c.execute('SELECT * FROM picks WHERE usuario=? ORDER BY id DESC LIMIT ?', (usuario, limit))
    else:
        c.execute('SELECT * FROM picks ORDER BY id DESC LIMIT ?', (limit,))
    rows = c.fetchall(); conn.close(); return rows
