"""Walk-forward mensual de los modelos 1X2.

Bloques: meses calendario. Para cada mes se entrena con todas las filas
jugadas ANTES del primer día del mes (desde 2020-21) y se predice el mes.
Las métricas viven en `metrics.py` (solo numpy) y se reexportan aquí.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.ml.dataset import ROW_SEASONS
from src.ml.metrics import bootstrap, calibration, per_match, summary
from src.ml.models import Spec

__all__ = ["bootstrap", "calibration", "month_blocks", "per_match", "summary", "walk_forward"]


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
