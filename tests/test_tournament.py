"""Tests del simulador de torneo (cuadro oficial FIFA) y del Breaking News Engine."""
import random

from src.agents.breaking_news import BreakingNewsEngine
from src.etl.pipeline import extract, transform, validate_rows
from src.simulation.tournament import R32, TournamentSimulator, assign_thirds, monte_carlo


def get_strengths():
    return transform(validate_rows(extract()))


def test_torneo_produce_campeon_reproducible():
    res1 = TournamentSimulator(get_strengths(), seed=42).run()
    res2 = TournamentSimulator(get_strengths(), seed=42).run()
    assert res1.champion == res2.champion
    assert res1.champion != res1.runner_up


def test_estructura_del_cuadro_oficial():
    res = TournamentSimulator(get_strengths(), seed=7).run()
    assert len(res.knockout["Dieciseisavos"]) == 16
    assert len(res.knockout["Octavos"]) == 8
    assert len(res.knockout["Cuartos"]) == 4
    assert len(res.knockout["Semifinal"]) == 2
    assert len(res.knockout["Final"]) == 1
    for table in res.group_tables.values():
        assert len(table) == 4
        assert sum(s.played for s in table) == 12


def test_terceros_caen_en_llaves_permitidas():
    res = TournamentSimulator(get_strengths(), seed=11).run()
    allowed = {m: b[2:] for m, _, b in R32 if b.startswith("3:")}
    assert len(res.third_slot_assign) == 8
    for match_id, group in res.third_slot_assign.items():
        assert group in allowed[match_id], f"{group} no permitido en {match_id}"


def test_assign_thirds_cubre_combinacion_dificil():
    # combinación arbitraria de 8 grupos: debe existir matching válido
    assign = assign_thirds(["A", "B", "C", "D", "E", "F", "G", "H"])
    assert len(set(assign.values())) == 8


def test_resultados_fijados_se_respetan():
    fixed = {"C|0": (0, 5)}  # BRA 0-5 MAR
    sim = TournamentSimulator(get_strengths(), seed=3, fixed_group_results=fixed)
    res = sim.run()
    m = res.group_matches["C"][0]
    assert (m.home, m.away, m.home_goals, m.away_goals) == ("BRA", "MAR", 0, 5)


def test_montecarlo_probabilidades_suman_1():
    probs = monte_carlo(get_strengths(), n=50, seed=1)
    assert abs(sum(p["champion"] for p in probs.values()) - 1.0) < 1e-6


def test_breaking_news_inyectado_baja_contexto():
    eng = BreakingNewsEngine(rng=random.Random(0), enabled=False)
    eng.inject("BRA", -0.2, "Lesión de la figura")
    ctx, news = eng.roll_for_match("BRA")
    assert ctx == 0.3
    assert "Lesión" in news[0]
