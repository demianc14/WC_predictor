"""Dixon-Coles conjunto para la Champions: nombres, clubes sin liga y walk-forward sin fuga."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.clubs.data import Match
from src.europe import backtest
from src.europe import data as eu

FIX = Path(__file__).parent / "fixtures" / "clubs"
ROWS = json.loads((FIX / "europe_toy.json").read_text(encoding="utf-8"))


def test_el_feed_pasa_a_partidos_con_alias_y_sin_jugar():
    ms = eu.european(ROWS, "UCL", eu.season_of(2023))
    assert {m.season for m in ms} == {"2324"} and {m.div for m in ms} == {"UCL"}
    assert ms[0].home == "Inter" and ms[0].score() == (2, 0)          # "Internazionale"
    assert ms[2].away == "Man City"                                   # "Man. City"
    assert ms[3].away == "Porto" and not ms[3].played                  # "Porto" ya es football-data


def test_alias_de_las_ligas_extra_y_variantes_del_feed():
    assert eu.name("PSV") == "PSV Eindhoven" and eu.name("Sporting CP") == "Sp Lisbon"
    assert eu.name("Shakhtar Donetsk") == eu.name("Shakhtar")   # dos grafías
    assert eu.name("Atleti") == "Ath Madrid"    # de src/ml/europe.py


def test_un_nombre_en_dos_paises_no_se_permite():
    d = date(2024, 1, 6)
    with pytest.raises(ValueError, match="Nombres repetidos"):
        eu.check_names([Match("E0", "2324", d, "Rangers", "A", 1, 0),
                        Match("SC0", "2324", d, "Rangers", "B", 1, 0)])


def test_clubes_sin_liga_son_los_que_solo_juegan_en_europa():
    d = date(2024, 1, 6)
    ms = [Match("E0", "2324", d, "Arsenal", "Chelsea", 1, 0),
          Match("UCL", "2324", d, "Arsenal", "Celtic", 2, 0)]
    assert eu.without_league(ms) == {"Celtic"}


def _season(start: date) -> list[Match]:
    """Liga inglesa e italiana de juguete conectadas por partidos de Champions."""
    ms = []
    for w in range(30):
        d = start + timedelta(days=7 * w)
        ms += [Match("E0", "2425", d, "A", "B", 2, 0), Match("E0", "2425", d, "B", "A", 1, 1),
               Match("I1", "2425", d, "C", "D", 1, 0), Match("I1", "2425", d, "D", "C", 0, 2)]
        if w % 3 == 2:
            ms.append(Match("UCL", "2425", d + timedelta(days=3), "A", "C", 1 + w % 2, 1))
    return ms


def test_walk_forward_no_mira_el_dia_del_partido_ni_despues():
    ms = _season(date(2024, 8, 5))
    rows = backtest.walk_forward(ms, ("2425",))
    assert rows and all(r["home"] == "A" for r in rows)
    last = date.fromisoformat(rows[-1]["day"])
    otro = [Match(m.div, m.season, m.day, m.home, m.away, 9, 0) if m.day >= last else m
            for m in ms]                                               # cambia el futuro
    assert backtest.walk_forward(otro, ("2425",))[-1]["model"] == rows[-1]["model"]


def test_walk_forward_salta_al_debutante_sin_partidos_previos():
    ms = _season(date(2024, 8, 5)) + [Match("UCL", "2425", date(2024, 9, 18), "A", "Nuevo", 3, 0)]
    skipped: list[Match] = []
    rows = backtest.walk_forward(sorted(ms, key=lambda m: m.day), ("2425",), skipped=skipped)
    assert [m.away for m in skipped] == ["Nuevo"]
    assert all(r["away"] != "Nuevo" for r in rows)


def test_reporte_compara_modelo_y_base_sobre_la_misma_muestra():
    rows = backtest.walk_forward(_season(date(2024, 8, 5)), ("2425",))
    rep = backtest.report(rows)
    assert rep["model"]["n"] == rep["base"]["n"] == len(rows)
    assert set(rep["diff"]) == {"brier", "rps", "logloss"}


def test_fase_de_liga_normaliza_nombres_y_deja_afuera_las_eliminatorias():
    from src.europe import run
    rows = [{**ROWS[0], "RoundNumber": 8}, {**ROWS[1], "RoundNumber": 9}]
    cal = run.league_phase(rows)
    assert [(f.home, f.away) for f in cal] == [("Inter", "Celtic")]


def test_la_base_de_la_champions_solo_mira_temporadas_anteriores():
    from src.europe import run
    d = date(2025, 10, 1)
    ms = [Match("UCL", "2526", d, "A", "B", 1, 0), Match("UCL", "2627", d, "A", "B", 0, 1),
          Match("E0", "2526", d, "A", "B", 0, 0)]
    assert run.base_rates(ms) == [0.5, 0.25, 0.25]                      # 1 ficticio de cada


def _toy_ratings(n=36):
    from src.clubs.model import Ratings
    teams = [f"T{i:02d}" for i in range(1, n + 1)]
    att = {t: 2.0 - i * 0.04 for i, t in enumerate(teams)}           # T01 el mejor
    return teams, Ratings(teams, att, {t: 1 / a for t, a in att.items()}, 1.3, 1.2, -0.05)


def test_el_cuadro_usa_cada_puesto_del_1_al_24_una_vez():
    from src.europe import knockout
    puestos = sorted(p for fila in knockout.SIDE for par in fila for p in par)
    assert puestos == list(range(1, 25))


def test_cada_ronda_tiene_los_clubes_justos_y_un_campeon():
    import numpy as np

    from src.europe import knockout
    teams, r = _toy_ratings()
    br = knockout.Bracket(r, np.random.default_rng(1))
    for _ in range(50):
        reached = br.run(teams)
        assert len(reached) == 16 and set(teams[24:]).isdisjoint(reached)   # 25-36 afuera
        assert all(reached[t] >= 0 for t in teams[:8])                     # top 8 directo a octavos
        assert [sum(v >= k for v in reached.values()) for k in range(5)] == [16, 8, 4, 2, 1]


def test_la_llave_hereda_el_mejor_lugar_y_simulate_suma_uno_por_ronda():
    import numpy as np

    from src.europe import knockout
    teams, r = _toy_ratings()
    br = knockout.Bracket(r, np.random.default_rng(2))
    assert br.tie(("T20", 20), ("T05", 5))[1] == 5                       # gane quien gane
    fixtures = [(teams[i], teams[(i + 7) % 36]) for i in range(36)]
    out = knockout.simulate(r, [], teams, fixtures, n=300)
    for k, total in zip(knockout.ROUNDS, (16, 8, 4, 2, 1)):
        assert abs(sum(o["ko"][k] for o in out.values()) - total) < 36 * 5e-5   # redondeo
    assert out["T01"]["ko"]["champion"] > out["T30"]["ko"]["champion"]
