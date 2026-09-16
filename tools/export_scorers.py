"""Exporta la cuota de gol reciente por jugador y selección.

Lee goalscorers.csv (cache martj42) y, para cada una de las 48 selecciones,
calcula qué fracción de los goles RECIENTES (últimos ~3 años) metió cada
jugador. Eso aproxima quién anota hoy en cada equipo, sin datos de plantilla.

Uso en el front:
  - Posibles goleadores de un partido: top jugadores por cuota.
  - Bota de Oro (Monte Carlo): goles simulados del equipo × cuota del jugador
    = goles proyectados del jugador en el torneo.

Salida: data/processed/scorers.json  -> {fifa_code: [[nombre, cuota], ...]}
Cuotas normalizadas a sumar 1 sobre los jugadores listados (top N + resto
agrupado se descarta para no inflar nombres irrelevantes).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from src.etl.scrapers.history import FIFA_TO_HISTORY

RAW = Path("data/raw/teams_2026.csv")
GOALS = Path("data/cache/history/goalscorers.csv")
OUT = Path("data/processed/scorers.json")
LOOKBACK_DAYS = 365 * 3
TOP_N = 8           # jugadores por equipo
MIN_GOALS = 2       # ignorar quien metió 1 solo gol (ruido)


def main() -> None:
    cutoff = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()

    # nombre martj42 por fifa code
    fifa_to_name: dict[str, str] = {}
    with RAW.open() as f:
        for row in csv.DictReader(f):
            fifa_to_name[row["fifa_code"]] = FIFA_TO_HISTORY.get(row["fifa_code"], row["name"])
    name_to_fifa = {v: k for k, v in fifa_to_name.items()}

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with GOALS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["date"] < cutoff or r.get("own_goal") == "TRUE":
                continue
            fifa = name_to_fifa.get(r["team"])
            if not fifa:
                continue
            scorer = (r.get("scorer") or "").strip()
            if scorer:
                counts[fifa][scorer] += 1

    out: dict[str, list] = {}
    for fifa in fifa_to_name:
        players = [(n, c) for n, c in counts.get(fifa, {}).items() if c >= MIN_GOALS]
        players.sort(key=lambda x: -x[1])
        players = players[:TOP_N]
        tot = sum(c for _, c in players)
        if tot == 0:
            out[fifa] = []
            continue
        out[fifa] = [[n, round(c / tot, 4)] for n, c in players]

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    covered = sum(1 for v in out.values() if v)
    print(f"✅ Goleadores de {covered}/48 equipos -> {OUT}")
    for fifa in ["ARG", "ESP", "BRA", "FRA"]:
        top = out.get(fifa, [])[:3]
        print(f"   {fifa}: " + ", ".join(f"{n} ({p*100:.0f}%)" for n, p in top))


if __name__ == "__main__":
    main()
