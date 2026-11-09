"""Champions 2026-27: Monte Carlo de la fase de liga y de las eliminatorias hasta la final.

Cuadro del reglamento 2026/27 (Art. 19-22 y Anexo B, verificados el 9-nov-2026):

- Playoff (9-24), ida y vuelta: 9/10 contra 23/24, 11/12 contra 21/22, 13/14 contra
  19/20 y 15/16 contra 17/18. Quién juega contra quién dentro de cada par sale del
  sorteo; el mejor clasificado juega la vuelta de local.
- Octavos: cada par 1/2, 3/4, 5/6 y 7/8 se reparte por sorteo, uno a cada lado del
  cuadro. En cada lado, 5/6 espera al ganador de 11/12–21/22, 3/4 al de 13/14–19/20,
  7/8 al de 9/10–23/24 y 1/2 al de 15/16–17/18.
- Cuartos y semis siguen el cuadro fijo: (5/6 · 3/4) y (7/8 · 1/2) en cuartos, y esos
  dos ganadores en semis. Quien elimina a un cabeza de serie hereda su lugar, y el de
  mejor lugar juega la vuelta de local.
- Final a partido único en cancha neutral, entre los dos lados del cuadro.
- Empate en el global: prórroga de 30 minutos (un tercio de partido, de local quien
  juega la vuelta) y, si sigue igual, penales al 50%. Es una simplificación: el
  reglamento no da más que eso, y el modelo no sabe nada de penales.
"""
from __future__ import annotations

import numpy as np

from src.betting.odds import joint_matrix
from src.clubs.data import Match
from src.clubs.model import Ratings
from src.clubs.season import current_table

# (cabeza de serie, par del playoff que lo enfrenta como sembrado, par no sembrado)
SIDE = (((5, 6), (11, 12), (21, 22)), ((3, 4), (13, 14), (19, 20)),
        ((7, 8), (9, 10), (23, 24)), ((1, 2), (15, 16), (17, 18)))
# llegar a octavos, a cuartos, a semis y a la final, y ganarla
ROUNDS = ("r16", "qf", "sf", "final", "champion")


def league_positions(r: Ratings, played: list[Match], teams: list[str],
                     fixtures: list[tuple[str, str]], n: int, rng: np.random.Generator
                     ) -> tuple[np.ndarray, np.ndarray]:
    """(posición final de cada club en cada corrida, puntos). Mismo muestreo que
    `src.clubs.season.simulate`, pero devuelve cada corrida: las eliminatorias
    necesitan la tabla entera, no solo su distribución."""
    ix = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    base = current_table(played, teams)
    pts = np.tile([base[t]["pts"] for t in teams], (n, 1)).astype(float)
    gd = np.tile([base[t]["gf"] - base[t]["gc"] for t in teams], (n, 1)).astype(float)
    gf = np.tile([base[t]["gf"] for t in teams], (n, 1)).astype(float)
    for h, a in fixtures:
        g = np.array(r.probs(h, a)[3])
        k = len(g)
        cell = rng.choice(g.size, size=n, p=g.ravel() / g.sum())
        x, y = cell // k, cell % k
        i, j = ix[h], ix[a]
        pts[:, i] += np.where(x > y, 3, np.where(x == y, 1, 0))
        pts[:, j] += np.where(y > x, 3, np.where(x == y, 1, 0))
        gd[:, i] += x - y
        gd[:, j] += y - x
        gf[:, i] += x
        gf[:, j] += y
    key = pts * 1e6 + gd * 1e3 + gf + rng.random((n, T))
    pos = np.empty((n, T), dtype=int)
    pos[np.arange(n)[:, None], np.argsort(-key, axis=1)] = np.arange(T)
    return pos, pts


