import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime
import pytz
import database as db

COL_TZ = pytz.timezone('America/Bogota')


def _secret(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def fetch_final_scores(odds_api_key):
    """Trae scores finales (hasta 3 días atrás) para liquidar picks automáticamente."""
    scores_by_event = {}
    conn_sports = set()
    pending = db.get_pending_picks()
    for row in pending:
        if row[3]:
            conn_sports.add(row[3])
    for sport_key in conn_sports:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/",
                params={"apiKey": odds_api_key, "daysFrom": 3},
                timeout=20,
            )
            if r.status_code != 200:
                st.warning(f"Scores {sport_key}: HTTP {r.status_code}")
                continue
            for ev in r.json():
                if not ev.get("completed"):
                    continue
                scores = ev.get("scores") or []
                score_map = {}
                for s in scores:
                    try:
                        score_map[s.get("name")] = float(s.get("score"))
                    except (TypeError, ValueError):
                        score_map[s.get("name")] = None
                home = ev.get("home_team"); away = ev.get("away_team")
                scores_by_event[ev.get("id")] = {
                    "home": home, "away": away,
                    "home_score": score_map.get(home),
                    "away_score": score_map.get(away),
                }
        except Exception as e:
            st.warning(f"Error consultando scores de {sport_key}: {e}")
    return scores_by_event


def _log_crud(detalle):
    u = (st.session_state.get("user") or [None] * 3)[2]
    db.log_login_event(u, identificacion="MASTER", es_master=True, evento="crud", detalle=detalle)


