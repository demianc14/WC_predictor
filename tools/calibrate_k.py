"""Calibracion de K usando el set de validacion de 5 upsets reales.

Cada partido tiene dos modos:
  - NEUTRO: ctx=0.5/0.5, sin tocar nada -> mide la fuerza cruda del modelo.
  - CONTEXTO: ctx ajustado segun la descripcion del usuario (estadio, lesiones,
    DT, debut nerviosismo) -> mide cuanto ayuda inyectar el contexto.

Para cada K en el barrido y cada modo:
  - Calcula (lambda_h, lambda_a) con la K probada.
  - Saca P(1), P(X), P(2) analiticamente con Dixon-Coles.
  - Compara contra el resultado real con Brier score y log-loss.

Brier score (multiclase, una observacion):
  B = sum_{i in {1,X,2}} (p_i - y_i)^2
  Va de 0 (perfecto) a 2 (peor caso). Promediar entre partidos.

Log-loss:
  L = -log(p_actual)
  Penaliza fuerte cuando se predice ~0 a algo que pasa.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from src.betting.odds import compute_match_probabilities
from src.etl.models import TeamStrength
from src.simulation.match_engine import expected_goals_pair

STRENGTHS = Path("data/processed/strengths_2026.json")

# ─── Set de validacion ────────────────────────────────────────────────
# real = '1' (gana home), 'X' (empate), '2' (gana away)
# ctx_h, ctx_a en [0,1]: 0.5 = neutro. La asimetria refleja
# lo que el usuario describio (estadio, DT, lesiones, debut).
VAL_SET: list[dict[str, Any]] = [
    # ── UPSETS: favorito/lider-en-forma perdio o empato ───────────────
    {
        "label": "ESP 0-0 CPV  (debut Esp; Yamal lesionado; estadio 70-30 a favor CPV)",
        "home": "ESP", "away": "CPV", "real": "X", "kind": "upset",
        "score": "0-0",
        "ctx_h": 0.40,  # figura lesionada baja la confianza
        "ctx_a": 0.65,  # publico empujando
    },
    {
        "label": "CIV 1-0 ECU  (debut ECU con nervios; CIV local en grupo E)",
        "home": "CIV", "away": "ECU", "real": "1", "kind": "upset",
        "score": "1-0",
        "ctx_h": 0.55,
        "ctx_a": 0.40,  # debut + nervios
    },
    {
        "label": "AUS 2-0 TUR  (debut TUR; AUS con experiencia mundialista)",
        "home": "AUS", "away": "TUR", "real": "1", "kind": "upset",
        "score": "2-0",
        "ctx_h": 0.58,  # historial mundialista
        "ctx_a": 0.40,  # debut
    },
    {
        "label": "PAR 1-0 BRA  (eliminatoria Conmebol; Alfaro DT; BRA mal momento)",
        "home": "PAR", "away": "BRA", "real": "1", "kind": "upset",
        "score": "1-0",
        "ctx_h": 0.68,  # localia + Alfaro
        "ctx_a": 0.32,  # mal momento BRA
    },
    {
        "label": "QAT 1-1 SUI  (estadio lleno; SUI confiado no cerro)",
        "home": "QAT", "away": "SUI", "real": "X", "kind": "upset",
        "score": "1-1",
        "ctx_h": 0.65,
        "ctx_a": 0.42,  # exceso de confianza
    },
    # ── ESPERADOS: el favorito gano como tocaba ───────────────────────
    {
        "label": "MEX 2-0 RSA  (Mexico local, RSA por debajo)",
        "home": "MEX", "away": "RSA", "real": "1", "kind": "expected",
        "score": "2-0",
        "ctx_h": 0.60,  # localia
        "ctx_a": 0.45,
    },
    {
        "label": "HAI 0-1 SCO  (HAI muy por debajo; SCO ganaba como esperado)",
        "home": "HAI", "away": "SCO", "real": "2", "kind": "expected",
        "score": "0-1",
        "ctx_h": 0.45,
        "ctx_a": 0.55,
    },
    {
        "label": "GER 7-1 CUW  (Alemania elite; Curazao sin chances)",
        "home": "GER", "away": "CUW", "real": "1", "kind": "expected",
        "score": "7-1",
        "ctx_h": 0.60,
        "ctx_a": 0.40,
    },
    {
        "label": "SWE 5-1 TUN  (Suecia gran eliminatoria; Tunez por debajo)",
        "home": "SWE", "away": "TUN", "real": "1", "kind": "expected",
        "score": "5-1",
        "ctx_h": 0.60,
        "ctx_a": 0.45,
    },
]

K_SWEEP = [0.4, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.4, 1.6]


def load_strengths() -> dict[str, TeamStrength]:
    raw = json.loads(STRENGTHS.read_text(encoding="utf-8"))
    return {r["fifa_code"]: TeamStrength(**r) for r in raw}


def one_hot(real: str) -> tuple[float, float, float]:
    return {"1": (1.0, 0.0, 0.0), "X": (0.0, 1.0, 0.0), "2": (0.0, 0.0, 1.0)}[real]


def brier_3way(p1: float, px: float, p2: float, real: str) -> float:
    y1, yx, y2 = one_hot(real)
    return (p1 - y1) ** 2 + (px - yx) ** 2 + (p2 - y2) ** 2


def log_loss_3way(p1: float, px: float, p2: float, real: str) -> float:
    eps = 1e-12
    p = {"1": p1, "X": px, "2": p2}[real]
    return -math.log(max(p, eps))


def evaluate(k: float, ctx_mode: str, strengths: dict[str, TeamStrength]) -> dict:
    """Para una K y un modo de contexto, calcula metricas + breakdown por partido.

    Reporta metricas globales y desglosadas por 'kind' (upset/expected): un buen
    modelo debe bajar el error en AMBOS grupos. Si baja en upsets pero sube en
    expected, esta perdiendo discriminacion (aplanando de mas).
    """
    rows = []
    by_kind: dict[str, list[float]] = {"upset": [], "expected": []}
    briers, losses = [], []
    for m in VAL_SET:
        h, a = strengths[m["home"]], strengths[m["away"]]
        if ctx_mode == "neutral":
            cx_h, cx_a = 0.5, 0.5
        else:
            cx_h, cx_a = m["ctx_h"], m["ctx_a"]
        lam_h, lam_a = expected_goals_pair(h, a, cx_h, cx_a, k=k)
        p = compute_match_probabilities(lam_h, lam_a)
        b = brier_3way(p.p_home, p.p_draw, p.p_away, m["real"])
        ll = log_loss_3way(p.p_home, p.p_draw, p.p_away, m["real"])
        briers.append(b)
        losses.append(ll)
        by_kind[m["kind"]].append(ll)
        rows.append({
            "label": m["label"], "real": m["real"], "score": m["score"],
            "kind": m["kind"], "lam_h": lam_h, "lam_a": lam_a,
            "p1": p.p_home, "px": p.p_draw, "p2": p.p_away,
            "brier": b, "logloss": ll,
        })
    return {
        "k": k, "mode": ctx_mode,
        "avg_brier": sum(briers) / len(briers),
        "avg_logloss": sum(losses) / len(losses),
        "ll_upset": sum(by_kind["upset"]) / len(by_kind["upset"]),
        "ll_expected": sum(by_kind["expected"]) / len(by_kind["expected"]),
        "rows": rows,
    }


def fmt_pct(p: float) -> str:
    return f"{p*100:5.1f}%"


def print_table(results: list[dict]) -> None:
    print("\n  K      | Brier glob | LL global | LL upsets | LL esperados")
    print("  ───────┼────────────┼───────────┼───────────┼─────────────")
    for r in results:
        print(f"  {r['k']:.2f}   |   {r['avg_brier']:.4f}   |  {r['avg_logloss']:.4f}   |"
              f"  {r['ll_upset']:.4f}   |   {r['ll_expected']:.4f}")


def print_breakdown(result: dict) -> None:
    print(f"\n  Detalle para K={result['k']}, modo={result['mode']}:")
    for r in result["rows"]:
        actual_p = {"1": r["p1"], "X": r["px"], "2": r["p2"]}[r["real"]]
        print(f"    {r['label']}")
        print(f"      λ {r['lam_h']:.2f}-{r['lam_a']:.2f}   "
              f"1={fmt_pct(r['p1'])}  X={fmt_pct(r['px'])}  2={fmt_pct(r['p2'])}   "
              f"real={r['real']} ({fmt_pct(actual_p)})  "
              f"Brier={r['brier']:.3f}")


def main() -> None:
    strengths = load_strengths()
    print("=" * 78)
    print("  CALIBRACION K — set de 5 upsets (todos contra el favorito teorico)")
    print("=" * 78)

    print("\n── MODO NEUTRO (ctx=0.5/0.5; mide solo la fuerza del prior+likelihood) ──")
    neutral = [evaluate(k, "neutral", strengths) for k in K_SWEEP]
    print_table(neutral)

    print("\n── MODO CON CONTEXTO (estadio/DT/lesion/debut) ──")
    ctx = [evaluate(k, "context", strengths) for k in K_SWEEP]
    print_table(ctx)

    # mejor K segun log-loss en modo CONTEXTO (el que mejor refleja realidad)
    best_ctx = min(ctx, key=lambda r: r["avg_logloss"])
    best_neu = min(neutral, key=lambda r: r["avg_logloss"])
    print(f"\n  Mejor K (NEUTRO):    {best_neu['k']:.2f}   "
          f"(Brier {best_neu['avg_brier']:.3f}, LogLoss {best_neu['avg_logloss']:.3f})")
    print(f"  Mejor K (CONTEXTO):  {best_ctx['k']:.2f}   "
          f"(Brier {best_ctx['avg_brier']:.3f}, LogLoss {best_ctx['avg_logloss']:.3f})")

    # Breakdown del mejor K en modo contexto
    print_breakdown(best_ctx)

    # Comparar contra K=1.6 (actual) en modo contexto
    current_ctx = next(r for r in ctx if r["k"] == 1.6)
    print("\n  Comparacion contra K=1.6 actual (modo contexto):")
    print_breakdown(current_ctx)


if __name__ == "__main__":
    main()
