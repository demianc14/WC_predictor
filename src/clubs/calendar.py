"""Calendario completo de la temporada desde fixturedownload.com.

football-data.co.uk solo publica la próxima semana; fixturedownload trae los
380 (o 306) partidos con fecha y, si ya se jugaron, el marcador. Los nombres
no coinciden ("FC Bayern München" vs "Bayern Munich"), así que el cruce no se
escribe a mano: se deduce de los partidos ya jugados en las dos fuentes
(mismo día ±1 y mismo marcador) y falla si algún equipo queda sin pareja.

Los partidos sin horario confirmado vienen a medianoche (hora de la liga);
se marcan con `tbc` y su fecha es solo la de la jornada prevista.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from src.clubs import data
from src.clubs.leagues import League

FEED_URL = "https://fixturedownload.com/feed/json/{feed}-{year}"
SEASON_YEAR = 2026            # fixturedownload nombra la temporada por su año de inicio
PLACEHOLDER_UTC = {"00:00:00Z", "22:00:00Z", "23:00:00Z"}


@dataclass(frozen=True)
class Fixture:
    round: int
    day: date
    home: str                 # nombre de fixturedownload (el "oficial")
    away: str
    hg: int | None
    ag: int | None
    tbc: bool                 # fecha provisional

    @property
    def played(self) -> bool:
        return self.hg is not None


def ensure_calendar(lg: League, force: bool = False) -> list[dict]:
    path = data.CACHE_DIR / f"calendar_{lg.feed}_{SEASON_YEAR}.json"
    if force or not data._fresh(path, permanent=False):
        data._download(FEED_URL.format(feed=lg.feed, year=SEASON_YEAR), path)
    return json.loads(path.read_text(encoding="utf-8"))


def parse_calendar(rows: list[dict]) -> list[Fixture]:
    out = []
    for r in rows:
        ts = r["DateUtc"]
        out.append(Fixture(
            round=int(r["RoundNumber"]),
            day=datetime.strptime(ts[:10], "%Y-%m-%d").date(),
            home=r["HomeTeam"], away=r["AwayTeam"],
            hg=r.get("HomeTeamScore"), ag=r.get("AwayTeamScore"),
            tbc=r.get("HomeTeamScore") is None and ts[11:] in PLACEHOLDER_UTC,
        ))
    return sorted(out, key=lambda f: (f.day, f.round))


def match_names(cal: list[Fixture], played: list[data.Match]) -> dict[str, str]:
    """Nombre del calendario -> nombre de football-data, votado por resultados.

    Cada partido jugado del calendario vota por los partidos de football-data
    del mismo día (±1, por husos horarios) con el mismo marcador. Gana el
    nombre con más votos; un empate o un equipo sin votos es un error.
    """
    by_score: dict[tuple[int, int], list[data.Match]] = {}
    for m in played:
        by_score.setdefault((m.hg, m.ag), []).append(m)
    votes: dict[str, Counter] = {}
    for f in cal:
        if not f.played:
            continue
        for m in by_score.get((f.hg, f.ag), []):
            if abs((m.day - f.day).days) <= 1:
                votes.setdefault(f.home, Counter())[m.home] += 1
                votes.setdefault(f.away, Counter())[m.away] += 1
    teams = {f.home for f in cal} | {f.away for f in cal}
    out, problems = {}, []
    for t in sorted(teams):
        top = votes.get(t, Counter()).most_common(2)
        if not top or (len(top) == 2 and top[0][1] == top[1][1]):
            problems.append(t)
        else:
            out[t] = top[0][0]
    if problems or len(set(out.values())) != len(out):
        raise ValueError(f"Cruce de nombres ambiguo o incompleto: {problems or out}")
    return out


def load(lg: League, played: list[data.Match]) -> tuple[list[Fixture], dict[str, str]]:
    """Calendario con nombres de football-data y el mapa nombre -> nombre oficial."""
    cal = parse_calendar(ensure_calendar(lg))
    names = match_names(cal, played)
    fixed = [Fixture(f.round, f.day, names[f.home], names[f.away], f.hg, f.ag, f.tbc)
             for f in cal]
    check_against(fixed, played)
    return fixed, {v: k for k, v in names.items()}


def check_against(cal: list[Fixture], played: list[data.Match]) -> None:
    """Fail fast si las dos fuentes no cuentan la misma historia."""
    fd = {(m.home, m.away): (m.hg, m.ag) for m in played}
    for f in cal:
        if (f.home, f.away) in fd and f.played and fd[(f.home, f.away)] != (f.hg, f.ag):
            raise ValueError(f"{f.home}-{f.away}: calendario {f.hg}-{f.ag}, "
                             f"football-data {fd[(f.home, f.away)]}")


def pending(cal: list[Fixture], played: list[data.Match]) -> list[Fixture]:
    """Lo que falta jugar según football-data (más fresco que el calendario)."""
    done = {(m.home, m.away) for m in played}
    return [f for f in cal if (f.home, f.away) not in done]


def next_round(cal: list[Fixture], today: date, days: int = 7) -> list[Fixture]:
    return [f for f in cal if not f.played and today <= f.day < today + timedelta(days=days)]
