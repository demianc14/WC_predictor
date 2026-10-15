"""xG de StatsBomb: resumen de eventos, ratings por rival e integración al ETL."""
from datetime import date

import pytest

import src.etl.scrapers.statsbomb as sb
from src.etl.pipeline import enrich_with_statsbomb, extract, validate_rows
from src.etl.scrapers.statsbomb import TeamMatch, summarize_events, team_rows
from src.etl.xg_ratings import fit_ratings


def _shot(team, xg, minute=10, period=1, kind="Open Play", outcome="Saved"):
    return {"period": period, "minute": minute, "second": 0, "team": {"name": team},
            "player": {"name": "X"}, "type": {"name": "Shot"}, "location": [100, 40],
            "shot": {"statsbomb_xg": xg, "type": {"name": kind},
                     "outcome": {"name": outcome}, "body_part": {"name": "Right Foot"}}}


def test_resumen_excluye_tanda_y_marca_penales():
    events = [
        _shot("Spain", 0.30),
        _shot("Spain", 0.78, kind="Penalty", outcome="Goal"),
        _shot("Italy", 0.10, minute=118, period=4),
        _shot("Italy", 0.78, minute=121, period=5, kind="Penalty"),  # tanda
    ]
    summary = summarize_events(events)
    assert len(summary["shots"]) == 3
    assert summary["minutes"] == 118

    match = {"match_id": 1, "match_date": "2024-07-01", "home_score": 1, "away_score": 1,
             "home_team": {"home_team_name": "Spain"},
             "away_team": {"away_team_name": "Italy"}}
    esp, ita = team_rows(match, summary, "Euro 2024")
    assert esp.xg == pytest.approx(1.08) and esp.np_xg == pytest.approx(0.30)
    assert esp.np_xg_against == pytest.approx(0.10)
    assert ita.opponent == "Spain" and ita.shots == 1


def _tm(team, opp, npxg, npxga, d=date(2024, 6, 20)):
    return TeamMatch(match_id=hash((team, opp, d)) % 10**6, date=d, competition="T 2024",
                     team=team, opponent=opp, minutes=90, goals=0, goals_against=0,
                     xg=npxg, np_xg=npxg, xg_against=npxga, np_xg_against=npxga, shots=10)


def test_ratings_ajustan_por_rival():
    """A y B generan el mismo xG crudo, pero A lo hace contra el rival más duro."""
    rows = []
    for _ in range(4):
        rows += [_tm("A", "Duro", 1.2, 1.0), _tm("Duro", "A", 1.0, 1.2),
                 _tm("B", "Blando", 1.2, 1.0), _tm("Blando", "B", 1.0, 1.2),
                 _tm("Duro", "Blando", 1.5, 0.5), _tm("Blando", "Duro", 0.5, 1.5)]
    r = fit_ratings(rows, today=date(2024, 7, 1))
    assert r["A"].raw_xg_for == pytest.approx(r["B"].raw_xg_for)
    assert r["A"].xg_for > r["B"].xg_for
    assert r["Duro"].defe < r["Blando"].defe


def test_recencia_pesa_mas_lo_reciente():
    rows = [_tm("A", "B", 2.0, 0.5, date(2024, 6, 1)), _tm("B", "A", 0.5, 2.0, date(2024, 6, 1)),
            _tm("A", "B", 0.5, 2.0, date(2020, 6, 1)), _tm("B", "A", 2.0, 0.5, date(2020, 6, 1))]
    r = fit_ratings(rows, today=date(2024, 7, 1))
    assert r["A"].xg_for > r["B"].xg_for


def test_enrich_mezcla_con_csv(monkeypatch, tmp_path):
    teams = validate_rows(extract())
    esp = next(t for t in teams if t.fifa_code == "ESP")
    rows = []
    for i in range(6):
        d = date(2024, 6, 10 + i)
        rows += [_tm("Spain", "France", 2.5, 0.3, d), _tm("France", "Spain", 0.3, 2.5, d)]
    monkeypatch.setattr(sb, "load_team_matches", lambda **_: rows)
    out = {t.fifa_code: t for t in enrich_with_statsbomb(teams, xg_path=tmp_path / "xg.json")}
    assert (tmp_path / "xg.json").exists()
    # España sube su xG a favor respecto del CSV; un equipo sin datos no cambia
    assert out["ESP"].xg_for > esp.xg_for
    assert out["HAI"] == next(t for t in teams if t.fifa_code == "HAI")


def test_enrich_sin_datos_deja_el_csv(monkeypatch, tmp_path):
    teams = validate_rows(extract())
    monkeypatch.setattr(sb, "load_team_matches", lambda **_: [])
    assert enrich_with_statsbomb(teams, xg_path=tmp_path / "xg.json") == teams
