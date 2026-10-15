"""Ratings de xG ajustados por rival (StatsBomb, selecciones).

Promediar el xG crudo engaña: generar 2.0 xG contra Gambia no es lo mismo
que contra Francia. Ajustamos un modelo multiplicativo (Maher 1982, el mismo
que usa el motor de partido) sobre el xG sin penales por 90':

    npxG(i vs j) ≈ MU × ataque_i × defensa_j

con tres correcciones:

  1. RECENCIA: cada partido pesa exp(-edad_días / TAU). Con TAU=730 la
     Copa América/Euro 2024 pesan ~0.35 y el Mundial 2022 ~0.15.
  2. SHRINKAGE: PRIOR_GAMES partidos ficticios "promedio" por equipo, para
     que una selección con 3 partidos no quede en un extremo por azar.
  3. NORMALIZACIÓN: media geométrica de ataque y defensa = 1.

Se resuelve por mínimos cuadrados ponderados alternados (converge en ~20
iteraciones). Salida: xG a favor/en contra esperados contra un rival medio.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date

from src.etl.scrapers.statsbomb import SB_TO_FIFA, TeamMatch

TAU_DAYS = 730.0
PRIOR_GAMES = 2.0
ITERATIONS = 50


@dataclass
class XgRating:
    team: str                 # nombre StatsBomb
    fifa_code: str | None
    xg_for: float             # npxG/90 esperado vs rival medio
    xg_against: float         # npxG/90 concedido esperado vs rival medio
    raw_xg_for: float         # npxG/90 crudo ponderado (sin ajuste por rival)
    raw_xg_against: float
    att: float                # multiplicador (1 = medio)
    defe: float               # multiplicador (>1 concede más que el medio)
    n_matches: int
    n_eff: float              # suma de pesos de recencia
    goals: int
    goals_against: int
    last_match: str
    competitions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _per90(value: float, minutes: float) -> float:
    return value * 90.0 / max(minutes, 90.0)


def fit_ratings(rows: list[TeamMatch], today: date | None = None) -> dict[str, XgRating]:
    """Ajusta ataque/defensa por equipo. Clave del dict: nombre StatsBomb."""
    if not rows:
        return {}
    today = today or date.today()
    obs = []  # (team, opp, npxg90, w)
    for r in rows:
        w = math.exp(-max(0, (today - r.date).days) / TAU_DAYS)
        obs.append((r.team, r.opponent, _per90(r.np_xg, r.minutes), w))

    teams = sorted({o[0] for o in obs})
    mu = sum(y * w for _, _, y, w in obs) / sum(w for *_, w in obs)
    att = dict.fromkeys(teams, 1.0)
    dfn = dict.fromkeys(teams, 1.0)

    by_team = defaultdict(list)
    by_opp = defaultdict(list)
    for t, o, y, w in obs:
        by_team[t].append((o, y, w))
        by_opp[o].append((t, y, w))

    for _ in range(ITERATIONS):
        # ataque_i = Σ w·y / Σ w·MU·def_j   (+ prior de PRIOR_GAMES partidos medios)
        for t in teams:
            num = sum(w * y for _, y, w in by_team[t]) + PRIOR_GAMES * mu
            den = sum(w * mu * dfn[o] for o, _, w in by_team[t]) + PRIOR_GAMES * mu
            att[t] = num / den
        for t in teams:
            num = sum(w * y for _, y, w in by_opp[t]) + PRIOR_GAMES * mu
            den = sum(w * mu * att[a] for a, _, w in by_opp[t]) + PRIOR_GAMES * mu
            dfn[t] = num / den
        ga = math.exp(sum(math.log(att[t]) for t in teams) / len(teams))
        gd = math.exp(sum(math.log(dfn[t]) for t in teams) / len(teams))
        att = {t: v / ga for t, v in att.items()}
        dfn = {t: v / gd for t, v in dfn.items()}
    # MU absorbe la normalización para que MU·att·def siga ajustando los datos
    mu_adj = mu * ga * gd

    out: dict[str, XgRating] = {}
    for t in teams:
        mine = [r for r in rows if r.team == t]
        ws = [math.exp(-max(0, (today - r.date).days) / TAU_DAYS) for r in mine]
        wsum = sum(ws)
        raw_f = sum(w * _per90(r.np_xg, r.minutes) for w, r in zip(ws, mine)) / wsum
        raw_a = sum(w * _per90(r.np_xg_against, r.minutes) for w, r in zip(ws, mine)) / wsum
        comps = sorted({r.competition for r in mine}, key=lambda c: c[-4:])
        out[t] = XgRating(
            team=t,
            fifa_code=SB_TO_FIFA.get(t),
            xg_for=round(mu_adj * att[t], 3),
            xg_against=round(mu_adj * dfn[t], 3),
            raw_xg_for=round(raw_f, 3),
            raw_xg_against=round(raw_a, 3),
            att=round(att[t], 4),
            defe=round(dfn[t], 4),
            n_matches=len(mine),
            n_eff=round(wsum, 2),
            goals=sum(r.goals for r in mine),
            goals_against=sum(r.goals_against for r in mine),
            last_match=max(r.date for r in mine).isoformat(),
            competitions=comps,
        )
    return out


if __name__ == "__main__":
    from src.etl.scrapers.statsbomb import load_team_matches

    ratings = fit_ratings(load_team_matches(offline=True))
    print(f"{'equipo':22s} {'xGF':>5s} {'xGA':>5s} {'dif':>6s} {'crudoF':>6s} "
          f"{'crudoA':>6s} {'n':>3s} {'n_eff':>5s}")
    for r in sorted(ratings.values(), key=lambda r: r.xg_against - r.xg_for)[:30]:
        print(f"{r.team:22s} {r.xg_for:5.2f} {r.xg_against:5.2f} "
              f"{r.xg_for - r.xg_against:+6.2f} {r.raw_xg_for:6.2f} {r.raw_xg_against:6.2f} "
              f"{r.n_matches:3d} {r.n_eff:5.2f}")
