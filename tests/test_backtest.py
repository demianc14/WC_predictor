"""Tests del backtest y del ELO reconstruido. Sin red: solo snapshots congelados."""
from datetime import date

import pytest

from src.etl.models import TeamStrength
from src.evaluation.backtest import (
    Params,
    brier_3way,
    dixon_coles_valid,
    load_elo,
    load_matches,
    load_strengths,
    model_1x2,
    model_advance,
    rps_3way,
    run,
)
from src.evaluation.elo import (
    compute_ratings,
    elo_1x2,
    expected_score,
    fit_draw_c,
    goal_multiplier,
    k_factor,
)
from src.simulation.match_engine import penalty_win_probability


def make(code, post, att=1.0, defe=1.0):
    return TeamStrength(fifa_code=code, name=code, group="A", prior=post,
                        likelihood=post, posterior=post, att=att, defe=defe)


# ─── Métricas ────────────────────────────────────────────────────────

def test_brier_extremos_y_uniforme():
    assert brier_3way((1.0, 0.0, 0.0), "1") == 0.0
    assert brier_3way((0.0, 0.0, 1.0), "1") == 2.0
    assert brier_3way((1 / 3, 1 / 3, 1 / 3), "X") == pytest.approx(2 / 3)


def test_rps_castiga_menos_errar_por_un_escalon():
    """Decir 'empate' cuando gana el local es menos grave que decir 'visitante'."""
    assert rps_3way((0.0, 1.0, 0.0), "1") == pytest.approx(0.5)
    assert rps_3way((0.0, 0.0, 1.0), "1") == pytest.approx(1.0)
    assert rps_3way((1.0, 0.0, 0.0), "1") == 0.0


# ─── ELO ─────────────────────────────────────────────────────────────

def test_elo_expectativa_y_factores():
    assert expected_score(0) == 0.5
    assert expected_score(400) == pytest.approx(10 / 11)
    assert goal_multiplier(1) == 1.0 and goal_multiplier(2) == 1.5
    assert goal_multiplier(-4) == pytest.approx(15 / 8)
    assert k_factor("FIFA World Cup") == 60 and k_factor("Friendly") == 20
    assert k_factor("UEFA Euro qualification") == 40 and k_factor("UEFA Euro") == 50


def test_elo_1x2_conserva_la_esperanza_del_elo():
    for we in (0.1, 0.5, 0.93):
        p1, px, p2 = elo_1x2(we, draw_c=0.4)
        assert p1 + px + p2 == pytest.approx(1.0)
        assert p1 + px / 2 == pytest.approx(we)
        assert min(p1, px, p2) >= 0.0


def test_compute_ratings_es_suma_cero_y_respeta_el_corte():
    rows = [
        {"_date": date(2026, 1, 1), "home_team": "A", "away_team": "B", "home_score": 2,
         "away_score": 0, "neutral": True, "tournament": "Friendly"},
        {"_date": date(2026, 7, 1), "home_team": "B", "away_team": "A", "home_score": 9,
         "away_score": 0, "neutral": True, "tournament": "FIFA World Cup"},
    ]
    ratings, _ = compute_ratings(rows, cutoff=date(2026, 6, 11))
    # 20 (amistoso) × 1.5 (2 goles) × (1 − 0.5) = +15
    assert ratings["A"] == pytest.approx(1515.0)
    assert ratings["B"] == pytest.approx(1485.0)


def test_fit_draw_c_recupera_empates_entre_iguales():
    history = [(0.5, "X")] * 30 + [(0.5, "1")] * 35 + [(0.5, "2")] * 35
    assert fit_draw_c(history) == pytest.approx(0.30)


# ─── Predictores del modelo ──────────────────────────────────────────

def test_probabilidad_de_clasificar_es_complementaria():
    """P(clasifica A vs B) + P(clasifica B vs A) = 1, incluso con anfitrión."""
    for a, b in [(make("ARG", 0.9, 1.3, 0.7), make("NZL", 0.4, 0.8, 1.4)),
                 (make("USA", 0.6), make("BEL", 0.75))]:
        assert model_advance(a, b, Params()) + model_advance(b, a, Params()) \
            == pytest.approx(1.0, abs=1e-6)


def test_model_1x2_suma_1_y_favorece_al_fuerte():
    p1, px, p2 = model_1x2(make("ESP", 0.95, 1.4, 0.6), make("CUW", 0.3, 0.7, 1.5), Params())
    assert p1 + px + p2 == pytest.approx(1.0)
    assert p1 > 0.7 > p2


def test_penales_simetricos_y_recortados():
    assert penalty_win_probability(0.7, 0.6) + penalty_win_probability(0.6, 0.7) \
        == pytest.approx(1.0)
    assert penalty_win_probability(1.0, 0.0) == 0.78
    assert penalty_win_probability(0.0, 1.0) == 0.22


def test_dixon_coles_valid_rechaza_rho_extremo():
    assert dixon_coles_valid(1.5, 1.2, -0.13)
    assert not dixon_coles_valid(4.5, 1.0, -0.25)   # τ(0,1) = 1 + 4.5·(−0.25) < 0


# ─── Snapshots e integración ─────────────────────────────────────────

def test_snapshot_del_mundial_esta_completo_y_es_coherente():
    matches = load_matches()
    assert sum(m.is_group for m in matches) == 72
    assert len(matches) == 104
    strengths, elo = load_strengths(), load_elo()
    for m in matches:
        assert m.home in strengths and m.away in strengths
        assert m.home in elo["ratings"] and m.away in elo["ratings"]
        if not m.is_group and m.home_goals == m.away_goals:
            assert m.shootout_winner in (m.home, m.away)
    final = matches[-1]
    assert final.round == "F"


def test_backtest_el_modelo_supera_al_azar_en_todos_los_tramos():
    rep = run()
    for seg in ("grupos", "grupos_fuera_de_muestra", "eliminatorias"):
        assert rep[seg]["modelo"]["brier"] < rep[seg]["uniforme"]["brier"]
    assert sum(b["n"] for b in rep["calibracion_1x2"]) == 72 * 3
