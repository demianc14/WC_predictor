"""Métricas 1X2 por partido, bootstrap y calibración (solo numpy).

Aparte de `evaluate.py` para que el ciclo diario las use sin cargar
scikit-learn: la imagen de Docker que corre todos los días no lo trae.

- Por partido (menor es mejor): Brier 1X2 (0 a 2), RPS (0 a 1, respeta el
  orden 1 < X < 2) y log-loss.
- Intervalos: bootstrap por partido al 95%; las diferencias entre dos modelos
  se remuestrean pareadas (los mismos partidos para ambos).
"""
from __future__ import annotations

import numpy as np

BOOT_SAMPLES = 2000
BOOT_SEED = 2026


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
