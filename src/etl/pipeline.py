"""Pipeline ETL: Extract -> Transform -> Load.

EXTRACT   lee data/raw/teams_2026.csv (datos crudos, intocables)
TRANSFORM valida cada fila con Pydantic y calcula prior/likelihood/posterior
LOAD      escribe data/processed/strengths_2026.json (lo que consume el simulador)

Ejecutar:  python -m src.etl.pipeline
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from src.etl.form import compute_dynamic_form
from src.etl.models import Team, TeamStrength
from src.etl.resilience import compute_all as compute_resilience_all
from src.etl.scrapers.elo import get_elo_for_fifa_codes

RAW_PATH = Path("data/raw/teams_2026.csv")
PROCESSED_PATH = Path("data/processed/strengths_2026.json")
XG_PATH = Path("data/processed/xg_statsbomb.json")

# Peso del xG de StatsBomb frente al xG curado del CSV: n_eff / (n_eff + SB_SHRINK).
# n_eff es la suma de pesos de recencia (Euro/Copa 2024 ~0.35 por partido), así
# que un equipo con Mundial 2022 + Euro 2024 completos (~3) queda en ~60% StatsBomb.
SB_SHRINK = 2.0

# Sigmoide del ELO: centro 1750 (mediana de selecciones mundialistas), escala 100.
# 1750 -> 0.5, 1850 -> 0.73, 1950 -> 0.88, 2050 -> 0.96, 2150 -> 0.98.
# 1650 -> 0.27, 1550 -> 0.12, 1450 -> 0.04.
ELO_CENTER = 1750.0
ELO_SCALE = 100.0

# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------

def extract(path: Path = RAW_PATH) -> pd.DataFrame:
    """Lee el CSV crudo. No transforma nada: solo trae los datos tal cual."""
    if not path.exists():
        raise FileNotFoundError(f"No existe el dataset crudo: {path}")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------------------------

def validate_rows(df: pd.DataFrame) -> list[Team]:
    """Cada fila del CSV pasa por el contrato Pydantic `Team`.

    Si UNA fila está corrupta, el pipeline falla aquí con un mensaje claro
    (fail fast) en lugar de contaminar la simulación.
    """
    teams: list[Team] = []
    errors: list[str] = []
    for i, row in df.iterrows():
        try:
            teams.append(Team(**row.to_dict()))
        except Exception as exc:  # noqa: BLE001 - queremos reportar todo
            errors.append(f"Fila {i} ({row.get('name', '?')}): {exc}")
    if errors:
        raise ValueError("Datos crudos inválidos:\n" + "\n".join(errors))
    return teams


def compute_prior(team: Team) -> float:
    """PRIOR (historia, peso 20%): qué tan grande es el equipo *históricamente*.

    Tres componentes:
    - ELO actual (eloratings.net): mejor predictor histórico, sigmoide
      centrada en 1750 (mediana mundialista).
    - ranking FIFA: respaldo si no hay ELO; decae exponencialmente.
    - historia mundialista: títulos, participaciones, mejor resultado.

    Cuando hay ELO disponible, gana el ELO (peso 0.55) sobre el rank FIFA
    (peso 0.0 — queda solo para mostrar). Sin ELO, cae al modelo viejo.
    """
    history_score = min(
        1.0,
        team.wc_titles * 0.16          # cada título pesa fuerte
        + team.wc_appearances * 0.015  # experiencia mundialista
        + team.best_finish * 0.30,     # qué tan lejos llegó alguna vez
    )

    if team.elo_rating is not None:
        elo_score = 1.0 / (1.0 + math.exp(-(team.elo_rating - ELO_CENTER) / ELO_SCALE))
        return round(0.55 * elo_score + 0.45 * history_score, 4)

    # Fallback: rank FIFA si no se pudo scrapear el ELO.
    rank_score = math.exp(-(team.fifa_rank - 1) / 35.0)
    return round(0.55 * rank_score + 0.45 * history_score, 4)


def compute_likelihood(team: Team) -> float:
    """LIKELIHOOD (actualidad, peso 50%): qué tan bien llega el equipo HOY.

    - forma: puntos de los últimos 10 partidos (W=3, D=1, L=0) / 30
    - xG: diferencia esperada de goles pasada por una sigmoide.
    - valor de plantilla (Transfermarkt): proxy de calidad individual,
      en escala log (€2bn no vale el doble que €1bn para ganar partidos).

    Si hay valor de plantilla: forma 0.40 + xG 0.30 + valor 0.30.
    Si no: forma 0.55 + xG 0.45 (modelo viejo).
    """
    pts = sum({"W": 3, "D": 1, "L": 0}[r] for r in team.form_last10)
    form_score = pts / 30.0
    xg_diff = team.xg_for - team.xg_against
    xg_score = 1.0 / (1.0 + math.exp(-2.2 * xg_diff))  # sigmoide centrada en 0

    if team.squad_value_meur is not None and team.squad_value_meur > 0:
        # log10(valor M€): €30M -> 1.48, €300M -> 2.48, €1300M -> 3.11.
        # sigmoide centrada en log10(250)=2.40 (plantilla "mundialista media").
        log_val = math.log10(team.squad_value_meur)
        value_score = 1.0 / (1.0 + math.exp(-2.0 * (log_val - 2.40)))
        return round(0.40 * form_score + 0.30 * xg_score + 0.30 * value_score, 4)

    return round(0.55 * form_score + 0.45 * xg_score, 4)


def compute_posterior(prior: float, likelihood: float) -> float:
    """POSTERIOR (70% del modelo): combinación ponderada y renormalizada.

    Pesos absolutos del proyecto: prior=0.20, likelihood=0.50.
    Dentro del bloque "base estadística" eso equivale a 2/7 y 5/7.
    """
    return round((0.20 * prior + 0.50 * likelihood) / 0.70, 4)


def transform(teams: list[Team]) -> list[TeamStrength]:
    """Calcula prior/likelihood/posterior y los perfiles ataque/defensa.

    ATAQUE y DEFENSA (modelo de Maher 1982, base de Dixon-Coles):
      att = xg_for / promedio(xg_for)        -> 1.0 = ataque promedio del torneo
      defe = xg_against / promedio(xg_against) -> >1.0 = defensa más permeable

    El posterior sigue gobernando la *clase* general del equipo (historia +
    actualidad); att/defe definen el *perfil*: cómo convierte esa clase en
    goles a favor y en contra.
    """
    avg_xgf = sum(t.xg_for for t in teams) / len(teams)
    avg_xga = sum(t.xg_against for t in teams) / len(teams)

    # att/defe BASE del CSV (xG historico, escala torneo). Sirven de prior
    # para el shrinkage de la forma dinamica.
    csv_att = {t.fifa_code: round(t.xg_for / avg_xgf, 4) for t in teams}
    csv_defe = {t.fifa_code: round(t.xg_against / avg_xga, 4) for t in teams}

    codes = [t.fifa_code for t in teams]

    # Resiliencia: scalar por equipo desde historial real (martj42 dataset).
    # Si falla por red, todos quedan en 0.5 (neutro) y no rompe el pipeline.
    try:
        resilience_map = {fifa: rb.score for fifa, rb in
                          compute_resilience_all(codes).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Resiliencia no disponible ({exc}); usando 0.5 neutro para todos")
        resilience_map = {}

    # Att/Def DINAMICO (goles recientes ponderados). Sustituye al xG fijo.
    # Si falla por red, caemos al att/defe del CSV.
    try:
        forms = compute_dynamic_form(codes, csv_att, csv_defe)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Forma dinamica no disponible ({exc}); usando att/defe del CSV")
        forms = {}

    strengths = []
    for t in teams:
        p = compute_prior(t)
        lik = compute_likelihood(t)
        form = forms.get(t.fifa_code)
        att = form.att_dyn if form else csv_att[t.fifa_code]
        defe = form.defe_dyn if form else csv_defe[t.fifa_code]
        strengths.append(
            TeamStrength(
                fifa_code=t.fifa_code,
                name=t.name,
                group=t.group,
                prior=p,
                likelihood=lik,
                posterior=compute_posterior(p, lik),
                att=att,
                defe=defe,
                resilience=resilience_map.get(t.fifa_code, 0.5),
            )
        )
    return strengths


# ---------------------------------------------------------------------------
# LOAD
# ---------------------------------------------------------------------------

def load(strengths: list[TeamStrength], path: Path = PROCESSED_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [s.model_dump() for s in strengths]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def enrich_with_elo(teams: list[Team]) -> list[Team]:
    """Inyecta `elo_rating` desde eloratings.net en cada Team.

    Si el scraper falla (sin red), continúa con elo=None y el prior
    cae al modelo viejo basado en rank FIFA. No rompe el pipeline.
    """
    codes = [t.fifa_code for t in teams]
    try:
        elos = get_elo_for_fifa_codes(codes)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  No se pudo obtener ELO ({exc}); usando fallback por rank FIFA")
        return teams
    enriched: list[Team] = []
    missing = 0
    for t in teams:
        elo = elos.get(t.fifa_code)
        if elo is None:
            missing += 1
        enriched.append(t.model_copy(update={"elo_rating": elo}))
    if missing:
        print(f"⚠️  {missing}/{len(teams)} equipos sin ELO (caen al fallback)")
    return enriched


def enrich_with_transfermarkt(teams: list[Team]) -> list[Team]:
    """Inyecta valor de plantilla y edad promedio (Transfermarkt).

    Lazy import: el scraper hace red. Si falla, los Team quedan sin estos
    campos y el likelihood cae al modelo viejo (forma + xG). No rompe.
    """
    from src.etl.scrapers.transfermarkt import get_transfermarkt_data
    codes = [t.fifa_code for t in teams]
    try:
        tm = get_transfermarkt_data(codes)
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Transfermarkt no disponible ({exc}); likelihood sin valor de plantilla")
        return teams
    enriched: list[Team] = []
    missing = 0
    for t in teams:
        d = tm.get(t.fifa_code)
        if not d or d.squad_value_meur is None:
            missing += 1
            enriched.append(t)
            continue
        enriched.append(t.model_copy(update={
            "squad_value_meur": d.squad_value_meur,
            "avg_age": d.avg_age,
        }))
    if missing:
        print(f"⚠️  {missing}/{len(teams)} equipos sin valor de plantilla")
    return enriched


def enrich_with_statsbomb(teams: list[Team], xg_path: Path = XG_PATH) -> list[Team]:
    """Reemplaza (en parte) el xG curado del CSV por xG real de StatsBomb.

    Ajusta ratings por rival sobre los torneos de selecciones del open data y
    mezcla cada equipo con su valor del CSV según cuánta muestra reciente tiene.
    El xG de StatsBomb se reescala a la media del CSV para no mover la escala
    que usan el likelihood y att/defe. Sin red usa la caché; sin caché, CSV.
    """
    from src.etl.scrapers.statsbomb import load_team_matches
    from src.etl.xg_ratings import fit_ratings

    try:
        rows = load_team_matches()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  StatsBomb sin red ({exc}); usando solo la caché")
        try:
            rows = load_team_matches(offline=True)
        except Exception:  # noqa: BLE001
            rows = []
    ratings = fit_ratings(rows)
    if not ratings:
        print("⚠️  Sin datos de StatsBomb; xG del CSV")
        return teams

    xg_path.parent.mkdir(parents=True, exist_ok=True)
    xg_path.write_text(json.dumps(
        sorted((r.to_dict() for r in ratings.values()), key=lambda r: r["team"]),
        indent=1, ensure_ascii=False), encoding="utf-8")

    by_code = {r.fifa_code: r for r in ratings.values() if r.fifa_code}
    matched = [t for t in teams if t.fifa_code in by_code]
    if not matched:
        return teams
    scale_f = (sum(t.xg_for for t in matched)
               / sum(by_code[t.fifa_code].xg_for for t in matched))
    scale_a = (sum(t.xg_against for t in matched)
               / sum(by_code[t.fifa_code].xg_against for t in matched))

    enriched: list[Team] = []
    for t in teams:
        r = by_code.get(t.fifa_code)
        if r is None:
            enriched.append(t)
            continue
        w = r.n_eff / (r.n_eff + SB_SHRINK)
        enriched.append(t.model_copy(update={
            "xg_for": round(w * r.xg_for * scale_f + (1 - w) * t.xg_for, 3),
            "xg_against": round(w * r.xg_against * scale_a + (1 - w) * t.xg_against, 3),
        }))
    print(f"📊 StatsBomb: {len(rows) // 2} partidos, xG real para "
          f"{len(matched)}/{len(teams)} equipos")
    return enriched


def run_pipeline() -> list[TeamStrength]:
    """Orquesta E -> T -> L y retorna las fuerzas calculadas."""
    df = extract()
    teams = validate_rows(df)
    teams = enrich_with_elo(teams)
    teams = enrich_with_transfermarkt(teams)
    teams = enrich_with_statsbomb(teams)
    strengths = transform(teams)
    out = load(strengths)
    print(f"✅ ETL completo: {len(strengths)} equipos -> {out}")
    return strengths


if __name__ == "__main__":
    run_pipeline()
