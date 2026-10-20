"""Las cinco grandes ligas: código de football-data, segunda división con la
que se ajusta el modelo (conecta ascendidos y descendidos) y el feed del
calendario completo en fixturedownload.com.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    code: str          # identificador corto del proyecto
    name: str
    div: str           # football-data: primera
    lower: str         # football-data: segunda
    feed: str          # fixturedownload.com/feed/json/{feed}-{año}
    places: dict[str, tuple[int, int]]   # zona -> (desde, hasta), posiciones 1-based


LEAGUES: dict[str, League] = {lg.code: lg for lg in (
    League("PL", "Premier League", "E0", "E1", "epl",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("LL", "LaLiga", "SP1", "SP2", "la-liga",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("BL", "Bundesliga", "D1", "D2", "bundesliga",
           {"champions": (1, 4), "descenso": (17, 18)}),
    League("SA", "Serie A", "I1", "I2", "serie-a",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("L1", "Ligue 1", "F1", "F2", "ligue-1",
           {"champions": (1, 3), "descenso": (17, 18)}),
)}
