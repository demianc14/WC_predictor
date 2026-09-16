"""Tests de los contratos de datos (Pydantic)."""
import pytest
from pydantic import ValidationError

from src.etl.models import MatchResult, Stage, Team, TeamStrength


def make_team(**overrides):
    base = dict(
        name="Brazil", fifa_code="bra", group="C", confederation="CONMEBOL",
        fifa_rank=5, wc_titles=5, wc_appearances=22, best_finish=1.0,
        form_last10="WWWDWLWWDW", xg_for=2.1, xg_against=0.8,
    )
    base.update(overrides)
    return Team(**base)


def test_team_valido_normaliza_codigo():
    assert make_team().fifa_code == "BRA"


def test_team_rechaza_form_invalida():
    with pytest.raises(ValidationError):
        make_team(form_last10="WWXDWLWWDW")  # 'X' no es W/D/L


def test_team_rechaza_grupo_inexistente():
    with pytest.raises(ValidationError):
        make_team(group="Z")  # solo A-L


def test_match_rechaza_mismo_equipo():
    with pytest.raises(ValidationError):
        MatchResult(stage=Stage.FINAL, home="BRA", away="BRA", home_goals=1, away_goals=0)


def test_match_winner_y_empate():
    m = MatchResult(stage=Stage.GROUP, home="BRA", away="MAR", home_goals=2, away_goals=2)
    assert m.winner is None
    m2 = MatchResult(stage=Stage.GROUP, home="BRA", away="MAR", home_goals=3, away_goals=1)
    assert m2.winner == "BRA"


def test_final_strength_respeta_pesos():
    s = TeamStrength(fifa_code="BRA", name="Brazil", group="C",
                     prior=0.8, likelihood=0.8, posterior=0.8)
    # contexto neutro: 0.7*0.8 + 0.3*0.5 = 0.71
    assert abs(s.final_strength(0.5) - 0.71) < 1e-9
    # contexto se recorta a [0,1]
    assert s.final_strength(5.0) == s.final_strength(1.0)
