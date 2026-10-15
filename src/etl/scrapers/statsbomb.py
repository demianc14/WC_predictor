"""Tiros y xG de selecciones desde StatsBomb Open Data.

Fuente: github.com/statsbomb/open-data (licencia abierta, atribución StatsBomb).
Cada tiro trae `shot.statsbomb_xg`: la probabilidad de gol de la SITUACIÓN
(ubicación, arquero y defensores del freeze frame) antes del remate.

Qué descargamos: los torneos de selecciones masculinas recientes que el open
data cubre completos. El Mundial 2026 NO está en el open data (a sep-2026).

Los eventos de un partido pesan ~3-5 MB; solo guardamos un resumen compacto
por partido (tiros + marcador + duración) en data/cache/statsbomb/shots/.
Esa caché es permanente: un partido jugado no cambia.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
CACHE_DIR = Path("data/cache/statsbomb")

# (competition_id, season_id, etiqueta). Verificado contra competitions.json
# el 2026-09-22. El Mundial 2018 y anteriores no se incluyen: con la
# ponderación por recencia pesarían < 2%.
COMPETITIONS: list[tuple[int, int, str]] = [
    (55, 43, "Euro 2020"),
    (43, 106, "Mundial 2022"),
    (1267, 107, "AFCON 2023"),
    (55, 282, "Euro 2024"),
    (223, 282, "Copa América 2024"),
]

# Nombre StatsBomb -> código FIFA. Cubre las 48 del Mundial 2026 que aparecen
# en el open data; el resto de selecciones se usa igual en el ajuste por rival
# (con su nombre StatsBomb como id), solo que no llega al pipeline.
SB_TO_FIFA: dict[str, str] = {
    "Mexico": "MEX", "South Africa": "RSA", "South Korea": "KOR",
    "Czech Republic": "CZE", "Canada": "CAN", "Qatar": "QAT", "Switzerland": "SUI",
    "Brazil": "BRA", "Morocco": "MAR", "Scotland": "SCO", "United States": "USA",
    "Paraguay": "PAR", "Australia": "AUS", "Turkey": "TUR", "Germany": "GER",
    "Côte d'Ivoire": "CIV", "Ecuador": "ECU", "Netherlands": "NED", "Japan": "JPN",
    "Sweden": "SWE", "Tunisia": "TUN", "Belgium": "BEL", "Egypt": "EGY",
    "Iran": "IRN", "Spain": "ESP", "Cape Verde Islands": "CPV",
    "Saudi Arabia": "KSA", "Uruguay": "URU", "France": "FRA", "Senegal": "SEN",
    "Argentina": "ARG", "Algeria": "ALG", "Austria": "AUT", "Portugal": "POR",
    "Congo DR": "COD", "Colombia": "COL", "England": "ENG", "Croatia": "CRO",
    "Ghana": "GHA", "Panama": "PAN",
}


@dataclass(frozen=True)
class TeamMatch:
    """Una selección en un partido: lo que generó y lo que concedió."""

    match_id: int
    date: date
    competition: str
    team: str            # nombre StatsBomb
    opponent: str
    minutes: float       # duración jugada (90 o ~120 con prórroga)
    goals: int
    goals_against: int
    xg: float            # todos los tiros (incluye penales, sin tanda)
    np_xg: float         # sin penales: lo que usa el modelo
    xg_against: float
    np_xg_against: float
    shots: int


def _get_json(url: str) -> object:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (WC_predictor/1.0)"})
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_matches(comp_id: int, season_id: int, force: bool = False) -> list[dict]:
    path = CACHE_DIR / f"matches_{comp_id}_{season_id}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    data = _get_json(f"{BASE_URL}/matches/{comp_id}/{season_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def summarize_events(events: list[dict]) -> dict:
    """Reduce los eventos de un partido a tiros + duración.

    Excluye la tanda de penales (period 5): no es juego ni tiene xG útil.
    """
    shots = []
    minutes = 90.0
    for e in events:
        period = e.get("period", 1)
        if period >= 5:
            continue
        minutes = max(minutes, e.get("minute", 0) + e.get("second", 0) / 60)
        if e.get("type", {}).get("name") != "Shot":
            continue
        s = e["shot"]
        shots.append({
            "team": e["team"]["name"],
            "player": e.get("player", {}).get("name"),
            "minute": e.get("minute"),
            "xg": round(float(s.get("statsbomb_xg", 0.0)), 4),
            "type": s.get("type", {}).get("name"),
            "outcome": s.get("outcome", {}).get("name"),
            "body_part": s.get("body_part", {}).get("name"),
            "location": e.get("location"),
        })
    return {"minutes": round(minutes, 1), "shots": shots}


def fetch_match_shots(match_id: int, force: bool = False) -> dict:
    path = CACHE_DIR / "shots" / f"{match_id}.json"
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    summary = summarize_events(_get_json(f"{BASE_URL}/events/{match_id}.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


def team_rows(match: dict, summary: dict, competition: str) -> list[TeamMatch]:
    """Las dos filas (local y visita) de un partido."""
    home = match["home_team"]["home_team_name"]
    away = match["away_team"]["away_team_name"]
    goals = {home: match["home_score"], away: match["away_score"]}
    agg = {t: {"xg": 0.0, "np": 0.0, "n": 0} for t in (home, away)}
    for s in summary["shots"]:
        if s["team"] not in agg:
            continue
        a = agg[s["team"]]
        a["xg"] += s["xg"]
        a["n"] += 1
        if s["type"] != "Penalty":
            a["np"] += s["xg"]
    d = date.fromisoformat(match["match_date"])
    rows = []
    for team, opp in ((home, away), (away, home)):
        rows.append(TeamMatch(
            match_id=match["match_id"], date=d, competition=competition,
            team=team, opponent=opp, minutes=summary["minutes"],
            goals=goals[team], goals_against=goals[opp],
            xg=round(agg[team]["xg"], 4), np_xg=round(agg[team]["np"], 4),
            xg_against=round(agg[opp]["xg"], 4), np_xg_against=round(agg[opp]["np"], 4),
            shots=agg[team]["n"],
        ))
    return rows


def load_team_matches(
    competitions: list[tuple[int, int, str]] = COMPETITIONS,
    workers: int = 8,
    offline: bool = False,
) -> list[TeamMatch]:
    """Todas las filas equipo-partido de los torneos elegidos.

    offline=True usa solo lo que ya está en caché (sin red): los partidos que
    falten se omiten en vez de descargarse.
    """
    rows: list[TeamMatch] = []
    for comp_id, season_id, label in competitions:
        mpath = CACHE_DIR / f"matches_{comp_id}_{season_id}.json"
        if offline and not mpath.exists():
            continue
        matches = fetch_matches(comp_id, season_id)

        def _one(m: dict) -> tuple[dict, dict | None]:
            spath = CACHE_DIR / "shots" / f"{m['match_id']}.json"
            if offline and not spath.exists():
                return m, None
            return m, fetch_match_shots(m["match_id"])

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for m, summary in pool.map(_one, matches):
                if summary is not None:
                    rows.extend(team_rows(m, summary, label))
    rows.sort(key=lambda r: (r.date, r.match_id, r.team))
    return rows


if __name__ == "__main__":
    all_rows = load_team_matches()
    names = sorted({r.team for r in all_rows})
    print(f"✅ {len(all_rows) // 2} partidos, {len(names)} selecciones")
    print("Sin código FIFA:", [n for n in names if n not in SB_TO_FIFA])
