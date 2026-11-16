import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
import requests
from openai import OpenAI
import json
import database as db
import market_model as mm

COL_TZ = pytz.timezone('America/Bogota')
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

GROUP_ICONS = {
    "Soccer": "⚽", "Basketball": "🏀", "Tennis": "🎾", "Baseball": "⚾",
    "Ice Hockey": "🏒", "American Football": "🏈", "Mixed Martial Arts": "🥊",
}
GROUP_PRIORITY = ["Soccer", "Basketball", "Tennis", "Baseball", "Ice Hockey",
                  "American Football", "Mixed Martial Arts"]
# Ligas prioritarias de fútbol (subcadenas en la key de la API) para el usuario colombiano
SOCCER_PRIORITY = [
    "uefa_champs_league", "uefa_europa_league", "soccer_epl", "spain_la_liga",
    "italy_serie_a", "germany_bundesliga", "france_ligue_one",
    "conmebol_libertadores", "conmebol_sudamericana",
    "brazil_campeonato", "mexico_ligamx", "argentina_primera_division",
    "mls", "fifa_world_cup", "copa_america", "conmebol_world_cup",
]
MAX_SPORTS = 14  # tope de deportes por refresh para proteger la cuota de la API


def _secret(key, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


@st.cache_data(ttl=21600, show_spinner=False)
def get_active_sports(api_key):
    """Lista de deportes ACTIVOS in-season (gratis, no consume cuota).

    Filtra por grupos populares y prioriza ligas de fútbol relevantes para Colombia.
    """
    try:
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/?apiKey={api_key}", timeout=15)
        if r.status_code != 200:
            return []
        sports = [s for s in r.json()
                  if s.get("active") and not s.get("has_outrights") and s.get("group") in GROUP_ICONS]
    except Exception:
        return []

    def rank(s):
        grp = GROUP_PRIORITY.index(s.get("group")) if s.get("group") in GROUP_PRIORITY else 99
        key = s.get("key", "")
        soc = 0
        for i, pat in enumerate(SOCCER_PRIORITY):
            if pat in key:
                soc = i + 1
                break
        return (grp, soc if soc else 100)

    sports.sort(key=rank)
    return sports[:MAX_SPORTS]


@st.cache_data(ttl=3600, show_spinner=False)
def get_sports_matches(api_key, markets="h2h,totals"):
    """Trae partidos de la semana en curso. Devuelve (matches, creditos_restantes, errores)."""
    today_col = datetime.now(COL_TZ).date()
    start_of_week = today_col - timedelta(days=today_col.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    matches_this_week = []
    remaining = None
    errores = []

    for sport in get_active_sports(api_key):
        key = sport.get("key")
        odds_url = (f"https://api.the-odds-api.com/v4/sports/{key}/odds/"
                    f"?apiKey={api_key}&regions=us&markets={markets}&oddsFormat=decimal")
        try:
            r = requests.get(odds_url, timeout=15)
            if r.headers.get("x-requests-remaining") is not None:
                try:
                    remaining = int(r.headers["x-requests-remaining"])
                except ValueError:
                    pass
            if r.status_code != 200:
                errores.append(f"{key}: HTTP {r.status_code}")
                continue
            for match in r.json():
                try:
                    commence = str(match.get("commence_time", "")).replace("Z", "+00:00")
                    match_time = datetime.fromisoformat(commence).astimezone(COL_TZ)
                except (ValueError, TypeError):
                    continue
                if not (start_of_week <= match_time.date() <= end_of_week):
                    continue
                icon = GROUP_ICONS.get(sport.get("group"), "🏆")
                matches_this_week.append({
                    "event_id": match.get("id"),
                    "sport_key": key,
                    "sport_title": sport.get("title", key),
                    "icon": icon,
                    "match_time": match_time,
                    "home_team": match.get("home_team"),
                    "away_team": match.get("away_team"),
                    "bookmakers": match.get("bookmakers", []),
                })
        except Exception as e:
            errores.append(f"{key}: {e}")

    matches_this_week.sort(key=lambda x: x["match_time"])
    return matches_this_week, remaining, errores


def get_match_status(match_time):
    """Calcula si el partido no ha iniciado, está en vivo o terminó"""
    now_col = datetime.now(COL_TZ)
    time_diff = now_col - match_time

    if time_diff < timedelta(0):
        return "PRE-PARTIDO", f"El partido aún no ha iniciado. Empieza a las {match_time.strftime('%H:%M')} hora Colombia. Da análisis y pronósticos de pre-partido."
    elif timedelta(0) <= time_diff <= timedelta(hours=2, minutes=30):
        return "EN VIVO", "El partido está EN VIVO en este momento. Adapta tu análisis a apuestas en vivo (Live Betting), enfócate en lo que puede pasar en el resto del juego (ej. próximo gol, ganador del partido actual, más/menos goles en lo que resta)."
    else:
        return "FINALIZADO", "El partido probablemente ya finalizó. Haz un breve resumen de lo que pudo haber pasado y cómo resultaron las apuestas pre-partido."


def build_match_math(match):
    """Métricas matemáticas del partido: consenso sin margen + mejor cuota + mercados derivados."""
    books = match.get("bookmakers", [])
    fair = mm.consensus_fair_probs(books, "h2h")
    best = mm.best_prices(books, "h2h")
    n_books = len([b for b in books if any(m.get("key") == "h2h" for m in b.get("markets", []))])
    math_data = {"fair": fair, "best": best, "n_books": n_books, "derived": None}
    if "soccer" in (match.get("sport_key") or ""):
        p_draw = fair.get("Draw")
        p_home = fair.get(match.get("home_team"))
        p_away = fair.get(match.get("away_team"))
        if p_draw and p_home and p_away:
            try:
                math_data["derived"] = mm.derived_markets(p_home, p_draw, p_away, total_hint=None)
            except Exception:
                pass
    return math_data


def format_math_block(match, math_data):
    """Bloque de texto con los números justos para el prompt de la IA."""
    lines = []
    fair, best = math_data["fair"], math_data["best"]
    for outcome, prob in fair.items():
        b = best.get(outcome)
        if b:
            ev = mm.expected_value(prob, b["odds"])
            lines.append(f"  {outcome}: prob justa {prob*100:.1f}% | mejor cuota {b['odds']} ({b['book']}) | EV {ev*100:+.1f}%")
    d = math_data.get("derived")
    if d:
        lines.append(f"  λ_home={d['lambda_home']} λ_away={d['lambda_away']} (matriz Dixon-Coles calibrada al mercado)")
        lines.append(f"  Over 2.5: {d['over_2_5']*100:.1f}% | Under 2.5: {d['under_2_5']*100:.1f}% | BTTS Sí: {d['btts_yes']*100:.1f}% | 1X: {d['1x']*100:.1f}% | X2: {d['x2']*100:.1f}%")
    totals = mm.consensus_fair_probs(match.get("bookmakers", []), "totals", point=2.5)
    t_best = mm.best_prices(match.get("bookmakers", []), "totals", point=2.5)
    for name in ("Over", "Under"):
        prob = totals.get(name)
        b = t_best.get(name)
        if prob and b:
            ev = mm.expected_value(prob, b["odds"])
            lines.append(f"  2.5 {name}: prob justa consenso {prob*100:.1f}% | mejor cuota {b['odds']} ({b['book']}) | EV {ev*100:+.1f}%")
    return "\n".join(lines)


def _track_record_text():
    try:
        stats = db.get_pick_stats(days=90)
        if stats["n_liquidados"] > 0:
            return (f"Historial del bot (90 días): {stats['acierto_pct']}% de aciertos "
                    f"(n={stats['n_liquidados']}), ROI {stats['roi_pct']:+.1f}%, "
                    f"Brier {stats['brier']}")
    except Exception:
        pass
    return "Historial del bot: aún sin muestra liquidada (los picks nuevos empiezan a medirse ya)."


@st.cache_data(ttl=1800, show_spinner=False)
def _call_openai(api_key, model, prompt):
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Eres un tipster profesional y analista cuantitativo de apuestas. Respondes ÚNICAMENTE con un objeto JSON válido."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=2500,
    )
    return response.choices[0].message.content


def generate_ai_analysis(openai_api_key, match_info, math_data, extra_context=None):
    status_code, status_context = get_match_status(match_info['match_time'])
    has_odds = bool(math_data.get("fair"))
    if has_odds:
        odds_block = format_math_block(match_info, math_data)
        cuota_rule = ("- Usa ÚNICAMENTE las cuotas/casas listadas arriba o cuotas de distintos mercados que puedas justificar, "
                      "pero NUNCA inventes una cuota: elige siempre la mejor de las listadas.")
        ev_rule = "- Prioriza picks con EV >= 0 (prob justa × cuota >= 1). Si NINGÚN pick tiene EV positivo, dilo honestamente en \"conclusiones\" y marca en cada pick \"es_valor\": false."
        pick_fields = ('"cuota": 1.85, "casa": "Casa", "prob_modelo": 0.58, "edge_pct": 7.3, "es_valor": true, ')
    else:
        odds_block = ("Cuotas: NO DISPONIBLES para este partido (liga sin cobertura de líneas en tus APIs).\n"
                      f"{extra_context or ''}")
        cuota_rule = ("- NO HAY CUOTAS: NUNCA inventes una cuota. En cada pick pon \"cuota\": null, \"casa\": null y "
                      "\"prob_modelo\": null.\n"
                      "- El pick debe ser legible con su mercado (ej. 'Gana Atlético Nacional', 'Over 2.5', 'Ambos marcan').")
        ev_rule = ("- No marques valor (\"es_valor\": false siempre): esto es análisis estadístico/táctico, no una apuesta de valor medida.")
        pick_fields = ('"cuota": null, "casa": null, "prob_modelo": null, "edge_pct": null, "es_valor": false, ')
    track = _track_record_text()
    model = _secret("openai_model", "gpt-4o-mini")
    extra_block = f"\n{extra_context}\n" if (extra_context and has_odds) else ""

    prompt = f"""Actúa como un tipster deportivo de nivel PRO y analista cuantitativo. Analiza {match_info['home_team']} vs {match_info['away_team']} ({match_info['sport_title']}).

Estado actual: {status_context}

Cuotas justas calculadas por consenso de casas (MARGEN YA RETIRADO) y mejor precio disponible:
{odds_block}
{extra_block}
{track}

REGLAS OBLIGATORIAS:
{cuota_rule}
{ev_rule}
- Si un mercado no se puede clasificar automáticamente, usa market_key "otros" y prob_modelo null.
- seleccion_raw DEBE ser el nombre exacto del resultado según la API (ej.: nombre del equipo, "Draw", "Over"/"Under") para que el sistema liquide el pick automáticamente.
- Cada array de riesgo tiene EXACTAMENTE 4 apuestas alternativas usando mercados diversos (1X2, doble oportunidad, over/under, BTTS, hándicap, esquinas, tarjetas, ambos marcan, etc.).

Devuelve ÚNICAMENTE un JSON válido con esta estructura exacta:
{{
  "conclusiones": ["Conclusión 1 adaptada al estado", "Conclusión 2", "Conclusión 3", "Conclusión 4"],
  "bajo_riesgo": [
    {{"mercado": "Nombre", "seleccion": "Texto legible", "seleccion_raw": "Nombre exacto API", "market_key": "h2h|totals|spreads|btts|otros", "linea": null, {pick_fields}"explicacion": "Por qué", "pick": "El Pick: [Apuesta]"}}
  ],
  "riesgo_medio": [... mismo formato, 4 picks ...],
  "alto_riesgo": [... mismo formato, 4 picks ...],
  "analisis_ia": "Análisis profundo de 2 párrafos adaptado al estado actual del partido.",
  "consenso": ["Resumen 1", "Resumen 2"]
}}
"""
    try:
        raw = _call_openai(openai_api_key, model, prompt)
        data = json.loads(raw)
        # Ground truth server-side: recalcular prob/edge desde el consenso, no confiar en la IA
        _enrich_picks(data, match_info, math_data)
        return data, status_code
    except Exception as e:
        st.error(f"Error OpenAI: {e}")
        return None, status_code


def _fair_for(match_info, math_data, pick):
    """Proba justa (consenso) para un pick según su market_key. None si no aplica."""
    fair = math_data["fair"]
    sel = (pick.get("seleccion_raw") or pick.get("seleccion") or "").strip()
    mk = (pick.get("market_key") or "").lower()
    if mk in ("h2h", "1x2", "moneyline"):
        if sel in fair:
            return fair[sel]
        for k, v in fair.items():
            if k.lower() == sel.lower():
                return v
    if mk == "totals":
        totals = mm.consensus_fair_probs(match_info.get("bookmakers", []), "totals", point=2.5)
        name = "Over" if sel.lower().startswith(("over", "más", "mayor")) else "Under"
        return totals.get(name) or (math_data.get("derived") or {}).get(
            "over_2_5" if name == "Over" else "under_2_5")
    if mk == "btts":
        d = math_data.get("derived") or {}
        name = sel.lower()
        if any(w in name for w in ("si", "yes", "ambo")):
            return d.get("btts_yes")
        if any(w in name for w in ("no",)):
            return d.get("btts_no")
    return None


def _enrich_picks(data, match_info, math_data):
    home, away = match_info.get("home_team"), match_info.get("away_team")
    event_str = f"{home} vs {away}"
    empieza = match_info["match_time"].strftime("%Y-%m-%d %H:%M")
    has_odds = bool(math_data.get("fair"))
    for tier in ("bajo_riesgo", "riesgo_medio", "alto_riesgo"):
        for p in data.get(tier, []) or []:
            if not isinstance(p, dict):
                continue
            p["evento_id"] = match_info.get("event_id")
            p["sport_key"] = match_info.get("sport_key")
            p["deporte"] = match_info.get("deporte") or match_info.get("sport_title")
            p["evento"] = event_str
            p["empieza"] = empieza
            p["riesgo"] = tier.replace("_riesgo", "")
            prob = _fair_for(match_info, math_data, p) if has_odds else None
            p["prob_modelo"] = round(prob, 4) if prob is not None else None
            if not has_odds:
                # Liga sin líneas: jamás dejes cuotas inventadas por la IA pasar al registro
                p["cuota"] = None
                p["casa"] = None
                p["edge"] = None
                p["kelly_frac"] = None
                p["es_valor"] = False
                continue
            cuota = p.get("cuota")
            try:
                cuota = float(cuota)
            except (TypeError, ValueError):
                cuota = None
            if prob is not None and cuota:
                p["edge"] = round(mm.expected_value(prob, cuota), 4)
                p["kelly_frac"] = round(mm.kelly_fraction(prob, cuota), 4)
                p["es_valor"] = p["edge"] >= 0.0
            else:
                p["edge"] = None
                p["kelly_frac"] = None
                p["es_valor"] = False


def show_live_stream_options(match):
    now_col = datetime.now(COL_TZ)
    time_diff = now_col - match['match_time']
    is_live = timedelta(0) <= time_diff <= timedelta(hours=2, minutes=30)

    search_query = f"{match['home_team']} vs {match['away_team']} en vivo"

    if is_live:
        st.success("🔴 ¡El partido está EN VIVO AHORA! Ábrelo en una ventana externa para verlo:", icon="🔴")
        c1, c2, c3 = st.columns(3)
        c1.link_button("📺 Buscar en YouTube", f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}", width="stretch")
        c2.link_button("🔴 Ver en Google", f"https://www.google.com/search?q={search_query.replace(' ', '+')}+online", width="stretch")
        c3.link_button("⭐ Buscar en ESPN/DAZN", f"https://www.google.com/search?q={search_query.replace(' ', '+')}+ESPN+o+DAZN", width="stretch")
    else:
        st.info("⏳ El partido aún no ha comenzado o ya finalizó. Aquí podrás verlo en vivo cuando inicie:")
        st.markdown(f"[Busca canales oficiales aquí](https://www.google.com/search?q=Donde+ver+{match['home_team']}+vs+{match['away_team']}+colombia)")


def _save_tier_picks(tier_picks, origen="ia"):
    usuario = st.session_state.user[2]
    saved = 0
    for p in tier_picks:
        if not p.get("seleccion"):
            continue
        try:
            db.save_pick({
                "evento_id": p.get("evento_id"),
                "sport_key": p.get("sport_key"),
                "deporte": p.get("deporte"),
                "evento": p.get("evento"),
                "empieza": p.get("empieza"),
                "mercado": p.get("mercado"),
                "market_key": p.get("market_key", "otros"),
                "seleccion": p.get("seleccion"),
                "seleccion_raw": p.get("seleccion_raw") or p.get("seleccion"),
                "linea": p.get("linea"),
                "cuota": p.get("cuota"),
                "casa": p.get("casa"),
                "prob_modelo": p.get("prob_modelo"),
                "edge": p.get("edge"),
                "kelly_frac": p.get("kelly_frac"),
                "riesgo": p.get("riesgo", "medio"),
                "origen": origen,
                "usuario": usuario,
            })
            saved += 1
        except Exception:
            pass
    return saved


def render_math_badges(math_data, match=None):
    fair, best = math_data["fair"], math_data["best"]
    if not fair:
        st.caption("Sin cuotas de casas para calcular el consenso.")
        return
    parts = []
    for outcome, prob in fair.items():
        b = best.get(outcome)
        label = outcome if len(outcome) <= 18 else outcome[:15] + "…"
        if b:
            parts.append(f"**{label}**: {prob*100:.1f}% · {b['odds']} ({b['book']})")
        else:
            parts.append(f"**{label}**: {prob*100:.1f}%")
    st.markdown("📐 **Consenso sin margen (" + f"{math_data['n_books']} casas" + "):**  \n" + " | ".join(parts))

    d = math_data.get("derived")
    tb = {}
    if match is not None:
        tb = mm.best_prices(match.get("bookmakers", []), "totals", point=2.5)
    valor = []
    for outcome, prob in fair.items():
        b = best.get(outcome)
        if b and mm.expected_value(prob, b["odds"]) >= 0.02:
            ev = mm.expected_value(prob, b["odds"])
            valor.append(f"💎 **{outcome}** @ {b['odds']} ({b['book']}) — EV **+{ev*100:.1f}%**")
    if d:
        st.caption(f"λ {d['lambda_home']}-{d['lambda_away']} · Over 2.5: {d['over_2_5']*100:.0f}% · "
                   f"Under 2.5: {d['under_2_5']*100:.0f}% · BTTS: {d['btts_yes']*100:.0f}%")
        for name, prob in (("Over", d["over_2_5"]), ("Under", d["under_2_5"])):
            b = tb.get(name)
            if b and mm.expected_value(prob, b["odds"]) >= 0.02:
                ev = mm.expected_value(prob, b["odds"])
                valor.append(f"💎 **{name} 2.5** @ {b['odds']} ({b['book']}) — EV **+{ev*100:.1f}%**")
    if valor:
        st.success("Valor detectado al mejor precio del mercado:  \n" + "  \n".join(valor))
    else:
        st.caption("💰 Ningún mercado supera un EV ≥ +2% al mejor precio (mercado eficiente en este partido).")


def render_picks_column(col, title, emoji, picks, banca):
    with col:
        st.markdown(f"**{emoji} {title}**")
        for i, item in enumerate(picks, 1):
            prob = item.get("prob_modelo")
            edge = item.get("edge")
            kfrac = item.get("kelly_frac")
            es_valor = item.get("es_valor")
            badge = "💎" if es_valor else ""
            meta = []
            if prob is not None:
                meta.append(f"Prob justa: **{prob*100:.1f}%**")
            if edge is not None:
                meta.append(f"EV: **{edge*100:+.1f}%**")
            if kfrac:
                meta.append(f"Kelly ¼: **{kfrac*100:.1f}%** (≈ ${kfrac*banca:,.0f})")
            st.markdown(f"**{i}. {badge} {item.get('mercado','')}**  \n{item.get('explicacion','')}")
            if meta:
                st.caption(" · ".join(meta))
            pick_txt = item.get("pick")
            if not pick_txt:
                if item.get("cuota"):
                    pick_txt = f"{item.get('seleccion','')} @ {item.get('cuota')} en {item.get('casa','')}"
                else:
                    pick_txt = str(item.get("seleccion", ""))
            st.success(f"**{pick_txt}**")
            if i < len(picks):
                st.markdown("---")


def show_betting_app():
    st.markdown("<h1 style='text-align: center;'>🤖 AI Sports Bet Generator PRO</h1>", unsafe_allow_html=True)
    odds_api_key = st.secrets["odds_api"]; openai_api_key = st.secrets["openai"]
    markets = _secret("odds_markets", "h2h")  # "h2h,totals" añade líneas O/U a 2× el costo de créditos
    st.sidebar.caption(f"Mercados: **{markets}** · Totals = 2× créditos (Over/Under derivados gratis vía Dixon‑Coles)")

    st.sidebar.title("⚙️ Panel de Control")
    banca = st.sidebar.number_input("💰 Banca para Kelly (COP)", min_value=10_000, max_value=1_000_000_000, value=100_000, step=10_000)
    timeframe = st.sidebar.radio("📅 Periodo", ["Hoy", "Esta Semana"], horizontal=True)
    if st.sidebar.button("🧹 Limpiar Memoria"):
        st.cache_data.clear()
        st.rerun()

    all_matches, credits, errores = get_sports_matches(odds_api_key, markets=markets)
    if credits is not None:
        st.sidebar.caption(f"📡 Créditos Odds API restantes: **{credits}**")
        if credits < 50:
            st.sidebar.warning("Cuota de la API de cuotas baja. Reduce el uso o amplía el plan.")
    if errores:
        with st.sidebar.expander(f"⚠️ Deportes sin datos ({len(errores)})"):
            for e in errores:
                st.caption(e)

    if not all_matches:
        st.error("No hay partidos esta semana (o la API de cuotas no respondió). Intenta '🧹 Limpiar Memoria'.")
        return

    sports_available = list(dict.fromkeys([f"{m['icon']} {m['sport_title']}" for m in all_matches]))
    selected_sport = st.sidebar.selectbox("Deporte", ["Todos"] + sorted(sports_available))

    today_col = datetime.now(COL_TZ).date()
    filtered = [m for m in all_matches
                if (selected_sport == "Todos" or f"{m['icon']} {m['sport_title']}" == selected_sport)
                and (timeframe == "Esta Semana" or m['match_time'].date() == today_col)]

    if filtered:
        if st.button(f"🚀 Generar Análisis IA para {len(filtered)} partidos", width="stretch"):
            st.session_state['generate'] = True
            db.increment_analysis(st.session_state.user[2])

    current_day = None
    for match in filtered:
        if timeframe == "Esta Semana":
            fecha_str = f"{DIAS_SEMANA[match['match_time'].weekday()]} {match['match_time'].day:02d}/{match['match_time'].month:02d}"
            if current_day != fecha_str:
                if current_day:
                    st.divider()
                st.markdown(f"### 📅 {fecha_str}")
                current_day = fecha_str

        status_code, _ = get_match_status(match['match_time'])
        status_emoji = "🔴 EN VIVO" if status_code == "EN VIVO" else ("⏳ Próximamente" if status_code == "PRE-PARTIDO" else "✅ Finalizado")

        st.markdown(f"#### {match['icon']} {match['home_team']} vs {match['away_team']} - 🕒 {match['match_time'].strftime('%H:%M')} ({status_emoji})")

        math_data = build_match_math(match)

        with st.expander("💰 Ver Cuotas, Mercado Justo, Análisis IA y Transmisión"):
            show_live_stream_options(match)
            st.divider()
            render_math_badges(math_data, match)
            st.divider()

            if st.session_state.get('generate'):
                with st.spinner(f"IA analizando datos (Estado: {status_code})..."):
                    ai_data, _ = generate_ai_analysis(openai_api_key, match, math_data)

                if ai_data:
                    all_ai_picks = (ai_data.get("bajo_riesgo", []) + ai_data.get("riesgo_medio", [])
                                    + ai_data.get("alto_riesgo", []))
                    guardar = st.button(f"💾 Guardar los {len(all_ai_picks)} picks de este partido en el historial",
                                        key=f"save_{match['event_id']}")
                    if guardar:
                        n = _save_tier_picks(all_ai_picks, origen="ia")
                        st.toast(f"Guardados {n} picks para medir su rendimiento 🎯")

                    st.markdown("##### 🔑 Conclusiones clave")
                    for c in ai_data.get("conclusiones", []):
                        st.markdown(f"- {c}")
                    st.divider()

                    st.markdown("##### 🎯 Mejores apuestas para este partido (4 alternativas por riesgo)")
                    c1, c2, c3 = st.columns(3)
                    for col, title, emoji, key in [(c1, "Bajo Riesgo", "🟢", "bajo_riesgo"),
                                                   (c2, "Medio Riesgo", "🟡", "riesgo_medio"),
                                                   (c3, "Alto Riesgo", "🔴", "alto_riesgo")]:
                        render_picks_column(col, title, emoji, ai_data.get(key, []), banca)

                    st.markdown("##### 📊 Análisis del pronóstico de apuesta (IA)")
                    st.write(ai_data.get("analisis_ia", ""))

                    st.markdown("##### 🌐 Consenso y Resumen")
                    for cons in ai_data.get("consenso", []):
                        st.info(cons)
            else:
                st.warning("Presiona el botón superior para generar los análisis IA.")

    # ------------------------------------------------------------------
    # Liga BetPlay Dimayor (opcional: secret football_api). The Odds API NO la cubre
    # -> análisis estadístico/táctico IA (sin líneas de valor), picks sin cuota.
    # ------------------------------------------------------------------
    import betplay
    if betplay.is_configured():
        with st.expander("🇨🇴 Liga BetPlay — análisis IA (sin líneas de valor disponibles)", expanded=False):
            st.caption("The Odds API no cubre esta liga → análisis estadístico/táctico con forma real vía API‑Football. "
                       "Los picks se guardan **sin cuota**: cuentan en % aciertos, no en ROI.")
            if st.button("🔎 Cargar fixtures de la Liga esta semana", key="bp_load"):
                st.session_state.bp_load = True
            if st.session_state.get("bp_load"):
                league = None
                try:
                    league = betplay.get_betplay_league()
                except Exception as e:
                    st.error(f"API‑Football: {e}")
                if not league:
                    st.warning("No se encontró la liga o la API no respondió. Revisa tu secret `football_api`.")
                else:
                    st.markdown(f"**{league['name']}** · Temporada {league['season']}")
                    fixtures = []
                    try:
                        fixtures = betplay.get_this_week_fixtures(league["id"], league["season"])
                    except Exception as e:
                        st.error(f"API‑Football: {e}")
                    if not fixtures:
                        st.info("No hay fixtures programados para esta semana.")
                    for it in fixtures:
                        fecha = f"{DIAS_SEMANA[it['match_time'].weekday()]} {it['match_time'].strftime('%d/%m %H:%M')}"
                        ronda = f" · {it.get('round')}" if it.get("round") else ""
                        st.markdown(f"##### 🇨🇴 {it['home_team']} vs {it['away_team']} — {fecha}{ronda}")
                        if it.get("venue"):
                            st.caption(f"📍 {it['venue']}")
                        fh, fa = [], []
                        try:
                            if it.get("home_id"):
                                fh = betplay.get_team_form(it["home_id"], league["id"], league["season"])
                            if it.get("away_id"):
                                fa = betplay.get_team_form(it["away_id"], league["id"], league["season"])
                        except Exception:
                            pass
                        st.caption(f"Forma reciente (últ. 5) — {it['home_team']}: **{' '.join(fh) or '—'}**  ·  {it['away_team']}: **{' '.join(fa) or '—'}**")
                        if st.button(f"🤖 Generar análisis IA", key=f"gen_bp_{it['fixture_id']}"):
                            st.session_state[f"bp_gen_{it['fixture_id']}"] = True
                        if st.session_state.get(f"bp_gen_{it['fixture_id']}"):
                            bp_match = {
                                "event_id": str(it["fixture_id"]),
                                "sport_key": "betplay",
                                "sport_title": league["name"],
                                "deporte": league["name"],
                                "icon": "🇨🇴",
                                "match_time": it["match_time"],
                                "home_team": it["home_team"],
                                "away_team": it["away_team"],
                                "bookmakers": [],
                            }
                            extra = (f"Datos reales API-Football (temporada {league['season']} del torneo colombiano). "
                                     f"Forma reciente (últimos 5, G/E/P): {it['home_team']}: {' '.join(fh) or 'sin datos'} | "
                                     f"{it['away_team']}: {' '.join(fa) or 'sin datos'}. "
                                     + (f"Ronda: {it['round']}. " if it.get("round") else "")
                                     + (f"Sede: {it['venue']}." if it.get("venue") else ""))
                            with st.spinner("IA analizando (sin cuotas — análisis estadístico)..."):
                                ai_data, _ = generate_ai_analysis(
                                    openai_api_key, bp_match,
                                    {"fair": {}, "best": {}, "n_books": 0, "derived": None},
                                    extra_context=extra)
                            if ai_data:
                                all_ai_picks = (ai_data.get("bajo_riesgo", []) + ai_data.get("riesgo_medio", []) + ai_data.get("alto_riesgo", []))
                                if st.button(f"💾 Guardar {len(all_ai_picks)} picks del partido en el historial", key=f"save_bp_{it['fixture_id']}"):
                                    n = _save_tier_picks(all_ai_picks, origen="ia")
                                    st.toast(f"Guardados {n} picks (sin cuota — medición por acierto/fallo) 🎯")
                                st.markdown("##### 🔑 Conclusiones clave")
                                for c in ai_data.get("conclusiones", []):
                                    st.markdown(f"- {c}")
                                st.divider()
                                bc1, bc2, bc3 = st.columns(3)
                                for col, title, emoji, key in [(bc1, "Bajo Riesgo", "🟢", "bajo_riesgo"),
                                                               (bc2, "Medio Riesgo", "🟡", "riesgo_medio"),
                                                               (bc3, "Alto Riesgo", "🔴", "alto_riesgo")]:
                                    render_picks_column(col, title, emoji, ai_data.get(key, []), banca)
                                st.markdown("##### 📊 Análisis del pronóstico (IA)")
                                st.write(ai_data.get("analisis_ia", ""))
                                for cons in ai_data.get("consenso", []):
                                    st.info(cons)

    # ------------------------------------------------------------------
    # Historial y rendimiento del bot (auditabilidad para todos)
    # ------------------------------------------------------------------
    st.divider()
    with st.expander("📈 Mi historial de picks y rendimiento del bot"):
        usuario = st.session_state.user[2]
        stats = db.get_pick_stats(days=90, usuario=None)
        if stats["n_liquidados"] == 0:
            st.info("Todavía no hay picks liquidados. Genera análisis, guárdalos con 💾 y el administrador liquidará los resultados "
                    "(o se liquidarán automáticamente vía la API de scores). Aquí verás % de aciertos, ROI, Brier y CLV.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Picks liquidados", stats["n_liquidados"])
            c2.metric("Aciertos", f"{stats['acierto_pct']}% ({stats['aciertos']}/{stats['n_liquidados']})")
            c3.metric("ROI (1u plana)", f"{stats['roi_pct']:+.1f}%")
            c4.metric("Brier (calibración)", stats["brier"] if stats["brier"] is not None else "—")
            if stats["avg_clv"] is not None:
                st.caption(f"CLV medio: {stats['avg_clv']*100:+.2f}% (positivo = el mercado se movió a favor de tus picks)")
            rows = db.get_recent_picks(limit=15, usuario=usuario)
            if rows:
                df = pd.DataFrame(rows, columns=["id", "ts", "evento_id", "sport_key", "deporte", "evento", "empieza",
                                                 "mercado", "market_key", "seleccion", "seleccion_raw", "linea",
                                                 "cuota", "casa", "prob_modelo", "edge", "kelly_frac", "riesgo",
                                                 "origen", "usuario", "resultado", "closing_odds", "clv"])
                st.dataframe(df[["empieza", "deporte", "evento", "mercado", "cuota", "casa",
                                 "prob_modelo", "edge", "riesgo", "resultado"]], width="stretch")

    st.caption("🎯 Medir antes que adivinar: el bot registra cuota, probabilidad justa y resultado de cada pick. "
               "Juego responsable — las apuestas conllevan riesgo de pérdida.")
