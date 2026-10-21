"""Piloto de clubes: parser de football-data, ajuste Dixon-Coles y simulación."""
import random
from datetime import date, timedelta

from src.clubs.backtest import no_vig
from src.clubs.data import Match, parse_csv
from src.clubs.model import fit
from src.clubs.season import remaining_fixtures, simulate

CSV = """﻿Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,HxG,AxG,AvgH,AvgD,AvgA,AvgCH,AvgCD,AvgCA
E0,15/08/2026,20:00,Arsenal,Hull,3,0,2.4,0.5,1.3,5.5,9.0,1.25,6.0,11.0
E0,16/08/26,15:00,Hull,Arsenal,,,,,4.0,3.6,1.9,,,
"""


def test_parse_csv_fechas_xg_y_cuotas_de_cierre():
    a, b = parse_csv(CSV, "2627")
    assert a.day == date(2026, 8, 15) and a.played and (a.hg, a.ag) == (3, 0)
    assert a.hxg == 2.4 and a.odds == (1.25, 6.0, 11.0)   # prefiere cierre
    assert b.day == date(2026, 8, 16) and not b.played
    assert b.odds == (4.0, 3.6, 1.9)                       # sin cierre: promedio


def _liga(n_rounds: int = 6, seed: int = 1) -> list[Match]:
    """Liga sintética: A ataca mucho, D defiende mal."""
    rng = random.Random(seed)
    att = {"A": 2.0, "B": 1.2, "C": 1.0, "D": 0.8}
    dfn = {"A": 0.7, "B": 1.0, "C": 1.0, "D": 1.5}

    def pois(lam: float) -> int:
        k, p, L = 0, 1.0, 2.718281828 ** -lam
        while True:
            p *= rng.random()
            if p < L:
                return k
            k += 1

    out, day = [], date(2026, 1, 1)
    for _ in range(n_rounds):
        for h in att:
            for a in att:
                if h != a:
                    out.append(Match("E0", "2627", day, h, a, pois(1.3 * 1.2 * att[h] * dfn[a]),
                                     pois(1.3 * att[a] * dfn[h])))
                    day += timedelta(days=1)
    return out


def test_fit_recupera_el_orden_de_fuerzas():
    ms = _liga()
    r = fit(ms, ms[-1].day + timedelta(days=1), prior=1.0)
    assert max(r.att, key=r.att.get) == "A"
    assert max(r.defe, key=r.defe.get) == "D"      # defensa alta = concede más
    assert r.home > 1.0
    ph, pd, pa, g = r.probs("A", "D")
    assert ph > 0.6 and abs(ph + pd + pa - 1) < 1e-9


def test_simulacion_reparte_todas_las_posiciones():
    ms = _liga(n_rounds=1)
    played = ms[:6]
    teams = ["A", "B", "C", "D"]
    assert len(remaining_fixtures(played, teams)) == 6
    out = simulate(fit(ms, ms[-1].day), played, teams, n=500)
    for i in range(4):
        assert abs(sum(out[t]["pos"][i] for t in teams) - 1) < 1e-6
    assert out["A"]["pos"][0] > out["D"]["pos"][0]


def test_no_vig_quita_el_margen():
    p = no_vig((2.0, 3.4, 3.8))
    assert abs(sum(p) - 1) < 1e-12 and p[0] > p[2]


def test_score_solo_para_partidos_jugados():
    import pytest
    a, b = parse_csv(CSV, "2627")
    assert a.score() == (3, 0)
    with pytest.raises(ValueError, match="no se jugó"):
        b.score()
