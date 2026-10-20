"""Las cinco grandes: ajusta el modelo de cada liga, simula lo que falta de la
temporada, predice la próxima jornada contra las cuotas y mide el modelo
contra el mercado.

    python -m src.clubs.run                    # las cinco, desde la caché
    python -m src.clubs.run --league SP1       # solo una (E0, SP1, D1, I1, F1)
    python -m src.clubs.run --force            # baja todo de nuevo

Próxima jornada: `fixtures.csv` de football-data (trae cuotas, pero solo unos
días hacia adelante) más los partidos de los próximos 7 días del calendario de
fixturedownload. Si el calendario no está disponible, la simulación usa todo
cruce local-visita no jugado y la jornada sale solo de football-data.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from src.clubs import calendar, data
from src.clubs.backtest import no_vig, score, value_roi, walk_forward
from src.clubs.leagues import BACKTEST, DISPLAY, LEAGUES, League
from src.clubs.model import XG_WEIGHT, XI, Ratings, fit
from src.clubs.season import current_table, remaining_fixtures, simulate

OUT_DIR = Path("data/processed")
NEXT_DAYS = 7


def out_path(lg: League) -> Path:
    return OUT_DIR / f"clubs_{lg.code}.json"


def _pred(r: Ratings, home: str, away: str) -> dict:
    ph, pd, pa, g = r.probs(home, away)
    lh, la = r.lambdas(home, away)
    cells = ((x, y, g[x][y]) for x in range(len(g)) for y in range(len(g)))
    top = max(cells, key=lambda c: c[2])
    return {"model": [round(ph, 4), round(pd, 4), round(pa, 4)],
            "lam": [round(lh, 2), round(la, 2)], "top": [top[0], top[1]]}


def next_matches(r: Ratings, fd_next: list[data.Match], cal_next: list[calendar.Fixture],
                 ) -> list[dict]:
    """Une las dos fuentes por (local, visita); football-data aporta cuotas y fecha."""
    rows: dict[tuple[str, str], dict] = {}
    for f in cal_next:
        rows[(f.home, f.away)] = {"day": f.day.isoformat(), "round": f.round, "tbc": f.tbc,
                                  "home": f.home, "away": f.away, "odds": None}
    for m in fd_next:
        row = rows.setdefault((m.home, m.away), {"round": None, "home": m.home, "away": m.away})
        row.update(day=m.day.isoformat(), tbc=False, odds=list(m.odds) if m.odds else None)
    out = []
    for (h, a), row in sorted(rows.items(), key=lambda kv: kv[1]["day"]):
        if h in r.att and a in r.att:
            o = row["odds"]
            out.append({**row, **_pred(r, h, a),
                        "market": [round(p, 4) for p in no_vig(tuple(o))] if o else None})
    return out


def build(lg: League, today: date | None = None, sims: int = 10000) -> dict:
    matches = data.load_matches([lg.code, lg.lower], list(lg.seasons))
    cur = [m for m in matches if m.div == lg.code and m.season == data.CURRENT_SEASON]
    played = [m for m in cur if m.played]
    today = today or date.today()
    r = fit(matches, today)

    try:
        cal, official, fixes = calendar.load(lg, played)
    except Exception as e:                      # degradación elegante
        print(f"⚠️  {lg.name}: sin calendario de fixturedownload ({e}); sigo sin él")
        cal, official, fixes = [], {}, []
    for fx in fixes:
        print(f"⚠️  {lg.name}, calendario corregido: {fx}")
    teams = sorted(official) if official else sorted({m.home for m in cur} | {m.away for m in cur})
    if len(teams) != lg.teams:
        raise ValueError(f"{lg.name}: {len(teams)} equipos, se esperaban {lg.teams}")

    pending = calendar.pending(cal, played) if cal else []
    fixtures = ([(f.home, f.away) for f in pending] if cal
                else remaining_fixtures(played, teams))
    if len(played) + len(fixtures) != lg.matches:
        raise ValueError(f"{lg.name}: {len(played)} jugados + {len(fixtures)} por jugar "
                         f"≠ {lg.matches}")
    table = current_table(played, teams)
    proj = simulate(r, played, teams, n=sims, fixtures=fixtures)

    fd_next = [f for f in data.load_fixtures(lg.code) if today <= f.day]
    cal_next = calendar.next_round(pending, today, NEXT_DAYS)
    nxt = next_matches(r, fd_next, cal_next)
    # resto del calendario, compacto: [jornada, día, tbc, local, visita, p1, px, p2]
    rest = [[f.round, f.day.isoformat(), int(f.tbc), f.home, f.away,
             *(round(p, 3) for p in r.probs(f.home, f.away)[:3])]
            for f in pending if f.day >= today + timedelta(days=NEXT_DAYS) or f.day < today]

    bt = walk_forward(matches, lg.code, list(BACKTEST))
    by_season = {}
    for s in BACKTEST:
        rows = [b for b in bt if b["season"] == s]
        if rows:
            by_season[s] = {"model": score(rows, "model"), "market": score(rows, "market"),
                            "base": score(rows, "base"), "value": value_roi(rows)}
    return {
        "league": lg.code, "name": lg.name, "lower": lg.lower_name, "places": lg.places,
        "updated": max(m.day for m in played).isoformat(), "fitted": today.isoformat(),
        "params": {"mu": r.mu, "home": r.home, "rho": r.rho, "xi": XI, "xg_weight": XG_WEIGHT},
        "teams": [{"t": t, "n": DISPLAY.get(t, official.get(t, t)), "att": r.att[t],
                   "def": r.defe[t], **table[t], **proj[t]} for t in teams],
        "remaining": len(fixtures), "played": len(played),
        "next": nxt, "calendar": rest, "calendar_fixes": fixes, "backtest": by_season,
    }


def run(lg: League, force: bool = False, sims: int = 10000) -> dict:
    if force:
        for s in lg.seasons:
            for d in (lg.code, lg.lower):
                data.ensure_season(d, s, force=True)
        calendar.ensure_calendar(lg, force=True)
    out = build(lg, sims=sims)
    out_path(lg).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(out["teams"], key=lambda t: -t["pos"][0])[:3]
    print(f"✅ {lg.name}: {out['played']} jugados, {out['remaining']} por jugar, "
          f"{len(out['next'])} en los próximos {NEXT_DAYS} días")
    print("   Campeón:", ", ".join(f"{t['n']} {t['pos'][0]:.0%}" for t in top))
    for s, b in out["backtest"].items():
        print(f"   {s} (n={b['model']['n']}): Brier/RPS modelo {b['model']['brier']}/"
              f"{b['model']['rps']}, mercado {b['market']['brier']}/{b['market']['rps']}, "
              f"base {b['base']['brier']}/{b['base']['rps']}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=sorted(LEAGUES), action="append",
                    help="división de football-data; repetible. Por defecto, las cinco")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-n", type=int, default=10000)
    args = ap.parse_args()
    if args.force:
        data.ensure_fixtures(force=True)
    for code in args.league or LEAGUES:
        run(LEAGUES[code], force=args.force, sims=args.n)


if __name__ == "__main__":
    main()
