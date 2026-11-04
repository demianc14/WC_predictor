"""Partidos para el Dixon-Coles conjunto: ligas domésticas + Champions y Europa League.

Los ratings de Maher son globales: un club de la Premier y uno de la Eredivisie
quedan en la misma escala porque los conectan los partidos europeos (y los
ascensos y descensos dentro de cada país). Para eso se juntan:

- Las diez divisiones de las cinco grandes ligas.
- Ligas extra de football-data en el mismo formato (`EXTRA_DIVS`), donde
  juegan los clubes que más se cruzan con los nuestros en Europa.
- Champions y Europa League desde 2019-20 (fixturedownload, `src/ml/europe.py`),
  como partidos con div `UCL` / `UEL`.

Un club europeo sin liga en la fuente (Bodø/Glimt, Slavia Praha, ...) entra
solo con sus partidos europeos: su rating se apoya en pocos partidos y lo dice
su `n_eff`.

Nombres: el feed se cruza con football-data por igualdad o con `ALIASES`; un
club que no está en football-data igual se normaliza (el feed a veces escribe
el mismo club de dos maneras). `python -m src.europe.data --report` lista los
nombres del feed que quedaron sin liga.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from src.clubs import calendar, data
from src.clubs.data import Match
from src.clubs.leagues import LEAGUES
from src.ml import europe

# Países Bajos, Portugal, Turquía, Bélgica, Grecia y Escocia
EXTRA_DIVS = ("N1", "P1", "T1", "B1", "G1", "SC0")
SEASONS = ("2122", "2223", "2324", "2425", "2526", "2627")
COMPS = {"champions-league": "UCL", "europa-league": "UEL"}

ALIASES = {
    **europe.ALIASES,
    # clubes de las ligas extra: nombre del feed -> nombre de football-data
    "AEK Athens": "AEK",
    "Braga": "Sp Braga",
    "FC Porto": "Porto",
    "Fenerbahçe": "Fenerbahce",
    "Istanbul Basaksehir": "Buyuksehyr",
    "N.E.C.": "Nijmegen",
    "Olympiacos": "Olympiakos",
    "PSV": "PSV Eindhoven",
    "Sporting CP": "Sp Lisbon",
    "Standard Liège": "Standard",
    "Union SG": "St. Gilloise",
    "Vitória SC": "Guimaraes",
    # sin liga en la fuente: el mismo club escrito de dos maneras
    "Crvena zvezda": "Crvena Zvezda",
    "GNK Dinamo": "Dinamo Zagreb",
    "Lech Poznan": "Lech",
    "M. Haifa": "Maccabi Haifa",
    "Omonoia": "Omonia",
    "Plzen": "Viktoria Plzen",
    "S. Bratislava": "Slovan Bratislava",
    "Shakhtar Donetsk": "Shakhtar",
    "Sturm Graz": "Sturm",
}


def divisions() -> list[str]:
    return [d for lg in LEAGUES.values() for d in (lg.code, lg.lower)] + list(EXTRA_DIVS)


def season_of(year: int) -> str:
    """2024 -> "2425", la temporada de football-data que empieza ese año."""
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def name(feed_name: str) -> str:
    return ALIASES.get(feed_name, feed_name)


def european(rows: list[dict], comp: str, season: str) -> list[Match]:
    """Un feed de fixturedownload como partidos (jugados o no) con div `comp`."""
    return [Match(comp, season, f.day, name(f.home), name(f.away), f.hg, f.ag)
            for f in calendar.parse_calendar(rows)]



def load_european(years: tuple[int, ...] = europe.YEARS) -> list[Match]:
    out: list[Match] = []
    for feed, comp in COMPS.items():
        for y in years:
            p = europe.ensure(feed, y)
            if p is not None:
                out += european(json.loads(p.read_text(encoding="utf-8")), comp, season_of(y))
    return out


def load_domestic(seasons: tuple[str, ...] = SEASONS) -> list[Match]:
    return data.load_matches(divisions(), list(seasons))


def check_names(domestic: list[Match]) -> None:
    """Un nombre en dos países serían dos clubes con un solo rating: no se permite."""
    where: dict[str, set[str]] = defaultdict(set)
    for m in domestic:
        c = m.div.rstrip("0123456789")
        where[m.home].add(c)
        where[m.away].add(c)
    dup = {t: cs for t, cs in where.items() if len(cs) > 1}
    if dup:
        raise ValueError(f"Nombres repetidos entre países: {dup}")


def load() -> list[Match]:
    domestic = load_domestic()
    check_names(domestic)
    return sorted(domestic + load_european(), key=lambda m: m.day)


def without_league(matches: list[Match]) -> set[str]:
    """Clubes que solo aparecen en partidos europeos (sin liga doméstica en la fuente)."""
    dom = {t for m in matches if m.div not in COMPS.values() for t in (m.home, m.away)}
    return {t for m in matches if m.div in COMPS.values() for t in (m.home, m.away)} - dom


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Datos del Dixon-Coles conjunto")
    ap.add_argument("--report", action="store_true", help="lista los clubes sin liga")
    args = ap.parse_args(argv)
    ms = load()
    eu = [m for m in ms if m.div in COMPS.values()]
    print(f"✅ {len(ms) - len(eu)} partidos de liga ({len(divisions())} divisiones) "
          f"y {len(eu)} europeos")
    if args.report:
        alone = sorted(without_league(ms))
        print(f"🌍 sin liga en la fuente ({len(alone)}): {', '.join(alone)}")


if __name__ == "__main__":
    main()
