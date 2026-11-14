"""Champions: eliminatorias en el almacén (T2), con el feed real de 2025-26 como fixture.

En ese feed las eliminatorias son las rondas 9 a 17: playoff 9/10, octavos 11/12,
cuartos 13/14, semis 15/16 y final 17. El marcador no distingue la prórroga, así que
al almacén solo van las idas (9, 11, 13 y 15), que nunca la tienen.
"""
import csv
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.clubs.model import Ratings
from src.europe import data as eu
from src.europe import run
from src.pipeline import daily, store

FIX = Path(__file__).parent / "fixtures" / "ucl_eliminatorias_2025.json"
KO = json.loads(FIX.read_text(encoding="utf-8"))
RATED = {eu.name(m[k]) for m in KO for k in ("HomeTeam", "AwayTeam")}


# --- match_id ---------------------------------------------------------------------------

def test_los_ids_de_la_fase_de_liga_ya_guardados_no_cambian():
    # Copia de las filas UCL del almacén al 14-nov (data/ no entra a la imagen Docker).
    with (FIX.parent / "ucl_ids_almacen.csv").open(encoding="utf-8", newline="") as f:
        ucl = list(csv.DictReader(f))
    assert len(ucl) == 9                                         # hay filas para comparar
    for r in ucl:
        assert store.match_id("UCL", r["season"], r["home"], r["away"]) == r["match_id"]
        assert store.ko_round(r["match_id"]) is None


def test_el_id_de_eliminatorias_no_choca_con_la_fase_de_liga_ni_entre_rondas():
    liga = store.match_id("UCL", "2526", "Benfica", "Real Madrid")
    r9 = store.match_id("UCL", "2526", "Benfica", "Real Madrid", ko_round=9)
    assert r9 == "UCL-2526-R9-Benfica-Real_Madrid" and r9 != liga
    assert store.ko_round(r9) == 9 and store.ko_round(liga) is None
    assert store.ko_round(store.match_id("UCL", "2526", "RB Leipzig", "R1", None)) is None


def test_en_el_feed_real_los_cruces_de_eliminatorias_repiten_cruces_de_la_fase_de_liga():
    # Por eso hace falta la ronda en el id (medido sobre 2025-26: 7 cruces repetidos).
    liga = json.loads((FIX.parent / "ucl_fase_liga_2025.json").read_text(encoding="utf-8"))
    pares = {(m["HomeTeam"], m["AwayTeam"]) for m in liga if m["RoundNumber"] <= 8}
    ko = [(m["HomeTeam"], m["AwayTeam"]) for m in KO]
    assert sum(p in pares for p in ko) == 7 and len(set(ko)) == len(ko)


# --- lectura del feed -------------------------------------------------------------------

def test_el_feed_2025_26_trae_las_eliminatorias_completas_y_normalizadas():
    fx, skipped = run.knockout_phase(KO, RATED)
    assert skipped == [] and len(fx) == 45
    assert Counter(f.round for f in fx) == run.KO_ROUNDS
    assert ("Ath Madrid" in {f.home for f in fx}) and "Atleti" not in {f.home for f in fx}


def test_una_ronda_incompleta_o_con_un_club_sin_rating_no_entra_y_se_avisa():
    primero = min(x["MatchNumber"] for x in KO if x["RoundNumber"] == 11)
    sin_uno = [m for m in KO if m["MatchNumber"] != primero]
    fx, skipped = run.knockout_phase(sin_uno, RATED)
    assert 11 not in {f.round for f in fx} and len(fx) == 45 - 8
    assert len(skipped) == 1 and skipped[0].startswith("ronda 11")

    provisional = [{**m, "HomeTeam": "To be announced"} if m["RoundNumber"] == 9 else m
                   for m in KO]
    fx, skipped = run.knockout_phase(provisional, RATED)
    assert 9 not in {f.round for f in fx} and 10 in {f.round for f in fx}
    assert skipped[0].startswith("ronda 9") and "To be announced" in skipped[0]


def test_sin_eliminatorias_en_el_feed_no_hay_nada_ni_avisos():
    liga = [{**KO[0], "RoundNumber": 8}]
    assert run.knockout_phase(liga, RATED) == ([], [])


# --- qué se predice y qué se guarda ----------------------------------------------------

def _ratings(teams):
    att = {t: 1.0 + 0.01 * i for i, t in enumerate(sorted(teams))}
    return Ratings(sorted(teams), att, {t: 1.0 for t in teams}, 1.4, 1.25, -0.05)


