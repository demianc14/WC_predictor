"""Partido y cuotas entre dos clubes de una misma liga.

Usa los parámetros ya ajustados en `data/processed/clubs_<div>.json` (lo que
escribe `python -m src.clubs.run`), así que la CLI y la web dan exactamente
los mismos números sin reajustar nada:

    λ_local  = μ · localía · ataque_local · defensa_visita
    λ_visita = μ ·           ataque_visita · defensa_local

y de ahí la matriz Dixon-Coles con el ρ de la liga → 1X2, goles, ambos
anotan, marcadores y cuota justa. Con `--odds` compara contra la casa.

    python -m src.clubs.h2h E0 Arsenal "Man City"
    python -m src.clubs.h2h SP1 barcelona "real madrid" --odds 1.95 3.9 3.6
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path

from src.betting.odds import MatchProbabilities, compute_match_probabilities
from src.clubs.leagues import LEAGUES

DATA_DIR = Path("data/processed")


def load(code: str, data_dir: Path = DATA_DIR) -> dict:
    path = data_dir / f"clubs_{code}.json"
    if not path.exists():
        raise FileNotFoundError(f"Falta {path}: corre python -m src.clubs.run --league {code}")
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("'", "").split())


def find_team(lg: dict, query: str) -> dict:
    """Por nombre de football-data o nombre a mostrar; exacto, si no, parcial único."""
    q = _norm(query)
    teams = lg["teams"]
    exact = [t for t in teams if q in (_norm(t["t"]), _norm(t["n"]))]
    if exact:
        return exact[0]
    partial = [t for t in teams if q in _norm(t["t"]) or q in _norm(t["n"])]
    if len(partial) == 1:
        return partial[0]
    options = ", ".join(t["n"] for t in (partial or teams))
    raise ValueError(f"'{query}' {'es ambiguo' if partial else 'no está'} en "
                     f"{lg['name']}: {options}")


def lambdas(lg: dict, home: dict, away: dict) -> tuple[float, float]:
    p = lg["params"]
    return (p["mu"] * p["home"] * home["att"] * away["def"],
            p["mu"] * away["att"] * home["def"])


def predict(lg: dict, home: str, away: str) -> tuple[dict, dict, MatchProbabilities]:
    h, a = find_team(lg, home), find_team(lg, away)
    if h is a:
        raise ValueError("Elige dos clubes distintos")
    lh, la = lambdas(lg, h, a)
    return h, a, compute_match_probabilities(lh, la, rho=lg["params"]["rho"], top_n_scores=6)


def report(lg: dict, h: dict, a: dict, p: MatchProbabilities,
           odds: tuple[float, float, float] | None = None) -> str:
    fair = p.fair_odds()
    lines = [f"⚽ {h['n']} vs {a['n']} · {lg['name']} (datos al {lg['updated']})",
             f"   Goles esperados: {p.lam_h:.2f} – {p.lam_a:.2f}", "",
             f"   {'Mercado':<22}{'Prob.':>7}{'Cuota justa':>13}"]
    rows = [("1 · " + h["n"], p.p_home, fair["1"]), ("X · Empate", p.p_draw, fair["X"]),
            ("2 · " + a["n"], p.p_away, fair["2"]),
            ("Over 2.5", p.p_over[2.5], fair["Over_2.5"]),
            ("Under 2.5", p.p_under[2.5], fair["Under_2.5"]),
            ("Ambos anotan", p.p_btts, fair["BTTS_Yes"])]
    lines += [f"   {n[:22]:<22}{q:>7.1%}{c:>13.2f}" for n, q, c in rows]
    lines += ["", "   Marcadores: " + ", ".join(f"{x}-{y} {q:.0%}"
                                                 for x, y, q in p.top_scorelines)]
    if odds:
        lines += ["", f"   {'Contra la casa':<22}{'Cuota':>7}{'EV':>9}{'¼-Kelly':>10}"]
        for n, q, o in zip(("1", "X", "2"), (p.p_home, p.p_draw, p.p_away), odds):
            v = MatchProbabilities.value(q, o)
            lines.append(f"   {n:<22}{o:>7.2f}{v['ev']:>+9.1%}{v['kelly'] / 4:>10.1%}")
        lines.append("   Ojo: en el backtest el mercado fue más preciso que el modelo "
                     "en 2025-26; un EV positivo no es una recomendación.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Partido y cuotas entre dos clubes")
    ap.add_argument("league", choices=sorted(LEAGUES), help="división de football-data")
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--odds", type=float, nargs=3, metavar=("1", "X", "2"),
                    help="cuotas decimales de la casa para comparar")
    args = ap.parse_args(argv)
    try:
        lg = load(args.league)
        h, a, p = predict(lg, args.home, args.away)
    except (FileNotFoundError, ValueError) as e:
        raise SystemExit(f"❌ {e}") from None
    print(report(lg, h, a, p, tuple(args.odds) if args.odds else None))


if __name__ == "__main__":
    main()
