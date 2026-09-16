"""Exporta strengths_2026.json al bundle JS que consume app/index.html.

Mantiene el frontend SINCRONIZADO con el modelo: tras cada cambio (nuevos
datos, recalibracion de K), correr este script regenera la data embebida.

Genera dos artefactos:
  - data/processed/frontend_teams.json  (consumible por fetch o copy-paste)
  - imprime el bloque `const TEAMS=[...]` listo para pegar en index.html

Campos exportados por equipo: c (code), n (nombre ES), g (grupo),
p (posterior), a (att), d (defe), r (resilience).
"""
from __future__ import annotations

import json
from pathlib import Path

STRENGTHS = Path("data/processed/strengths_2026.json")
OUT_JSON = Path("data/processed/frontend_teams.json")

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


def build_bundle() -> list[dict]:
    raw = json.loads(STRENGTHS.read_text(encoding="utf-8"))
    out = []
    for s in raw:
        c = s["fifa_code"]
        out.append({
            "c": c,
            "n": NAME_ES.get(c, s["name"]),
            "g": s["group"],
            "p": round(s["posterior"], 4),
            "a": round(s["att"], 4),
            "d": round(s["defe"], 4),
            "r": round(s["resilience"], 4),
        })
    return out


def main() -> None:
    bundle = build_bundle()
    OUT_JSON.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    js = "const TEAMS=" + json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + ";"
    print(f"✅ {len(bundle)} equipos -> {OUT_JSON}")
    print("\n--- Bloque JS (pegar en index.html, reemplaza const TEAMS=...) ---\n")
    print(js)


if __name__ == "__main__":
    main()
