"""Exporta las fuerzas del modelo al JS embebido en app/index.html.

Mantiene el frontend SINCRONIZADO con el modelo: tras cada `etl`, correr
este script reescribe en index.html las líneas `const TEAMS=...;`
(fuerzas actuales) y `const TEAMS_PRE=...;` (snapshot pre-Mundial del
15-jun, que usa el archivo del Mundial 2026 para mostrar lo que el modelo
esperaba antes de jugarse).

Campos por equipo: c (code), n (nombre ES), g (grupo del Mundial 2026),
p (posterior), a (att), d (defe), r (resilience) y, si hay datos de
StatsBomb: xf/xa (npxG/90 a favor/en contra ajustado por rival), xn
(partidos), xt (torneos).

Además exporta la última ventana internacional: `const TEAMS_WIN=...;`
(fuerzas congeladas al inicio de la ventana, WINDOW_SNAPSHOT) y
`const WINDOW=...;` (partidos de las 48 jugados después de esa fecha),
para que la web compare lo que esperaba el modelo con lo que pasó.
"""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

from src.clubs.leagues import LEAGUES
from src.etl.scrapers import elo as elo_scraper
from src.etl.scrapers import transfermarkt as tm
from src.etl.scrapers.history import FIFA_TO_HISTORY

STRENGTHS = Path("data/processed/strengths_2026.json")
SNAPSHOT = Path("data/snapshots/strengths_2026-06-15.json")
# Fuerzas al cierre de la ventana anterior: punto de partida de la actual.
WINDOW_SNAPSHOT = Path("data/snapshots/strengths_2026-09-22.json")
WINDOW_FROM = "2026-09-22"
RESULTS = Path("data/cache/history/results.csv")
CLUBS_DIR = Path("data/processed")                     # python -m src.clubs.run
# Próxima ventana: calendario curado a mano (fuentes en la columna `source`).
FIXTURES = Path("data/raw/fixtures_2026-11.csv")
ELO_NAMES = Path("data/cache/elo/teams.tsv")       # eloratings.net en.teams.tsv
ELO_ALIAS = {"Republic of Ireland": "Ireland"}
XG = Path("data/processed/xg_statsbomb.json")
OUT_JSON = Path("data/processed/frontend_teams.json")
INDEX = Path("app/index.html")

# Nombres en espanol (los que ya usaba el front).
NAME_ES = {
    "MEX": "México", "RSA": "Sudáfrica", "KOR": "Corea del Sur", "CZE": "Chequia",
    "CAN": "Canadá", "BIH": "Bosnia y Herzegovina", "QAT": "Catar", "SUI": "Suiza",
    "BRA": "Brasil", "MAR": "Marruecos", "HAI": "Haití", "SCO": "Escocia",
    "USA": "Estados Unidos", "PAR": "Paraguay", "AUS": "Australia", "TUR": "Turquía",
    "GER": "Alemania", "CUW": "Curazao", "CIV": "Costa de Marfil", "ECU": "Ecuador",
    "NED": "Países Bajos", "JPN": "Japón", "SWE": "Suecia", "TUN": "Túnez",
    "BEL": "Bélgica", "EGY": "Egipto", "IRN": "Irán", "NZL": "Nueva Zelanda",
    "ESP": "España", "CPV": "Cabo Verde", "KSA": "Arabia Saudita", "URU": "Uruguay",
    "FRA": "Francia", "SEN": "Senegal", "IRQ": "Irak", "NOR": "Noruega",
    "ARG": "Argentina", "ALG": "Argelia", "AUT": "Austria", "JOR": "Jordania",
    "POR": "Portugal", "COD": "RD Congo", "UZB": "Uzbekistán", "COL": "Colombia",
    "ENG": "Inglaterra", "CRO": "Croacia", "GHA": "Ghana", "PAN": "Panamá",
}


