"""Backtest del modelo contra los 104 partidos reales del Mundial 2026.

Qué se evalúa:
  - Fase de grupos (72): probabilidades 1X2 del resultado a 90'.
  - Eliminatorias (32): P(clasifica el equipo listado como local), integrando
    prórroga y penales igual que simulate_match(). martj42 registra el marcador
    tras la prórroga, así que en eliminatorias no se puede evaluar el 1X2 a 90'.

Contra qué se compara:
  - ELO pre-torneo (reconstruido al 10-jun, ver src/evaluation/elo.py).
  - Uniforme (1/3 por resultado, 1/2 por clasificado): el piso de "no sé nada".

Fuga de datos: el modelo usa el snapshot del ETL del 15-jun y BASE/K se
ajustaron mirando partidos hasta el 17-jun. Los partidos posteriores a
LEAK_CUTOFF son la evaluación fuera de muestra limpia; el resto se reporta
aparte.

Ejecutar:  python -m src.cli backtest [--refit]
"""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.betting.odds import joint_matrix
from src.etl.models import TeamStrength
from src.evaluation.elo import elo_1x2, expected_score, rating_diff
from src.simulation.match_engine import (
    BASE,
    EXTRA_TIME_FACTOR,
    RHO,
    K,
    expected_goals_pair,
    penalty_win_probability,
)
from src.simulation.tournament import HOST_BONUS, HOSTS

STRENGTHS_SNAPSHOT = Path("data/snapshots/strengths_2026-06-15.json")
ELO_SNAPSHOT = Path("data/snapshots/elo_pre_2026-06-11.json")
RESULTS = Path("data/raw/wc2026_results.csv")
REPORT_OUT = Path("data/processed/backtest_2026.json")

LEAK_CUTOFF = date(2026, 6, 17)
BOOTSTRAP_SAMPLES = 5000
BOOTSTRAP_SEED = 2026

K_GRID = [round(0.4 + 0.1 * i, 2) for i in range(17)]        # 0.4 .. 2.0
BASE_GRID = [round(1.0 + 0.05 * i, 2) for i in range(17)]    # 1.0 .. 1.8
RHO_GRID = [round(-0.40 + 0.05 * i, 2) for i in range(11)]   # -0.40 .. 0.10


@dataclass(frozen=True)
class Params:
    k: float = K
    base: float = BASE
    rho: float = RHO


@dataclass(frozen=True)
class RealMatch:
    date: date
    round: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    neutral: bool
    shootout_winner: str

    @property
    def is_group(self) -> bool:
        return self.round == "GROUP"

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "1"
        return "X" if self.home_goals == self.away_goals else "2"

    @property
    def home_advanced(self) -> bool:
        if self.home_goals != self.away_goals:
            return self.home_goals > self.away_goals
        return self.shootout_winner == self.home


# ─── Métricas ────────────────────────────────────────────────────────

OUTCOMES = ("1", "X", "2")


def brier_3way(p: tuple[float, float, float], outcome: str) -> float:
    """Σ (p_i − y_i)² sobre 1/X/2. 0 = perfecto, 2 = peor caso, 0.667 = uniforme."""
    return sum((pi - (1.0 if o == outcome else 0.0)) ** 2 for pi, o in zip(p, OUTCOMES))


def rps_3way(p: tuple[float, float, float], outcome: str) -> float:
    """Ranked Probability Score: como Brier pero respeta el orden 1 < X < 2.

    Predecir empate cuando gana el local se castiga menos que predecir la
    victoria visitante. Es la métrica estándar para resultados de fútbol.
    """
    y = [1.0 if o == outcome else 0.0 for o in OUTCOMES]
    c1 = p[0] - y[0]
    c2 = (p[0] + p[1]) - (y[0] + y[1])
    return 0.5 * (c1 ** 2 + c2 ** 2)


def brier_binary(p: float, happened: bool) -> float:
    return (p - (1.0 if happened else 0.0)) ** 2


def log_loss(p_of_what_happened: float) -> float:
    return -math.log(max(p_of_what_happened, 1e-12))


# ─── Predictores ─────────────────────────────────────────────────────

