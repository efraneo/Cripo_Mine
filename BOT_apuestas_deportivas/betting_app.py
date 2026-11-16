import streamlit as st
from datetime import datetime, timedelta
import pytz
import requests
from openai import OpenAI
import json
import database as db

SPORT_ICONS = {"soccer": "⚽", "basketball": "🏀", "tennis": "🎾", "baseball": "⚾", "american_football": "🏈", "ice_hockey": "🏒", "mma": "🥊", "esports": "🎮"}
POPULAR_SPORTS = ['soccer', 'basketball', 'tennis', 'baseball', 'mma_mixed_martial_arts', 'ice_hockey', 'american_football_nfl']
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

@st.cache_data(ttl=3600)
def get_sports_matches(api_key):
    col_tz = pytz.timezone('America/Bogota')
    today_col = datetime.now(col_tz).date()
    start_of_week = today_col - timedelta(days=today_col.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    matches_this_week = []
    for sport_key in POPULAR_SPORTS:
        odds_url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/?apiKey={api_key}&regions=us&oddsFormat=decimal"
        try:
            odds_response = requests.get(odds_url)
            if odds_response.status_code == 200:
                for match in odds_response.json():
                    match_time = datetime.fromisoformat(match['commence_time'][:-1]).astimezone(col_tz)
                    if start_of_week <= match_time.date() <= end_of_week:
                        matches_this_week.append({
                            "sport_title": sport_key.replace('_', ' ').title(), "icon": SPORT_ICONS.get(sport_key, "🏆"),
                            "match_time": match_time, "home_team": match['home_team'], "away_team": match['away_team'], "bookmakers": match['bookmakers']
                        })
        except: pass
    matches_this_week.sort(key=lambda x: x['match_time'])
    return matches_this_week

def get_match_status(match_time):
    """Calcula si el partido no ha iniciado, está en vivo o terminó"""
    col_tz = pytz.timezone('America/Bogota')
    now_col = datetime.now(col_tz)
    time_diff = now_col - match_time
    
    if time_diff < timedelta(0):
        return "PRE-PARTIDO", f"El partido aún no ha iniciado. Empieza a las {match_time.strftime('%H:%M')} hora Colombia. Da análisis y pronósticos de pre-partido."
    elif timedelta(0) <= time_diff <= timedelta(hours=2, minutes=30):
        return "EN VIVO", "El partido está EN VIVO en este momento. Adapta tu análisis a apuestas en vivo (Live Betting), enfócate en lo que puede pasar en el resto del juego (ej. próximo gol, ganador del partido actual, más/menos goles en lo que resta)."
    else:
        return "FINALIZADO", "El partido probablemente ya finalizó. Haz un breve resumen de lo que pudo haber pasado y cómo resultaron las apuestas pre-partido."

def generate_ai_analysis(api_key, match_info):
    client = OpenAI(api_key=api_key)
    odds_str = "".join([f"{bm['title']}: " + " | ".join([f"{o['name']} @ {o['price']}" for m in bm['markets'] if m['key']=='h2h' for o in m['outcomes']]) + "\n" for bm in match_info['bookmakers'][:3]])
    
    # Calcular estado del partido para que la IA lo use
    status_code, status_context = get_match_status(match_info['match_time'])
    
    prompt = f"""Actúa como un tipster deportivo de nivel PRO. Analiza {match_info['home_team']} vs {match_info['away_team']} ({match_info['sport_title']}).
    Estado actual: {status_context}
    Cuotas actuales (1X2 o H2H): {odds_str}
    
    Devuelve ÚNICAMENTE un JSON válido. Es OBLIGATORIO que cada array de riesgo tenga exactamente 4 apuestas alternativas usando mercados diversos (esquinas, ambos marcan, hándicap, tarjetas, etc.).
    
    Estructura exacta:
    {{
      "conclusiones": ["Conclusión 1 adaptada al estado", "Conclusión 2", "Conclusión 3", "Conclusión 4"],
      "bajo_riesgo": [
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}}
      ],
      "riesgo_medio": [
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}}
      ],
      "alto_riesgo": [
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}},
        {{"mercado": "Nombre", "explicacion": "Por qué", "pick": "El Pick: [Apuesta] @ [Cuota] en [Casa]"}}
      ],
      "analisis_ia": "Análisis profundo de 2 párrafos adaptado al estado actual del partido.",
      "consenso": ["Resumen 1", "Resumen 2"]
    }}
    """
    try:
        response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"})
        return json.loads(response.choices[0].message.content), status_code
    except Exception as e:
        st.error(f"Error OpenAI: {e}"); return None, status_code

def show_live_stream_options(match):
    """Muestra enlaces externos si el partido está en vivo"""
    col_tz = pytz.timezone('America/Bogota')
    now_col = datetime.now(col_tz)
    time_diff = now_col - match['match_time']
    is_live = timedelta(0) <= time_diff <= timedelta(hours=2, minutes=30)
    
    search_query = f"{match['home_team']} vs {match['away_team']} en vivo"
    
    if is_live:
        st.success("🔴 ¡El partido está EN VIVO AHORA! Ábrelo en una ventana externa para verlo:", icon="🔴")
        c1, c2, c3 = st.columns(3)
        c1.link_button("📺 Buscar en YouTube", f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}", use_container_width=True)
        c2.link_button("🔴 Ver en Google", f"https://www.google.com/search?q={search_query.replace(' ', '+')}+online", use_container_width=True)
        c3.link_button("⭐ Buscar en ESPN/DAZN", f"https://www.google.com/search?q={search_query.replace(' ', '+')}+ESPN+o+DAZN", use_container_width=True)
    else:
        st.info("⏳ El partido aún no ha comenzado o ya finalizó. Aquí podrás verlo en vivo cuando inicie:")
        st.markdown(f"[Busca canales oficiales aquí](https://www.google.com/search?q=Donde+ver+{match['home_team']}+vs+{match['away_team']}+colombia)")

def show_betting_app():
    st.markdown("<h1 style='text-align: center;'>🤖 AI Sports Bet Generator PRO</h1>", unsafe_allow_html=True)
    odds_api_key = st.secrets["odds_api"]; openai_api_key = st.secrets["openai"]
    
    st.sidebar.title("⚙️ Panel de Control")
    timeframe = st.sidebar.radio("📅 Periodo", ["Hoy", "Esta Semana"], horizontal=True)
    if st.sidebar.button("🧹 Limpiar Memoria"): st.cache_data.clear()
    
    all_matches = get_sports_matches(odds_api_key)
    if not all_matches: st.error("No hay partidos hoy."); return
    
    sports_available = list(set([f"{m['icon']} {m['sport_title']}" for m in all_matches]))
    selected_sport = st.sidebar.selectbox("Deporte", ["Todos"] + sorted(sports_available))
    
    col_tz = pytz.timezone('America/Bogota'); today_col = datetime.now(col_tz).date()
    filtered = [m for m in all_matches if (selected_sport=="Todos" or f"{m['icon']} {m['sport_title']}"==selected_sport) and (timeframe=="Esta Semana" or m['match_time'].date()==today_col)]
    
    if filtered:
        if st.button(f"🚀 Generar Análisis IA para {len(filtered)} partidos", use_container_width=True):
            st.session_state['generate'] = True
            db.increment_analysis(st.session_state.user[2])
            
    current_day = None
    for match in filtered:
        if timeframe == "Esta Semana":
            fecha_str = f"{DIAS_SEMANA[match['match_time'].weekday()]} {match['match_time'].day:02d}/{match['match_time'].month:02d}"
            if current_day != fecha_str:
                if current_day: st.divider()
                st.markdown(f"### 📅 {fecha_str}"); current_day = fecha_str
        
        # Calcular estado para mostrar el indicador visual en el título
        status_code, _ = get_match_status(match['match_time'])
        status_emoji = "🔴 EN VIVO" if status_code == "EN VIVO" else ("⏳ Próximamente" if status_code == "PRE-PARTIDO" else "✅ Finalizado")
        
        st.markdown(f"#### {match['icon']} {match['home_team']} vs {match['away_team']} - 🕒 {match['match_time'].strftime('%H:%M')} ({status_emoji})")
        
        with st.expander("💰 Ver Cuotas, Análisis IA y Transmisión"):
            show_live_stream_options(match)
            st.divider()

            if st.session_state.get('generate'):
                with st.spinner(f"IA analizando datos (Estado: {status_code})..."): 
                    ai_data, _ = generate_ai_analysis(openai_api_key, match)
                
                if ai_data:
                    st.markdown("##### 🔑 Conclusiones clave")
                    [st.markdown(f"- {c}") for c in ai_data.get("conclusiones", [])]
                    st.divider()
                    
                    st.markdown("##### 🎯 Mejores apuestas para este partido (4 alternativas por riesgo)")
                    c1, c2, c3 = st.columns(3)
                    for col, title, emoji, key in [(c1,"Bajo Riesgo","🟢","bajo_riesgo"), (c2,"Medio Riesgo","🟡","riesgo_medio"), (c3,"Alto Riesgo","🔴","alto_riesgo")]:
                        with col:
                            st.markdown(f"**{emoji} {title}**")
                            for i, item in enumerate(ai_data.get(key, []), 1):
                                st.markdown(f"**{i}. {item.get('mercado','')}**\n{item.get('explicacion','')}")
                                st.success(f"**{item.get('pick','')}**")
                                if i < len(ai_data.get(key, [])): st.markdown("---")
                            
                    st.markdown("##### 📊 Análisis del pronóstico de apuesta (IA)")
                    st.write(ai_data.get("analisis_ia", ""))
                    
                    st.markdown("##### 🌐 Consenso y Resumen")
                    for cons in ai_data.get("consenso", []):
                        st.info(cons)
            else: 
                st.warning("Presiona el botón superior para generar los análisis IA.")
