"""Tests del modulo de resiliencia y el modificador en el match engine."""
from src.etl.resilience import _shrink
from src.simulation.match_engine import (
    RESILIENCE_GAP_SATURATION,
    RESILIENCE_GAP_THRESHOLD,
    RESILIENCE_MAX_REDUCTION,
    resilience_modifier,
)


def test_shrink_a_baseline_con_muestra_cero():
    assert _shrink(0.0, 0, k=4, baseline=0.5) == 0.5
    assert _shrink(1.0, 0, k=4, baseline=0.5) == 0.5


def test_shrink_converge_a_raw_con_muestra_grande():
    # con n>>k el raw domina
    assert abs(_shrink(0.8, 100, k=4, baseline=0.5) - 0.8) < 0.02


def test_modifier_inactivo_si_gap_chico():
    # gap por debajo del threshold: no actua, sin importar resiliencia
    assert resilience_modifier(0.9, RESILIENCE_GAP_THRESHOLD - 0.01) == 1.0
    assert resilience_modifier(0.1, RESILIENCE_GAP_THRESHOLD - 0.01) == 1.0
    # gap negativo (yo soy mejor): tampoco actua
    assert resilience_modifier(0.9, -0.3) == 1.0


def test_modifier_alta_resiliencia_baja_defe_en_gap_grande():
    # resiliencia 1.0, gap saturado -> reduccion maxima
    factor = resilience_modifier(1.0, RESILIENCE_GAP_SATURATION + 0.1)
    assert abs(factor - (1.0 - RESILIENCE_MAX_REDUCTION)) < 1e-6
    # resiliencia 0.5 -> factor 1.0 (neutro)
    assert resilience_modifier(0.5, 0.5) == 1.0
    # baja resiliencia: factor > 1 (defe peor)
    assert resilience_modifier(0.0, RESILIENCE_GAP_SATURATION + 0.1) > 1.0


def test_modifier_es_monotonico_en_resiliencia():
    gap = 0.30
    factors = [resilience_modifier(r, gap) for r in [0.0, 0.25, 0.5, 0.75, 1.0]]
    # a mayor resiliencia, menor factor
    assert factors == sorted(factors, reverse=True)