def host_context(code: str) -> float:
    """Contexto que usa el torneo simulado: neutro + bonus de anfitrión."""
    return min(1.0, 0.5 + HOST_BONUS) if code in HOSTS else 0.5


def _one_x_two(grid: list[list[float]]) -> tuple[float, float, float]:
    n = len(grid)
    p1 = sum(grid[x][y] for x in range(n) for y in range(x))
    px = sum(grid[x][x] for x in range(n))
    return p1, px, 1.0 - p1 - px


def model_lambdas(h: TeamStrength, a: TeamStrength, params: Params) -> tuple[float, float]:
    return expected_goals_pair(h, a, host_context(h.fifa_code), host_context(a.fifa_code),
                               k=params.k, base=params.base)


def model_1x2(h: TeamStrength, a: TeamStrength, params: Params) -> tuple[float, float, float]:
    lam_h, lam_a = model_lambdas(h, a, params)
    return _one_x_two(joint_matrix(lam_h, lam_a, params.rho))


def model_advance(h: TeamStrength, a: TeamStrength, params: Params) -> float:
    """P(clasifica h): gana en 90' + empata y gana prórroga o penales."""
    p1, px, _ = model_1x2(h, a, params)
    lam_h, lam_a = model_lambdas(h, a, params)
    et_home, et_draw, _ = _one_x_two(
        joint_matrix(lam_h * EXTRA_TIME_FACTOR, lam_a * EXTRA_TIME_FACTOR, rho=0.0))
    pen = penalty_win_probability(h.final_strength(host_context(h.fifa_code)),
                                  a.final_strength(host_context(a.fifa_code)))
    return p1 + px * (et_home + et_draw * pen)


def elo_we(elo: dict, m: RealMatch) -> float:
    r = elo["ratings"]
    return expected_score(rating_diff(r[m.home], r[m.away], m.neutral))


# ─── Carga ───────────────────────────────────────────────────────────

def load_matches(path: Path = RESULTS) -> list[RealMatch]:
    with path.open(encoding="utf-8") as f:
        return [RealMatch(
            date=date.fromisoformat(r["date"]), round=r["round"],
            home=r["home"], away=r["away"],
            home_goals=int(r["home_score"]), away_goals=int(r["away_score"]),
            neutral=r["neutral"] == "TRUE", shootout_winner=r["shootout_winner"],
        ) for r in csv.DictReader(f)]


def load_strengths(path: Path = STRENGTHS_SNAPSHOT) -> dict[str, TeamStrength]:
    return {r["fifa_code"]: TeamStrength(**r)
            for r in json.loads(path.read_text(encoding="utf-8"))}


