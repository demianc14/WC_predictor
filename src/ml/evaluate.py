"""Walk-forward mensual, métricas por partido, bootstrap y calibración.

- Bloques: meses calendario. Para cada mes se entrena con todas las filas
  jugadas ANTES del primer día del mes (desde 2020-21) y se predice el mes.
- Métricas por partido (menor es mejor): Brier 1X2 (0 a 2), RPS (0 a 1, respeta
  el orden 1 < X < 2) y log-loss. Siempre sobre la misma muestra.
- Intervalos: bootstrap por partido al 95%; las diferencias entre dos modelos
  se remuestrean pareadas (los mismos partidos para ambos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.ml.dataset import ROW_SEASONS
from src.ml.models import Spec

BOOT_SAMPLES = 2000
BOOT_SEED = 2026


def month_blocks(df: pd.DataFrame, seasons: tuple[str, ...]) -> list[pd.Timestamp]:
    days = df.loc[df["season"].isin(seasons) & df["y"].notna(), "day"]
    return sorted({d.replace(day=1) for d in days})


def walk_forward(df: pd.DataFrame, spec: Spec, seasons: tuple[str, ...]) -> np.ndarray:
    """Probabilidades (n, 3) para las filas jugadas de `seasons`; NaN en el resto."""
    played = df["y"].notna() & df["season"].isin(ROW_SEASONS)
    out = np.full((len(df), 3), np.nan)
    for start in month_blocks(df, seasons):
        end = start + pd.offsets.MonthBegin(1)
        test = played & df["season"].isin(seasons) & (df["day"] >= start) & (df["day"] < end)
        train = played & (df["day"] < start)
        assert df.loc[train, "day"].max() < df.loc[test, "day"].min()   # nada del futuro
        model = spec.make().fit(df[train])
        out[test.to_numpy()] = model.predict_proba(df[test])
    return out


def per_match(y: np.ndarray, p: np.ndarray) -> dict[str, np.ndarray]:
    y = y.astype(int)
    onehot = np.eye(3)[y]
    brier = ((p - onehot) ** 2).sum(axis=1)
    cum = np.cumsum(p, axis=1)[:, :2] - np.cumsum(onehot, axis=1)[:, :2]
    rps = (cum ** 2).sum(axis=1) / 2
    ll = -np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))
    return {"brier": brier, "rps": rps, "logloss": ll}


def summary(y: np.ndarray, p: np.ndarray) -> dict:
    m = per_match(y, p)
    return {"n": int(len(y)), **{k: float(v.mean()) for k, v in m.items()}}


def bootstrap(values: np.ndarray, samples: int = BOOT_SAMPLES, seed: int = BOOT_SEED
              ) -> tuple[float, float, float]:
    """Media e IC 95% remuestreando partidos (para diferencias, pasar a − b)."""
    rng = np.random.default_rng(seed)
    n = len(values)
    means = np.empty(samples)
    for i in range(0, samples, 200):                 # en tandas, para no usar 100+ MB
        k = min(200, samples - i)
        means[i:i + k] = values[rng.integers(0, n, (k, n))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(values.mean()), float(lo), float(hi)


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[list[dict]]:
    """Por clase (1, X, 2): prob. media predicha contra frecuencia real en cada tramo."""
    out = []
    for c in range(3):
        edges = np.linspace(0, 1, bins + 1)
        idx = np.clip(np.digitize(p[:, c], edges) - 1, 0, bins - 1)
        rows = []
        for b in range(bins):
            sel = idx == b
            if sel.sum() >= 15:
                rows.append({"pred": float(p[sel, c].mean()), "obs": float((y[sel] == c).mean()),
                             "n": int(sel.sum())})
        out.append(rows)
    return out
