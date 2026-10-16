"""Piloto Premier League: ajusta el modelo, simula la temporada, predice la
próxima jornada contra las cuotas y mide el modelo contra el mercado.

    python -m src.clubs.premier            # usa la caché (refresca la temporada actual cada 12 h)
    python -m src.clubs.premier --force    # baja todo de nuevo
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.clubs import data
from src.clubs.backtest import no_vig, score, value_roi, walk_forward
from src.clubs.model import XG_WEIGHT, XI, fit
from src.clubs.season import current_table, remaining_fixtures, simulate

DIV, LOWER = "E0", "E1"
SEASONS = ["2324", "2425", "2526", data.CURRENT_SEASON]
OUT = Path("data/processed/clubs_premier.json")
NICE = {"Man City": "Manchester City", "Man United": "Manchester United",
        "Nott'm Forest": "Nottingham Forest", "Wolves": "Wolverhampton",
        "Sheffield United": "Sheffield United", "Newcastle": "Newcastle United"}


def build(today: date | None = None, sims: int = 10000) -> dict:
    matches = data.load_matches([DIV, LOWER], SEASONS)
    cur = [m for m in matches if m.div == DIV and m.season == data.CURRENT_SEASON]
    played = [m for m in cur if m.played]
    teams = sorted({m.home for m in cur} | {m.away for m in cur})
    last = max(m.day for m in played)
    today = today or date.today()
    r = fit(matches, today)

    table = current_table(played, teams)
    proj = simulate(r, played, teams, n=sims)
    fixtures = [f for f in data.load_fixtures(DIV) if f.home in r.att and f.away in r.att]
    nxt = []
    for f in fixtures:
        ph, pd, pa, g = r.probs(f.home, f.away)
        lh, la = r.lambdas(f.home, f.away)
        cells = ((x, y, g[x][y]) for x in range(len(g)) for y in range(len(g)))
        top = max(cells, key=lambda c: c[2])
        nxt.append({"day": f.day.isoformat(), "home": f.home, "away": f.away,
                    "model": [round(ph, 4), round(pd, 4), round(pa, 4)],
                    "market": [round(p, 4) for p in no_vig(f.odds)] if f.odds else None,
                    "odds": list(f.odds) if f.odds else None,
                    "lam": [round(lh, 2), round(la, 2)], "top": [top[0], top[1]]})

    bt = walk_forward(matches, DIV, ["2526", data.CURRENT_SEASON])
    by_season = {}
    for s in ("2526", data.CURRENT_SEASON):
        rows = [b for b in bt if b["season"] == s]
        if rows:
            by_season[s] = {"model": score(rows, "model"), "market": score(rows, "market"),
                            "value": value_roi(rows)}
    return {
        "updated": last.isoformat(), "fitted": today.isoformat(),
        "params": {"mu": r.mu, "home": r.home, "rho": r.rho, "xi": XI, "xg_weight": XG_WEIGHT},
        "teams": [{"t": t, "n": NICE.get(t, t), "att": r.att[t], "def": r.defe[t],
                   **table[t], **proj[t]} for t in teams],
        "remaining": len(remaining_fixtures(played, teams)), "played": len(played),
        "next": nxt, "backtest": by_season,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-n", type=int, default=10000)
    args = ap.parse_args()
    if args.force:
        for s in SEASONS:
            for d in (DIV, LOWER):
                data.ensure_season(d, s, force=True)
        data.ensure_fixtures(force=True)
    out = build(sims=args.n)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(out["teams"], key=lambda t: -t["pos"][0])[:4]
    print(f"✅ Premier: {out['played']} jugados, {out['remaining']} por jugar, "
          f"{len(out['next'])} en la próxima jornada")
    print("   Campeón:", ", ".join(f"{t['n']} {t['pos'][0]:.0%}" for t in top))
    for s, b in out["backtest"].items():
        print(f"   {s}: Brier modelo {b['model']['brier']} vs mercado "
              f"{b['market']['brier']} (n={b['model']['n']})")


if __name__ == "__main__":
    main()
