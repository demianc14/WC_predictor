"""Tests del motor Maher + Dixon-Coles."""
import random

import pytest

from src.etl.models import Stage, TeamStrength
from src.simulation.match_engine import (
    BASE,
    expected_goals_pair,
    poisson_sample,
    sample_score_dc,
    simulate_match,
    tau,
)


def make(code, post, att, defe):
    return TeamStrength(fifa_code=code, name=code, group="A",
                        prior=post, likelihood=post, posterior=post,
                        att=att, defe=defe)


def test_tau_corrige_solo_marcadores_bajos():
    lam, mu = 1.3, 1.1
    assert tau(0, 0, lam, mu) > 1.0   # ρ<0 -> sube 0-0
    assert tau(1, 1, lam, mu) > 1.0   # sube 1-1
    assert tau(1, 0, lam, mu) < 1.0   # baja 1-0
    assert tau(0, 1, lam, mu) < 1.0   # baja 0-1
    assert tau(2, 1, lam, mu) == 1.0  # el resto intacto
    assert tau(3, 3, lam, mu) == 1.0


def test_dixon_coles_sube_empates_bajos():
    """La firma estadística de DC: más 0-0/1-1 que el Poisson independiente."""
    rng = random.Random(42)
    N = 60000
    lam, mu = 1.3, 1.1
    dc_low = pois_low = 0
    for _ in range(N):
        x, y = sample_score_dc(lam, mu, rng)
        if (x, y) in ((0, 0), (1, 1)):
            dc_low += 1
        x, y = poisson_sample(lam, rng), poisson_sample(mu, rng)
        if (x, y) in ((0, 0), (1, 1)):
            pois_low += 1
    # Con rho=-0.13 el aumento teórico es ~13-15%; exigimos al menos +5%
    assert dc_low > pois_low * 1.05


def test_maher_att_def_definen_perfil():
    """Mismo posterior, perfiles distintos -> lambdas distintas."""
    atacante = make("ATT", 0.7, att=1.5, defe=1.2)   # anota y concede mucho
    cerrojo = make("DEF", 0.7, att=0.8, defe=0.6)    # anota poco, concede poco
    la, lb = expected_goals_pair(atacante, cerrojo)
    # El atacante enfrenta defensa sólida (0.6); el cerrojo enfrenta colador (1.2)
    assert la == pytest.approx(BASE * 1.5 * 0.6)   # misma clase -> exp(0)=1
    assert lb == pytest.approx(BASE * 0.8 * 1.2)


def test_lambdas_acotadas():
    crack = make("AAA", 1.0, att=2.5, defe=0.2)
    debil = make("ZZZ", 0.0, att=0.2, defe=2.5)
    la, lb = expected_goals_pair(crack, debil)
    assert la <= 4.5 and lb >= 0.15


def test_simulate_match_sigue_funcionando():
    rng = random.Random(1)
    a, b = make("AAA", 0.8, 1.3, 0.8), make("BBB", 0.5, 1.0, 1.0)
    m = simulate_match(a, b, Stage.FINAL, rng)
    assert m.winner in ("AAA", "BBB")  # eliminación directa siempre decide
