"""Scraper del historial de partidos internacionales.

Fuente: martj42/international_results en GitHub. CSV publico, abierto,
actualizado a diario. Cubre TODOS los partidos internacionales desde
1872 + un companero goalscorers.csv con minuto de cada gol (que usamos
para derivar marcadores de medio tiempo y, de ahi, comeback_rate).

Cache local con TTL semanal en data/cache/history/.
"""
from __future__ import annotations

import csv
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
GOALS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/goalscorers.csv"
CACHE_DIR = Path("data/cache/history")
TTL_SECONDS = 7 * 24 * 3600

# Mapeo FIFA -> nombre exacto en el dataset martj42.
# Los nombres que no aparecen aqui son identicos al nombre canonico
# (Spain, England, Brazil, etc). Verificado contra results.csv.
FIFA_TO_HISTORY: dict[str, str] = {
    "MEX": "Mexico", "RSA": "South Africa", "KOR": "South Korea",
    "CZE": "Czech Republic",
    "CAN": "Canada", "BIH": "Bosnia and Herzegovina", "QAT": "Qatar", "SUI": "Switzerland",
    "BRA": "Brazil", "MAR": "Morocco", "HAI": "Haiti", "SCO": "Scotland",
    "USA": "United States", "PAR": "Paraguay", "AUS": "Australia", "TUR": "Turkey",
    "GER": "Germany", "CUW": "Curaçao", "CIV": "Ivory Coast", "ECU": "Ecuador",
    "NED": "Netherlands", "JPN": "Japan", "SWE": "Sweden", "TUN": "Tunisia",
    "BEL": "Belgium", "EGY": "Egypt", "IRN": "Iran", "NZL": "New Zealand",
    "ESP": "Spain", "CPV": "Cape Verde", "KSA": "Saudi Arabia", "URU": "Uruguay",
    "FRA": "France", "SEN": "Senegal", "IRQ": "Iraq", "NOR": "Norway",
    "ARG": "Argentina", "ALG": "Algeria", "AUT": "Austria", "JOR": "Jordan",
    "POR": "Portugal", "COD": "DR Congo", "UZB": "Uzbekistan", "COL": "Colombia",
    "ENG": "England", "CRO": "Croatia", "GHA": "Ghana", "PAN": "Panama",
}

# Torneos oficiales considerados "competitivos" (no amistosos)
# para metricas de winrate competitivo.
COMPETITIVE_TOURNAMENTS = {
    "FIFA World Cup", "FIFA World Cup qualification",
    "UEFA Euro", "UEFA Euro qualification",
    "Copa América", "Copa América qualification",
    "African Cup of Nations", "African Cup of Nations qualification",
    "AFC Asian Cup", "AFC Asian Cup qualification",
    "CONCACAF Championship", "CONCACAF Gold Cup", "CONCACAF Nations League",
    "OFC Nations Cup",
    "UEFA Nations League",
    "Confederations Cup",
    "Copa América Centenario",
    "African Nations Championship",
}


# ─── Cache & download ────────────────────────────────────────────────

def _is_fresh(path: Path) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < TTL_SECONDS


def _download(url: str, target: Path) -> None:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (WC_llm/0.1)"})
    with urlopen(req, timeout=60) as resp:
        body = resp.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)


def ensure_cache(force: bool = False) -> tuple[Path, Path]:
    """Garantiza que results.csv y goalscorers.csv esten en cache."""
    results_path = CACHE_DIR / "results.csv"
    goals_path = CACHE_DIR / "goalscorers.csv"
    if force or not _is_fresh(results_path):
        _download(RESULTS_URL, results_path)
    if force or not _is_fresh(goals_path):
        _download(GOALS_URL, goals_path)
    return results_path, goals_path


# ─── Parsing ─────────────────────────────────────────────────────────

def load_results(since: date | None = None) -> list[dict]:
    """Carga results.csv como list[dict] (filtrando partidos sin score y opcionalmente
    posteriores a `since`).
    """
    results_path, _ = ensure_cache()
    rows: list[dict] = []
    with results_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["home_score"] in ("", "NA") or r["away_score"] in ("", "NA"):
                continue
            try:
                d = date.fromisoformat(r["date"])
            except ValueError:
                continue
            if since and d < since:
                continue
            r["_date"] = d
            r["home_score"] = int(r["home_score"])
            r["away_score"] = int(r["away_score"])
            r["neutral"] = (r["neutral"] == "TRUE")
            rows.append(r)
    return rows


def load_goalscorers(since: date | None = None) -> list[dict]:
    """Carga goalscorers.csv (minuto de cada gol).

    Filtramos minutos invalidos (algunas filas tienen '' o '<NA>')."""
    _, goals_path = ensure_cache()
    rows: list[dict] = []
    with goals_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                d = date.fromisoformat(r["date"])
                minute = int(r["minute"])
            except (ValueError, KeyError):
                continue
            if since and d < since:
                continue
            r["_date"] = d
            r["minute"] = minute
            rows.append(r)
    return rows
