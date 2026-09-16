"""Calculo de RESILIENCIA por seleccion: como rinde en situaciones adversas.

Cuatro sub-features, cada una en [0, 1]:

  1. no_loss_rate_vs_top  — % partidos sin derrota vs top tier
                            (capacidad de competir cuando estas en desventaja)
  2. clean_sheet_vs_top   — % vallas invictas vs top tier
                            (solidez defensiva bajo presion)
  3. comeback_rate        — % partidos donde iban perdiendo al HT y no perdieron al FT
                            (capacidad de recuperarse mentalmente)
  4. competitive_winrate  — winrate en torneos oficiales (no amistosos)
                            (templanza en partidos que pesan)

Cada sub-feature usa shrinkage hacia 0.5 con muestras chicas para no
sobreestimar selecciones con pocos partidos vs top. La salida final es
un escalar `resilience_score ∈ [0, 1]`.

Ventana temporal: ultimos 4 anios.
Top tier: equipos con ELO actual > 1900 (configurable).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from src.etl.scrapers.elo import FIFA_TO_ELO, fetch_world_tsv, parse_world_tsv
from src.etl.scrapers.history import (
    COMPETITIVE_TOURNAMENTS,
    FIFA_TO_HISTORY,
    load_goalscorers,
    load_results,
)

LOOKBACK_YEARS = 4
TOP_TIER_ELO = 1900  # umbral para considerar al rival "top"
SHRINK_K = 4         # equivalente a 4 partidos "de baseline 0.5"


@dataclass
class ResilienceBreakdown:
    fifa_code: str
    no_loss_vs_top: float
    n_vs_top: int
    clean_sheet_vs_top: float
    comeback_rate: float
    n_behind_ht: int
    competitive_winrate: float
    n_competitive: int
    score: float  # combinacion final [0,1]


# ─── helpers ────────────────────────────────────────────────────────

def _shrink(raw_rate: float, n: int, k: int = SHRINK_K, baseline: float = 0.5) -> float:
    """Blend raw_rate con baseline segun tamano muestral.

    Con n=0 devuelve baseline; con n grande devuelve raw_rate.
    Equivalente a anadir k partidos "promedio" al denominador.
    """
    return (raw_rate * n + baseline * k) / (n + k)


def _top_tier_history_names(top_elo: int = TOP_TIER_ELO) -> set[str]:
    """Devuelve los nombres (estilo martj42) de equipos top por ELO actual."""
    elo_by_code = parse_world_tsv(fetch_world_tsv())
    # invertir FIFA_TO_ELO + cruzar con FIFA_TO_HISTORY
    elo_to_fifa = {v: k for k, v in FIFA_TO_ELO.items()}
    out: set[str] = set()
    for elo_code, elo in elo_by_code.items():
        if elo < top_elo:
            continue
        fifa = elo_to_fifa.get(elo_code)
        if fifa and fifa in FIFA_TO_HISTORY:
            out.add(FIFA_TO_HISTORY[fifa])
    # ademas: incluir equipos top que NO esten en nuestra lista de 48
    # (Italia, Dinamarca, etc) — son rivales relevantes. Para esos no
    # tenemos FIFA code pero podemos mapear por nombre comun.
    # Estos nombres viven directo en el dataset martj42:
    EXTRA_TOP = {
        "Italy", "Denmark", "Wales", "Hungary", "Poland", "Russia",
        "Romania", "Slovakia", "Slovenia", "Greece", "Ireland",
        "Mali", "Nigeria", "Cameroon", "Tunisia",
        "Costa Rica", "Honduras",
        "Venezuela", "Bolivia", "Chile", "Peru",
        "South Korea", "China PR", "Vietnam",
    }
    # filtramos por ELO conocido si esta en el mapa
    for name in EXTRA_TOP:
        # solo agregamos si supera el umbral en el TSV (busqueda inversa)
        for elo_code, elo in elo_by_code.items():
            if elo >= top_elo and FIFA_TO_HISTORY.get(elo_to_fifa.get(elo_code, ""), "") == name:
                out.add(name)
                break
    return out


def _ht_score_lookup(goals: list[dict]) -> dict[tuple, tuple[int, int]]:
    """Para cada partido en goalscorers, devuelve (gh_HT, ga_HT) si calculable.

    Clave: (date_iso, home_team, away_team)
    Solo cuenta goles con minute <= 45.
    Goles en alargue del primer tiempo (minute > 45 pero antes del descanso)
    no se incluyen — pequeno sesgo aceptable.
    """
    ht_goals: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for g in goals:
        if g["minute"] > 45:
            continue
        key = (g["date"], g["home_team"], g["away_team"])
        # g["team"] = quien anoto. own_goal cambia favor.
        scoring_team = g["team"]
        own_goal = g.get("own_goal") == "TRUE"
        # gol cuenta para el equipo opuesto si es own_goal
        if (scoring_team == g["home_team"]) ^ own_goal:
            ht_goals[key][0] += 1
        else:
            ht_goals[key][1] += 1
    return {k: tuple(v) for k, v in ht_goals.items()}


# ─── computos por equipo ────────────────────────────────────────────

def compute_team(
    history_name: str,
    fifa_code: str,
    results: list[dict],
    ht_scores: dict[tuple, tuple[int, int]],
    top_names: set[str],
) -> ResilienceBreakdown:
    n_top = wins_draws_top = clean_sheets_top = 0
    n_behind = comeback = 0
    n_comp = wins_comp = 0

    for r in results:
        is_home = r["home_team"] == history_name
        is_away = r["away_team"] == history_name
        if not (is_home or is_away):
            continue

        gf = r["home_score"] if is_home else r["away_score"]
        ga = r["away_score"] if is_home else r["home_score"]
        opponent = r["away_team"] if is_home else r["home_team"]
        won = gf > ga
        drew = gf == ga

        # (1) y (2) vs top tier
        if opponent in top_names:
            n_top += 1
            if won or drew:
                wins_draws_top += 1
            if ga == 0:
                clean_sheets_top += 1

        # (3) comeback rate: cuenta solo si iban perdiendo al HT
        key = (r["date"], r["home_team"], r["away_team"])
        ht = ht_scores.get(key)
        if ht is not None:
            ht_gf = ht[0] if is_home else ht[1]
            ht_ga = ht[1] if is_home else ht[0]
            if ht_gf < ht_ga:  # iban perdiendo al descanso
                n_behind += 1
                if gf >= ga:
                    comeback += 1

        # (4) winrate competitivo (no amistosos)
        if any(t in r["tournament"] for t in COMPETITIVE_TOURNAMENTS):
            n_comp += 1
            if won:
                wins_comp += 1

    no_loss_vs_top = _shrink(wins_draws_top / n_top if n_top else 0.0, n_top)
    clean_sheet_vs_top = _shrink(clean_sheets_top / n_top if n_top else 0.0, n_top)
    comeback_rate = _shrink(comeback / n_behind if n_behind else 0.0, n_behind,
                            k=2, baseline=0.30)  # baseline 30% es realista para comeback
    competitive_winrate = _shrink(wins_comp / n_comp if n_comp else 0.0, n_comp,
                                  k=6, baseline=0.40)

    # combinacion ponderada: no_loss y clean_sheet son los mas senalizadores
    # de "aguantar al grande"; comeback captura templanza; competitive captura
    # rendimiento en partidos que importan.
    score = (
        0.35 * no_loss_vs_top
        + 0.25 * clean_sheet_vs_top
        + 0.20 * comeback_rate
        + 0.20 * competitive_winrate
    )

    return ResilienceBreakdown(
        fifa_code=fifa_code,
        no_loss_vs_top=round(no_loss_vs_top, 3),
        n_vs_top=n_top,
        clean_sheet_vs_top=round(clean_sheet_vs_top, 3),
        comeback_rate=round(comeback_rate, 3),
        n_behind_ht=n_behind,
        competitive_winrate=round(competitive_winrate, 3),
        n_competitive=n_comp,
        score=round(score, 3),
    )


def compute_all(fifa_codes: list[str]) -> dict[str, ResilienceBreakdown]:
    """Devuelve {fifa_code: ResilienceBreakdown} para los codigos dados.

    Despues de computar los raw scores, RENORMALIZA de modo que la media
    quede en 0.5 y la dispersion se preserve. Razon: el modificador
    condicional del match engine asume 0.5 = neutro. Sin esta paso, equipos
    cerca de la media absoluta (~0.43) terminan con bonus negativo (les
    empeoramos la defensa), lo que es el opuesto del efecto deseado.

    Tras el shift+clip, "resilience" es una metrica RELATIVA al pool de 48
    selecciones: 0.5 = promedio del torneo, >0.5 = mas resistente que el
    promedio, <0.5 = mas fragil.
    """
    since = date.today() - timedelta(days=365 * LOOKBACK_YEARS)
    results = load_results(since=since)
    goals = load_goalscorers(since=since)
    ht_scores = _ht_score_lookup(goals)
    top_names = _top_tier_history_names()

    raw: dict[str, ResilienceBreakdown] = {}
    for fifa in fifa_codes:
        hist_name = FIFA_TO_HISTORY.get(fifa)
        if not hist_name:
            continue
        raw[fifa] = compute_team(hist_name, fifa, results, ht_scores, top_names)

    if not raw:
        return raw

    # Recentrado a media 0.5 con clip suave.
    raw_scores = [b.score for b in raw.values()]
    mean = sum(raw_scores) / len(raw_scores)
    out: dict[str, ResilienceBreakdown] = {}
    for fifa, b in raw.items():
        shifted = max(0.05, min(0.95, b.score - mean + 0.5))
        out[fifa] = ResilienceBreakdown(
            fifa_code=b.fifa_code,
            no_loss_vs_top=b.no_loss_vs_top,
            n_vs_top=b.n_vs_top,
            clean_sheet_vs_top=b.clean_sheet_vs_top,
            comeback_rate=b.comeback_rate,
            n_behind_ht=b.n_behind_ht,
            competitive_winrate=b.competitive_winrate,
            n_competitive=b.n_competitive,
            score=round(shifted, 3),
        )
    return out


if __name__ == "__main__":
    import csv
    from pathlib import Path
    with Path("data/raw/teams_2026.csv").open() as f:
        codes = [r["fifa_code"] for r in csv.DictReader(f)]
    breakdowns = compute_all(codes)
    rows = sorted(breakdowns.values(), key=lambda b: -b.score)
    print(f"{'fifa':5s} {'score':>6s}  {'noLoss_top':>10s} {'CS_top':>7s} {'comeback':>9s} {'comp_wr':>8s}  "
          f"{'n_top':>5s} {'n_HT':>4s} {'n_comp':>6s}")
    for b in rows:
        print(f"{b.fifa_code:5s} {b.score:6.3f}  "
              f"{b.no_loss_vs_top:10.3f} {b.clean_sheet_vs_top:7.3f} "
              f"{b.comeback_rate:9.3f} {b.competitive_winrate:8.3f}  "
              f"{b.n_vs_top:5d} {b.n_behind_ht:4d} {b.n_competitive:6d}")
