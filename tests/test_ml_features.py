"""Modelo supervisado: sin fuga de datos en las features ni en el walk-forward."""
import random
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.clubs.data import Match
from src.clubs.leagues import LEAGUES
from src.ml import evaluate
from src.ml.features import FEATURES_FULL, build, elo_form_rest

LG = [LEAGUES["E0"]]
SEASONS = ("2324", "2425")


def _liga(seed: int = 7) -> list[Match]:
    """Dos temporadas de primera (6 equipos) y segunda (4), resultados al azar."""
    rng = random.Random(seed)
    out = []
    for i, season in enumerate(SEASONS):
        day = date(2023 + i, 8, 5)
        for div, teams in (("E0", "ABCDEF"), ("E1", "GHIJ")):
            d = day
            for h in teams:
                for a in teams:
                    if h != a:
                        out.append(Match(div, season, d, h, a, rng.randint(0, 3), rng.randint(0, 3),
                                         odds=(2.0, 3.4, 3.9) if div == "E0" else None))
                        d += timedelta(days=3)
    return out


def test_cambiar_el_futuro_no_mueve_las_features_del_pasado():
    ms = _liga()
    cut = date(2024, 9, 1)
    futuro = [replace(m, hg=m.ag, ag=m.hg + 2) if m.day >= cut else m for m in ms]
    a, b = build(ms, LG, SEASONS), build(futuro, LG, SEASONS)
    cols = FEATURES_FULL
    antes = a["day"] <= pd.Timestamp(cut)          # incluye el mismo día del corte
    pd.testing.assert_frame_equal(a.loc[antes, cols], b.loc[antes, cols])
    # y la prueba es sensible: después del corte sí cambian
    assert not np.allclose(a.loc[~antes, cols].fillna(0), b.loc[~antes, cols].fillna(0))


def test_partidos_del_mismo_dia_no_se_ven_entre_si():
    d = date(2024, 1, 6)
    ms = [Match("E0", "2324", d, "A", "B", 5, 0), Match("E0", "2324", d, "B", "C", 0, 5)]
    f = elo_form_rest(ms, {"E0"})
    assert f[("E0", d, "B", "C")]["elo_diff"] == 0           # no sabe que B perdió 5-0 ese día
    assert np.isnan(f[("E0", d, "B", "C")]["form_pts_h"])


def test_elo_y_forma_se_actualizan_despues_del_partido():
    d = date(2024, 1, 6)
    ms = [Match("E0", "2324", d, "A", "B", 2, 0),
          Match("E0", "2324", d + timedelta(days=4), "B", "A", 1, 1)]
    f = elo_form_rest(ms, {"E0"})[("E0", d + timedelta(days=4), "B", "A")]
    assert f["elo_diff"] < 0                                 # A ganó: ahora tiene más ELO
    assert f["form_pts_h"] == 0 and f["form_pts_a"] == 3
    assert f["form_gf_a"] == 2 and f["rest_h"] == 4 and f["rest_a"] == 4


def test_las_cuotas_nunca_son_feature():
    df = build(_liga(), LG, SEASONS)
    assert not any(c.startswith("mk_") or "odds" in c for c in FEATURES_FULL)
    assert df[["mk_h", "mk_d", "mk_a"]].notna().all().all()   # pero están como benchmark


class _Spy:
    """Modelo trivial que anota con qué fechas se entrenó."""
    calls: list = []

    def fit(self, df):
        _Spy.calls.append(df["day"].max())
        return self

    def predict_proba(self, df):
        _Spy.calls.append(("pred", df["day"].min()))
        return np.full((len(df), 3), 1 / 3)


class _SpySpec:
    def make(self):
        return _Spy()


def test_walk_forward_entrena_solo_con_meses_anteriores():
    days = pd.date_range("2023-08-01", "2025-05-31", freq="5D")
    df = pd.DataFrame({"day": days, "y": [i % 3 for i in range(len(days))],
                       "season": ["2324" if d < pd.Timestamp("2024-07-01") else "2425"
                                  for d in days], "div": "E0"})
    _Spy.calls = []
    p = evaluate.walk_forward(df, _SpySpec(), ("2425",))
    assert np.isnan(p[df["season"] == "2324"]).all()
    assert not np.isnan(p[df["season"] == "2425"]).any()
    pairs = list(zip(_Spy.calls[::2], _Spy.calls[1::2]))
    assert pairs and all(train_max < pred[1].replace(day=1) for train_max, pred in pairs)


def test_metricas_coinciden_con_las_de_selecciones():
    from src.evaluation.backtest import OUTCOMES, brier_3way, rps_3way
    rng = np.random.default_rng(0)
    p = rng.dirichlet([1, 1, 1], 50)
    y = rng.integers(0, 3, 50)
    m = evaluate.per_match(y, p)
    assert m["brier"] == pytest.approx([brier_3way(tuple(q), OUTCOMES[k]) for q, k in zip(p, y)])
    assert m["rps"] == pytest.approx([rps_3way(tuple(q), OUTCOMES[k]) for q, k in zip(p, y)])
    assert m["logloss"] == pytest.approx(-np.log(p[np.arange(50), y]))


def test_bootstrap_es_reproducible_y_contiene_la_media():
    v = np.random.default_rng(1).normal(0.2, 0.1, 400)
    a, b = evaluate.bootstrap(v, samples=500), evaluate.bootstrap(v, samples=500)
    assert a == b and a[1] < a[0] < a[2]
