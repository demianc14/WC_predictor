"""Partido y cuotas entre clubes: mismo resultado que el modelo ajustado."""

import pytest

from src.clubs.h2h import find_team, lambdas, predict, report
from src.clubs.model import Ratings

LG = {
    "name": "Liga de prueba", "updated": "2026-10-19",
    "params": {"mu": 1.3, "home": 1.2, "rho": -0.05},
    "teams": [{"t": "Man City", "n": "Manchester City", "att": 1.6, "def": 0.6},
              {"t": "Man United", "n": "Manchester United", "att": 1.1, "def": 1.0},
              {"t": "Ath Madrid", "n": "Atlético de Madrid", "att": 1.2, "def": 0.8}],
}


def test_busca_por_nombre_corto_largo_o_parcial_sin_acentos():
    assert find_team(LG, "man city")["t"] == "Man City"
    assert find_team(LG, "Manchester United")["t"] == "Man United"
    assert find_team(LG, "atletico")["t"] == "Ath Madrid"


def test_nombre_ambiguo_o_inexistente_falla_con_opciones():
    with pytest.raises(ValueError, match="ambiguo.*Manchester City"):
        find_team(LG, "manchester")
    with pytest.raises(ValueError, match="no está"):
        find_team(LG, "Real Oviedo")


def test_coincide_con_el_modelo_ajustado():
    names = [t["t"] for t in LG["teams"]]
    r = Ratings(names, {t["t"]: t["att"] for t in LG["teams"]},
                {t["t"]: t["def"] for t in LG["teams"]}, mu=1.3, home=1.2, rho=-0.05)
    h, a, p = predict(LG, "Man City", "Ath Madrid")
    assert lambdas(LG, h, a) == pytest.approx(r.lambdas("Man City", "Ath Madrid"))
    ph, pd, pa, _ = r.probs("Man City", "Ath Madrid")
    assert (p.p_home, p.p_draw, p.p_away) == pytest.approx((ph, pd, pa), abs=1e-12)
    assert p.p_home + p.p_draw + p.p_away == pytest.approx(1)


def test_localia_cambia_el_favorito():
    _, _, ida = predict(LG, "Man United", "Ath Madrid")
    _, _, vuelta = predict(LG, "Ath Madrid", "Man United")
    assert ida.p_home > vuelta.p_away


def test_mismo_club_falla():
    with pytest.raises(ValueError, match="distintos"):
        predict(LG, "Man City", "manchester city")


def test_reporte_con_cuotas_muestra_ev():
    h, a, p = predict(LG, "Man City", "Man United")
    txt = report(LG, h, a, p, odds=(1.5, 4.5, 6.0))
    assert "Manchester City vs Manchester United" in txt and "EV" in txt
