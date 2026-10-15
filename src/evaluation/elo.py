"""ELO reconstruido desde el historial, con fecha de corte.

eloratings.net solo publica el rating ACTUAL, así que no sirve para saber
cuánto valía cada selección el día antes del Mundial. Aquí se recalcula con
la metodología World Football Elo sobre el dataset martj42, usando solo
partidos anteriores al corte: un baseline reproducible y sin fuga de datos.

    We = 1 / (10^(−dr/400) + 1)          dr incluye +100 de localía si no es neutral
    ΔR = K · G · (W − We)                K por torneo, G por diferencia de goles
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import date

INITIAL_RATING = 1500.0
HOME_ADVANTAGE = 100.0

MAJOR_FINALS = {
    "UEFA Euro", "Copa América", "African Cup of Nations", "AFC Asian Cup",
    "Gold Cup", "CONCACAF Championship", "Confederations Cup", "Oceania Nations Cup",
}
NATIONS_LEAGUES = {"UEFA Nations League", "CONCACAF Nations League"}


def k_factor(tournament: str) -> float:
    if tournament == "FIFA World Cup":
        return 60.0
    if tournament in MAJOR_FINALS:
        return 50.0
    if "qualification" in tournament or tournament in NATIONS_LEAGUES:
        return 40.0
    if tournament == "Friendly":
        return 20.0
    return 30.0


def goal_multiplier(goal_diff: int) -> float:
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11.0 + gd) / 8.0


def expected_score(rating_diff: float) -> float:
    """We del equipo con ventaja `rating_diff` (empate cuenta 0.5)."""
    return 1.0 / (10.0 ** (-rating_diff / 400.0) + 1.0)


def rating_diff(r_home: float, r_away: float, neutral: bool) -> float:
    return r_home - r_away + (0.0 if neutral else HOME_ADVANTAGE)


def elo_1x2(we: float, draw_c: float) -> tuple[float, float, float]:
    """1X2 desde We con un modelo de empate de un parámetro.

    P(X) = c · 2·min(We, 1−We): máximo (= c) entre iguales, → 0 en goleadas
    anunciadas. El reparto conserva la esperanza del ELO: P(1) + P(X)/2 = We.
    Con c ≤ 1 las tres probabilidades quedan en [0, 1].
    """
    px = draw_c * 2.0 * min(we, 1.0 - we)
    return we - px / 2.0, px, 1.0 - we - px / 2.0


def compute_ratings(
    rows: Iterable[dict], cutoff: date, draw_fit_since: int = 1998,
) -> tuple[dict[str, float], list[tuple[float, str]]]:
    """Recorre partidos en orden cronológico hasta `cutoff` (exclusivo).

    `rows` usa el formato de history.load_results() (home_score/away_score
    int, neutral bool, _date). Devuelve (ratings por nombre martj42,
    [(We_home, resultado '1'/'X'/'2')] de los Mundiales desde
    `draw_fit_since`, para ajustar el modelo de empate).
    """
    ratings: dict[str, float] = {}
    wc_history: list[tuple[float, str]] = []
    for r in sorted(rows, key=lambda r: r["_date"]):
        if r["_date"] >= cutoff:
            break
        home, away = r["home_team"], r["away_team"]
        rh = ratings.get(home, INITIAL_RATING)
        ra = ratings.get(away, INITIAL_RATING)
        we = expected_score(rating_diff(rh, ra, r["neutral"]))
        gd = r["home_score"] - r["away_score"]
        w = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        if r["tournament"] == "FIFA World Cup" and r["_date"].year >= draw_fit_since:
            wc_history.append((we, "1" if gd > 0 else ("X" if gd == 0 else "2")))
        delta = k_factor(r["tournament"]) * goal_multiplier(gd) * (w - we)
        ratings[home] = rh + delta
        ratings[away] = ra - delta
    return ratings, wc_history


def fit_draw_c(history: list[tuple[float, str]]) -> float:
    """c que maximiza la verosimilitud 1X2 de `history` (búsqueda en rejilla)."""
    def loglik(c: float) -> float:
        total = 0.0
        for we, outcome in history:
            p1, px, p2 = elo_1x2(we, c)
            p = {"1": p1, "X": px, "2": p2}[outcome]
            total += math.log(max(p, 1e-12))
        return total

    grid = [i / 100 for i in range(5, 101)]
    return max(grid, key=loglik)
