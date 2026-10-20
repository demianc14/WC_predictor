"""Att/Def DINAMICO desde goles recientes (sustituto del xG fijo del CSV).

FBref bloquea scraping de xG de selecciones (Cloudflare) y el xG nacional
no esta disponible publico de forma limpia. En su lugar derivamos el perfil
ofensivo/defensivo actual desde los goles reales de los ultimos N partidos
del dataset martj42, con tres correcciones:

  1. PONDERACION POR RECENCIA: cada partido pesa exp(-edad_dias / TAU).
     Lo de hace 2 meses pesa mas que lo de hace 2 anios.

  2. AJUSTE POR CALIDAD DEL RIVAL: golear a un debil informa menos que golear
     a un grande. Cada gol se ajusta dividiendo por la "facilidad" esperada
     del rival (defensas fuertes -> tus goles valen mas; ataques fuertes ->
     los goles que recibes pesan menos como sintoma).
     Aproximamos la calidad del rival por su ELO (que ya tenemos).

  3. SHRINKAGE HACIA EL CSV: con pocos partidos recientes, el att/def dinamico
     se mezcla con el valor "historico" del CSV para no sobre-reaccionar a una
     muestra chica. Peso del dinamico = n_eff / (n_eff + SHRINK_GAMES).

La salida son multiplicadores att/def en la MISMA escala que el pipeline
viejo (1.0 = promedio del torneo), para que el match engine no cambie.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.etl.scrapers.elo import FIFA_TO_ELO, fetch_world_tsv, parse_world_tsv
from src.etl.scrapers.history import FIFA_TO_HISTORY, load_results

LOOKBACK_DAYS = 730          # 2 anios de partidos elegibles
RECENCY_TAU = 300.0          # vida media ~300 dias en el peso de recencia
MAX_MATCHES = 15             # tope de partidos considerados (los mas recientes)
SHRINK_GAMES = 12.0          # equivalente en "partidos" del prior del CSV.
                             # peso dinamico ~35% con n_eff tipico ~7. NO optimizado
                             # contra el set de upsets (que premia ignorar la forma);
                             # es un punto medio: capta actualidad sin sobre-reaccionar
                             # a amistosos ruidosos. Ver nota en docs sobre validacion.
GOALS_CAP = 5                # cap de goles por partido (evita que un 7-0 distorsione)

# El ajuste por rival usa el ELO. Normalizamos: rival con ELO medio (1750)
# => factor 1.0. Rival fuerte (mas defensa) => tus goles valen mas.
ELO_REF = 1750.0
ELO_OPP_SCALE = 350.0        # cuanto modula el ELO del rival (suave)


@dataclass
class DynamicForm:
    fifa_code: str
    att_dyn: float          # multiplicador ofensivo dinamico (escala torneo)
    defe_dyn: float         # multiplicador defensivo dinamico (escala torneo)
    n_matches: int          # partidos usados
    n_eff: float            # peso efectivo (suma de pesos de recencia)
    shrink_weight: float    # cuanto pesa lo dinamico vs el CSV [0,1]


def _elo_by_history_name() -> dict[str, int]:
    """{nombre_martj42: elo} para todos los equipos que podamos mapear."""
    elo_by_code = parse_world_tsv(fetch_world_tsv())
    elo_to_fifa = {v: k for k, v in FIFA_TO_ELO.items()}
    out: dict[str, int] = {}
    for elo_code, elo in elo_by_code.items():
        fifa = elo_to_fifa.get(elo_code)
        if fifa and fifa in FIFA_TO_HISTORY:
            out[FIFA_TO_HISTORY[fifa]] = elo
    return out


def _team_matches(history_name: str, results: list[dict], today: date) -> list[dict]:
    """Partidos del equipo en la ventana, mas recientes primero, tope MAX_MATCHES."""
    rows = []
    for r in results:
        is_home = r["home_team"] == history_name
        is_away = r["away_team"] == history_name
        if not (is_home or is_away):
            continue
        gf = r["home_score"] if is_home else r["away_score"]
        ga = r["away_score"] if is_home else r["home_score"]
        opponent = r["away_team"] if is_home else r["home_team"]
        rows.append({
            "date": r["_date"],
            "gf": min(gf, GOALS_CAP),
            "ga": min(ga, GOALS_CAP),
            "opponent": opponent,
            "age_days": (today - r["_date"]).days,
        })
    rows.sort(key=lambda m: m["date"], reverse=True)
    return rows[:MAX_MATCHES]


def compute_dynamic_form(
    fifa_codes: list[str],
    csv_att: dict[str, float],
    csv_defe: dict[str, float],
) -> dict[str, DynamicForm]:
    """Calcula att/def dinamico para cada fifa_code.

    csv_att / csv_defe: los multiplicadores que ya calcula el pipeline desde el
    xG fijo del CSV (sirven de prior para el shrinkage).
    """
    import math

    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    results = load_results(since=since)
    elo_map = _elo_by_history_name()

    # --- 1. recolectar goles ponderados por equipo ---
    raw: dict[str, dict] = {}
    for fifa in fifa_codes:
        hname = FIFA_TO_HISTORY.get(fifa)
        if not hname:
            continue
        matches = _team_matches(hname, results, today)
        w_sum = gf_w = ga_w = 0.0
        for m in matches:
            w = math.exp(-m["age_days"] / RECENCY_TAU)
            # ajuste por rival: rival fuerte (ELO alto) => sube el valor de tus
            # goles a favor y reduce el "castigo" de tus goles en contra.
            opp_elo = elo_map.get(m["opponent"], ELO_REF)
            opp_factor = 1.0 + (opp_elo - ELO_REF) / ELO_OPP_SCALE  # ~0.5..1.5
            gf_w += w * m["gf"] * opp_factor
            ga_w += w * m["ga"] / opp_factor
            w_sum += w
        raw[fifa] = {"gf_w": gf_w, "ga_w": ga_w, "w_sum": w_sum, "n": len(matches)}

    if not raw:
        return {}

    # --- 2. medias ponderadas crudas (goles/partido equivalente) ---
    for fifa, d in raw.items():
        d["gf_pg"] = d["gf_w"] / d["w_sum"] if d["w_sum"] else 0.0
        d["ga_pg"] = d["ga_w"] / d["w_sum"] if d["w_sum"] else 0.0

    # --- 3. normalizar a escala torneo (media de las 48 = 1.0) ---
    avg_gf = sum(d["gf_pg"] for d in raw.values()) / len(raw)
    avg_ga = sum(d["ga_pg"] for d in raw.values()) / len(raw)

    out: dict[str, DynamicForm] = {}
    for fifa, d in raw.items():
        att_norm = d["gf_pg"] / avg_gf if avg_gf else 1.0
        defe_norm = d["ga_pg"] / avg_ga if avg_ga else 1.0

        # --- 4. shrinkage hacia el CSV ---
        n_eff = d["w_sum"]  # peso efectivo de recencia (no el conteo crudo)
        sw = n_eff / (n_eff + SHRINK_GAMES)
        att_final = sw * att_norm + (1 - sw) * csv_att.get(fifa, 1.0)
        defe_final = sw * defe_norm + (1 - sw) * csv_defe.get(fifa, 1.0)

        out[fifa] = DynamicForm(
            fifa_code=fifa,
            att_dyn=round(att_final, 4),
            defe_dyn=round(defe_final, 4),
            n_matches=d["n"],
            n_eff=round(n_eff, 2),
            shrink_weight=round(sw, 3),
        )
    return out


if __name__ == "__main__":
    import json
    from pathlib import Path

    # cargar att/def del CSV ya procesado (strengths actual)
    strengths = json.loads(Path("data/processed/strengths_2026.json").read_text())
    csv_att = {s["fifa_code"]: s["att"] for s in strengths}
    csv_defe = {s["fifa_code"]: s["defe"] for s in strengths}
    codes = [s["fifa_code"] for s in strengths]

    forms = compute_dynamic_form(codes, csv_att, csv_defe)
    print(f"{'fifa':5s} {'att_csv':>7s} {'att_dyn':>7s}  {'def_csv':>7s} {'def_dyn':>7s}  "
          f"{'n':>2s} {'sw':>5s}")
    for fifa in sorted(forms, key=lambda c: -forms[c].att_dyn):
        f = forms[fifa]
        print(f"{fifa:5s} {csv_att[fifa]:7.2f} {f.att_dyn:7.2f}  "
              f"{csv_defe[fifa]:7.2f} {f.defe_dyn:7.2f}  {f.n_matches:2d} {f.shrink_weight:5.2f}")
