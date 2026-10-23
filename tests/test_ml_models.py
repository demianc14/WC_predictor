"""Modelos y conclusión del reporte."""
import numpy as np
import pandas as pd

from src.ml.models import BaseRates, Spec, grid
from src.ml.report import conclusion


def test_base_rates_por_liga_con_prior():
    df = pd.DataFrame({"div": ["E0"] * 3 + ["SP1"], "y": [0, 0, 1, 2]})
    p = BaseRates().fit(df).predict_proba(pd.DataFrame({"div": ["E0", "SP1", "D1"]}))
    assert np.allclose(p[0], [3 / 6, 2 / 6, 1 / 6]) and np.allclose(p.sum(axis=1), 1)
    assert np.allclose(p[2], [3 / 7, 2 / 7, 2 / 7])          # liga sin historia: total


def test_modelos_sklearn_devuelven_tres_columnas_que_suman_uno():
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(size=(300, 3)), columns=["a", "b", "c"])
    df["y"] = rng.integers(0, 3, 300)
    df.loc[::7, "b"] = np.nan                               # la logística imputa, el boosting no
    for spec in (Spec("logit_x", ("a", "b", "c"), {"C": 1.0}),
                 Spec("hgb", ("a", "b", "c"), {"learning_rate": 0.1, "max_leaf_nodes": 4,
                                               "min_samples_leaf": 20, "max_iter": 20})):
        p = spec.make().fit(df).predict_proba(df)
        assert p.shape == (300, 3) and np.allclose(p.sum(axis=1), 1)


def test_grilla_rapida_un_candidato_por_familia():
    assert all(len(v) == 1 for v in grid(quick=True).values())
    assert len(grid()["hgb"]) == 16                     # 8 combinaciones, con y sin Europa
    assert sum("+ Europa" in s.label for s in grid()["logit_dc"]) == 3


def test_conclusion_dice_empate_si_el_intervalo_cruza_cero():
    allm = {"hgb": {"rps": 0.2}}
    d = {"hgb-dc": {"rps": (-0.001, -0.004, 0.002)}, "hgb-market": {"rps": (0.005, 0.002, 0.008)}}
    txt = conclusion("hgb", d, allm)
    assert "no se distingue del Dixon-Coles" in txt and "por detrás del mercado" in txt
