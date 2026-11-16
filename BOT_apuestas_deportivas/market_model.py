"""
market_model.py — Motor estadístico del Bot de Apuestas.

Inspirado en los mejores proyectos open-source de la categoría:
  - golazo (ohugonnot): de-vig Shin/Power, solver de lambdas, matriz Dixon-Coles.
  - Sentinel/Testbett (dukemawex): implied prob, devig, edge, Kelly fraccional, Brier.
  - prediction-tool (TemiKayode): line shopping (mejor precio), CLV.

Todo es stdlib puro (math). No requiere datos históricos externos:
ancla las probabilidades al propio mercado (consenso multi-casa sin margen),
que es la fuente de información más honesta disponible gratis.
"""
import math

# ---------------------------------------------------------------------------
# Probabilidades básicas
# ---------------------------------------------------------------------------

def implied_prob(decimal_odds):
    """Probabilidad implícita en una cuota decimal."""
    if not decimal_odds or decimal_odds <= 0:
        return 0.0
    return 1.0 / decimal_odds


def overround(odds_list):
    return sum(implied_prob(o) for o in odds_list)


def demargin_proportional(odds_list):
    """De-vig por normalización simple. Rápido y robusto."""
    inv = [implied_prob(o) for o in odds_list]
    total = sum(inv)
    if total <= 0:
        return [1.0 / len(odds_list)] * len(odds_list)
    return [p / total for p in inv]


def demargin_power(odds_list):
    """De-vig 'power': corrige el sesgo favorito-outsider."""
    inv = [implied_prob(o) for o in odds_list]
    lo, hi = 0.5, 1.5
    for _ in range(60):
        k = (lo + hi) / 2
        s = sum(p ** k for p in inv)
        if s > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    ps = [p ** k for p in inv]
    s = sum(ps)
    return [p / s for p in ps]


def demargin_shin(odds_list):
    """De-vig método Shin (1993): estado del arte contra el sesgo favorito-outsider.

    Modela una fracción z de parieurs informados. Generaliza a n resultados.
    """
    inv = [implied_prob(o) for o in odds_list]
    book = sum(inv)
    if book <= 0:
        return [1.0 / len(odds_list)] * len(odds_list)

    def probs(z):
        n = len(inv)
        d = 2.0 * (1.0 - z) if z < 1 else 1e-9
        return [
            (math.sqrt(z * z + 4.0 * (1.0 - z) * (pi * pi) / book) - z) / d
            for pi in inv
        ]

    lo, hi = 0.0, 0.9999
    for _ in range(80):
        z = (lo + hi) / 2
        if sum(probs(z)) > 1.0:
            lo = z
        else:
            hi = z
    ps = probs((lo + hi) / 2)
    s = sum(ps)
    return [p / s for p in ps]


def demargin(odds_list, method="proportional"):
    if method == "shin":
        return demargin_shin(odds_list)
    if method == "power":
        return demargin_power(odds_list)
    return demargin_proportional(odds_list)


# ---------------------------------------------------------------------------
# Consenso multi-casa + line shopping
# ---------------------------------------------------------------------------

def per_book_demargined(bookmakers, market_key="h2h", method="proportional"):
    """Devuelve [(outcome_name, fair_prob, raw_odds, book_title)] de-viggeados por casa."""
    rows = []
    for bm in bookmakers or []:
        for m in bm.get("markets", []):
            if m.get("key") != market_key:
                continue
            outcomes = m.get("outcomes", [])
            prices = [o.get("price") for o in outcomes]
            if len(prices) < 2 or any(p is None or p <= 1.0 for p in prices):
                continue
            fair = demargin(prices, method=method)
            for o, p in zip(outcomes, fair):
                rows.append({
                    "outcome": o.get("name"),
                    "point": o.get("point"),          # presente en totals/spreads
                    "fair_prob": p,
                    "odds": o.get("price"),
                    "book": bm.get("title", "?"),
                })
    return rows


def consensus_fair_probs(bookmakers, market_key="h2h", point=None, method="proportional"):
    """Proba justa por resultado = promedio de las probas de-viggeadas por casa.

    Para totals/spreads filtra por `point` (p.ej. 2.5). Devuelve dict outcome -> fair_prob.
    Las casas con baja liquidez o líneas raras pesan igual; suficiente para consenso.
    """
    rows = [r for r in per_book_demargined(bookmakers, market_key, method)
            if point is None or r["point"] == point]
    acc = {}
    n = {}
    for r in rows:
        acc[r["outcome"]] = acc.get(r["outcome"], 0.0) + r["fair_prob"]
        n[r["outcome"]] = n.get(r["outcome"], 0) + 1
    fair = {k: acc[k] / n[k] for k in acc}
    total = sum(fair.values())
    if total > 0:
        fair = {k: v / total for k, v in fair.items()}
    return fair


