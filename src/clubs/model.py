"""Dixon-Coles por liga, ajustado con numpy (sin scipy).

λ_local  = μ · h · ataque_local · defensa_visitante
λ_visita = μ ·     ataque_visita · defensa_local

Los parámetros se ajustan por máxima verosimilitud Poisson con el algoritmo
iterativo de Maher (cada ataque = goles hechos / goles esperados con ataque
1, y así por turnos), con peso exp(-ξ·días) para que lo reciente mande
(Dixon y Coles, 1997). Después se busca ρ por grilla con las λ fijas.

- Objetivo de gol: si el partido tiene xG, mezcla goles y xG (`xg_weight`);
  el xG es menos ruidoso que el marcador con pocas jornadas jugadas.
- Shrinkage: `prior` goles ficticios a ritmo promedio para cada equipo, así
  un recién llegado con 3 partidos no queda con ratings extremos.
- Se ajusta junto con la segunda división: los equipos que suben y bajan
  conectan las dos tablas, y los ascendidos llegan con historia real.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from src.betting.odds import joint_matrix
from src.clubs.data import Match

XI = 0.0019          # por día: un partido de hace un año pesa ~50%
XG_WEIGHT = 0.5
PRIOR = 3.0


@dataclass
class Ratings:
    teams: list[str]
    att: dict[str, float]
    defe: dict[str, float]
    mu: float
    home: float
    rho: float
    n_eff: dict[str, float] = field(default_factory=dict)

    def lambdas(self, home: str, away: str) -> tuple[float, float]:
        return (self.mu * self.home * self.att[home] * self.defe[away],
                self.mu * self.att[away] * self.defe[home])

    def probs(self, home: str, away: str) -> tuple[float, float, float, list[list[float]]]:
        lh, la = self.lambdas(home, away)
        g = joint_matrix(lh, la, rho=self.rho)
        n = len(g)
        ph = sum(g[x][y] for x in range(n) for y in range(n) if x > y)
        pd = sum(g[x][x] for x in range(n))
        return ph, pd, 1 - ph - pd, g


def fit(matches: list[Match], ref: date, xi: float = XI, xg_weight: float = XG_WEIGHT,
        prior: float = PRIOR, iters: int = 60) -> Ratings:
    played = [m for m in matches if m.played and m.day < ref]
    teams = sorted({m.home for m in played} | {m.away for m in played})
    ix = {t: i for i, t in enumerate(teams)}
    h = np.array([ix[m.home] for m in played])
    a = np.array([ix[m.away] for m in played])
    w = np.exp(-xi * np.array([(ref - m.day).days for m in played], dtype=float))

    def target(g: int, xg: float | None) -> float:
        return g if xg is None else (1 - xg_weight) * g + xg_weight * xg
    yh = np.array([target(m.hg, m.hxg) for m in played])
    ya = np.array([target(m.ag, m.axg) for m in played])

    n = len(teams)
    att, dfn = np.ones(n), np.ones(n)
    mu = float((w * (yh + ya)).sum() / (2 * w.sum()))
    hadv = float((w * yh).sum() / max((w * ya).sum(), 1e-9))
    for _ in range(iters):
        eh = mu * hadv * dfn[a]           # esperado local sin su ataque
        ea = mu * dfn[h]                  # esperado visita sin su ataque
        num = np.bincount(h, w * yh, n) + np.bincount(a, w * ya, n) + prior * mu
        den = np.bincount(h, w * eh, n) + np.bincount(a, w * ea, n) + prior * mu
        att = num / den
        eh = mu * hadv * att[h]           # esperado concedido por la visita sin su defensa
        ea = mu * att[a]
        num = np.bincount(a, w * yh, n) + np.bincount(h, w * ya, n) + prior * mu
        den = np.bincount(a, w * eh, n) + np.bincount(h, w * ea, n) + prior * mu
        dfn = num / den
        # normaliza (media geométrica 1) y reajusta μ y localía
        att /= math.exp(np.log(att).mean())
        dfn /= math.exp(np.log(dfn).mean())
        lh = att[h] * dfn[a]
        la = att[a] * dfn[h]
        hadv = float((w * yh).sum() / (w * lh).sum()) / float((w * ya).sum() / (w * la).sum())
        mu = float((w * ya).sum() / (w * la).sum())

    rating = Ratings(teams, dict(zip(teams, att.round(4))), dict(zip(teams, dfn.round(4))),
                     round(mu, 4), round(hadv, 4), 0.0,
                     {t: round(float(np.bincount(h, w, n)[i] + np.bincount(a, w, n)[i]), 1)
                      for t, i in ix.items()})
    rating.rho = fit_rho(rating, played, w)
    return rating


def fit_rho(r: Ratings, played: list[Match], w: np.ndarray) -> float:
    """ρ por grilla: solo importan los marcadores 0-0, 1-0, 0-1 y 1-1."""
    lam = [r.lambdas(m.home, m.away) for m in played]
    best, best_ll = 0.0, -math.inf
    for rho in np.arange(-0.25, 0.101, 0.01):
        ll = 0.0
        for (lh, la), m, wi in zip(lam, played, w):
            x, y = m.hg, m.ag
            if x > 1 or y > 1:
                continue
            t = {(0, 0): 1 - lh * la * rho, (0, 1): 1 + lh * rho,
                 (1, 0): 1 + la * rho, (1, 1): 1 - rho}[(x, y)]
            if t <= 0:
                ll = -math.inf
                break
            ll += wi * math.log(t)
        if ll > best_ll:
            best, best_ll = float(round(rho, 2)), ll
    return best
