"""Features pre-partido para el modelo supervisado 1X2.

Regla única, verificada por `tests/test_ml_features.py`: la fila de un partido
jugado el día D solo usa partidos jugados ANTES de D, ni siquiera los del
mismo día. Las cuotas se guardan aparte (`mk_*`) como benchmark y nunca
entran en `FEATURES_*`.

- ELO de clubes: K=20, +60 de localía, sin multiplicador por goles. Arranca
  en 1500 en primera y 1350 en segunda; se actualiza también con los
  partidos de segunda, así los ascendidos llegan con su nivel.
- Forma: puntos, goles a favor y en contra por partido en los últimos 5 (de
  cualquier división del país que tengamos). Sin historia queda NaN.
- Descanso: días desde el último partido, tope 21. Solo vemos la liga: un
  partido de copa o de Europa en el medio no cuenta (limitación conocida).
- Dixon-Coles: el modelo de `src/clubs/model.py`, reajustado cada lunes con
  los 3 años previos de primera y segunda de esa liga.
- xG: no entra. Solo existe desde 2026-27 y no hay con qué entrenarlo.
"""
from __future__ import annotations

import bisect
import math
from collections import defaultdict, deque
from datetime import date, timedelta
from itertools import groupby

import numpy as np
import pandas as pd

from src.clubs.backtest import no_vig
from src.clubs.data import Match
from src.clubs.leagues import LEAGUES, League
from src.clubs.model import fit

ELO_K = 20.0
ELO_HOME = 60.0
ELO_START = {1: 1500.0, 2: 1350.0}
FORM_N = 5
REST_CAP = 21
DC_HISTORY_DAYS = 3 * 365

FEATURES_ELO = ["elo_diff"]
FEATURES_FORM = ["form_pts_h", "form_pts_a", "form_gf_h", "form_ga_h", "form_gf_a", "form_ga_a"]
FEATURES_REST = ["rest_h", "rest_a"]
FEATURES_DC = ["dc_ph", "dc_pd", "dc_pa", "dc_log_lh", "dc_log_la"]
LEAGUE_COLS = [f"lg_{c}" for c in LEAGUES]
FEATURES_BASIC = FEATURES_ELO + FEATURES_FORM + FEATURES_REST + LEAGUE_COLS
FEATURES_FULL = FEATURES_BASIC + FEATURES_DC


def outcome(m: Match) -> int:
    hg, ag = m.score()
    return 0 if hg > ag else 1 if hg == ag else 2


def _country(div: str) -> str:
    return div.rstrip("0123456789")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _key(m: Match) -> tuple:
    return (m.div, m.day, m.home, m.away)


def elo_form_rest(matches: list[Match], top_divs: set[str]) -> dict[tuple, dict]:
    """Features de ELO, forma y descanso, día por día, antes de actualizar."""
    elo: dict[tuple, float] = {}
    hist: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=FORM_N))
    last: dict[tuple, date] = {}
    out: dict[tuple, dict] = {}
    ordered = sorted(matches, key=lambda m: m.day)
    for day, group in groupby(ordered, key=lambda m: m.day):
        ms = list(group)
        for m in ms:                                   # 1) features con lo de ayer
            start = ELO_START[1 if m.div in top_divs else 2]
            kh, ka = (_country(m.div), m.home), (_country(m.div), m.away)
            f = {"elo_diff": elo.get(kh, start) - elo.get(ka, start)}
            for side, k in (("h", kh), ("a", ka)):
                h = hist[k]
                f[f"form_pts_{side}"] = float(np.mean([x[0] for x in h])) if h else math.nan
                f[f"form_gf_{side}"] = float(np.mean([x[1] for x in h])) if h else math.nan
                f[f"form_ga_{side}"] = float(np.mean([x[2] for x in h])) if h else math.nan
                f[f"rest_{side}"] = min((day - last[k]).days, REST_CAP) if k in last else math.nan
            out[_key(m)] = f
        for m in ms:                                   # 2) recién ahora se actualiza
            if not m.played:
                continue
            start = ELO_START[1 if m.div in top_divs else 2]
            kh, ka = (_country(m.div), m.home), (_country(m.div), m.away)
            rh, ra = elo.get(kh, start), elo.get(ka, start)
            exp_h = 1 / (1 + 10 ** (-(rh + ELO_HOME - ra) / 400))
            hg, ag = m.score()
            s = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            elo[kh] = rh + ELO_K * (s - exp_h)
            elo[ka] = ra - ELO_K * (s - exp_h)
            pts = 3 if hg > ag else 1 if hg == ag else 0
            hist[kh].append((pts, hg, ag))
            hist[ka].append((3 - pts if pts != 1 else 1, ag, hg))
            last[kh] = last[ka] = day
    return out


def dc_features(matches: list[Match], lg: League, targets: list[Match]) -> dict[tuple, dict]:
    """Dixon-Coles reajustado cada lunes con los 3 años previos de la liga."""
    pool = sorted((m for m in matches if m.div in (lg.code, lg.lower) and m.played),
                  key=lambda m: m.day)
    days = [m.day for m in pool]
    out: dict[tuple, dict] = {}
    for week, group in groupby(sorted(targets, key=lambda m: m.day), key=lambda m: _monday(m.day)):
        lo = bisect.bisect_left(days, week - timedelta(days=DC_HISTORY_DAYS))
        hi = bisect.bisect_left(days, week)
        hist = pool[lo:hi]
        r = fit(hist, week) if hist else None
        for m in group:
            if r is None or m.home not in r.att or m.away not in r.att:
                out[_key(m)] = dict.fromkeys(FEATURES_DC, math.nan)
                continue
            ph, pd_, pa, _ = r.probs(m.home, m.away)
            lh, la = r.lambdas(m.home, m.away)
            out[_key(m)] = {"dc_ph": ph, "dc_pd": pd_, "dc_pa": pa,
                            "dc_log_lh": math.log(lh), "dc_log_la": math.log(la)}
    return out


def build(matches: list[Match], leagues: list[League], seasons: tuple[str, ...]) -> pd.DataFrame:
    """Una fila por partido de primera en `seasons`, con features y benchmark."""
    top = {lg.code for lg in leagues}
    efr = elo_form_rest(matches, top)
    rows = []
    for lg in leagues:
        targets = [m for m in matches if m.div == lg.code and m.season in seasons]
        dc = dc_features(matches, lg, targets)
        for m in targets:
            mk = no_vig(m.odds) if m.odds else (math.nan,) * 3
            rows.append({
                "div": m.div, "season": m.season, "day": m.day, "home": m.home, "away": m.away,
                "y": outcome(m) if m.played else math.nan,
                "hg": m.hg, "ag": m.ag,
                "mk_h": mk[0], "mk_d": mk[1], "mk_a": mk[2],
                **efr[_key(m)], **dc[_key(m)],
                **{c: float(c == f"lg_{m.div}") for c in LEAGUE_COLS},
            })
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    return df.sort_values(["day", "div", "home"]).reset_index(drop=True)
