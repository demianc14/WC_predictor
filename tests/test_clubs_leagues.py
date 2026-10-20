"""Cinco ligas: formato de cada CSV, cruce de nombres con el calendario,
validación de la liga a dos ruedas y ajuste del modelo en cada liga."""
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.clubs.backtest import base_rates, score
from src.clubs.calendar import (
    Fixture,
    check_against,
    match_names,
    parse_calendar,
    pending,
    repair_round_robin,
)
from src.clubs.data import Match, parse_csv
from src.clubs.leagues import LEAGUES
from src.clubs.model import fit
from src.clubs.run import next_matches
from src.clubs.season import simulate

FIX = Path(__file__).parent / "fixtures" / "clubs"


@pytest.mark.parametrize("code", sorted(LEAGUES))
def test_csv_real_de_cada_liga(code):
    """Primeras filas reales de 2026-27: resultado, xG y cuotas de cierre."""
    ms = parse_csv((FIX / f"{code}_2627.csv").read_text(encoding="utf-8-sig"), "2627")
    assert len(ms) == 4
    for m in ms:
        assert m.div == code and m.played and m.day.year == 2026
        assert m.hxg is not None and m.axg is not None
        assert m.odds and all(o > 1 for o in m.odds)


def test_csv_viejo_sin_xg():
    (m, *_) = parse_csv((FIX / "E0_2324.csv").read_text(encoding="utf-8-sig"), "2324")
    assert m.played and m.hxg is None and m.odds


def _match(h, a, hg, ag, day):
    return Match("SP1", "2627", day, h, a, hg, ag)


def _fixture(h, a, hg, ag, day, rnd=1):
    return Fixture(rnd, day, h, a, hg, ag, tbc=False)


D = date(2026, 8, 15)


def test_cruce_de_nombres_por_resultados():
    played = [_match("Alaves", "Getafe", 3, 0, D), _match("Sevilla", "Vallecano", 2, 1, D),
              _match("Getafe", "Sevilla", 1, 1, D + timedelta(days=7))]
    cal = [_fixture("Deportivo Alavés", "Getafe CF", 3, 0, D),
           # medianoche UTC: un día corrido respecto de football-data
           _fixture("Sevilla FC", "Rayo Vallecano", 2, 1, D - timedelta(days=1)),
           _fixture("Getafe CF", "Sevilla FC", 1, 1, D + timedelta(days=7))]
    assert match_names(cal, played) == {
        "Deportivo Alavés": "Alaves", "Getafe CF": "Getafe",
        "Sevilla FC": "Sevilla", "Rayo Vallecano": "Vallecano"}


def test_cruce_falla_con_el_nombre_exacto_sin_pareja():
    played = [_match("Alaves", "Getafe", 3, 0, D)]
    cal = [_fixture("Deportivo Alavés", "Getafe CF", 3, 0, D),
           _fixture("Real Oviedo", "Getafe CF", None, None, D + timedelta(days=7))]
    with pytest.raises(ValueError, match="Real Oviedo"):
        match_names(cal, played)


def test_check_against_detecta_marcadores_distintos():
    with pytest.raises(ValueError, match="Alaves-Getafe"):
        check_against([_fixture("Alaves", "Getafe", 2, 0, D)],
                      [_match("Alaves", "Getafe", 3, 0, D)])


def _round_robin(teams):
    return [_fixture(h, a, None, None, D) for h in teams for a in teams if h != a]


def test_round_robin_invierte_el_cruce_repetido():
    cal = _round_robin("ABC")
    i = next(i for i, f in enumerate(cal) if (f.home, f.away) == ("B", "A"))
    cal.pop(i)
    cal.append(_fixture("A", "B", None, None, D + timedelta(days=90), rnd=4))  # error del feed
    fixed, fixes = repair_round_robin(cal, 3)
    assert sorted((f.home, f.away) for f in fixed) == sorted(
        (f.home, f.away) for f in _round_robin("ABC"))
    assert fixes == ["jornada 4: A-B repetido, se invierte a B-A"]


def test_round_robin_rechaza_un_calendario_incompleto():
    with pytest.raises(ValueError, match="dos ruedas"):
        repair_round_robin(_round_robin("ABC")[:-1], 3)


