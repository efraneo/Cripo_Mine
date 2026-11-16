"""
betplay.py — Liga BetPlay Dimayor (Colombia) vía API-Football (api-sports.io).

OPCIONAL: solo se activa si existe el secret `football_api` en Secrets
(o variable de entorno FOOTBALL_API_KEY). Sin clave, la app funciona igual.

Notas honestas:
- The Odds API NO cubre la Liga BetPlay -> no hay líneas de valor para esta liga.
  Los análisis aquí son estadísticos/tácticos (forma, H2H), NO apuestas de valor.
- Plan gratuito de API-Football: 100 req/día. Por eso se cachea agresivamente:
  liga 7 días, fixtures 1h, forma 12h.
- Endpoint base: https://v3.football.api-sports.io  (header x-apisports-key)
"""
import os
from datetime import datetime, timedelta

import pytz
import requests
import streamlit as st

COL_TZ = pytz.timezone("America/Bogota")
BASE_URL = "https://v3.football.api-sports.io"
TIMEOUT = 20


def _get_key():
    try:
        key = st.secrets.get("football_api") or st.secrets.get("FOOTBALL_API_KEY")
    except Exception:
        key = None
    return key or os.environ.get("FOOTBALL_API_KEY")


def is_configured():
    return bool(_get_key())


def _api(endpoint, params):
    headers = {"x-apisports-key": _get_key()}
    r = requests.get(f"{BASE_URL}/{endpoint}", params=params, headers=headers, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"API-Football HTTP {r.status_code}")
    data = r.json()
    errors = data.get("errors") or {}
    if errors:
        raise RuntimeError(f"API-Football errors: {errors}")
    return data.get("response", [])


@st.cache_data(ttl=604800, show_spinner=False)  # 7 días
def get_betplay_league():
    """Encuentra dinámicamente la Liga BetPlay / Primera A de Colombia."""
    items = _api("leagues", {"country": "Colombia", "current": "true", "type": "League"})
    if not items:
        items = _api("leagues", {"country": "Colombia"})

    def score_of(item):
        name = (item.get("league") or {}).get("name", "").lower()
        pts = 0
        for pat, p in (("betplay", 100), ("primera", 80), ("dimayor", 60), ("profesional", 30), ("a", 10)):
            if pat in name:
                pts += p
        return pts

    items = sorted(items, key=score_of, reverse=True)
    for item in items:
        league = item.get("league") or {}
        seasons = item.get("seasons") or []
        current = next((s for s in seasons if s.get("current")), None)
        if current:
            return {
                "id": league.get("id"),
                "name": league.get("name"),
                "season": current.get("year"),
                "coverage_odds": bool((current.get("coverage") or {}).get("odds")),
                "logo": league.get("logo"),
            }
    return None


@st.cache_data(ttl=3600, show_spinner=False)  # 1h
def get_this_week_fixtures(league_id, season):
    today = datetime.now(COL_TZ).date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    items = _api(
        "fixtures",
        {
            "league": league_id,
            "season": season,
            "from": start_of_week.strftime("%Y-%m-%d"),
            "to": end_of_week.strftime("%Y-%m-%d"),
            "timezone": "America/Bogota",
        },
    )
    fixtures = []
    for it in items:
        fx = it.get("fixture") or {}
        league = it.get("league") or {}
        teams = it.get("teams") or {}
        home = (teams.get("home") or {}).get("name")
        away = (teams.get("away") or {}).get("name")
        date_iso = fx.get("date")
        try:
            match_time = datetime.fromisoformat(str(date_iso).replace("Z", "+00:00")).astimezone(COL_TZ)
        except (ValueError, TypeError):
            continue
        fixtures.append(
            {
                "fixture_id": fx.get("id"),
                "match_time": match_time,
                "home_team": home,
                "away_team": away,
                "home_id": (teams.get("home") or {}).get("id"),
                "away_id": (teams.get("away") or {}).get("id"),
                "venue": (fx.get("venue") or {}).get("name"),
                "round": league.get("round"),
                "status": (fx.get("status") or {}).get("short"),
            }
        )
    fixtures.sort(key=lambda f: f["match_time"])
    return fixtures


@st.cache_data(ttl=43200, show_spinner=False)  # 12h
def get_team_form(team_id, league_id, season, last=5):
    """Racha: lista de 'G'/'E'/'P' de los últimos partidos (perspectiva del equipo)."""
    items = _api(
        "fixtures",
        {"league": league_id, "season": season, "team": team_id, "last": last, "status": "FT-AET-PEN"},
    )
    form = []
    for it in items[-last:]:
        teams = it.get("teams") or {}
        home_id = (teams.get("home") or {}).get("id")
        goals = (it.get("goals") or {})
        gh, ga = goals.get("home"), goals.get("away")
        if gh is None or ga is None:
            continue
        if team_id == home_id:
            gf, gc = gh, ga
        else:
            gf, gc = ga, gh
        form.append("G" if gf > gc else ("E" if gf == gc else "P"))
    return form
