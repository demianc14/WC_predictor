"""Scraper de ELO desde eloratings.net.

eloratings.net renderiza la tabla por JS, pero los datos viven en un TSV
plano servido en https://www.eloratings.net/World.tsv. Columnas que nos
importan:
    col 0: rank
    col 2: codigo interno eloratings (no es ISO-2)
    col 3: ELO actual

Estrategia:
    1) Descargar World.tsv si la caché tiene > TTL.
    2) Mapear FIFA code (3 letras) -> codigo eloratings (2 letras).
    3) Devolver dict {fifa_code: elo_int}.

Sin BeautifulSoup ni dependencias nuevas: solo urllib + pathlib.
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.request import Request, urlopen

ELO_URL = "https://www.eloratings.net/World.tsv"
CACHE_PATH = Path("data/cache/elo/world.tsv")
TTL_SECONDS = 7 * 24 * 3600  # una semana

# Mapeo FIFA (3 letras) -> codigo eloratings.net (2 letras).
# Verificado contra en.teams.tsv el 2026-06-15. Solo cubre las 48 selecciones
# del Mundial 2026; ampliar segun necesidad.
FIFA_TO_ELO: dict[str, str] = {
    # Grupo A
    "MEX": "MX", "RSA": "ZA", "KOR": "KR", "CZE": "CZ",
    # Grupo B
    "CAN": "CA", "BIH": "BA", "QAT": "QA", "SUI": "CH",
    # Grupo C
    "BRA": "BR", "MAR": "MA", "HAI": "HT", "SCO": "SQ",
    # Grupo D
    "USA": "US", "PAR": "PY", "AUS": "AU", "TUR": "TR",
    # Grupo E
    "GER": "DE", "CUW": "CW", "CIV": "CI", "ECU": "EC",
    # Grupo F
    "NED": "NL", "JPN": "JP", "SWE": "SE", "TUN": "TN",
    # Grupo G
    "BEL": "BE", "EGY": "EG", "IRN": "IR", "NZL": "NZ",
    # Grupo H
    "ESP": "ES", "CPV": "CV", "KSA": "SA", "URU": "UY",
    # Grupo I
    "FRA": "FR", "SEN": "SN", "IRQ": "IQ", "NOR": "NO",
    # Grupo J
    "ARG": "AR", "ALG": "DZ", "AUT": "AT", "JOR": "JO",
    # Grupo K
    "POR": "PT", "COD": "CD", "UZB": "UZ", "COL": "CO",
    # Grupo L
    "ENG": "EN", "CRO": "HR", "GHA": "GH", "PAN": "PA",
}


def _is_cache_fresh(path: Path = CACHE_PATH, ttl: int = TTL_SECONDS) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl


def _download_tsv(url: str = ELO_URL) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (WC_llm/0.1)"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def fetch_world_tsv(force: bool = False) -> str:
    """Devuelve el contenido del World.tsv (cacheado, salvo force=True)."""
    if not force and _is_cache_fresh():
        return CACHE_PATH.read_text(encoding="utf-8")
    body = _download_tsv()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(body, encoding="utf-8")
    return body


def parse_world_tsv(body: str) -> dict[str, int]:
    """Parsea el TSV y devuelve {codigo_eloratings: elo_int}."""
    out: dict[str, int] = {}
    for line in body.splitlines():
        cols = line.split("\t")
        if len(cols) < 4:
            continue
        code, rating = cols[2], cols[3]
        try:
            out[code] = int(rating)
        except ValueError:
            continue
    return out


def get_elo_for_fifa_codes(
    fifa_codes: list[str], force: bool = False
) -> dict[str, int | None]:
    """Para cada FIFA code, devuelve su ELO actual (o None si no esta mapeado)."""
    body = fetch_world_tsv(force=force)
    elo_by_code = parse_world_tsv(body)
    result: dict[str, int | None] = {}
    for fifa in fifa_codes:
        elo_code = FIFA_TO_ELO.get(fifa)
        if elo_code is None:
            result[fifa] = None
            continue
        result[fifa] = elo_by_code.get(elo_code)
    return result


if __name__ == "__main__":
    import csv
    import sys

    csv_path = Path("data/raw/teams_2026.csv")
    if not csv_path.exists():
        print(f"No existe {csv_path}", file=sys.stderr)
        sys.exit(1)

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        fifa_codes = [row["fifa_code"] for row in reader]

    elos = get_elo_for_fifa_codes(fifa_codes)
    missing = [c for c, v in elos.items() if v is None]
    print(f"OK: {len(elos) - len(missing)}/{len(elos)} equipos con ELO")
    if missing:
        print(f"FALTAN: {missing}")
        sys.exit(2)
    for fifa, elo in sorted(elos.items(), key=lambda kv: -(kv[1] or 0)):
        print(f"  {fifa}  {elo}")