def load_elo(path: Path = ELO_SNAPSHOT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ─── Evaluación ──────────────────────────────────────────────────────

def score_matches(matches: list[RealMatch], strengths: dict[str, TeamStrength],
                  elo: dict, params: Params) -> list[dict]:
    """Una fila por partido con las predicciones y pérdidas de cada predictor."""
    rows = []
    for m in matches:
        h, a = strengths[m.home], strengths[m.away]
        we = elo_we(elo, m)
        row = {"date": m.date.isoformat(), "round": m.round, "home": m.home,
               "away": m.away, "score": f"{m.home_goals}-{m.away_goals}",
               "after_cutoff": m.date > LEAK_CUTOFF}
        if m.is_group:
            idx = OUTCOMES.index(m.outcome)
            preds = {"modelo": model_1x2(h, a, params),
                     "elo": elo_1x2(we, elo["draw_c"]),
                     "uniforme": (1 / 3, 1 / 3, 1 / 3)}
            row["outcome"] = m.outcome
            lam_h, lam_a = model_lambdas(h, a, params)
            grid = joint_matrix(lam_h, lam_a, params.rho)
            row["exp_goals"] = sum((x + y) * grid[x][y]
                                   for x in range(len(grid)) for y in range(len(grid)))
            row["goals"] = m.home_goals + m.away_goals
            for name, p in preds.items():
                row[name] = {"p": [round(v, 4) for v in p],
                             "brier": brier_3way(p, m.outcome),
                             "rps": rps_3way(p, m.outcome),
                             "logloss": log_loss(p[idx]),
                             "hit": max(range(3), key=lambda i: p[i]) == idx}
        else:
            adv_preds = {"modelo": model_advance(h, a, params), "elo": we, "uniforme": 0.5}
            adv = m.home_advanced
            row["advanced"] = m.home if adv else m.away
            for name, q in adv_preds.items():
                row[name] = {"p": round(q, 4),
                             "brier": brier_binary(q, adv),
                             "logloss": log_loss(q if adv else 1.0 - q),
                             "hit": (q > 0.5) == adv}
        rows.append(row)
    return rows


def paired_bootstrap(diffs: list[float], n: int = BOOTSTRAP_SAMPLES,
                     seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """Media e IC 95% de la diferencia por partido, remuestreando partidos."""
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(n))
    return sum(diffs) / len(diffs), means[int(0.025 * n)], means[int(0.975 * n) - 1]


def summarize(rows: list[dict], metrics: tuple[str, ...]) -> dict:
    out: dict[str, Any] = {}
    for name in ("modelo", "elo", "uniforme"):
        out[name] = {mt: sum(r[name][mt] for r in rows) / len(rows) for mt in metrics}
        out[name]["acierto"] = sum(r[name]["hit"] for r in rows) / len(rows)
    diff = [r["modelo"]["brier"] - r["elo"]["brier"] for r in rows]
    mean, lo, hi = paired_bootstrap(diff)
    out["modelo_menos_elo_brier"] = {"media": mean, "ic95": [lo, hi]}
    out["n"] = len(rows)
    return out


def reliability(rows: list[dict]) -> list[dict]:
    """Calibración 1X2 del modelo en grupos: agrupa las 3 probabilidades de
    cada partido por tramo y compara lo predicho con la frecuencia observada."""
    edges = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0001]
    pairs = [(p, 1.0 if o == r["outcome"] else 0.0)
             for r in rows for p, o in zip(r["modelo"]["p"], OUTCOMES)]
    table = []
    for lo, hi in zip(edges, edges[1:]):
        b = [(p, y) for p, y in pairs if lo <= p < hi]
        if b:
            table.append({"tramo": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(b),
                          "predicho": sum(p for p, _ in b) / len(b),
                          "observado": sum(y for _, y in b) / len(b)})
    return table


def dixon_coles_valid(lam: float, mu: float, rho: float) -> bool:
    """τ ≥ 0 en las 4 celdas corregidas; fuera de este rango DC no es una distribución."""
    return 1.0 + lam * rho >= 0 and 1.0 + mu * rho >= 0 and 1.0 - lam * mu * rho >= 0 \
        and 1.0 - rho >= 0


def refit_params(matches: list[RealMatch], strengths: dict[str, TeamStrength]) -> Params:
    """(K, BASE, ρ) que maximizan la verosimilitud del marcador exacto."""
    group = [m for m in matches if m.is_group]
    best, best_ll = Params(), -math.inf
    for k in K_GRID:
        for base in BASE_GRID:
            lams = [model_lambdas(strengths[m.home], strengths[m.away], Params(k, base))
                    for m in group]
            for rho in RHO_GRID:
                if not all(dixon_coles_valid(lh, la, rho) for lh, la in lams):
                    continue
                ll = 0.0
                for m, (lh, la) in zip(group, lams):
                    grid = joint_matrix(lh, la, rho)
                    n = len(grid) - 1
                    ll += math.log(max(grid[min(m.home_goals, n)][min(m.away_goals, n)], 1e-12))
                if ll > best_ll:
                    best, best_ll = Params(k, base, rho), ll
    return best