# Rivales fuera de las 48 que aparecen en la ventana (fallback: nombre en inglés).
OPP_ES = {
    "Bahrain": "Baréin", "Benin": "Benín", "Cameroon": "Camerún", "China": "China",
    "Comoros": "Comoras", "Denmark": "Dinamarca", "Dominican Republic": "Rep. Dominicana",
    "Equatorial Guinea": "Guinea Ecuatorial", "Ethiopia": "Etiopía", "Gabon": "Gabón",
    "Greece": "Grecia", "Italy": "Italia", "Kuwait": "Kuwait", "Lesotho": "Lesoto",
    "Mozambique": "Mozambique", "Niger": "Níger", "North Macedonia": "Macedonia del Norte",
    "Oman": "Omán", "Peru": "Perú", "Poland": "Polonia", "Republic of Ireland": "Irlanda",
    "Romania": "Rumania", "Russia": "Rusia", "Rwanda": "Ruanda", "Serbia": "Serbia",
    "Slovenia": "Eslovenia", "South Sudan": "Sudán del Sur", "Syria": "Siria",
    "Trinidad and Tobago": "Trinidad y Tobago", "United Arab Emirates": "Emiratos Árabes",
    "Wales": "Gales", "Yemen": "Yemen", "Zambia": "Zambia", "Zimbabwe": "Zimbabue",
    "Burundi": "Burundi", "Somalia": "Somalia", "Eritrea": "Eritrea", "Gambia": "Gambia",
    "Israel": "Israel", "Kosovo": "Kosovo", "Mali": "Malí", "Angola": "Angola",
    "Uganda": "Uganda", "Botswana": "Botsuana", "Guinea": "Guinea", "India": "India",
    "Palestine": "Palestina", "Bolivia": "Bolivia", "Chile": "Chile", "Venezuela": "Venezuela",
    "Costa Rica": "Costa Rica", "Nicaragua": "Nicaragua", "Burkina Faso": "Burkina Faso",
    "Guatemala": "Guatemala", "Jamaica": "Jamaica", "Singapore": "Singapur",
    "Malawi": "Malaui", "Togo": "Togo", "Liberia": "Liberia", "Sierra Leone": "Sierra Leona",
    "Kenya": "Kenia", "Libya": "Libia", "Sudan": "Sudán",
}
TOURNAMENT_ES = {
    "Friendly": "Amistoso", "African Cup of Nations qualification": "Clasif. Copa África",
    "Gulf Cup": "Copa del Golfo", "Kirin Cup": "Copa Kirin",
}


def build_window(path: Path = RESULTS, since: str = WINDOW_FROM) -> list[dict]:
    """Partidos de las 48 jugados después de `since`, en orden cronológico.

    El CSV de martj42 trae a veces el mismo partido cargado dos veces en días
    consecutivos (p. ej. Argentina 4-0 Bolivia, 30-sep y 1-oct): se descarta
    la repetición si coincide local, visitante y marcador en ≤2 días.
    """
    to_code = {v: k for k, v in FIFA_TO_HISTORY.items()}
    out: list[dict] = []
    seen: dict[tuple, date] = {}
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["date"] <= since or r["home_score"] in ("", "NA"):
                continue
            h, a = r["home_team"], r["away_team"]
            if h not in to_code and a not in to_code:
                continue
            key = (h, a, r["home_score"], r["away_score"])
            d = date.fromisoformat(r["date"])
            if key in seen and (d - seen[key]).days <= 2:
                continue
            seen[key] = d
            out.append({
                "dt": r["date"],
                "h": to_code.get(h), "hn": NAME_ES.get(to_code.get(h), OPP_ES.get(h, h)),
                "a": to_code.get(a), "an": NAME_ES.get(to_code.get(a), OPP_ES.get(a, a)),
                "s": [int(r["home_score"]), int(r["away_score"])],
                "t": TOURNAMENT_ES.get(r["tournament"], r["tournament"]),
                "nt": r["neutral"].upper() == "TRUE",
            })
    return out


