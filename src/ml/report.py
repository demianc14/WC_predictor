"""Resultados del test y reporte `docs/RESULTADOS_ML.md`, generado por código.

Nada de este reporte se escribe a mano: las tablas, los intervalos, la
calibración y la conclusión salen de `metrics.json` de la corrida. Para
regenerarlo sin reentrenar:

    python -m src.ml.report data/ml/runs/<fecha>_<huella>
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.clubs.leagues import LEAGUES
from src.ml import evaluate

NAMES = {"base": "Base (frecuencias 1X2)", "logit_basic": "Logística sin Dixon-Coles",
         "logit_dc": "Logística + Dixon-Coles", "hgb": "Gradient boosting",
         "dc": "Dixon-Coles", "market": "Mercado (cierre, sin margen)"}
ML = ("logit_basic", "logit_dc", "hgb")
def season(s: str) -> str:
    return f"20{s[:2]}-{s[2:]}"
COLORS = {"hgb": "#1b7f3b", "logit_dc": "#2a6fdb", "dc": "#c2410c", "market": "#555555"}


def results(rows: pd.DataFrame, probs: dict[str, np.ndarray]) -> dict:
    y = rows["y"].to_numpy().astype(int)
    per = {k: evaluate.per_match(y, p) for k, p in probs.items()}

    def table(mask: np.ndarray) -> dict:
        return {k: evaluate.summary(y[mask], p[mask]) for k, p in probs.items()}

    by_league = []
    for (div, season), g in rows.groupby(["div", "season"]):
        m = np.zeros(len(rows), bool)
        m[g.index] = True
        by_league.append({"div": div, "season": season, "models": table(m)})
    pooled = {}
    for season in sorted(rows["season"].unique()):
        m = (rows["season"] == season).to_numpy()
        pooled[season] = table(m)
    everything = np.ones(len(rows), bool)
    pooled["all"] = table(everything)

    ci = {k: {met: evaluate.bootstrap(per[k][met]) for met in ("rps", "logloss", "brier")}
          for k in probs}
    diffs = {f"{a}-{b}": {met: evaluate.bootstrap(per[a][met] - per[b][met])
                          for met in ("rps", "logloss")}
             for a in ML for b in ("dc", "market")}
    diffs["dc-market"] = {met: evaluate.bootstrap(per["dc"][met] - per["market"][met])
                          for met in ("rps", "logloss")}
    draws = {k: {"pred": float(p[:, 1].mean()), "obs": float((y == 1).mean())}
             for k, p in probs.items()}
    calib = {k: evaluate.calibration(y, probs[k]) for k in COLORS}
    best = min(ML, key=lambda k: pooled["all"][k]["rps"])
    return {"n": int(len(rows)), "by_league": by_league, "pooled": pooled, "ci": ci,
            "diffs": diffs, "draws": draws, "calibration": calib, "best": best,
            "conclusion": conclusion(best, diffs, pooled["all"])}


def _verdict(lo: float, hi: float, better: str, worse: str, tie: str) -> str:
    return better if hi < 0 else worse if lo > 0 else tie


def conclusion(best: str, diffs: dict, allm: dict) -> str:
    d_dc, d_mk = diffs[f"{best}-dc"]["rps"], diffs[f"{best}-market"]["rps"]
    vs_dc = _verdict(d_dc[1], d_dc[2], "mejora al Dixon-Coles", "es peor que el Dixon-Coles",
                     "no se distingue del Dixon-Coles")
    vs_mk = _verdict(d_mk[1], d_mk[2], "le gana al mercado", "queda por detrás del mercado",
                     "no se distingue del mercado")
    return (f"El mejor supervisado en test, «{NAMES[best]}» (RPS {allm[best]['rps']:.4f}), "
            f"{vs_dc} (diferencia de RPS {d_dc[0]:+.4f}, IC 95% {d_dc[1]:+.4f} a {d_dc[2]:+.4f}) "
            f"y {vs_mk} (diferencia {d_mk[0]:+.4f}, IC 95% {d_mk[1]:+.4f} a {d_mk[2]:+.4f}).")


def _ci(t: tuple[float, float, float]) -> str:
    return f"{t[0]:.4f} [{t[1]:.4f}, {t[2]:.4f}]"


def _row(name: str, s: dict, bold: bool = False) -> str:
    f = (lambda v: f"**{v:.4f}**") if bold else (lambda v: f"{v:.4f}")
    return f"| {name} | {s['n']} | {f(s['brier'])} | {f(s['rps'])} | {f(s['logloss'])} |"


def calibration_svg(calib: dict, path: Path) -> None:
    W, H, pad, gap = 940, 330, 46, 52
    pw = (W - 2 * pad - 2 * gap) / 3
    ph = H - 2 * pad
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H + 30}" '
             f'font-family="sans-serif" font-size="12">',
             f'<rect width="{W}" height="{H + 30}" fill="#ffffff"/>']
    for c, title in enumerate(("Gana el local (1)", "Empate (X)", "Gana la visita (2)")):
        x0 = pad + c * (pw + gap)
        top = 0.8 if c != 1 else 0.5
        X = lambda v, x0=x0, top=top: x0 + v / top * pw            # noqa: E731
        Y = lambda v, top=top: pad + ph - v / top * ph              # noqa: E731
        parts.append(f'<text x="{x0 + pw / 2}" y="{pad - 14}" text-anchor="middle" '
                     f'font-weight="bold">{title}</text>')
        parts.append(f'<rect x="{x0}" y="{pad}" width="{pw}" height="{ph}" fill="none" '
                     f'stroke="#bbb"/>')
        parts.append(f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(top)}" y2="{Y(top)}" '
                     f'stroke="#999" stroke-dasharray="4 4"/>')
        for v in np.arange(0, top + 1e-9, 0.1 if top <= 0.5 else 0.2):
            parts.append(f'<text x="{X(v)}" y="{pad + ph + 16}" text-anchor="middle" '
                         f'fill="#555">{v:.1f}</text>')
            parts.append(f'<text x="{x0 - 6}" y="{Y(v) + 4}" text-anchor="end" '
                         f'fill="#555">{v:.1f}</text>')
        for k, color in COLORS.items():
            pts = [(r["pred"], r["obs"]) for r in calib[k][c] if r["pred"] <= top]
            if len(pts) > 1:
                d = " ".join(f"{X(a):.1f},{Y(min(b, top)):.1f}" for a, b in pts)
                parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" '
                             f'stroke-width="2"/>')
    lx = pad
    for k, color in COLORS.items():
        parts.append(f'<rect x="{lx}" y="{H + 8}" width="14" height="4" fill="{color}"/>')
        parts.append(f'<text x="{lx + 20}" y="{H + 14}">{NAMES[k]}</text>')
        lx += 210
    parts.append(f'<text x="{W / 2}" y="{H - 6}" text-anchor="middle" fill="#555">'
                 f'probabilidad predicha (eje x) contra frecuencia observada (eje y)</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write(metrics: dict, path: Path, run: Path) -> None:
    cfg, res = metrics["config"], metrics["test"]
    svg = path.parent / "ml" / "calibracion.svg"
    svg.parent.mkdir(parents=True, exist_ok=True)
    calibration_svg(res["calibration"], svg)
    order = ["base", "logit_basic", "logit_dc", "hgb", "dc", "market"]
    L = [
        "# Resultados del modelo supervisado (1X2, clubes)",
        "",
        "> Generado por `python -m src.ml.train --leagues "
        f"{'all' if len(cfg['leagues']) == len(LEAGUES) else ','.join(cfg['leagues'])}"
        f"{' --quick' if cfg['quick'] else ''}`. No editar a mano.",
        "",
        f"- Fecha: {cfg['date']} · commit `{cfg['commit']}` · huella del dataset "
        f"`{cfg['fingerprint']}` · semilla {cfg['seed']}",
        f"- Ligas: {', '.join(LEAGUES[c].name for c in cfg['leagues'])}",
        f"- Partidos jugados con features: {cfg['rows_played']}",
        "- Temporadas: " + "; ".join(
            f"{lbl} {', '.join(season(s) for s in cfg['seasons'][k])}"
            for k, lbl in (("warmup", "historia previa"), ("train", "entrenamiento"),
                           ("valid", "validación"), ("test", "test"))),
        f"- Versiones: scikit-learn {cfg['versions']['sklearn']}, numpy "
        f"{cfg['versions']['numpy']}, pandas {cfg['versions']['pandas']}",
        f"- Artefactos: `{run.as_posix()}/` (predicciones, métricas, modelos)",
        "",
        "## Conclusión",
        "",
        res["conclusion"],
        "",
        "## Test: todas las ligas juntas",
        "",
        f"Misma muestra para todos: {res['n']} partidos de test con Dixon-Coles y cuotas de "
        "cierre. Brier (0 a 2), RPS (0 a 1) y log-loss: menor es mejor. Entre corchetes, el "
        "intervalo bootstrap al 95%.",
        "",
        "| Modelo | n | Brier | RPS | Log-loss |",
        "|---|---|---|---|---|",
    ]
    best_rps = min(res["pooled"]["all"][k]["rps"] for k in order)
    for k in order:
        s = res["pooled"]["all"][k]
        ci = res["ci"][k]
        L.append(f"| {NAMES[k]} | {s['n']} | {_ci(ci['brier'])} | "
                 f"{'**' if s['rps'] == best_rps else ''}{_ci(ci['rps'])}"
                 f"{'**' if s['rps'] == best_rps else ''} | {_ci(ci['logloss'])} |")
    L += ["", "### Diferencias pareadas (negativo = el primero es mejor)", "",
          "| Comparación | ΔRPS [IC 95%] | ΔLog-loss [IC 95%] |", "|---|---|---|"]
    for key, d in res["diffs"].items():
        a, b = key.split("-")
        L.append(f"| {NAMES[a]} − {NAMES[b]} | {_ci(d['rps'])} | {_ci(d['logloss'])} |")
    L += ["", "## Test por liga y temporada", "",
          "| Liga | Temporada | Modelo | n | Brier | RPS | Log-loss |",
          "|---|---|---|---|---|---|---|"]
    for b in res["by_league"]:
        best = min(b["models"][k]["rps"] for k in order)
        for k in order:
            s = b["models"][k]
            L.append(f"| {LEAGUES[b['div']].name} | {season(b['season'])} | "
                     + _row(NAMES[k], s, bold=s["rps"] == best)[2:])
    L += ["", "## Calibración", "", "![Curvas de calibración](ml/calibracion.svg)", "",
          "Tramos de 0.1 con al menos 15 partidos. Sobre la diagonal punteada, el modelo dice "
          "lo que después pasa.", "", "### Empates", "",
          "| Modelo | P(X) media predicha | Empates reales |", "|---|---|---|"]
    for k in order:
        d = res["draws"][k]
        L.append(f"| {NAMES[k]} | {d['pred']:.3f} | {d['obs']:.3f} |")
    L += ["", "## Validación: elección de hiperparámetros", "",
          "Walk-forward mensual en 2023-24 y 2024-25 (filas con Dixon-Coles). En cada familia "
          "gana el de menor log-loss; el test no se usa para elegir.", "",
          "| Candidato | n | Brier | RPS | Log-loss |", "|---|---|---|---|---|"]
    chosen = set(cfg["chosen"].values())
    for r in metrics["validation"]:
        L.append(_row(("✓ " if r["model"] in chosen else "") + r["model"], r))
    L += ["", "### Ablación (logística, features agregadas de a una, validación)", "",
          "| Features | n | Brier | RPS | Log-loss |", "|---|---|---|---|---|"]
    for r in metrics["ablation"]:
        L.append(_row(r["features"], r))
    L += ["", "## Método y límites", "",
          "- **Sin fuga de datos**: cada fila usa solo partidos de días anteriores; lo verifica "
          "`tests/test_ml_features.py` cambiando resultados futuros y comprobando que las "
          "features no se mueven. El walk-forward entrena solo con meses anteriores al que "
          "predice.",
          "- **Las cuotas no son feature**: solo se usan como benchmark.",
          "- **Features**: ELO de clubes (K=20, +60 de localía), forma de los últimos 5 "
          "(puntos, goles a favor y en contra), días de descanso (tope 21), liga y, en los "
          "modelos con Dixon-Coles, sus probabilidades y λ reajustados cada lunes.",
          "- **No entran**: xG (solo existe desde 2026-27), partidos de copa y de Europa "
          "(el descanso solo ve la liga), lesiones y alineaciones.",
          "- **2020-21 se jugó mayormente sin público**: la ventaja de local de ese año es "
          "atípica y forma parte del entrenamiento.",
          "- **2026-27 está en curso**: su muestra es chica y sus métricas se mueven cada semana.",
          ""]
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Regenera el reporte desde una corrida")
    ap.add_argument("run", type=Path)
    ap.add_argument("--report", type=Path, default=Path("docs/RESULTADOS_ML.md"))
    args = ap.parse_args()
    metrics = json.loads((args.run / "metrics.json").read_text(encoding="utf-8"))
    write(metrics, args.report, args.run)
    print(f"📄 {args.report}")


if __name__ == "__main__":
    main()