def run(refit: bool = False) -> dict:
    matches = load_matches()
    strengths = load_strengths()
    elo = load_elo()
    params = Params()
    rows = score_matches(matches, strengths, elo, params)
    group = [r for r in rows if r["round"] == "GROUP"]
    ko = [r for r in rows if r["round"] != "GROUP"]
    report = {
        "params": asdict(params),
        "leak_cutoff": LEAK_CUTOFF.isoformat(),
        "grupos": summarize(group, ("brier", "rps", "logloss")),
        "grupos_fuera_de_muestra": summarize([r for r in group if r["after_cutoff"]],
                                             ("brier", "rps", "logloss")),
        "eliminatorias": summarize(ko, ("brier", "logloss")),
        "calibracion_1x2": reliability(group),
        "goles_por_partido": {"predicho": sum(r["exp_goals"] for r in group) / len(group),
                              "real": sum(r["goals"] for r in group) / len(group)},
        "empates": {"predicho": sum(r["modelo"]["p"][1] for r in group) / len(group),
                    "real": sum(r["outcome"] == "X" for r in group) / len(group)},
        "partidos": rows,
    }
    if refit:
        fitted = refit_params(matches, strengths)
        ko_fit = [r for r in score_matches(matches, strengths, elo, fitted)
                  if r["round"] != "GROUP"]
        diff = [f["modelo"]["brier"] - c["modelo"]["brier"] for f, c in zip(ko_fit, ko)]
        mean, lo, hi = paired_bootstrap(diff)
        report["reajuste"] = {
            "params": asdict(fitted),
            "eliminatorias": summarize(ko_fit, ("brier", "logloss")),
            "reajustado_menos_actual_brier_ko": {"media": mean, "ic95": [lo, hi]},
        }
    return report


# ─── Salida ──────────────────────────────────────────────────────────

def _metrics_table(title: str, s: dict, metrics: tuple[str, ...]) -> None:
    print(f"\n{title}  (n={s['n']})")
    print(f"  {'':<10}" + "".join(f"{m:>10}" for m in metrics) + f"{'acierto':>10}")
    for name in ("modelo", "elo", "uniforme"):
        print(f"  {name:<10}" + "".join(f"{s[name][m]:>10.4f}" for m in metrics)
              + f"{s[name]['acierto']:>10.1%}")
    d = s["modelo_menos_elo_brier"]
    verdict = ("modelo mejor" if d["ic95"][1] < 0 else
               "ELO mejor" if d["ic95"][0] > 0 else "sin diferencia significativa")
    print(f"  Brier modelo − ELO: {d['media']:+.4f}  IC95% [{d['ic95'][0]:+.4f}, "
          f"{d['ic95'][1]:+.4f}]  → {verdict}")


def print_report(rep: dict) -> None:
    p = rep["params"]
    print("=" * 66)
    print("  BACKTEST — Mundial 2026 (snapshot del modelo al 15-jun)")
    print(f"  K={p['k']}  BASE={p['base']}  ρ={p['rho']}   (menor = mejor en todas las métricas)")
    print("=" * 66)
    _metrics_table("FASE DE GRUPOS — 1X2 a 90'", rep["grupos"], ("brier", "rps", "logloss"))
    _metrics_table(f"GRUPOS FUERA DE MUESTRA — después del {rep['leak_cutoff']}",
                   rep["grupos_fuera_de_muestra"], ("brier", "rps", "logloss"))
    _metrics_table("ELIMINATORIAS — ¿quién clasifica?", rep["eliminatorias"],
                   ("brier", "logloss"))

    print("\nCALIBRACIÓN 1X2 (grupos): cuando el modelo dice p, ¿pasa con frecuencia p?")
    for b in rep["calibracion_1x2"]:
        print(f"  {b['tramo']}  n={b['n']:>3}   predicho {b['predicho']:5.1%}"
              f"   observado {b['observado']:5.1%}")
    g, e = rep["goles_por_partido"], rep["empates"]
    print(f"\n  Goles/partido: predicho {g['predicho']:.2f}  real {g['real']:.2f}")
    print(f"  Empates:       predicho {e['predicho']:.1%}  real {e['real']:.1%}")

    if "reajuste" in rep:
        r = rep["reajuste"]
        fp = r["params"]
        print(f"\nREAJUSTE en grupos (marcador exacto) → K={fp['k']}  BASE={fp['base']}"
              f"  ρ={fp['rho']}")
        _metrics_table("  Eliminatorias con parámetros reajustados", r["eliminatorias"],
                       ("brier", "logloss"))
        d = r["reajustado_menos_actual_brier_ko"]
        print(f"  Brier KO reajustado − actual: {d['media']:+.4f}  IC95% "
              f"[{d['ic95'][0]:+.4f}, {d['ic95'][1]:+.4f}]")


def main(refit: bool = False) -> dict:
    rep = run(refit=refit)
    print_report(rep)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Detalle por partido -> {REPORT_OUT}")
    return rep


if __name__ == "__main__":
    main()
