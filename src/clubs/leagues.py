"""Las cinco grandes: código de football-data, segunda división con la que se
ajusta el modelo (conecta ascendidos y descendidos), tamaño de la liga y el
feed del calendario completo en fixturedownload.com.

Columnas verificadas el 20-oct-2026 en los 40 CSV de la caché (10 divisiones,
2023-24 a 2026-27): todas tienen cierre promedio (AvgC*) y de Bet365
(B365C*); el cierre de Pinnacle (PSC*) falta en 2026-27; xG (HxG/AxG) solo
existe desde 2026-27.
"""
from __future__ import annotations

from dataclasses import dataclass

SEASONS = ("2324", "2425", "2526", "2627")   # tres temporadas cerradas y la actual
BACKTEST = ("2526", "2627")


@dataclass(frozen=True)
class League:
    code: str          # división de football-data (E0, SP1, ...)
    name: str
    lower: str         # segunda división en football-data
    lower_name: str
    teams: int
    feed: str          # fixturedownload.com/feed/json/{feed}-{año}
    places: dict[str, tuple[int, int]]   # zona -> (desde, hasta), posiciones 1-based
    seasons: tuple[str, ...] = SEASONS

    @property
    def rounds(self) -> int:
        return 2 * (self.teams - 1)

    @property
    def matches(self) -> int:
        return self.teams * (self.teams - 1)


LEAGUES: dict[str, League] = {lg.code: lg for lg in (
    League("E0", "Premier League", "E1", "Championship", 20, "epl",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("SP1", "LaLiga", "SP2", "Segunda", 20, "la-liga",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("D1", "Bundesliga", "D2", "2. Bundesliga", 18, "bundesliga",
           {"champions": (1, 4), "descenso": (17, 18)}),
    League("I1", "Serie A", "I2", "Serie B", 20, "serie-a",
           {"champions": (1, 4), "descenso": (18, 20)}),
    League("F1", "Ligue 1", "F2", "Ligue 2", 18, "ligue-1",
           {"champions": (1, 3), "descenso": (17, 18)}),
)}

# Nombre a mostrar cuando el del calendario es un apodo o demasiado largo
# (clave: nombre de football-data).
DISPLAY = {
    "Man City": "Manchester City", "Man United": "Manchester United",
    "Tottenham": "Tottenham", "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest", "Wolves": "Wolverhampton",
    "Espanol": "Espanyol", "Santander": "Racing de Santander", "La Coruna": "Deportivo",
    "Celta": "Celta de Vigo", "Bayern Munich": "Bayern Múnich", "Freiburg": "Friburgo",
    "Brest": "Stade Brestois",
}
