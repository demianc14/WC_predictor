"""Partidos de Champions y Europa League para el descanso y la carga.

Fuente: fixturedownload.com, el mismo proveedor de los calendarios de liga.
Trae la fase de grupos (o de liga) y las eliminatorias, sin las previas.
Solo importa QUÉ DÍA jugó cada club de las cinco ligas: los marcadores no
entran al ELO ni a la forma.

Fuera, a propósito:
- Conference League: el feed existe recién desde 2024-25, y meterla solo en
  test haría que train y test midieran cosas distintas.
- Copas nacionales: fixturedownload no las publica.

Nombres: un club que se llama igual que en football-data se cruza solo; el
resto va en `ALIASES`, escrito a mano y revisado con
`python -m src.ml.europe --report`, que lista lo que quedó sin cruzar. Un club
sin cruzar se toma como extranjero (no juega en nuestras ligas).
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.clubs import calendar, data
from src.clubs.data import Match

FEEDS = ("champions-league", "europa-league")
YEARS = tuple(range(2019, 2027))          # 2019-20 a 2026-27, por año de inicio
EUROPE_DIR = data.CACHE_DIR / "europe"

ALIASES = {
    "Athletic Club": "Ath Bilbao",
    "Atleti": "Ath Madrid",
    "Atlético": "Ath Madrid",
    "Atlético de Madrid": "Ath Madrid",
    "B. Dortmund": "Dortmund",
    "Bayern": "Bayern Munich",
    "Bayern München": "Bayern Munich",
    "Espanyol": "Espanol",
    "Frankfurt": "Ein Frankfurt",
    "Internazionale": "Inter",
    "LOSC": "Lille",
    "Leipzig": "RB Leipzig",
    "Man Utd": "Man United",
    "Man. City": "Man City",
    "Man. United": "Man United",
    "Mönchengladbach": "M'gladbach",
    "Paris": "Paris SG",
    "Real Betis": "Betis",
    "Real Sociedad": "Sociedad",
    "St-Étienne": "St Etienne",
}


def path(feed: str, year: int) -> Path:
    return EUROPE_DIR / f"{feed}-{year}.json"


def ensure(feed: str, year: int, force: bool = False) -> Path | None:
    """Descarga el feed si hace falta; sin red usa la caché, y si no hay, None."""
    p = path(feed, year)
    permanent = year < calendar.SEASON_YEAR
    if force or not data._fresh(p, permanent=permanent):
        try:
            data._download(calendar.FEED_URL.format(feed=feed, year=year), p)
        except Exception as e:                        # degradación elegante
            print(f"⚠️  {feed}-{year}: no se pudo descargar ({e}); "
                  + ("uso la caché" if p.exists() else "sigo sin él"))
    return p if p.exists() and p.stat().st_size > 0 else None


def ensure_all() -> None:
    for feed in FEEDS:
        for year in YEARS:
            ensure(feed, year)


def cached_paths() -> list[Path]:
    """Los feeds que hay en la caché, en orden fijo (para la huella)."""
    return [p for feed in FEEDS for year in YEARS if (p := path(feed, year)).exists()]


def _countries(matches: list[Match]) -> dict[str, str]:
    """Nombre de football-data -> país (prefijo de la división)."""
    out: dict[str, set[str]] = defaultdict(set)
    for m in matches:
        c = m.div.rstrip("0123456789")
        out[m.home].add(c)
        out[m.away].add(c)
    dup = {t: cs for t, cs in out.items() if len(cs) > 1}
    if dup:
        raise ValueError(f"Nombres repetidos entre países: {dup}")
    return {t: next(iter(cs)) for t, cs in out.items()}


def load_rows() -> list[dict]:
    rows: list[dict] = []
    for p in cached_paths():
        rows += json.loads(p.read_text(encoding="utf-8"))
    return rows


def club_days(matches: list[Match], rows: list[dict] | None = None
              ) -> tuple[dict[tuple[str, str], list[date]], set[str]]:
    """(país, club de football-data) -> días con partido europeo jugado.

    Devuelve también los nombres del feed que no se cruzaron. Un partido sin
    marcador todavía no se jugó y no cuenta (puede moverse de fecha).
    """
    rows = load_rows() if rows is None else rows
    country = _countries(matches)
    days: dict[tuple[str, str], set[date]] = defaultdict(set)
    unmapped: set[str] = set()
    for f in calendar.parse_calendar(rows):
        if not f.played:
            continue
        for team in (f.home, f.away):
            name = ALIASES.get(team, team)
            if name in country:
                days[(country[name], name)].add(f.day)
            else:
                unmapped.add(team)
    return {k: sorted(v) for k, v in days.items()}, unmapped


def main(argv: list[str] | None = None) -> None:
    from src.ml import dataset
    ap = argparse.ArgumentParser(description="Partidos europeos de los clubes de las 5 ligas")
    ap.add_argument("--report", action="store_true", help="lista lo cruzado y lo no cruzado")
    args = ap.parse_args(argv)
    ensure_all()
    ms = dataset.load(dataset.leagues_from("all"))
    days, unmapped = club_days(ms)
    print(f"✅ {len(cached_paths())} feeds, {sum(map(len, days.values()))} partidos-club "
          f"de {len(days)} clubes de las cinco ligas")
    if args.report:
        by_country: dict[str, list[str]] = defaultdict(list)
        for (c, t), ds in sorted(days.items()):
            by_country[c].append(f"{t} ({len(ds)})")
        for c, ts in sorted(by_country.items()):
            print(f"   {c}: {', '.join(ts)}")
        print(f"🌍 sin cruzar ({len(unmapped)}), tomados como extranjeros:")
        print("   " + ", ".join(sorted(unmapped)))


if __name__ == "__main__":
    main()
