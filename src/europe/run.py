"""Champions 2026-27: próximos partidos 1X2 y Monte Carlo de la fase de liga.

    python -m src.europe.run            # escribe data/processed/ucl.json

Usa el Dixon-Coles conjunto (`src/europe/data.py`), ajustado con todo lo
jugado antes de hoy. La fase de liga son 8 jornadas, 36 clubes en una sola
tabla: del 1 al 8 pasan a octavos, del 9 al 24 juegan el playoff y del 25 al
36 quedan afuera. El desempate es puntos, diferencia, goles a favor y azar:
una simplificación del reglamento de la UEFA, que después mira goles de
visita, victorias y la fuerza de los rivales.

Solo la fase de liga: las eliminatorias dependen de un sorteo, y una ida y
vuelta repite el cruce local-visita, que el almacén usa como identificador.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from src.clubs import calendar
from src.clubs.backtest import _outcome
from src.clubs.data import Match
from src.clubs.model import XI, fit
from src.clubs.run import _pred
from src.clubs.season import current_table, simulate
from src.europe import backtest
from src.europe import data as eu
from src.ml import europe

OUT = Path("data/processed/ucl.json")
FEED, YEAR, COMP = "champions-league", 2026, "UCL"
SEASON = eu.season_of(YEAR)
LEAGUE_ROUNDS, TEAMS = 8, 36
ZONES = {"octavos": (1, 8), "playoff": (9, 24), "afuera": (25, 36)}
NEXT_DAYS = 7


def league_phase(rows: list[dict]) -> list[calendar.Fixture]:
    out = [f for f in calendar.parse_calendar(rows) if f.round <= LEAGUE_ROUNDS]
    return [calendar.Fixture(f.round, f.day, eu.name(f.home), eu.name(f.away), f.hg, f.ag, f.tbc)
            for f in out]


def base_rates(matches: list[Match]) -> list[float]:
    """1/X/2 de la Champions antes de esta temporada: la base, fija y conocida de antemano."""
    n = [1, 1, 1]
    for m in matches:
        if m.div == COMP and m.played and m.season < SEASON:
            n[_outcome(m)] += 1
    return [round(c / sum(n), 4) for c in n]


def build(today: date | None = None, sims: int = 10000, with_backtest: bool = True) -> dict:
    today = today or date.today()
    p = europe.ensure(FEED, YEAR)
    if p is None:
        raise FileNotFoundError(f"sin el feed {FEED}-{YEAR}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    cal = league_phase(raw)
    shown = {eu.name(r[k]): r[k] for r in raw for k in ("HomeTeam", "AwayTeam")}   # el del feed
    ms = eu.load()
    r = fit(ms, today)
    teams = sorted({f.home for f in cal} | {f.away for f in cal})
    if len(teams) != TEAMS or len(cal) != TEAMS * LEAGUE_ROUNDS // 2:
        raise ValueError(f"Champions: {len(teams)} clubes y {len(cal)} partidos en la fase de liga")
    missing = [t for t in teams if t not in r.att]
    if missing:
        raise ValueError(f"Champions: sin rating para {missing}")

    played = [Match(COMP, SEASON, f.day, f.home, f.away, f.hg, f.ag)
              for f in cal if f.played and f.day < today]
    pending = [f for f in cal if not (f.played and f.day < today)]
    table = current_table(played, teams)
    proj = simulate(r, played, teams, n=sims, fixtures=[(f.home, f.away) for f in pending])
    alone = eu.without_league(ms)
    league_of = {t: m.div for m in ms if m.div not in eu.COMPS.values() and m.season == SEASON
                 for t in (m.home, m.away)}
    nxt = [{"day": f.day.isoformat(), "round": f.round, "home": f.home, "away": f.away,
            **_pred(r, f.home, f.away)}
           for f in pending if today <= f.day < today + timedelta(days=NEXT_DAYS)]
    rest = [[f.round, f.day.isoformat(), f.home, f.away,
             *(round(p, 3) for p in r.probs(f.home, f.away)[:3])]
            for f in pending if f.day >= today + timedelta(days=NEXT_DAYS)]

    out = {
        "comp": COMP, "season": SEASON, "fitted": today.isoformat(),
        "updated": max((m.day for m in played), default=today).isoformat(),
        "params": {"mu": r.mu, "home": r.home, "rho": r.rho, "xi": XI},
        "zones": ZONES, "played": len(played), "remaining": len(pending),
        "base": base_rates(ms),
        "teams": [{"t": t, "n": shown.get(t, t), "league": league_of.get(t),
                   "no_league": t in alone, "n_eff": r.n_eff[t], "att": r.att[t],
                   "def": r.defe[t], **table[t], **proj[t],
                   **{z: round(sum(proj[t]["pos"][a - 1:b]), 4) for z, (a, b) in ZONES.items()}}
                  for t in teams],
        "next": nxt, "calendar": rest,
        # lo jugado de la fase de liga, para que el ciclo diario complete el almacén
        "results": [[m.day.isoformat(), m.home, m.away, m.hg, m.ag] for m in played],
    }
    if with_backtest:
        rows = backtest.walk_forward(ms, backtest.TEST)
        rep = backtest.report(rows)
        out["backtest"] = {"seasons": list(backtest.TEST), "model": rep["model"],
                           "base": rep["base"], "diff_rps": rep["diff"]["rps"]}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Champions 2026-27: partidos y fase de liga")
    ap.add_argument("-n", type=int, default=10000)
    args = ap.parse_args()
    out = build(sims=args.n)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(out["teams"], key=lambda t: -t["octavos"])[:5]
    print(f"✅ Champions: {out['played']} jugados, {out['remaining']} por jugar, "
          f"{len(out['next'])} en los próximos {NEXT_DAYS} días")
    print("   Top 8:", ", ".join(f"{t['t']} {t['octavos']:.0%}" for t in top))


if __name__ == "__main__":
    main()
