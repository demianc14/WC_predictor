"""Tests del modulo de cuotas analiticas."""
from src.betting.odds import MatchProbabilities, compute_match_probabilities


def test_probabilidades_suman_uno():
    p = compute_match_probabilities(1.5, 1.2)
    assert abs(p.p_home + p.p_draw + p.p_away - 1.0) < 1e-6
    assert abs(p.p_btts + p.p_no_btts - 1.0) < 1e-6
    for line, over in p.p_over.items():
        assert abs(over + p.p_under[line] - 1.0) < 1e-6


def test_favorito_claro_es_mas_probable():
    # lambdas asimetricas -> el equipo con lambda mayor gana mas seguido.
    p = compute_match_probabilities(2.5, 0.6)
    assert p.p_home > p.p_away
    assert p.p_home > 0.65


def test_value_kelly_solo_si_ev_positivo():
    # p_model=0.5, cuota libro=2.5 -> EV=+0.25, Kelly=(0.25)/(1.5)=0.1667
    v = MatchProbabilities.value(0.5, 2.5)
    assert v["ev"] > 0
    assert 0.15 < v["kelly"] < 0.18
    # p_model=0.3, cuota libro=2.5 -> EV=-0.25, Kelly debe ser 0 (no apostar)
    v2 = MatchProbabilities.value(0.3, 2.5)
    assert v2["ev"] < 0
    assert v2["kelly"] == 0.0


def test_top_scorelines_estan_ordenados():
    p = compute_match_probabilities(1.4, 1.4)
    probs = [s[2] for s in p.top_scorelines]
    assert probs == sorted(probs, reverse=True)
    assert len(p.top_scorelines) == 5
