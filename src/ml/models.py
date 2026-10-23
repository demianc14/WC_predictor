"""Modelos 1X2: base de frecuencias, logística multinomial y gradient boosting.

Todos exponen `fit(df)` y `predict_proba(df) -> (n, 3)` con columnas 1/X/2.
Las grillas de hiperparámetros son chicas a propósito: se eligen en las
temporadas de validación, nunca en test.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.ml.features import FEATURES_BASIC, FEATURES_EUROPE, FEATURES_FULL

SEED = 2627


class BaseRates:
    """Frecuencia de 1/X/2 de cada liga en el entrenamiento (con 1 partido ficticio de cada)."""

    def fit(self, df: pd.DataFrame) -> BaseRates:
        counts = df.groupby("div")["y"].value_counts().unstack(fill_value=0)
        counts = counts.reindex(columns=[0, 1, 2], fill_value=0) + 1
        self.rates = counts.div(counts.sum(axis=1), axis=0)
        self.overall = (df["y"].value_counts().reindex([0, 1, 2], fill_value=0) + 1).to_numpy()
        self.overall = self.overall / self.overall.sum()
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        return np.array([self.rates.loc[d].to_numpy() if d in self.rates.index else self.overall
                         for d in df["div"]])


class SkModel:
    def __init__(self, est, features: list[str]):
        self.est, self.features = est, features

    def fit(self, df: pd.DataFrame) -> SkModel:
        self.est.fit(df[self.features].to_numpy(dtype=float), df["y"].astype(int).to_numpy())
        return self

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        p = self.est.predict_proba(df[self.features].to_numpy(dtype=float))
        out = np.zeros((len(df), 3))
        out[:, self.est.classes_.astype(int)] = p
        return out


@dataclass(frozen=True)
class Spec:
    family: str
    features: tuple[str, ...] = ()
    params: dict = field(default_factory=dict, hash=False)

    @property
    def label(self) -> str:
        eu = " + Europa" if set(FEATURES_EUROPE) & set(self.features) else ""
        params = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return self.family + eu + (f" ({params})" if params else "")

    def make(self):
        if self.family == "base":
            return BaseRates()
        if self.family.startswith("logit"):
            est = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                                StandardScaler(),
                                LogisticRegression(C=self.params["C"], max_iter=2000))
            return SkModel(est, list(self.features))
        if self.family == "hgb":
            est = HistGradientBoostingClassifier(
                learning_rate=self.params["learning_rate"],
                max_leaf_nodes=self.params["max_leaf_nodes"],
                min_samples_leaf=self.params["min_samples_leaf"],
                max_iter=self.params.get("max_iter", 200), l2_regularization=1.0,
                early_stopping=False, random_state=SEED)
            return SkModel(est, list(self.features))
        raise ValueError(self.family)


def grid(quick: bool = False) -> dict[str, list[Spec]]:
    """Candidatos por familia, con y sin las features europeas.

    `quick` deja uno por familia, sin Europa (para tests y pruebas).
    """
    cs = [0.1] if quick else [0.01, 0.1, 1.0]
    hgb = ([(0.05, 8, 80)] if quick else
           [(lr, leaves, msl) for lr in (0.03, 0.06) for leaves in (8, 16) for msl in (40, 120)])
    variants = [()] if quick else [(), tuple(FEATURES_EUROPE)]
    basic, full = tuple(FEATURES_BASIC), tuple(FEATURES_FULL)
    return {
        "base": [Spec("base")],
        "logit_basic": [Spec("logit_basic", basic + eu, {"C": c}) for eu in variants for c in cs],
        "logit_dc": [Spec("logit_dc", full + eu, {"C": c}) for eu in variants for c in cs],
        "hgb": [Spec("hgb", full + eu, {"learning_rate": lr, "max_leaf_nodes": lv,
                                         "min_samples_leaf": ms})
                for eu in variants for lr, lv, ms in hgb],
    }