def test_solo_las_idas_se_guardan_y_la_final_se_predice_en_cancha_neutral():
    fx, _ = run.knockout_phase(KO, RATED)
    r = _ratings(RATED)
    rows = run.ko_next(r, fx, date(2026, 2, 16)) + run.ko_next(r, fx, date(2026, 5, 29))
    by_round = {n["ko_round"]: n for n in rows}
    assert {n["ko_round"] for n in rows} == {9, 17}              # la semana de cada fecha
    assert all(n["stored"] for n in rows if n["ko_round"] == 9)
    assert by_round[17]["stored"] is False and by_round[17]["neutral"] is True
    fin = next(f for f in fx if f.round == 17)
    p_local = run._pred(r, fin.home, fin.away)["model"]
    p_neutral = by_round[17]["model"]
    assert p_neutral[0] < p_local[0]                             # sin ventaja de local
    assert all(not n["stored"] for n in run.ko_next(r, fx, date(2026, 2, 23)))   # vueltas


def test_los_resultados_que_salen_son_solo_idas_jugadas_antes_de_hoy():
    fx, _ = run.knockout_phase(KO, RATED)
    res = run.ko_results(fx, date(2026, 3, 11))                  # el día de una ida de octavos
    assert {x[0] for x in res} == {9, 11}
    assert all(date.fromisoformat(x[1]) < date(2026, 3, 11) for x in res)
    assert len(res) == 8 + sum(1 for f in fx if f.round == 11 and f.day < date(2026, 3, 11))


@pytest.mark.parametrize("hoy, ko, skipped, estado", [
    (date(2027, 1, 10), False, [], "sin_publicar"),             # la fase de liga no terminó
    (date(2027, 2, 5), False, [], "sin_publicar"),              # terminó hace menos de 14 días
    (date(2027, 2, 12), False, [], "atrasado"),                 # 16 días sin playoff publicado
    (date(2027, 2, 12), True, [], "publicado"),
    (date(2027, 2, 12), True, ["ronda 11: 7 partidos (se esperan 8)"], "incompleto"),
])
def test_el_estado_del_feed_avisa_si_el_playoff_no_aparece(hoy, ko, skipped, estado):
    from src.clubs.calendar import Fixture
    liga = [Fixture(8, date(2027, 1, 27), "A", "B", 1 if hoy > date(2027, 1, 27) else None,
                    0 if hoy > date(2027, 1, 27) else None, False)]
    fx = [Fixture(9, date(2027, 2, 16), "A", "B", None, None, False)] if ko else []
    st = run.ko_status(liga, fx, skipped, hoy)
    assert st["state"] == estado and st["skipped"] == skipped


# --- ciclo diario -----------------------------------------------------------------------

def test_el_ciclo_guarda_la_ida_con_su_ronda_completa_su_resultado_y_mide_por_fase(
        tmp_path, monkeypatch):
    from tests.test_pipeline_daily import LG, _out
    monkeypatch.setattr(daily.data, "load_matches", lambda divs, seasons: [])
    ida = {"day": "2027-02-16", "round": 9, "ko_round": 9, "stored": True,
           "home": "Benfica", "away": "Real Madrid", "model": [0.3, 0.25, 0.45]}
    vuelta = {**ida, "day": "2027-02-24", "round": 10, "ko_round": 10, "stored": False,
              "home": "Real Madrid", "away": "Benfica"}
    liga = {"day": "2027-02-16", "round": 8, "home": "Benfica", "away": "Real Madrid",
            "model": [0.4, 0.3, 0.3]}

    def cyc(ucl, now):
        return daily.cycle(now, LG, fetcher=lambda: None, builder=lambda lg, today: _out(),
                           version="v1", commit="abc", store_path=tmp_path / "p.csv",
                           out_dir=tmp_path / "out", europe_builder=lambda today: ucl,
                           europe_version="v1+e1")
    base = {"season": "2627", "base": [0.5, 0.2, 0.3], "results": [], "ko_results": []}
    cyc({**base, "next": [ida, vuelta, liga]}, datetime(2027, 2, 15, 5, 30, tzinfo=timezone.utc))
    later = datetime(2027, 2, 17, 5, 30, tzinfo=timezone.utc)
    r = cyc({**base, "next": [], "results": [["2027-02-16", "Benfica", "Real Madrid", 0, 0]],
             "ko_results": [[9, "2027-02-16", "Benfica", "Real Madrid", 1, 0]]}, later)
    ucl = {x["match_id"]: x for x in store.load(tmp_path / "p.csv") if x["league"] == "UCL"}
    assert set(ucl) == {"UCL-2627-R9-Benfica-Real_Madrid", "UCL-2627-Benfica-Real_Madrid"}
    assert ucl["UCL-2627-R9-Benfica-Real_Madrid"]["result"] == "H"          # 1-0 de la ida
    assert ucl["UCL-2627-Benfica-Real_Madrid"]["result"] == "D"             # 0-0 de la liga
    stage = r["live"]["ucl"]["by_stage"]
    assert stage["liga"]["n"] == 1 and stage["eliminatorias"]["n"] == 1
    assert r["live"]["ucl"]["n"] == 2
