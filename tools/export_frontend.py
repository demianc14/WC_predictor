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

from src.etl.scrapers.history import FIFA_TO_HISTORY

STRENGTHS = Path("data/processed/strengths_2026.json")
SNAPSHOT = Path("data/snapshots/strengths_2026-06-15.json")
# Fuerzas al cierre de la ventana anterior: punto de partida de la actual.
WINDOW_SNAPSHOT = Path("data/snapshots/strengths_2026-09-22.json")
WINDOW_FROM = "2026-09-22"
RESULTS = Path("data/cache/history/results.csv")
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
    pre = build_bundle(SNAPSHOT, with_xg=False)
    OUT_JSON.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    html = INDEX.read_text(encoding="utf-8")
    html = inject(inject(html, "TEAMS", bundle), "TEAMS_PRE", pre)
    window = build_window()
    html = inject(inject(html, "TEAMS_WIN", build_bundle(WINDOW_SNAPSHOT, with_xg=False)),
                  "WINDOW", window)
    INDEX.write_text(html, encoding="utf-8")
    n_xg = sum(1 for b in bundle if "xf" in b)
    print(f"✅ {len(bundle)} equipos ({n_xg} con xG StatsBomb), {len(window)} partidos "
          f"de la ventana -> {OUT_JSON} y {INDEX}")


if __name__ == "__main__":
    main()
