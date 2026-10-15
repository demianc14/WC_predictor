"""Congela las entradas del backtest del Mundial 2026 (correr una vez, post-torneo).

Salidas (el backtest lee SOLO estos archivos, nunca cachés que se refrescan):
  data/raw/wc2026_results.csv             104 partidos reales, ronda y ganador de penales
  data/snapshots/elo_pre_2026-06-11.json  ELO reconstruido con partidos previos al torneo

El tercer insumo, data/snapshots/strengths_2026-06-15.json, es una copia del
strengths_2026.json que generó el ETL el 15-jun (no se regenera: correr el ETL
hoy usaría datos posteriores al torneo).

Ejecutar:  python -m tools.snapshot_wc2026
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from src.etl.scrapers.history import FIFA_TO_HISTORY, ensure_shootouts, load_results
from src.evaluation.elo import compute_ratings, fit_draw_c

TEAMS_CSV = Path("data/raw/teams_2026.csv")
RESULTS_OUT = Path("data/raw/wc2026_results.csv")
ELO_OUT = Path("data/snapshots/elo_pre_2026-06-11.json")

KICKOFF = date(2026, 6, 11)
GROUP_STAGE_END = date(2026, 6, 27)
KO_ROUNDS = ["R32"] * 16 + ["R16"] * 8 + ["QF"] * 4 + ["SF"] * 2 + ["3P", "F"]


def main() -> None:
    name_to_fifa = {v: k for k, v in FIFA_TO_HISTORY.items()}
    with TEAMS_CSV.open() as f:
        group_of = {r["fifa_code"]: r["group"] for r in csv.DictReader(f)}

    all_rows = load_results()
    wc = [r for r in all_rows
          if r["tournament"] == "FIFA World Cup" and r["_date"] >= KICKOFF]
    wc.sort(key=lambda r: r["_date"])

    shootout_winner: dict[tuple[str, str, str], str] = {}
    with ensure_shootouts().open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            shootout_winner[(r["date"], r["home_team"], r["away_team"])] = r["winner"]

    out_rows, n_group, ko_idx = [], 0, 0
    for r in wc:
        home, away = name_to_fifa[r["home_team"]], name_to_fifa[r["away_team"]]
        if r["_date"] <= GROUP_STAGE_END:
            if group_of[home] != group_of[away]:
                raise ValueError(f"Partido de grupos entre grupos distintos: {home}-{away}")
            rnd, grp = "GROUP", group_of[home]
            n_group += 1
        else:
            rnd, grp = KO_ROUNDS[ko_idx], ""
            ko_idx += 1
        so = ""
        if rnd != "GROUP" and r["home_score"] == r["away_score"]:
            so_name = shootout_winner.get((r["date"], r["home_team"], r["away_team"]))
            if so_name is None:
                raise ValueError(f"Eliminatoria empatada sin tanda registrada: {home}-{away}")
            so = name_to_fifa[so_name]
        out_rows.append({
            "date": r["date"], "round": rnd, "group": grp, "home": home, "away": away,
            "home_score": r["home_score"], "away_score": r["away_score"],
            "neutral": "TRUE" if r["neutral"] else "FALSE", "shootout_winner": so,
        })

    if n_group != 72 or ko_idx != 32:
        raise ValueError(f"Se esperaban 72 + 32 partidos, llegaron {n_group} + {ko_idx}")

    RESULTS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"✅ {len(out_rows)} partidos -> {RESULTS_OUT}")

    ratings, wc_history = compute_ratings(all_rows, cutoff=KICKOFF)
    draw_c = fit_draw_c(wc_history)
    elo = {fifa: round(ratings[name], 1) for fifa, name in FIFA_TO_HISTORY.items()}
    ELO_OUT.parent.mkdir(parents=True, exist_ok=True)
    ELO_OUT.write_text(json.dumps({
        "cutoff": KICKOFF.isoformat(),
        "method": "World Football Elo (eloratings.net) recalculado sobre martj42",
        "draw_c": draw_c,
        "draw_fit_matches": len(wc_history),
        "ratings": dict(sorted(elo.items(), key=lambda kv: -kv[1])),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ ELO de {len(elo)} selecciones al {KICKOFF} (draw_c={draw_c}, "
          f"ajustado en {len(wc_history)} partidos mundialistas) -> {ELO_OUT}")


if __name__ == "__main__":
    main()
