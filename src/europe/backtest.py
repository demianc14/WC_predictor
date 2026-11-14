"""Walk-forward de la Champions con el Dixon-Coles conjunto.

    python -m src.europe.backtest                    # test 2024-25 y 2025-26 contra la base
    python -m src.europe.backtest --fase validacion  # elige c → docs/ucl/validacion.json
    python -m src.europe.backtest --fase test        # una sola vez, con c congelado
                                                     # → docs/ucl/test.json

Antes de cada semana se reajusta el modelo con todo lo jugado hasta el día
anterior (ligas y Europa) y se predice el 1X2 de los partidos de Champions de
esa semana. Se compara, sobre la misma muestra, con una línea base que solo
conoce la frecuencia de 1/X/2 de la Champions hasta esa semana.

No hay mercado: football-data no publica cuotas de la Champions. El benchmark
contra las cuotas de cierre queda pendiente.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from src.clubs.backtest import _outcome, base_rates
from src.clubs.data import Match
from src.clubs.model import fit
from src.europe import data as eu
from src.ml.metrics import bootstrap, per_match, summary

TEST = ("2425", "2526")        # las dos temporadas con fase de liga de 36 ya cerradas
VALIDATION = ("2122", "2223", "2324")   # formato de grupos, todo antes del test

# Calibración del empate: P(X) × c y se renormaliza. c se elige por log-loss en validación
# y se congela acá, en un commit propio, antes de correr el test.
DRAW_GRID = tuple(round(0.60 + 0.02 * i, 2) for i in range(36))      # 0,60 a 1,30
DRAW_C: float | None = 0.9          # docs/ucl/validacion.json, 14-nov-2026
OUT_DIR = Path("docs/ucl")

# Regla de decisión de la calibración (T1), escrita antes de mirar el test: se adopta solo si
# el log-loss del test mejora más que el IC 95% esperado con n ≈ 376 (±0,012) y si el IC
# pareado por bootstrap del test excluye el cero. Si no, no se adopta y se documenta.
ADOPT_LOGLOSS = 0.012


def adopt(diff_logloss: tuple[float, float, float]) -> bool:
    """`diff_logloss` = (Δ, lo, hi) de calibrado − actual en test; negativo es mejor."""
    d, _, hi = diff_logloss
    return d < -ADOPT_LOGLOSS and hi < 0


def walk_forward(matches: list[Match], seasons: tuple[str, ...], comp: str = "UCL",
                 skipped: list[Match] | None = None) -> list[dict]:
    """`skipped` junta los partidos de un club sin ningún partido previo (no se predicen)."""
    skipped = [] if skipped is None else skipped
    target = [m for m in matches if m.div == comp and m.season in seasons and m.played]
    out: list[dict] = []
    if not target:
        return out
    week = target[0].day - timedelta(days=target[0].day.weekday())
    while week <= target[-1].day:
        nxt = week + timedelta(days=7)
        batch = [m for m in target if week <= m.day < nxt]
        if batch:
            r = fit(matches, week)
            base = base_rates(matches, comp, week)
            for m in batch:
                if m.home not in r.att or m.away not in r.att:
                    skipped.append(m)
                    continue
                ph, pd, pa, _ = r.probs(m.home, m.away)
                out.append({"season": m.season, "day": m.day.isoformat(), "home": m.home,
                            "away": m.away, "o": _outcome(m), "model": [ph, pd, pa],
                            "base": base, "n_eff": min(r.n_eff[m.home], r.n_eff[m.away])})
        week = nxt
    return out


def report(rows: list[dict]) -> dict:
    y = np.array([r["o"] for r in rows])
    p = np.array([r["model"] for r in rows])
    b = np.array([r["base"] for r in rows])
    diff = {k: bootstrap(per_match(y, p)[k] - per_match(y, b)[k])
            for k in ("brier", "rps", "logloss")}
    return {"model": summary(y, p), "base": summary(y, b), "diff": diff,
            "home": {"pred": float(p[:, 0].mean()), "obs": float((y == 0).mean()),
                     "pred_x": float(p[:, 1].mean()), "obs_x": float((y == 1).mean())}}


def calibrate(p: np.ndarray, c: float) -> np.ndarray:
    q = np.array(p, dtype=float)
    q[:, 1] *= c
    return q / q.sum(axis=1, keepdims=True)


def _arrays(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (np.array([r["o"] for r in rows]), np.array([r["model"] for r in rows]),
            np.array([r["base"] for r in rows]))


def grid(rows: list[dict]) -> dict[float, float]:
    """Log-loss de cada c de la grilla. Solo acepta filas de validación."""
    if any(r["season"] not in VALIDATION for r in rows):
        raise ValueError("c se elige solo con partidos de validación")
    y, p, _ = _arrays(rows)
    return {c: summary(y, calibrate(p, c))["logloss"] for c in DRAW_GRID}


def choose_c(rows: list[dict]) -> float:
    ll = grid(rows)
    return min(ll, key=lambda c: (ll[c], abs(c - 1)))


def check_disjoint(val: list[dict], test: list[dict]) -> None:
    """Validación y test no comparten temporadas ni fechas: todo lo de validación es antes."""
    if {r["season"] for r in val} & {r["season"] for r in test}:
        raise ValueError("validación y test comparten temporadas")
    if val and test and max(r["day"] for r in val) >= min(r["day"] for r in test):
        raise ValueError("validación y test se solapan en fechas")


def compare(rows: list[dict], c: float) -> dict:
    """Actual, calibrado y base sobre la misma muestra; Δ con IC por bootstrap pareado."""
    y, p, b = _arrays(rows)
    q = calibrate(p, c)
    pm = {k: per_match(y, x) for k, x in (("model", p), ("cal", q), ("base", b))}
    ks = ("brier", "rps", "logloss")
    return {"n": int(len(y)), "c": c,
            "model": summary(y, p), "calibrated": summary(y, q), "base": summary(y, b),
            "diff_cal_model": {k: bootstrap(pm["cal"][k] - pm["model"][k]) for k in ks},
            "diff_cal_base": {k: bootstrap(pm["cal"][k] - pm["base"][k]) for k in ks},
            "diff_model_base": {k: bootstrap(pm["model"][k] - pm["base"][k]) for k in ks},
            "freq": {"obs": [float((y == i).mean()) for i in range(3)],
                     "model": [float(x) for x in p.mean(axis=0)],
                     "calibrated": [float(x) for x in q.mean(axis=0)]}}


def _commit() -> str:
    try:
        return subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"


def _save(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def _meta(fase: str) -> dict:
    return {"fase": fase, "command": f"python -m src.europe.backtest --fase {fase}",
            "commit": _commit(),
            "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def run_validation(ms: list[Match]) -> dict:
    skipped: list[Match] = []
    rows = walk_forward(ms, VALIDATION, skipped=skipped)
    c = choose_c(rows)
    return {**_meta("validacion"), "seasons": list(VALIDATION), "criterion": "logloss",
            "grid": {str(k): v for k, v in grid(rows).items()}, "chosen_c": c,
            "skipped": len(skipped), "all": compare(rows, c),
            "by_season": {s: compare([r for r in rows if r["season"] == s], c)
                          for s in VALIDATION}}


def run_test(ms: list[Match], c: float | None = DRAW_C) -> dict:
    """El test, una sola vez: con c congelado en el código, igual al de validación."""
    if c is None:
        raise RuntimeError("c no está congelado: correr antes --fase validacion y fijar DRAW_C")
    val_path, test_path = OUT_DIR / "validacion.json", OUT_DIR / "test.json"
    if not val_path.exists() or json.loads(val_path.read_text())["chosen_c"] != c:
        raise RuntimeError(f"DRAW_C = {c} no coincide con {val_path}")
    if test_path.exists():
        raise RuntimeError(f"{test_path} ya existe: el test se corre una sola vez")
    meta = _meta("test")
    if meta["commit"].endswith("-dirty") or meta["commit"] == "desconocido":
        raise RuntimeError("el test corre desde un árbol limpio y commiteado")
    skipped: list[Match] = []
    val = walk_forward(ms, VALIDATION)
    rows = walk_forward(ms, TEST, skipped=skipped)
    check_disjoint(val, rows)
    rep = compare(rows, c)
    return {**meta, "seasons": list(TEST), "c": c, "skipped": len(skipped),
            "rule": {"adopt_logloss": ADOPT_LOGLOSS,
                     "adopt": adopt(rep["diff_cal_model"]["logloss"])},
            "all": rep, "by_season": {s: compare([r for r in rows if r["season"] == s], c)
                                      for s in TEST}}


def _print_cal(title: str, rep: dict) -> None:
    print(f"\n{title} (n = {rep['n']}, misma muestra, c = {rep['c']})")
    print(f"   {'':12}{'Brier':>8}{'RPS':>8}{'log-loss':>10}")
    for k in ("model", "calibrated", "base"):
        s = rep[k]
        print(f"   {k:12}{s['brier']:8.4f}{s['rps']:8.4f}{s['logloss']:10.4f}")
    for name in ("diff_cal_model", "diff_cal_base"):
        for k, (d, lo, hi) in rep[name].items():
            print(f"   {name} {k}: {d:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    f = rep["freq"]
    print("   X real {:.3f} / actual {:.3f} / calibrado {:.3f}; 1 real {:.3f} / actual {:.3f}"
          .format(f["obs"][1], f["model"][1], f["calibrated"][1], f["obs"][0], f["model"][0]))


def _print(title: str, rep: dict) -> None:
    m, b = rep["model"], rep["base"]
    print(f"\n{title} (n = {m['n']}, misma muestra)")
    print(f"   {'':10}{'Brier':>8}{'RPS':>8}{'log-loss':>10}")
    for k, s in (("modelo", m), ("base", b)):
        print(f"   {k:10}{s['brier']:8.4f}{s['rps']:8.4f}{s['logloss']:10.4f}")
    for k, (d, lo, hi) in rep["diff"].items():
        print(f"   Δ{k} modelo − base: {d:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    h = rep["home"]
    print(f"   1 predicho {h['pred']:.3f} / real {h['obs']:.3f}; "
          f"X predicho {h['pred_x']:.3f} / real {h['obs_x']:.3f}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Backtest de la Champions")
    ap.add_argument("--fase", choices=("validacion", "test"),
                    help="calibración del empate: elegir c o medirlo una vez en test")
    args = ap.parse_args(argv)
    ms = eu.load()
    if args.fase:
        out = run_validation(ms) if args.fase == "validacion" else run_test(ms)
        path = _save(args.fase, out)
        _print_cal(f"Champions {', '.join(out['seasons'])}", out["all"])
        for s, rep in out["by_season"].items():
            _print_cal(f"Champions {s}", rep)
        if args.fase == "validacion":
            print(f"\n→ c elegido: {out['chosen_c']} (fijarlo en DRAW_C)")
        else:
            print(f"\n→ ¿se adopta?: {'sí' if out['rule']['adopt'] else 'no'}")
        print(f"✅ {path} (commit {out['commit']})")
        return
    skipped: list[Match] = []
    rows = walk_forward(ms, TEST, skipped=skipped)
    print(f"⚠️  {len(skipped)} partidos sin predecir: un club debutaba sin partidos previos "
          f"({', '.join(sorted({t for m in skipped for t in (m.home, m.away)}))})")
    _print("Champions 2024-25 y 2025-26", report(rows))
    for s in TEST:
        _print(f"Champions {s}", report([r for r in rows if r["season"] == s]))
    alone = eu.without_league(ms)
    weak = [r for r in rows if r["home"] in alone or r["away"] in alone]
    if weak:
        _print("Partidos con un club sin liga en la fuente", report(weak))
    now = walk_forward(ms, ("2627",))
    if now:
        _print("Champions 2026-27 hasta hoy", report(now))


if __name__ == "__main__":
    main()
