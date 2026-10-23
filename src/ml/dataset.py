"""Partidos para el modelo supervisado y su huella.

Temporadas (football-data, primera y segunda de las cinco ligas):
- 2019-20: solo historia previa (ELO, forma y el primer ajuste Dixon-Coles).
- 2020-21 a 2022-23: entrenamiento.
- 2023-24 y 2024-25: validación, para elegir hiperparámetros.
- 2025-26 y 2026-27: test final, que no se mira hasta elegir.
El walk-forward siempre entrena con todo lo anterior al bloque que predice,
así que en test también se entrena con validación; lo que no se hace es
elegir nada mirando el test.
"""
from __future__ import annotations

import hashlib

from src.clubs import data
from src.clubs.data import Match
from src.clubs.leagues import LEAGUES, League
from src.ml import europe

WARMUP = ("1920",)
TRAIN = ("2021", "2122", "2223")
VALID = ("2324", "2425")
TEST = ("2526", data.CURRENT_SEASON)
ALL_SEASONS = WARMUP + TRAIN + VALID + TEST
ROW_SEASONS = TRAIN + VALID + TEST


def leagues_from(arg: str) -> list[League]:
    if arg == "all":
        return list(LEAGUES.values())
    codes = [c.strip() for c in arg.split(",")]
    unknown = [c for c in codes if c not in LEAGUES]
    if unknown:
        raise ValueError(f"Ligas desconocidas: {unknown}. Opciones: {sorted(LEAGUES)} o 'all'")
    return [LEAGUES[c] for c in codes]


def load(leagues: list[League]) -> list[Match]:
    divs = [d for lg in leagues for d in (lg.code, lg.lower)]
    return data.load_matches(divs, list(ALL_SEASONS))


def fingerprint(leagues: list[League]) -> str:
    """SHA-256 de los CSV y feeds europeos que entran, en orden fijo: identifica el dataset."""
    h = hashlib.sha256()
    for lg in leagues:
        for div in (lg.code, lg.lower):
            for s in ALL_SEASONS:
                path = data.CACHE_DIR / f"{div}_{s}.csv"
                h.update(f"{div}_{s}".encode())
                h.update(path.read_bytes())
    for path in europe.cached_paths():               # Champions y Europa League
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]