def show_master_crud():
    st.subheader("🛠️ Panel MASTER — Control Total (solo tú)")
    st.caption("Edición completa de usuarios: autorizar, extender tiempo, editar todo, crear, borrar y resetear claves. "
               "Cada acción queda registrada en el Historial de Ingresos como evento `crud`.")
    if db.storage_status() == "supabase-missing-tables":
        st.error("Supabase está configurado pero faltan las tablas. Corre `SUPABASE_SCHEMA.sql` y recarga.")
        return

    users = db.get_all_users()
    df = pd.DataFrame(users, columns=['Identificación', 'Usuario', 'Correo', 'F. Inicio', 'F. Final',
                                      'Perfil', 'Ingresos', 'Análisis', 'Estado', 'Membresía']) if users else pd.DataFrame(columns=['Identificación', 'Usuario', 'Correo', 'F. Inicio', 'F. Final', 'Perfil', 'Ingresos', 'Análisis', 'Estado', 'Membresía'])

    t_edit, t_new, t_del, t_ext, t_key, t_hist = st.tabs([
        "✏️ Editar", "➕ Crear", "🗑 Borrar", "⏳ Extender tiempo", "🔑 Reset clave", "📜 Historial de ingresos"])

    # ---------- EDITAR ----------
    with t_edit:
        if df.empty:
            st.info("No hay usuarios aún.")
        else:
            st.caption("Edita sólo estas columnas y presiona **Aplicar cambios**. `Usuario`/`Identificación` no se tocan aquí.")
            edited = st.data_editor(df, disabled=["Identificación", "Usuario"],
                                    num_rows="fixed", width="stretch", key="master_editor")
            if st.button("💾 Aplicar cambios", type="primary"):
                col_map = {"Correo": "correo", "F. Inicio": "fecha_inicio", "F. Final": "fecha_final",
                           "Perfil": "perfil", "Estado": "estado", "Membresía": "membresia",
                           "Ingresos": "numero_ingresos", "Análisis": "analisis_realizados"}
                orig = df.set_index("Identificación")
                new = edited.set_index("Identificación")
                cambios = 0
                resumen = []
                for idx in orig.index:
                    diff = {}
                    for col, field in col_map.items():
                        if str(orig.loc[idx, col]) != str(new.loc[idx, col]):
                            diff[field] = new.loc[idx, col]
                    if diff:
                        if db.update_user_fields(idx, diff):
                            cambios += 1
                            resumen.append(f"{orig.loc[idx, 'Usuario']}: {list(diff)}")
                if cambios:
                    _log_crud(f"edición {cambios} usuarios — " + "; ".join(resumen))
                    st.success(f"Actualizados {cambios} usuario(s).")
                    st.rerun()
                else:
                    st.info("Sin cambios detectados.")

    # ---------- CREAR ----------
    with t_new:
        with st.form("crear_usuario_form"):
            st.markdown("**Crear usuario manualmente** (entra directo, sin aprobación)")
            c1, c2 = st.columns(2)
            identificacion = c1.text_input("Identificación (cédula)*")
            usuario = c2.text_input("Usuario*")
            correo = st.text_input("Correo")
            clave = st.text_input("Clave inicial*", type="password")
            c3, c4, c5 = st.columns(3)
            perfil = c3.selectbox("Perfil", ["usuario", "administrador"])
            estado = c4.selectbox("Estado", ["aprobado", "pendiente", "rechazado"])
            membresia = c5.selectbox("Membresía", ["paga", "gratis"])
            fecha_final = st.text_input("Vencimiento (YYYY-MM-DD o 'NA')", value="NA")
            submit = st.form_submit_button("➕ Crear usuario")
            if submit:
                if not (identificacion.strip() and usuario.strip() and clave.strip()):
                    st.error("Identificación, usuario y clave son obligatorios.")
                else:
                    ok = db.create_user(identificacion.strip(), usuario.strip(), clave.strip(),
                                        correo.strip(), perfil=perfil, estado=estado,
                                        membresia=membresia, fecha_final=fecha_final.strip())
                    if ok:
                        _log_crud(f"crear usuario {usuario}")
                        st.success(f"Usuario **{usuario}** creado.")
                        st.rerun()
                    else:
                        st.error("Ya existe ese usuario o identificación.")

    # ---------- BORRAR ----------
    with t_del:
        if not df.empty:
            sel = st.selectbox("Usuario a borrar", df['Identificación'].tolist(),
                               format_func=lambda i: f"{df.loc[df['Identificación'] == i, 'Usuario'].iloc[0]} ({i})")
            confirmar = st.checkbox("Entiendo que esto borra el usuario y su acceso", key="confirmar_borrar")
            if confirmar:
                if st.button("🗑 Borrar definitivamente", type="primary"):
                    if db.delete_user(sel):
                        _log_crud(f"borrar usuario {sel}")
                        st.success("Usuario borrado.")
                        st.rerun()
                    else:
                        st.error("No se pudo borrar.")
        else:
            st.info("No hay usuarios aún.")

    # ---------- EXTENDER TIEMPO ----------
    with t_ext:
        if not df.empty:
            sel = st.selectbox("Usuario a extender", df['Identificación'].tolist(),
                               format_func=lambda i: f"{df.loc[df['Identificación'] == i, 'Usuario'].iloc[0]} ({i}) — vence {df.loc[df['Identificación'] == i, 'F. Final'].iloc[0]}",
                               key="ext_sel")
            cols = st.columns(3)
            for col, days in zip(cols, (7, 30, 90)):
                if col.button(f"+{days} días", width="stretch"):
                    nuevo = db.extend_membership(sel, extra_days=days)
                    _log_crud(f"extender {days}d al usuario {sel} -> {nuevo}")
                    st.success(f"Nueva fecha final: **{nuevo}**. Membresía pagada y cuenta aprobada.")
                    st.rerun()
        else:
            st.info("No hay usuarios aún.")

    # ---------- RESET CLAVE ----------
    with t_key:
        if not df.empty:
            sel = st.selectbox("Usuario", df['Identificación'].tolist(),
                               format_func=lambda i: f"{df.loc[df['Identificación'] == i, 'Usuario'].iloc[0]} ({i})",
                               key="reset_sel")
            nueva = st.text_input("Nueva clave", type="password")
            if st.button("🔑 Cambiar clave"):
                if nueva.strip():
                    db.set_user_password(sel, nueva.strip())
                    _log_crud(f"reset clave usuario {sel}")
                    st.success("Clave actualizada.")
                else:
                    st.error("La clave no puede estar vacía.")
        else:
            st.info("No hay usuarios aún.")

    # ---------- HISTORIAL DE INGRESOS ----------
    with t_hist:
        st.caption("Cada login (normal o master) y cada acción de este panel quedan aquí. Sólo tú lo ves.")
        history = db.get_login_history(limit=150)
        if not history:
            st.info("Sin eventos todavía — o falta el esquema (corre SUPABASE_SCHEMA.sql / revisa que el historial exista en SQLite).")
        else:
            hist = pd.DataFrame(history)
            total = len(hist)
            hoy = pd.to_datetime(hist["ts"], errors="coerce")
            from datetime import datetime as _dt
            n_hoy = int((hoy.dt.date == _dt.now().date()).sum()) if hasattr(hoy, "dt") else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("Eventos registrados", total)
            c2.metric("Ingresos de hoy", n_hoy)
            c3.metric("Acciones del panel", int((hist.get("evento") == "crud").sum()) if "evento" in hist else 0)
            show = hist.rename(columns={"ts": "Fecha", "usuario": "Usuario", "identificacion": "Identificación",
                                        "es_master": "¿Master?", "evento": "Evento", "detalle": "Detalle"})
            st.dataframe(show, width="stretch")

    st.divider()


