"""Comparacion modelo viejo (sin ELO) vs nuevo (con ELO) en partidos surprise.

Casos:
  - Espana 1-1 Cabo Verde (amistoso reciente)
  - Australia 1-0 Turquia (amistoso reciente)

Para cada uno imprime, lado a lado:
  - lambdas esperadas
  - probabilidades 1X2 / Doble oportunidad
  - O/U 2.5, BTTS
  - top-5 marcadores
  - cuotas justas

La idea: ver si el ELO acerca el modelo a esos resultados "ilogicos".
"""
from __future__ import annotations

import json
from pathlib import Path

from src.betting.odds import compute_match_probabilities
from src.etl.models import TeamStrength
from src.simulation.match_engine import expected_goals_pair

OLD = Path("data/processed/strengths_2026.OLD.json")
NEW = Path("data/processed/strengths_2026.json")

MATCHES = [
    {"home": "ESP", "away": "CPV", "real": "1-1 (empate)"},
    {"home": "AUS", "away": "TUR", "real": "1-0 (gana Australia)"},
]


def load_strengths(path: Path) -> dict[str, TeamStrength]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {row["fifa_code"]: TeamStrength(**row) for row in raw}


def fmt_pct(p: float) -> str:
    return f"{p*100:5.1f}%"


def print_match(label: str, home: TeamStrength, away: TeamStrength) -> None:
    # Contexto neutro: 0.5 = sin noticias, sin sede.
    lam_h, lam_a = expected_goals_pair(home, away, 0.5, 0.5)
    probs = compute_match_probabilities(lam_h, lam_a)
    odds = probs.fair_odds()

    print(f"\n  [{label}]  posterior {home.fifa_code}={home.posterior:.3f}  "
          f"{away.fifa_code}={away.posterior:.3f}")
    print(f"           lambda_{home.fifa_code}={lam_h:.2f}   lambda_{away.fifa_code}={lam_a:.2f}")
    print(f"           1  ({home.fifa_code})  {fmt_pct(probs.p_home)}   "
          f"cuota justa {odds['1']:.2f}")
    print(f"           X  (empate) {fmt_pct(probs.p_draw)}   "
          f"cuota justa {odds['X']:.2f}")
    print(f"           2  ({away.fifa_code})  {fmt_pct(probs.p_away)}   "
          f"cuota justa {odds['2']:.2f}")
    print(f"           Over 2.5  {fmt_pct(probs.p_over[2.5])}   "
          f"Under 2.5  {fmt_pct(probs.p_under[2.5])}")
    print(f"           BTTS Si   {fmt_pct(probs.p_btts)}    "
          f"BTTS No    {fmt_pct(probs.p_no_btts)}")
    top = "  ".join(f"{x}-{y}({p*100:.1f}%)" for x, y, p in probs.top_scorelines)
    print(f"           top-5 marc: {top}")


def main() -> None:
    if not OLD.exists():
        raise SystemExit(
            "No existe data/processed/strengths_2026.OLD.json. "
            "Hace falta el backup pre-ELO para comparar."
        )

    old = load_strengths(OLD)
    new = load_strengths(NEW)

    print("=" * 76)
    print("  COMPARACION: modelo viejo (rank FIFA)  vs  nuevo (ELO eloratings)")
    print("=" * 76)

    for m in MATCHES:
        h, a = m["home"], m["away"]
        print(f"\n{'─'*76}")
        print(f"  {h} vs {a}   |   resultado real: {m['real']}")
        print_match("VIEJO", old[h], old[a])
        print_match("NUEVO", new[h], new[a])


if __name__ == "__main__":
    main()