def best_prices(bookmakers, market_key="h2h", point=None):
    """Line shopping: mejor cuota disponible por resultado (y en qué casa)."""
    rows = [r for r in per_book_demargined(bookmakers, market_key, "proportional")
            if point is None or r["point"] == point]
    best = {}
    for r in rows:
        cur = best.get(r["outcome"])
        if cur is None or r["odds"] > cur["odds"]:
            best[r["outcome"]] = {"odds": r["odds"], "book": r["book"]}
    return best


def expected_value(prob, decimal_odds):
    """EV = prob * cuota - 1. Positivo = apuesta de valor."""
    return prob * decimal_odds - 1.0


def kelly_fraction(prob, decimal_odds, fraction=0.25, cap=0.05):
    """Kelly fraccional (1/4 por defecto, tope 5% del bankroll)."""
    b = decimal_odds - 1.0
    if b <= 0 or prob <= 0:
        return 0.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    f = max(0.0, f) * fraction
    return min(f, cap)


def brier_score(probs, outcomes):
    if not probs:
        return None
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / len(probs)


# ---------------------------------------------------------------------------
# Motor Poisson / Dixon-Coles anclado al mercado (solo fútbol, 1X2)
# ---------------------------------------------------------------------------

def poisson_pmf(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dc_tau(i, j, lh, la, rho):
    """Corrección Dixon-Coles para los scores bajos (0-0, 1-0, 0-1, 1-1)."""
    if i == 0 and j == 0:
        return 1.0 - lh * la * rho
    if i == 0 and j == 1:
        return 1.0 + lh * rho
    if i == 1 and j == 0:
        return 1.0 + la * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lh, la, rho=-0.13, max_goals=9):
    m = {}
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_pmf(i, lh) * poisson_pmf(j, la) * dc_tau(i, j, lh, la, rho)
            p = max(p, 0.0)
            m[(i, j)] = p
            total += p
    if total > 0:
        for k in m:
            m[k] /= total
    return m


def outcome_probs(matrix):
    ph = pd = pa = 0.0
    for (i, j), p in matrix.items():
        if i > j:
            ph += p
        elif i == j:
            pd += p
        else:
            pa += p
    return ph, pd, pa


def calibrate_matrix(matrix, p_home, p_draw, p_away):
    """Reescala la matriz para que sus marginales 1X2 sean EXACTAMENTE las del mercado."""
    ph, pd, pa = outcome_probs(matrix)
    factor = {
        "H": (p_home / ph) if ph > 1e-12 else 0.0,
        "D": (p_draw / pd) if pd > 1e-12 else 0.0,
        "A": (p_away / pa) if pa > 1e-12 else 0.0,
    }

    def res_of(k):
        i, j = k
        return "H" if i > j else ("D" if i == j else "A")

    m2 = {k: v * factor[res_of(k)] for k, v in matrix.items()}
    s = sum(m2.values())
    return {k: v / s for k, v in m2.items()} if s > 0 else matrix


def solve_lambdas(p_home, p_draw, p_away, total_hint=None, rho=-0.13):
    """Grid search 2 etapas: encuentra (λ_home, λ_away) que reproduzcan las 1X2 del mercado."""

    def err(lh, la):
        m = score_matrix(lh, la, rho, max_goals=8)
        ph, pd, pa = outcome_probs(m)
        e = (ph - p_home) ** 2 + (pd - p_draw) ** 2 + (pa - p_away) ** 2
        if total_hint is not None:
            delta = (lh + la) - total_hint
            e += 0.01 * min(delta * delta, 1.0)
        return e

    def grid(lo, hi, step):
        best, berr = (1.0, 1.0), 1e9
        n = int((hi - lo) / step) + 1
        for a in range(n):
            lh = lo + a * step
            for b in range(n):
                la = lo + b * step
                if lh <= 0 or la <= 0:
                    continue
                e = err(lh, la)
                if e < berr:
                    berr, best = e, (lh, la)
        return best

    lh, la = grid(0.1, 4.5, 0.15)

    def refine(lh0, la0, span, step):
        best, berr = (lh0, la0), err(lh0, la0)
        n = int(2 * span / step) + 1
        for a in range(n):
            lh = lh0 - span + a * step
            for b in range(n):
                la = la0 - span + b * step
                if lh <= 0 or la <= 0:
                    continue
                e = err(lh, la)
                if e < berr:
                    berr, best = e, (lh, la)
        return best

    (lh, la) = refine(lh, la, 0.15, 0.05)
    (lh, la) = refine(lh, la, 0.06, 0.02)
    return lh, la


