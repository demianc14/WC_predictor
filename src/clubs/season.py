"""Monte Carlo del resto de la temporada: tabla proyectada y probabilidades."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from src.clubs.data import Match
from src.clubs.model import Ratings


def current_table(played: list[Match], teams: list[str]) -> dict[str, dict]:
    t = {c: {"pj": 0, "pts": 0, "gf": 0, "gc": 0} for c in teams}
    for m in played:
        for c, gf, gc in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            t[c]["pj"] += 1
            t[c]["gf"] += gf
            t[c]["gc"] += gc
            t[c]["pts"] += 3 if gf > gc else 1 if gf == gc else 0
    return t


def remaining_fixtures(played: list[Match], teams: list[str]) -> list[tuple[str, str]]:
    """Liga a dos ruedas: todo cruce local-visita que todavía no se jugó."""
    done = {(m.home, m.away) for m in played}
    return [(h, a) for h in teams for a in teams if h != a and (h, a) not in done]


def simulate(r: Ratings, played: list[Match], teams: list[str], n: int = 10000,
             seed: int = 2627, fixtures: list[tuple[str, str]] | None = None) -> dict:
    """`fixtures`: lo que falta según el calendario; sin él, todo cruce no jugado."""
    rng = np.random.default_rng(seed)
    ix = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    base = current_table(played, teams)
    pts = np.tile([base[t]["pts"] for t in teams], (n, 1)).astype(float)
    gd = np.tile([base[t]["gf"] - base[t]["gc"] for t in teams], (n, 1)).astype(float)
    gf = np.tile([base[t]["gf"] for t in teams], (n, 1)).astype(float)
    if fixtures is None:
        fixtures = remaining_fixtures(played, teams)
    for h, a in fixtures:
        _, _, _, g = r.probs(h, a)
        flat = np.array(g).ravel()
        k = len(g)
        cell = rng.choice(flat.size, size=n, p=flat / flat.sum())
        x, y = cell // k, cell % k
        i, j = ix[h], ix[a]
        pts[:, i] += np.where(x > y, 3, np.where(x == y, 1, 0))
        pts[:, j] += np.where(y > x, 3, np.where(x == y, 1, 0))
        gd[:, i] += x - y
        gd[:, j] += y - x
        gf[:, i] += x
        gf[:, j] += y
    # orden: puntos, diferencia, goles a favor, y azar para desempatar el resto
    key = pts * 1e6 + gd * 1e3 + gf + rng.random((n, T))
    pos = np.empty((n, T), dtype=int)
    pos[np.arange(n)[:, None], np.argsort(-key, axis=1)] = np.arange(T)
    out = {}
    for t, i in ix.items():
        dist = np.bincount(pos[:, i], minlength=T) / n
        out[t] = {"xpts": round(float(pts[:, i].mean()), 1),
                  "pos": [round(float(p), 4) for p in dist]}
    return out


def by_team(matches: list[Match]) -> dict[str, list[Match]]:
    d: dict[str, list[Match]] = defaultdict(list)
    for m in matches:
        d[m.home].append(m)
        d[m.away].append(m)
    return d