def build_extras(results: Path = RESULTS, n_form: int = 5) -> dict[str, dict]:
    """Datos de contexto para el ranking, solo desde las cachés locales (sin red).

    e/er: ELO actual y puesto mundial (eloratings.net); v/ag: valor de plantilla
    en M€ y edad promedio (Transfermarkt); f: últimos `n_form` partidos como
    [resultado W/D/L, goles a favor, en contra, rival, fecha], del más reciente.
    """
    out: dict[str, dict] = {c: {} for c in NAME_ES}
    if elo_scraper.CACHE_PATH.exists():
        by_code = {}
        for line in elo_scraper.CACHE_PATH.read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            if len(cols) >= 4 and cols[0].isdigit() and cols[3].isdigit():
                by_code[cols[2]] = (int(cols[0]), int(cols[3]))
        for c in out:
            hit = by_code.get(elo_scraper.FIFA_TO_ELO.get(c, ""))
            if hit:
                out[c].update(er=hit[0], e=hit[1])
    for c in out:
        page = tm.CACHE_DIR / f"{c}.html"
        if page.exists():
            value, age = tm._parse_team_page(page.read_text(encoding="utf-8"))
            if value is not None:
                out[c]["v"] = round(value, 1)
            if age is not None:
                out[c]["ag"] = age
    to_code = {v: k for k, v in FIFA_TO_HISTORY.items()}
    form: dict[str, list] = {c: [] for c in out}
    with results.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["home_score"] in ("", "NA"):
                continue
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            for team, opp, gf, ga in ((r["home_team"], r["away_team"], hs, as_),
                                      (r["away_team"], r["home_team"], as_, hs)):
                c = to_code.get(team)
                if c:
                    res = "W" if gf > ga else "D" if gf == ga else "L"
                    opp_n = NAME_ES.get(to_code.get(opp), OPP_ES.get(opp, opp))
                    form[c].append([res, gf, ga, opp_n, r["date"]])
    for c, rows in form.items():
        rows.sort(key=lambda x: x[4], reverse=True)
        out[c]["f"] = _dedupe_form(rows)[:n_form]
    return out


def _dedupe_form(rows: list[list]) -> list[list]:
    """Quita repeticiones del CSV (mismo rival y marcador en ≤2 días)."""
    kept: list[list] = []
    for r in rows:
        if any(k[3] == r[3] and k[1:3] == r[1:3]
               and abs((date.fromisoformat(k[4]) - date.fromisoformat(r[4])).days) <= 2
               for k in kept[-3:]):
            continue
        kept.append(r)
    return kept


def _elo_by_name() -> dict[str, int]:
    """ELO actual por nombre de selección (eloratings.net), desde las cachés."""
    codes = {}
    for line in ELO_NAMES.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            codes[cols[0]] = cols[1].strip()
    out = {}
    for line in elo_scraper.CACHE_PATH.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 4 and cols[3].isdigit() and cols[2] in codes:
            out[codes[cols[2]]] = int(cols[3])
    return out


def build_fixtures(bundle: list[dict], path: Path = FIXTURES) -> tuple[list[dict], list[dict]]:
    """Calendario de la próxima ventana + equipos "proxy" para rivales fuera de las 48.

    Un rival que no está en el modelo se estima desde su ELO con una recta
    ajustada sobre las 48 (fuerza, ataque y defensa vs ELO; R² ≈ 0.87 en la
    fuerza). Es una aproximación: se marca con px=1 para que la web lo diga.
    """
    to_code = {v: k for k, v in FIFA_TO_HISTORY.items()}
    elo = _elo_by_name()
    xs = [(r["e"], r) for r in bundle if r.get("e")]

    def fit(key: str) -> tuple[float, float]:
        n = len(xs)
        mx = sum(e for e, _ in xs) / n
        my = sum(r[key] for _, r in xs) / n
        b = sum((e - mx) * (r[key] - my) for e, r in xs) / sum((e - mx) ** 2 for e, _ in xs)
        return b, my - b * mx

    lines = {k: fit(k) for k in ("p", "a", "d")}
    clamp = {"p": (0.03, 0.99), "a": (0.35, 2.0), "d": (0.5, 2.6)}
    proxies: dict[str, dict] = {}

    def code_for(name: str) -> str | None:
        if name in to_code:
            return to_code[name]
        e = elo.get(ELO_ALIAS.get(name, name))
        if e is None:
            return None
        c = "~" + name
        if c not in proxies:
            row = {"c": c, "n": OPP_ES.get(name, name), "e": e, "r": 0.5, "px": 1}
            for k, (b, a0) in lines.items():
                lo, hi = clamp[k]
                row[k] = round(min(hi, max(lo, a0 + b * e)), 4)
            proxies[c] = row
        return c

    out = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            h, a = r["home_team"], r["away_team"]
            out.append({
                "dt": r["date"], "h": code_for(h), "a": code_for(a),
                "hn": NAME_ES.get(to_code.get(h), OPP_ES.get(h, h)),
                "an": NAME_ES.get(to_code.get(a), OPP_ES.get(a, a)),
                "t": TOURNAMENT_ES.get(r["tournament"], r["tournament"]),
                "nt": r["neutral"].upper() == "TRUE",
            })
    out.sort(key=lambda m: m["dt"])
    return out, list(proxies.values())


