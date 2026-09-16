"""Exporta los partidos YA JUGADOS del Mundial 2026 al formato del front.

Lee los resultados reales del cache martj42 (data/cache/history/results.csv),
los cruza con los 48 equipos del torneo y mapea cada partido jugado de fase
de grupos a la clave "G|idx" que usa app/index.html.

Indexado del front: para cada grupo, los partidos se generan como bucle
anidado i<j sobre los 4 equipos EN EL ORDEN DEL CSV teams_2026.csv:
    idx 0: (t0,t1)  idx 1: (t0,t2)  idx 2: (t0,t3)
    idx 3: (t1,t2)  idx 4: (t1,t3)  idx 5: (t2,t3)
El front guarda el marcador como [gol_t_i, gol_t_j] (t_i = el que aparece
primero en el CSV). Si en el dataset real el equipo "home" es t_j, hay que
INVERTIR el marcador para respetar la orientación del front.

Salida: data/processed/real_results.json
    { "fixed": {"A|0":[2,0], ...}, "matches":[{...legible...}] }
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.etl.scrapers.history import FIFA_TO_HISTORY

RAW = Path("data/raw/teams_2026.csv")
RESULTS = Path("data/cache/history/results.csv")
OUT = Path("data/processed/real_results.json")
TOURNAMENT = "FIFA World Cup"
SINCE = "2026-06-01"

# Suplemento manual: partidos ya jugados que el dataset martj42 todavia no
# cargo (suele tardar 1-2 dias). Clave: (home_fifa, away_fifa) -> (gh, ga).
# BORRAR cada entrada cuando el dataset la incorpore (para no duplicar).
# Actualizado 2026-06-29: fase de grupos completa ya en el dataset.
MANUAL_RESULTS: dict[tuple[str, str], tuple[int, int]] = {}


def group_order() -> dict[str, list[str]]:
    """{grupo: [fifa_codes en orden del CSV]} — define el indexado del front."""
    groups: dict[str, list[str]] = {}
    with RAW.open() as f:
        for row in csv.DictReader(f):
            groups.setdefault(row["group"], []).append(row["fifa_code"])
    return groups


def history_name_to_fifa() -> dict[str, str]:
    inv = {v: k for k, v in FIFA_TO_HISTORY.items()}
    # nombres que coinciden 1:1 (Spain, Brazil, etc.) no estan en FIFA_TO_HISTORY
    # pero el dataset los usa igual; los agregamos leyendo el CSV.
    with RAW.open() as f:
        for row in csv.DictReader(f):
            # el nombre del CSV puede diferir del de martj42; FIFA_TO_HISTORY ya cubre los raros
            inv.setdefault(row["name"], row["fifa_code"])
    return inv


def pair_index(group_codes: list[str], a: str, b: str) -> tuple[int, bool] | None:
    """Devuelve (idx, swap) para el par (a,b) en el orden del grupo.

    swap=True si 'a' (home real) va DESPUES de 'b' en el CSV, es decir hay
    que invertir el marcador para la orientacion del front.
    """
    idx = 0
    for i in range(len(group_codes)):
        for j in range(i + 1, len(group_codes)):
            ti, tj = group_codes[i], group_codes[j]
            if {ti, tj} == {a, b}:
                swap = (a == tj)  # home real es el segundo del CSV -> invertir
                return idx, swap
            idx += 1
    return None


def main() -> None:
    groups = group_order()
    code_of_group = {c: g for g, codes in groups.items() for c in codes}
    name2fifa = history_name_to_fifa()

    fixed: dict[str, list[int]] = {}
    matches: list[dict] = []

    with RESULTS.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["tournament"] != TOURNAMENT or r["date"] < SINCE:
                continue
            if r["home_score"] in ("", "NA") or r["away_score"] in ("", "NA"):
                continue
            ha = name2fifa.get(r["home_team"])
            aw = name2fifa.get(r["away_team"])
            if not ha or not aw:
                continue
            g = code_of_group.get(ha)
            # solo partidos de fase de grupos (mismo grupo)
            if g is None or code_of_group.get(aw) != g:
                continue
            pi = pair_index(groups[g], ha, aw)
            if pi is None:
                continue
            idx, swap = pi
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            score = [as_, hs] if swap else [hs, as_]  # orientado al CSV
            key = f"{g}|{idx}"
            fixed[key] = score
            ti = groups[g][0:][:]  # not used; clarity
            matches.append({
                "key": key, "date": r["date"], "group": g,
                "home": ha, "away": aw, "score": f"{hs}-{as_}",
            })

    # suplemento manual (no duplicar si ya vino del dataset)
    for (ha, aw), (hs, as_) in MANUAL_RESULTS.items():
        g = code_of_group.get(ha)
        if g is None or code_of_group.get(aw) != g:
            continue
        pi = pair_index(groups[g], ha, aw)
        if pi is None:
            continue
        idx, swap = pi
        key = f"{g}|{idx}"
        if key in fixed:
            continue  # el dataset ya lo trae
        fixed[key] = [as_, hs] if swap else [hs, as_]
        matches.append({"key": key, "date": "2026-06-17 (manual)", "group": g,
                        "home": ha, "away": aw, "score": f"{hs}-{as_}"})

    OUT.write_text(json.dumps({"fixed": fixed, "matches": matches},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(fixed)} partidos de grupos jugados -> {OUT}")
    for m in matches:
        print(f"   [{m['key']}] {m['date']}  {m['home']} {m['score']} {m['away']}  (grupo {m['group']})")


if __name__ == "__main__":
    main()