def derived_markets(p_home, p_draw, p_away, total_hint=None):
    """Matriz Dixon-Coles calibrada al mercado -> probabilidades derivadas.

    Devuelve dict con matriz lista para Over/Under 2.5, BTTS y dobles oportunidades.
    """
    lh, la = solve_lambdas(p_home, p_draw, p_away, total_hint=total_hint)
    m = score_matrix(lh, la, rho=-0.13, max_goals=10)
    m = calibrate_matrix(m, p_home, p_draw, p_away)

    p_over = sum(p for (i, j), p in m.items() if i + j >= 3)
    p_btts = sum(p for (i, j), p in m.items() if i >= 1 and j >= 1)
    ph, pd, pa = outcome_probs(m)

    return {
        "lambda_home": round(lh, 3),
        "lambda_away": round(la, 3),
        "over_2_5": p_over,
        "under_2_5": 1.0 - p_over,
        "btts_yes": p_btts,
        "btts_no": 1.0 - p_btts,
        "1x": ph + pd,   # doble oportunidad local o empate
        "x2": pd + pa,
        "12": ph + pa,
    }


def value_picks_for_match(bookmakers, sport_key_hint="soccer", home_team=None, away_team=None):
    """Detecta picks de VALOR por reglas (sin IA): EV >= 2% al mejor precio.

    Devuelve lista de dicts listas para mostrar en la UI y/o guardar.
    """
    picks = []
    fair = consensus_fair_probs(bookmakers, "h2h", method="proportional")
    best = best_prices(bookmakers, "h2h")
    for outcome, prob in fair.items():
        b = best.get(outcome)
        if not b:
            continue
        ev = expected_value(prob, b["odds"])
        picks.append({
            "mercado": f"1X2 / Ganador — {outcome}",
            "market_key": "h2h",
            "seleccion": outcome,
            "seleccion_raw": outcome,
            "linea": None,
            "cuota": b["odds"],
            "casa": b["book"],
            "prob_modelo": prob,
            "edge": ev,
            "kelly_frac": kelly_fraction(prob, b["odds"]),
            "es_valor": ev >= 0.02,
        })

    # Fútbol: mercados derivados (Over/Under 2.5) anclados al mercado
    if "soccer" in (sport_key_hint or "").lower() and len(fair) == 3:
        # Local/Away desde los nombres del evento (la API los da en el market h2h)
        p_draw = fair.get("Draw", fair.get("Empate", 1.0 / 3))
        p_home, p_away = None, None
        if home_team is not None:
            p_home = fair.get(home_team)
        if away_team is not None:
            p_away = fair.get(away_team)
        if p_home is None or p_away is None:
            others = [(k, v) for k, v in fair.items() if k not in ("Draw", "Empate")]
            if len(others) == 2:
                p_home, p_away = others[0][1], others[1][1]
        if p_home and p_away:
            try:
                dm = derived_markets(p_home, p_draw, p_away, total_hint=None)
                t_best = best_prices(bookmakers, "totals", point=2.5)
                for name, prob in (("Over", dm["over_2_5"]), ("Under", dm["under_2_5"])):
                    b = t_best.get(name)
                    if b:
                        ev = expected_value(prob, b["odds"])
                        picks.append({
                            "mercado": f"Over/Under 2.5 — {name} 2.5",
                            "market_key": "totals",
                            "seleccion": f"{name} 2.5",
                            "seleccion_raw": name,
                            "linea": 2.5,
                            "cuota": b["odds"],
                            "casa": b["book"],
                            "prob_modelo": prob,
                            "edge": ev,
                            "kelly_frac": kelly_fraction(prob, b["odds"]),
                            "es_valor": ev >= 0.02,
                        })
            except Exception:
                pass  # sin motor derivado -> se muestran solo h2h/IA
    return picks