def build_bundle(path: Path = STRENGTHS, with_xg: bool = True) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    xg = {}
    if with_xg and XG.exists():
        xg = {r["fifa_code"]: r for r in json.loads(XG.read_text(encoding="utf-8"))
              if r["fifa_code"]}
    out = []
    for s in raw:
        c = s["fifa_code"]
        row = {
            "c": c,
            "n": NAME_ES.get(c, s["name"]),
            "g": s["group"],
            "p": round(s["posterior"], 4),
            "a": round(s["att"], 4),
            "d": round(s["defe"], 4),
            "r": round(s["resilience"], 4),
        }
        if c in xg:
            r = xg[c]
            row.update(xf=r["xg_for"], xa=r["xg_against"], xn=r["n_matches"],
                       xt=r["competitions"])
        out.append(row)
    return out


def _js(name: str, data: list[dict]) -> str:
    return f"const {name}=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"


def inject(html: str, name: str, data: list[dict]) -> str:
    pattern = re.compile(rf"^const {name}=.*;$", re.M)
    if not pattern.search(html):
        raise ValueError(f"index.html no tiene la línea `const {name}=...;`")
    return pattern.sub(lambda _: _js(name, data), html, count=1)


def main() -> None:
    bundle = build_bundle()
    extras = build_extras()
    for row in bundle:
        row.update(extras.get(row["c"], {}))
    pre = build_bundle(SNAPSHOT, with_xg=False)
    OUT_JSON.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    html = INDEX.read_text(encoding="utf-8")
    html = inject(inject(html, "TEAMS", bundle), "TEAMS_PRE", pre)
    window = build_window()
    html = inject(inject(html, "TEAMS_WIN", build_bundle(WINDOW_SNAPSHOT, with_xg=False)),
                  "WINDOW", window)
    fixtures, proxies = build_fixtures(bundle)
    html = inject(inject(html, "NEXT", fixtures), "TEAMS_PROXY", proxies)
    clubs = {}
    for code in LEAGUES:
        path = CLUBS_DIR / f"clubs_{code}.json"
        if path.exists():
            lg = json.loads(path.read_text(encoding="utf-8"))
            lg.pop("calendar", None)        # la web solo muestra los próximos 7 días
            clubs[code] = lg
    html = re.sub(r"^const CLUBS=.*;$", lambda _: "const CLUBS=" + json.dumps(
        clubs, ensure_ascii=False, separators=(",", ":")) + ";", html, count=1, flags=re.M)
    INDEX.write_text(html, encoding="utf-8")
    n_xg = sum(1 for b in bundle if "xf" in b)
    print(f"✅ {len(bundle)} equipos ({n_xg} con xG StatsBomb), {len(window)} partidos "
          f"de la ventana, {len(fixtures)} próximos ({len(proxies)} rivales estimados por ELO) "
          f"-> {OUT_JSON} y {INDEX}")


if __name__ == "__main__":
    main()
