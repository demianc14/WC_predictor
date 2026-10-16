"""Walk-forward contra el mercado: antes de cada semana se reajusta el modelo
solo con lo ya jugado y se predice el 1X2 de esa semana. Se compara con las
cuotas de cierre promedio (sin margen) en Brier y log-loss.
"""
from __future__ import annotations

import math
from datetime import timedelta

from src.clubs.data import Match
from src.clubs.model import XG_WEIGHT, XI, fit


def no_vig(odds: tuple[float, float, float]) -> tuple[float, float, float]:
    inv = [1 / o for o in odds]
    s = sum(inv)
    return tuple(v / s for v in inv)  # type: ignore[return-value]


def _outcome(m: Match) -> int:
    return 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2


def walk_forward(matches: list[Match], div: str, seasons: list[str], xi: float = XI,
                 xg_weight: float = XG_WEIGHT, warmup_days: int = 0) -> list[dict]:
    target = [m for m in matches if m.div == div and m.season in seasons and m.played and m.odds]
    if not target:
        return []
    out = []
    start = target[0].day - timedelta(days=target[0].day.weekday())
    end = target[-1].day
    week = start
    while week <= end:
        nxt = week + timedelta(days=7)
        batch = [m for m in target if week <= m.day < nxt]
        if batch:
            r = fit(matches, week, xi=xi, xg_weight=xg_weight)
            for m in batch:
                if m.home not in r.att or m.away not in r.att:
                    continue
                ph, pd, pa, _ = r.probs(m.home, m.away)
                out.append({"season": m.season, "day": m.day.isoformat(), "home": m.home, "away": m.away,
                            "o": _outcome(m), "model": [ph, pd, pa], "market": list(no_vig(m.odds)),
                            "odds": list(m.odds)})
        week = nxt
    return out


def score(rows: list[dict], key: str) -> dict:
    n = len(rows)
    brier = sum(sum((p - (i == r["o"])) ** 2 for i, p in enumerate(r[key])) for r in rows) / n
    ll = -sum(math.log(max(r[key][r["o"]], 1e-9)) for r in rows) / n
    hit = sum(r[key].index(max(r[key])) == r["o"] for r in rows) / n
    return {"n": n, "brier": round(brier, 4), "logloss": round(ll, 4), "hit": round(hit, 4)}


def value_roi(rows: list[dict], edge: float = 0.05) -> dict:
    """Apuesta plana de 1 donde el modelo ve valor (p·cuota − 1 > edge), a cuota de cierre."""
    bets, profit = 0, 0.0
    for r in rows:
        for i in range(3):
            ev = r["model"][i] * r["odds"][i] - 1
            if ev > edge:
                bets += 1
                profit += (r["odds"][i] - 1) if r["o"] == i else -1
    return {"bets": bets, "roi": round(profit / bets, 4) if bets else None}