class Bracket:
    """Juega las eliminatorias de una corrida con el Dixon-Coles conjunto."""

    def __init__(self, r: Ratings, rng: np.random.Generator):
        self.r, self.rng = r, rng
        self._cdf: dict[tuple[str, str, bool], tuple[np.ndarray, int]] = {}

    def _score(self, home: str, away: str, neutral: bool = False) -> tuple[int, int]:
        key = (home, away, neutral)
        if key not in self._cdf:
            lh, la = self.r.lambdas(home, away)
            if neutral:
                lh /= self.r.home
            g = np.array(joint_matrix(lh, la, rho=self.r.rho))
            self._cdf[key] = (np.cumsum(g.ravel()) / g.sum(), len(g))
        cdf, k = self._cdf[key]
        cell = min(int(np.searchsorted(cdf, self.rng.random())), cdf.size - 1)
        return cell // k, cell % k

    def _extra(self, home: str, away: str) -> str | None:
        lh, la = self.r.lambdas(home, away)
        x, y = self.rng.poisson(lh / 3), self.rng.poisson(la / 3)
        return home if x > y else away if y > x else None

    def tie(self, a: tuple[str, int], b: tuple[str, int]) -> tuple[str, int]:
        """Ida y vuelta. Cada entrada es (club, lugar en el cuadro); gana el global y
        hereda el mejor lugar. El de mejor lugar juega la vuelta de local."""
        (top, s1), (low, s2) = sorted((a, b), key=lambda e: e[1])
        x1, y1 = self._score(low, top)            # ida: local el peor ubicado
        x2, y2 = self._score(top, low)            # vuelta
        g_top, g_low = y1 + x2, x1 + y2
        w = top if g_top > g_low else low if g_low > g_top else self._extra(top, low)
        if w is None:
            w = top if self.rng.random() < 0.5 else low
        return w, min(s1, s2)

    def final(self, a: str, b: str) -> str:
        h, aw = (a, b) if self.rng.random() < 0.5 else (b, a)
        x, y = self._score(h, aw, neutral=True)
        if x == y:
            lh, la = self.r.lambdas(h, aw)
            x, y = self.rng.poisson(lh / self.r.home / 3), self.rng.poisson(la / 3)
        if x == y:
            return h if self.rng.random() < 0.5 else aw
        return h if x > y else aw

    def run(self, order: list[str]) -> dict[str, int]:
        """`order[p]` = club en el puesto p+1. Devuelve club → última ronda alcanzada
        (índice en ROUNDS; los eliminados en el playoff no aparecen)."""
        reached: dict[str, int] = {}
        at = lambda p: order[p - 1]                                    # noqa: E731
        flip = lambda pair: pair if self.rng.random() < 0.5 else pair[::-1]   # noqa: E731
        sides: list[list[tuple[str, int]]] = [[], []]
        for seed, po_seed, po_low in SIDE:
            s, ps, pl = flip(seed), flip(po_seed), flip(po_low)
            for side in (0, 1):
                po = self.tie((at(ps[side]), ps[side]), (at(pl[side]), pl[side]))
                for t in (at(s[side]), po[0]):
                    reached[t] = 0
                sides[side].append(self.tie((at(s[side]), s[side]), po))
        finalists = []
        for slots in sides:
            for t, _ in slots:
                reached[t] = 1
            qf = [self.tie(slots[0], slots[1]), self.tie(slots[2], slots[3])]
            for t, _ in qf:
                reached[t] = 2
            sf = self.tie(qf[0], qf[1])
            reached[sf[0]] = 3
            finalists.append(sf[0])
        reached[self.final(*finalists)] = 4
        return reached


def simulate(r: Ratings, played: list[Match], teams: list[str],
             fixtures: list[tuple[str, str]], n: int = 10000, seed: int = 2627) -> dict:
    """Por club: puntos esperados, distribución de la posición final y P(cada ronda)."""
    rng = np.random.default_rng(seed)
    pos, pts = league_positions(r, played, teams, fixtures, n, rng)
    T = len(teams)
    counts = np.zeros((T, len(ROUNDS)))
    ix = {t: i for i, t in enumerate(teams)}
    br = Bracket(r, rng)
    for k in range(n):
        order = [""] * T
        for i, p in enumerate(pos[k]):
            order[p] = teams[i]
        for t, last in br.run(order).items():
            counts[ix[t], :last + 1] += 1
    out = {}
    for t, i in ix.items():
        out[t] = {"xpts": round(float(pts[:, i].mean()), 1),
                  "pos": [round(float(p), 4) for p in np.bincount(pos[:, i], minlength=T) / n],
                  "ko": {rd: round(float(c / n), 4) for rd, c in zip(ROUNDS, counts[i])}}
    return out
