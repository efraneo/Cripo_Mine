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
