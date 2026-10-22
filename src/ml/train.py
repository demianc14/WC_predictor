"""Entrena, valida y evalúa el modelo supervisado 1X2 de punta a punta.

    python -m src.ml.train --leagues all          # las cinco ligas
    python -m src.ml.train --leagues E0,SP1 --quick

1. Features de todos los partidos (se guardan por huella del dataset y se
   reutilizan si los CSV no cambiaron).
2. Validación (2023-24 y 2024-25): walk-forward mensual de cada candidato;
   gana el de menor log-loss en cada familia. Más una ablación de features.
3. Test (2025-26 y 2026-27): walk-forward con los elegidos, contra
   Dixon-Coles y el mercado sobre la misma muestra.
4. Artefactos en data/ml/runs/<fecha>_<huella>/ y reporte en docs/RESULTADOS_ML.md.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from src.ml import dataset, europe, evaluate, features, report
from src.ml.models import SEED, Spec, grid

ML_DIR = Path("data/ml")
FAMILIES = ("base", "logit_basic", "logit_dc", "hgb")
MK = ["mk_h", "mk_d", "mk_a"]
DC = ["dc_ph", "dc_pd", "dc_pa"]


def load_features(leagues, fp: str, rebuild: bool) -> pd.DataFrame:
    cache = ML_DIR / "cache" / f"features_{fp}.csv.gz"
    if cache.exists() and not rebuild:
        df = pd.read_csv(cache, parse_dates=["day"], dtype={"season": str})
        print(f"📦 features desde la caché ({cache})")
        return df
    print("🔧 calculando features (ELO, forma, descanso, Europa y Dixon-Coles semanal)…")
    matches = dataset.load(leagues)
    eu_days, _ = europe.club_days(matches)
    df = features.build(matches, leagues, dataset.ROW_SEASONS, eu_days or None)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def comparable(df: pd.DataFrame, seasons: tuple[str, ...], need_market: bool) -> np.ndarray:
    """Filas jugadas de `seasons` con Dixon-Coles (y mercado) disponibles."""
    m = df["season"].isin(seasons) & df["y"].notna() & df[DC].notna().all(axis=1)
    if need_market:
        m &= df[MK].notna().all(axis=1)
    return m.to_numpy()


def select(df: pd.DataFrame, quick: bool) -> tuple[dict[str, Spec], list[dict]]:
    sample = comparable(df, dataset.VALID, need_market=False)
    y = df.loc[sample, "y"].to_numpy()
    chosen: dict[str, Spec] = {}
    table: list[dict] = []
    for family, specs in grid(quick).items():
        best: tuple[Spec, float] | None = None
        for spec in specs:
            p = evaluate.walk_forward(df, spec, dataset.VALID)[sample]
            s = evaluate.summary(y, p)
            table.append({"model": spec.label, "family": family, **s})
            print(f"   validación {spec.label}: log-loss {s['logloss']:.4f}, RPS {s['rps']:.4f}")
            if best is None or s["logloss"] < best[1]:
                best = (spec, s["logloss"])
        assert best is not None                            # cada familia tiene candidatos
        chosen[family] = best[0]
    s = evaluate.summary(y, df.loc[sample, DC].to_numpy())
    table.append({"model": "Dixon-Coles", "family": "dc", **s})
    return chosen, table


def ablation(df: pd.DataFrame, c: float) -> list[dict]:
    """Logística con features agregadas de a una, en validación."""
    sample = comparable(df, dataset.VALID, need_market=False)
    y = df.loc[sample, "y"].to_numpy()
    steps = [("ELO", features.FEATURES_ELO),
             ("+ forma", features.FEATURES_FORM),
             ("+ descanso", features.FEATURES_REST),
             ("+ liga", features.LEAGUE_COLS),
             ("+ Dixon-Coles", features.FEATURES_DC),
             ("+ Europa", features.FEATURES_EUROPE)]
    cols: list[str] = []
    out: list[dict] = []
    for name, add in steps:
        cols = cols + list(add)
        p = evaluate.walk_forward(df, Spec("logit_ablation", tuple(cols), {"C": c}),
                                  dataset.VALID)[sample]
        out.append({"features": name, **evaluate.summary(y, p)})
        print(f"   ablación {name}: log-loss {out[-1]['logloss']:.4f}")
    return out


def test(df: pd.DataFrame, chosen: dict[str, Spec]) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    sample = comparable(df, dataset.TEST, need_market=True)
    probs = {f: evaluate.walk_forward(df, chosen[f], dataset.TEST)[sample] for f in FAMILIES}
    probs["dc"] = df.loc[sample, DC].to_numpy()
    probs["market"] = df.loc[sample, MK].to_numpy()
    return df.loc[sample].reset_index(drop=True), probs


def git_commit() -> str:
    if os.environ.get("WCP_COMMIT", "desconocido") != "desconocido":   # imagen de Docker
        return os.environ["WCP_COMMIT"]
    try:
        # "-dirty" si el código corrió con cambios sin commitear
        return subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "desconocido"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Modelo supervisado 1X2 para clubes")
    ap.add_argument("--leagues", default="all", help="'all' o códigos separados por coma")
    ap.add_argument("--quick", action="store_true", help="un candidato por familia")
    ap.add_argument("--rebuild", action="store_true", help="recalcula las features")
    ap.add_argument("--report", default="docs/RESULTADOS_ML.md")
    args = ap.parse_args(argv)
    np.random.seed(SEED)

    leagues = dataset.leagues_from(args.leagues)
    dataset.load(leagues)                          # asegura la caché antes de la huella
    europe.ensure_all()
    fp = dataset.fingerprint(leagues)
    df = load_features(leagues, fp, args.rebuild)
    n_rows = int(df["y"].notna().sum())
    print(f"✅ {n_rows} partidos jugados con features (huella {fp})")

    print("🔎 validación (2023-24, 2024-25)")
    chosen, val_table = select(df, args.quick)
    abl = ablation(df, chosen["logit_dc"].params["C"])
    print("🧪 test (2025-26, 2026-27)")
    rows, probs = test(df, chosen)
    results = report.results(rows, probs)

    run = ML_DIR / "runs" / f"{date.today().isoformat()}_{fp}"
    (run / "models").mkdir(parents=True, exist_ok=True)
    pred = rows[["div", "season", "day", "home", "away", "y"]].copy()
    for name, p in probs.items():
        pred[[f"{name}_1", f"{name}_X", f"{name}_2"]] = np.round(p, 5)
    pred.to_csv(run / "predictions.csv.gz", index=False)
    played = df[df["y"].notna()]
    for f in FAMILIES:                             # modelos finales con todo lo jugado
        joblib.dump(chosen[f].make().fit(played), run / "models" / f"{f}.joblib")
    config = {
        "fingerprint": fp, "commit": git_commit(), "date": date.today().isoformat(),
        "seed": SEED, "leagues": [lg.code for lg in leagues], "quick": args.quick,
        "seasons": {"warmup": dataset.WARMUP, "train": dataset.TRAIN,
                    "valid": dataset.VALID, "test": dataset.TEST},
        "chosen": {f: s.label for f, s in chosen.items()},
        "versions": {"sklearn": sklearn.__version__, "numpy": np.__version__,
                     "pandas": pd.__version__},
        "rows_played": n_rows,
    }
    metrics = {"config": config, "validation": val_table, "ablation": abl, "test": results}
    (run / "metrics.json").write_text(json.dumps(metrics, indent=1, default=str),
                                      encoding="utf-8")
    report.write(metrics, Path(args.report), run)
    print(f"📄 {args.report} y artefactos en {run}")
    print("   " + results["conclusion"])


if __name__ == "__main__":
    main()
