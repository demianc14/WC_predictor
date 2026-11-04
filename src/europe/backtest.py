"""Walk-forward de la Champions con el Dixon-Coles conjunto.

    python -m src.europe.backtest

Antes de cada semana se reajusta el modelo con todo lo jugado hasta el día
anterior (ligas y Europa) y se predice el 1X2 de los partidos de Champions de
esa semana. Se compara, sobre la misma muestra, con una línea base que solo
conoce la frecuencia de 1/X/2 de la Champions hasta esa semana.

No hay mercado: football-data no publica cuotas de la Champions. El benchmark
contra las cuotas de cierre queda pendiente.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np

from src.clubs.backtest import _outcome, base_rates
from src.clubs.data import Match
from src.clubs.model import fit
from src.europe import data as eu
from src.ml.metrics import bootstrap, per_match, summary

TEST = ("2425", "2526")        # las dos temporadas con fase de liga de 36 ya cerradas


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


def main() -> None:
    ms = eu.load()
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