def test_parse_calendar_marca_horarios_sin_confirmar():
    rows = [{"RoundNumber": 9, "DateUtc": "2026-10-24 00:00:00Z", "HomeTeam": "A",
             "AwayTeam": "B", "HomeTeamScore": None, "AwayTeamScore": None},
            {"RoundNumber": 9, "DateUtc": "2026-10-24 14:00:00Z", "HomeTeam": "C",
             "AwayTeam": "D", "HomeTeamScore": None, "AwayTeamScore": None}]
    a, c = parse_calendar(rows)
    assert a.tbc and not c.tbc and a.day == date(2026, 10, 24)


def test_pending_usa_lo_jugado_en_football_data():
    cal = [_fixture("A", "B", None, None, D), _fixture("B", "A", None, None, D)]
    assert [(f.home, f.away) for f in pending(cal, [_match("A", "B", 1, 0, D)])] == [("B", "A")]


def _liga(teams: list[str], seed: int = 3) -> list[Match]:
    """Liga sintética a dos ruedas, con el primer equipo bastante más fuerte."""
    rng = random.Random(seed)
    att = {t: 1.0 + (0.8 if i == 0 else 0.0) for i, t in enumerate(teams)}

    def pois(lam: float) -> int:
        k, p, lim = 0, 1.0, 2.718281828 ** -lam
        while True:
            p *= rng.random()
            if p < lim:
                return k
            k += 1

    out, day = [], date(2025, 8, 1)
    for h in teams:
        for a in teams:
            if h != a:
                out.append(Match("X", "2526", day, h, a, pois(1.5 * att[h]), pois(1.2 * att[a])))
                day += timedelta(days=1)
    return out


@pytest.mark.parametrize("code", sorted(LEAGUES))
def test_modelo_ajusta_y_simula_cada_liga(code):
    lg = LEAGUES[code]
    teams = [f"T{i:02d}" for i in range(lg.teams)]
    ms = _liga(teams)
    assert len(ms) == lg.matches and lg.rounds == 2 * (lg.teams - 1)
    half = ms[: len(ms) // 2]
    r = fit(ms, ms[-1].day + timedelta(days=1))
    assert set(r.att) == set(teams) and r.home > 1.0
    assert max(r.att, key=r.att.get) == "T00"
    rest = [(m.home, m.away) for m in ms[len(ms) // 2:]]
    out = simulate(r, half, teams, n=200, fixtures=rest)
    for i in range(lg.teams):
        assert abs(sum(out[t]["pos"][i] for t in teams) - 1) < 1e-6


def test_base_rates_solo_mira_el_pasado():
    ms = [Match("E0", "2526", D + timedelta(days=i), "A", "B", 1, 0) for i in range(3)]
    assert base_rates(ms, "E0", D) == [1 / 3] * 3            # nada antes: solo el prior
    assert base_rates(ms, "E0", D + timedelta(days=2)) == [3 / 5, 1 / 5, 1 / 5]


def test_score_reporta_rps_y_n():
    rows = [{"o": 0, "p": [1.0, 0.0, 0.0]}, {"o": 2, "p": [0.0, 1.0, 0.0]}]
    s = score(rows, "p")
    assert s["n"] == 2 and s["brier"] == 1.0 and s["rps"] == 0.25 and s["hit"] == 0.5


def test_next_matches_une_calendario_y_cuotas():
    ms = _liga(["A", "B", "C"])
    r = fit(ms, ms[-1].day + timedelta(days=1))
    day = date(2026, 10, 24)
    cal = [Fixture(9, day, "A", "B", None, None, tbc=True),
           Fixture(9, day, "B", "C", None, None, tbc=True)]
    fd = [Match("E0", "2627", day, "A", "B", odds=(2.0, 3.5, 4.0)),
          Match("E0", "2627", day, "Z", "A", odds=(2.0, 3.5, 4.0))]   # Z no está en el modelo
    out = next_matches(r, fd, cal)
    assert [(n["home"], n["away"]) for n in out] == [("A", "B"), ("B", "C")]
    ab, bc = out
    assert ab["market"] and not ab["tbc"] and ab["round"] == 9
    assert bc["market"] is None and bc["tbc"]
    assert abs(sum(ab["model"]) - 1) < 1e-3
