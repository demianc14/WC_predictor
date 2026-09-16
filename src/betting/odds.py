"""Probabilidades y cuotas analiticas a partir de (lambda_h, lambda_a).

No usa Monte Carlo: enumera la matriz Dixon-Coles 0..N x 0..N (N=8 es mas
que suficiente para lambdas tipicas de futbol) y suma las celdas que
caen en cada mercado. Es exacto hasta ~1e-4 y ~1000x mas rapido que MC
para cuotas de un solo partido.

Mercados cubiertos:
  - 1X2 (home / draw / away)
  - Over/Under X.5 goles (X = 0.5, 1.5, 2.5, 3.5, 4.5)
  - BTTS (both teams to score)
  - Marcadores exactos (top-N)
  - Doble oportunidad (1X, 12, X2)
  - Cuota justa (1/p) y deteccion de valor vs cuota de casa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.simulation.match_engine import RHO, tau

MAX_GOALS = 8  # 9x9 = 81 celdas; suma de masa > 0.9999 para lambdas <= 4


def joint_matrix(lam_h: float, lam_a: float, rho: float = RHO,
                 max_goals: int = MAX_GOALS) -> list[list[float]]:
    """Matriz P_DC(x,y) renormalizada a suma 1 sobre la rejilla."""
    # P_poisson_h(x) y P_poisson_a(y) precalculados.
    def pois(lam: float, n: int) -> list[float]:
        # log-space para evitar underflow en lambdas grandes.
        log_lam = math.log(lam) if lam > 0 else -1e9
        out, log_fact = [], 0.0
        for k in range(n + 1):
            if k > 0:
                log_fact += math.log(k)
            out.append(math.exp(k * log_lam - lam - log_fact))
        return out

    ph = pois(lam_h, max_goals)
    pa = pois(lam_a, max_goals)
    grid = [[ph[x] * pa[y] * tau(x, y, lam_h, lam_a, rho)
             for y in range(max_goals + 1)]
            for x in range(max_goals + 1)]
    total = sum(sum(row) for row in grid)
    return [[v / total for v in row] for row in grid]


@dataclass
class MatchProbabilities:
    """Probabilidades de los principales mercados, listas para imprimir."""
    lam_h: float
    lam_a: float
    p_home: float
    p_draw: float
    p_away: float
    p_over: dict[float, float]
    p_under: dict[float, float]
    p_btts: float
    p_no_btts: float
    top_scorelines: list[tuple[int, int, float]] = field(default_factory=list)

    # ---------- cuotas justas ----------
    @staticmethod
    def _odds(p: float) -> float:
        return float("inf") if p <= 0 else round(1.0 / p, 2)

    def fair_odds(self) -> dict[str, float]:
        return {
            "1": self._odds(self.p_home),
            "X": self._odds(self.p_draw),
            "2": self._odds(self.p_away),
            "1X": self._odds(self.p_home + self.p_draw),
            "12": self._odds(self.p_home + self.p_away),
            "X2": self._odds(self.p_draw + self.p_away),
            "BTTS_Yes": self._odds(self.p_btts),
            "BTTS_No": self._odds(self.p_no_btts),
            **{f"Over_{k}": self._odds(v) for k, v in self.p_over.items()},
            **{f"Under_{k}": self._odds(v) for k, v in self.p_under.items()},
        }

    @staticmethod
    def value(p_model: float, bookmaker_odds: float) -> dict[str, float]:
        """EV y fraccion Kelly de una apuesta dada cuota decimal del libro.

        EV     = p*k - 1            (esperado por unidad apostada)
        Kelly  = (p*k - 1)/(k - 1)  (fraccion del bankroll, solo si EV > 0)
        """
        if bookmaker_odds <= 1.0:
            return {"ev": 0.0, "kelly": 0.0, "edge_pct": 0.0}
        ev = p_model * bookmaker_odds - 1.0
        kelly = max(0.0, ev / (bookmaker_odds - 1.0))
        edge_pct = (p_model - 1.0 / bookmaker_odds) * 100
        return {"ev": round(ev, 4), "kelly": round(kelly, 4),
                "edge_pct": round(edge_pct, 2)}


def compute_match_probabilities(
    lam_h: float, lam_a: float, rho: float = RHO,
    top_n_scores: int = 5,
) -> MatchProbabilities:
    """Calcula 1X2, O/U, BTTS y top marcadores desde (lam_h, lam_a)."""
    grid = joint_matrix(lam_h, lam_a, rho)
    n = len(grid)

    p_home = sum(grid[x][y] for x in range(n) for y in range(n) if x > y)
    p_draw = sum(grid[x][x] for x in range(n))
    p_away = sum(grid[x][y] for x in range(n) for y in range(n) if x < y)

    p_over: dict[float, float] = {}
    p_under: dict[float, float] = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        over = sum(grid[x][y] for x in range(n) for y in range(n) if x + y > line)
        p_over[line] = over
        p_under[line] = 1.0 - over

    p_btts = sum(grid[x][y] for x in range(1, n) for y in range(1, n))
    p_no_btts = 1.0 - p_btts

    all_scores = [(x, y, grid[x][y]) for x in range(n) for y in range(n)]
    all_scores.sort(key=lambda t: -t[2])

    return MatchProbabilities(
        lam_h=lam_h, lam_a=lam_a,
        p_home=p_home, p_draw=p_draw, p_away=p_away,
        p_over=p_over, p_under=p_under,
        p_btts=p_btts, p_no_btts=p_no_btts,
        top_scorelines=all_scores[:top_n_scores],
    )
