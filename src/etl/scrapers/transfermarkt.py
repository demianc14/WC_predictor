"""Scraper de Transfermarkt: valor de plantilla y edad promedio por seleccion.

Transfermarkt NO esta detras de Cloudflare (a diferencia de FBref), pero si
exige un User-Agent de navegador y agradece pausas entre requests.

Flujo:
  1. Resolver el verein-id de cada seleccion via el buscador rapido
     (schnellsuche), cacheando el id para no repetir.
  2. Bajar la pagina del club y extraer:
       - valor total de plantilla  (€X.XX bn/m -> millones de euros)
       - edad promedio
  3. Cachear el HTML por seleccion con TTL semanal.

Datos que alimentan el LIKELIHOOD (actualidad): el valor de plantilla es un
proxy directo de calidad individual; la edad, de experiencia/frescura.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

CACHE_DIR = Path("data/cache/transfermarkt")
ID_CACHE = CACHE_DIR / "verein_ids.json"
TTL_SECONDS = 7 * 24 * 3600
SLEEP_BETWEEN = 2.0  # segundos entre requests, para no martillar
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Termino de busqueda por FIFA code (en ingles, como lo indexa TM).
# Si la busqueda devuelve algo ambiguo, el primer resultado-club suele ser
# la seleccion absoluta; los IDs se cachean tras la primera resolucion.
FIFA_TO_QUERY: dict[str, str] = {
    "MEX": "Mexico", "RSA": "South Africa", "KOR": "South Korea", "CZE": "Czech Republic",
    "CAN": "Canada", "BIH": "Bosnia-Herzegovina", "QAT": "Qatar", "SUI": "Switzerland",
    "BRA": "Brazil", "MAR": "Morocco", "HAI": "Haiti", "SCO": "Scotland",
    "USA": "United States", "PAR": "Paraguay", "AUS": "Australia", "TUR": "Turkey",
    "GER": "Germany", "CUW": "Curacao", "CIV": "Cote d'Ivoire", "ECU": "Ecuador",
    "NED": "Netherlands", "JPN": "Japan", "SWE": "Sweden", "TUN": "Tunisia",
    "BEL": "Belgium", "EGY": "Egypt", "IRN": "Iran", "NZL": "New Zealand",
    "ESP": "Spain", "CPV": "Cape Verde", "KSA": "Saudi Arabia", "URU": "Uruguay",
    "FRA": "France", "SEN": "Senegal", "IRQ": "Iraq", "NOR": "Norway",
    "ARG": "Argentina", "ALG": "Algeria", "AUT": "Austria", "JOR": "Jordan",
    "POR": "Portugal", "COD": "DR Congo", "UZB": "Uzbekistan", "COL": "Colombia",
    "ENG": "England", "CRO": "Croatia", "GHA": "Ghana", "PAN": "Panama",
}

# El valor viene como:  ...market-value-wrapper"><span class="waehrung">€</span>1.22<span class="waehrung">bn</span>
# IDs verificados a mano para selecciones que la busqueda confunde con
# territorios homonimos que TAMBIEN tienen categorias juveniles (la heuristica
# del companero juvenil no basta): USA vs Islas Virgenes, FRA vs Guayana Francesa.
# Y para selecciones cuyo termino de busqueda no matchea ('Czech Republic',
# "Cote d'Ivoire" no devuelven la senior). El slug es irrelevante: TM resuelve
# por verein-id, asi que usamos 'team' como slug generico.
VEREIN_ID_OVERRIDE: dict[str, str] = {
    "FRA": "team|3377",
    "USA": "team|3505",
    "CZE": "team|3445",
    "CIV": "team|3591",
}

VALUE_RE = re.compile(
    r'market-value-wrapper">\s*<span[^>]*>€</span>\s*([0-9.,]+)\s*<span[^>]*>(bn|m|k)</span>',
    re.S,
)
# La edad viene como:  Average age:\n <span ...>\n 26.8
AGE_RE = re.compile(r'Average age:\s*<span[^>]*>\s*([0-9]{2}\.[0-9])', re.S)


@dataclass
class TMData:
    fifa_code: str
    squad_value_meur: float | None  # valor total en millones de euros
    avg_age: float | None


def _fetch(url: str) -> str:
    # Accept-Language es importante: sin el, TM sirve un layout distinto
    # (sin el wrapper de valor en ingles) que rompe el parser.
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _load_id_cache() -> dict[str, str]:
    if ID_CACHE.exists():
        return json.loads(ID_CACHE.read_text(encoding="utf-8"))
    return {}


def _save_id_cache(cache: dict[str, str]) -> None:
    ID_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ID_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


_YOUTH_SUFFIXES = ("-u23", "-u21", "-u20", "-u19", "-u18", "-u17", "-u16", "-u15")


def resolve_verein_id(fifa: str, id_cache: dict[str, str]) -> tuple[str, str] | None:
    """Devuelve (slug, verein_id) de la SELECCION ABSOLUTA, cacheando el resultado.

    El buscador de TM devuelve decenas de clubes por relevancia; el equipo
    nacional puede estar en posicion 9+. Heuristica robusta: la seleccion
    absoluta es el unico verein cuyo slug `S` tiene companeros juveniles
    (`S-u21`, `S-u19`, ...) en los mismos resultados. Solo las selecciones
    nacionales tienen categorias juveniles indexadas en TM, asi que esto
    identifica al senior team sin ambiguedad.
    """
    if fifa in VEREIN_ID_OVERRIDE:
        slug, vid = VEREIN_ID_OVERRIDE[fifa].split("|", 1)
        id_cache[fifa] = VEREIN_ID_OVERRIDE[fifa]
        return slug, vid
    if fifa in id_cache:
        slug, vid = id_cache[fifa].split("|", 1)
        return slug, vid
    query = FIFA_TO_QUERY.get(fifa)
    if not query:
        return None
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={quote(query)}"
    html = _fetch(url)
    time.sleep(SLEEP_BETWEEN)

    # mapa slug -> id de todos los vereins en los resultados
    found: dict[str, str] = {}
    for m in re.finditer(r'/([a-z0-9-]+)/startseite/verein/([0-9]+)', html):
        found.setdefault(m.group(1), m.group(2))

    # senior team = slug sin sufijo juvenil que tenga al menos un companero juvenil
    base_slugs = {s for s in found if not any(s.endswith(suf) for suf in _YOUTH_SUFFIXES)}
    for slug in base_slugs:
        if any(f"{slug}{suf}" in found for suf in _YOUTH_SUFFIXES):
            id_cache[fifa] = f"{slug}|{found[slug]}"
            return slug, found[slug]
    return None


def _parse_team_page(html: str) -> tuple[float | None, float | None]:
    value = None
    mv = VALUE_RE.search(html)
    if mv:
        num = float(mv.group(1).replace(",", ""))
        unit = mv.group(2)
        value = num * 1000 if unit == "bn" else num if unit == "m" else num / 1000
    age = None
    ma = AGE_RE.search(html)
    if ma:
        age = float(ma.group(1))
    return value, age


def get_transfermarkt_data(fifa_codes: list[str], force: bool = False) -> dict[str, TMData]:
    """Para cada FIFA code, devuelve valor de plantilla (M€) y edad promedio."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    id_cache = _load_id_cache()
    out: dict[str, TMData] = {}

    for fifa in fifa_codes:
        resolved = resolve_verein_id(fifa, id_cache)
        if not resolved:
            out[fifa] = TMData(fifa, None, None)
            continue
        slug, vid = resolved
        page_cache = CACHE_DIR / f"{fifa}.html"
        fresh = page_cache.exists() and (time.time() - page_cache.stat().st_mtime) < TTL_SECONDS
        if force or not fresh:
            url = f"https://www.transfermarkt.com/{slug}/startseite/verein/{vid}"
            html = _fetch(url)
            page_cache.write_text(html, encoding="utf-8")
            time.sleep(SLEEP_BETWEEN)
        else:
            html = page_cache.read_text(encoding="utf-8")
        value, age = _parse_team_page(html)
        out[fifa] = TMData(fifa, value, age)

    _save_id_cache(id_cache)
    return out


if __name__ == "__main__":
    import csv
    with Path("data/raw/teams_2026.csv").open() as f:
        codes = [r["fifa_code"] for r in csv.DictReader(f)]
    data = get_transfermarkt_data(codes)
    ok = sum(1 for d in data.values() if d.squad_value_meur)
    print(f"OK: {ok}/{len(data)} con valor de plantilla\n")
    print(f"{'fifa':5s} {'valor(M€)':>10s} {'edad':>5s}")
    for fifa, d in sorted(data.items(), key=lambda kv: -(kv[1].squad_value_meur or 0)):
        v = f"{d.squad_value_meur:,.0f}" if d.squad_value_meur else "—"
        a = f"{d.avg_age}" if d.avg_age else "—"
        print(f"{fifa:5s} {v:>10s} {a:>5s}")