def show_performance_section():
    st.subheader("🧠 Rendimiento de Picks (aprendizaje del bot)")
    st.caption("Aquí se miden los aciertos REALES del bot: % aciertos, ROI sobre stake plano de 1 unidad, Brier (calibración) y CLV. "
               "Sin esta medición, el bot no puede mejorar.")

    odds_api_key = _secret("odds_api")
    stats = db.get_pick_stats(days=90)
    n = stats["n_liquidados"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Liquidados (90d)", n)
    c2.metric("Aciertos", f"{stats['acierto_pct']}% ({stats['aciertos']}/{n})" if n else "—")
    c3.metric("ROI 1u", f"{stats['roi_pct']:+.1f}%" if n else "—")
    c4.metric("Brier", stats["brier"] if stats["brier"] is not None else "—")
    c5.metric("CLV medio", f"{stats['avg_clv']*100:+.2f}%" if stats["avg_clv"] is not None else "—")

    if odds_api_key:
        col_a, col_b = st.columns([1, 1])
        if col_a.button("🔄 Liquidar picks pendientes (API de scores)"):
            with st.spinner("Consultando resultados oficiales…"):
                scores = fetch_final_scores(odds_api_key)
                graded = db.autograde_picks(scores)
            st.success(f"Liquidados automáticamente: {graded} picks.")
            st.rerun()
        if stats["voids"]:
            st.caption(f"Picks anulados (push/void): {stats['voids']}")
    else:
        st.caption("⚠️ `odds_api` no configurada en secrets — liquidación automática deshabilitada.")

    if stats["por_riesgo"]:
        df_r = pd.DataFrame(stats["por_riesgo"]).T.reset_index().rename(columns={"index": "Riesgo"})
        st.markdown("**Por nivel de riesgo**")
        st.dataframe(df_r, width="stretch")
        fig = px.bar(df_r, x="Riesgo", y="acierto_pct", color="roi_pct",
                     title="Aciertos por nivel de riesgo (%)", text="n",
                     color_continuous_scale="RdYlGn")
        st.plotly_chart(fig, width="stretch")
    if stats["por_deporte"]:
        df_d = pd.DataFrame(stats["por_deporte"]).T.reset_index().rename(columns={"index": "Deporte"})
        st.markdown("**Por deporte**")
        st.dataframe(df_d.sort_values("n", ascending=False), width="stretch")
    if stats["por_mercado"]:
        df_m = pd.DataFrame(stats["por_mercado"]).T.reset_index().rename(columns={"index": "Mercado"})
        st.markdown("**Por mercado**")
        st.dataframe(df_m.sort_values("n", ascending=False), width="stretch")

    st.divider()
    st.markdown("**Picks pendientes de liquidar** (manual u automática)")
    pending = db.get_pending_picks()
    if not pending:
        st.caption("No hay picks pendientes.")
    else:
        for row in pending[:25]:
            (pid, ts, evento_id, sport_key, deporte, evento, empieza, mercado, market_key,
             seleccion, seleccion_raw, linea, cuota, casa, prob, edge, kelly, riesgo, origen,
             usuario, resultado, closing_odds, clv) = row
            with st.expander(f"#{pid} · {empieza or '?'} · {evento} — {seleccion} @ {cuota} ({casa}) · riesgo {riesgo} · por {usuario}"):
                col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
                closing = col1.number_input("Cuota de cierre (opcional)", min_value=1.0, value=float(cuota or 2.0), step=0.01, key=f"cl_{pid}")
                if col2.button("✅ Ganada", key=f"w_{pid}"):
                    db.settle_pick(pid, "ganada", closing)
                    st.rerun()
                if col3.button("❌ Perdida", key=f"l_{pid}"):
                    db.settle_pick(pid, "perdida", closing)
                    st.rerun()
                if col4.button("↩️ Anular (void/push)", key=f"v_{pid}"):
                    db.settle_pick(pid, "void", closing)
                    st.rerun()


def show_dashboard():
    st.title("📊 Dashboard Administrador")
    st.write(f"Bienvenido, **{st.session_state.user[2]}** (Administrador)")

    # Banner de persistencia: el dataset NO debe morir en cada redeploy
    _status = db.storage_status()
    if _status == "sqlite":
        st.warning("💾 Estás guardando en **SQLite local**: Streamlit Cloud BORRA el archivo en cada redeploy. "
                   "Configura `SUPABASE_URL` y `SUPABASE_KEY` en Secrets y ejecuta `SUPABASE_SCHEMA.sql` para que nunca se pierdas nada.")
    elif _status == "supabase-missing-tables":
        st.error("⚠️ Supabase responde pero faltan las tablas. Ejecuta `SUPABASE_SCHEMA.sql` en Supabase → SQL Editor y recarga.")
    elif _status == "supabase":
        st.success("🗄️ Persistencia: **Supabase** (los datos sobreviven a redeploys).")

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
    st.plotly_chart(fig, width="stretch")

    st.divider()
    show_performance_section()

    if st.session_state.get("is_master"):
        st.divider()
        show_master_crud()

    st.divider()

    # Gestión de usuarios
    st.subheader("⚙️ Gestión de Usuarios")
    st.dataframe(df, width="stretch")

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
    st.dataframe(top_users[['Usuario', 'Ingresos', 'Análisis']], width="stretch")
