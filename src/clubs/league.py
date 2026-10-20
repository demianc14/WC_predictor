"""Las cinco grandes: ajusta el modelo de cada liga, simula lo que falta del
calendario real, predice la próxima jornada contra las cuotas y mide el
modelo contra el mercado.

    python -m src.clubs.league                 # las cinco, desde la caché
    python -m src.clubs.league --league LL     # solo una
    python -m src.clubs.league --force         # baja todo de nuevo
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.clubs import calendar, data
from src.clubs.backtest import no_vig, score, value_roi, walk_forward
from src.clubs.leagues import LEAGUES, League
from src.clubs.model import XG_WEIGHT, XI, Ratings, fit
from src.clubs.season import current_table, simulate

SEASONS = ["2324", "2425", "2526", data.CURRENT_SEASON]
BACKTEST = ["2526", data.CURRENT_SEASON]
OUT_DIR = Path("data/processed/clubs")


def _pred(r: Ratings, home: str, away: str) -> dict:
    ph, pd, pa, g = r.probs(home, away)
    lh, la = r.lambdas(home, away)
    cells = ((x, y, g[x][y]) for x in range(len(g)) for y in range(len(g)))
    top = max(cells, key=lambda c: c[2])
    return {"model": [round(ph, 4), round(pd, 4), round(pa, 4)],
            "lam": [round(lh, 2), round(la, 2)], "top": [top[0], top[1]]}


def build(lg: League, today: date | None = None, sims: int = 10000) -> dict:
    matches = data.load_matches([lg.div, lg.lower], SEASONS)
    cur = [m for m in matches if m.div == lg.div and m.season == data.CURRENT_SEASON]
    played = [m for m in cur if m.played]
    cal, official = calendar.load(lg, played)
    teams = sorted(official)
    today = today or date.today()
    r = fit(matches, today)

    pending = calendar.pending(cal, played)
    table = current_table(played, teams)
    proj = simulate(r, played, teams, n=sims, fixtures=[(f.home, f.away) for f in pending])

    odds = {(f.home, f.away): f.odds for f in data.load_fixtures(lg.div) if f.odds}
    nxt = []
    for f in calendar.next_round(pending, today):
        o = odds.get((f.home, f.away))
        nxt.append({"day": f.day.isoformat(), "round": f.round, "tbc": f.tbc,
                    "home": f.home, "away": f.away, **_pred(r, f.home, f.away),
                    "market": [round(p, 4) for p in no_vig(o)] if o else None,
                    "odds": list(o) if o else None})
    # el resto del calendario, compacto: [jornada, día, tbc, local, visita, p1, px, p2]
    rest = [[f.round, f.day.isoformat(), int(f.tbc), f.home, f.away,
             *(round(p, 3) for p in r.probs(f.home, f.away)[:3])] for f in pending]

    bt = walk_forward(matches, lg.div, BACKTEST)
    by_season = {}
    for s in BACKTEST:
        rows = [b for b in bt if b["season"] == s]
        if rows:
            by_season[s] = {"model": score(rows, "model"), "market": score(rows, "market"),
                            "value": value_roi(rows)}
    return {
        "league": lg.code, "name": lg.name, "places": lg.places,
        "updated": max(m.day for m in played).isoformat(), "fitted": today.isoformat(),
        "params": {"mu": r.mu, "home": r.home, "rho": r.rho, "xi": XI, "xg_weight": XG_WEIGHT},
        "teams": [{"t": t, "n": official[t], "att": r.att[t], "def": r.defe[t],
                   **table[t], **proj[t]} for t in teams],
        "remaining": len(pending), "played": len(played),
        "next": nxt, "calendar": rest, "backtest": by_season,
    }


def run(lg: League, force: bool = False, sims: int = 10000) -> dict:
    if force:
        for s in SEASONS:
            for d in (lg.div, lg.lower):
                data.ensure_season(d, s, force=True)
        calendar.ensure_calendar(lg, force=True)
    out = build(lg, sims=sims)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{lg.code}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(out["teams"], key=lambda t: -t["pos"][0])[:3]
    print(f"✅ {lg.name}: {out['played']} jugados, {out['remaining']} por jugar, "
          f"{len(out['next'])} en los próximos 7 días")
    print("   Campeón:", ", ".join(f"{t['n']} {t['pos'][0]:.0%}" for t in top))
    for s, b in out["backtest"].items():
        print(f"   {s}: Brier modelo {b['model']['brier']} vs mercado "
              f"{b['market']['brier']} (n={b['model']['n']})")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=sorted(LEAGUES), action="append")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-n", type=int, default=10000)
    args = ap.parse_args()
    if args.force:
        data.ensure_fixtures(force=True)
    for code in args.league or LEAGUES:
        run(LEAGUES[code], force=args.force, sims=args.n)


if __name__ == "__main__":
    main()
