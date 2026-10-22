"""Partidos europeos: cruce de nombres, descanso sin fuga y degradación elegante."""
import json
from datetime import date, timedelta
from pathlib import Path

from src.clubs import data
from src.clubs.data import Match
from src.clubs.leagues import LEAGUES
from src.ml import dataset, europe
from src.ml.features import FEATURES_EUROPE, build, elo_form_rest

FIX = Path(__file__).parent / "fixtures" / "clubs"
ROWS = json.loads((FIX / "europe_toy.json").read_text(encoding="utf-8"))
LIGA = [Match("E0", "2324", date(2023, 12, 30), "Arsenal", "Man City", 1, 1),
        Match("I1", "2324", date(2023, 12, 30), "Inter", "Milan", 1, 0)]


def test_cruza_alias_y_nombres_iguales_y_deja_afuera_a_los_extranjeros():
    days, unmapped = europe.club_days(LIGA, ROWS)
    assert days[("I", "Inter")] == [date(2024, 1, 2)]                 # "Internazionale"
    assert days[("E", "Man City")] == [date(2024, 1, 9)]              # "Man. City"
    # el partido sin marcador (20-feb) no cuenta: puede moverse de fecha
    assert days[("E", "Arsenal")] == [date(2024, 1, 3), date(2024, 1, 9)]
    assert unmapped == {"Celtic", "Ajax"}                              # Porto: solo sin jugar
    assert ("I", "Milan") not in days


def test_europa_baja_el_descanso_sin_mirar_el_mismo_dia():
    d = date(2024, 1, 6)
    ms = [Match("E0", "2324", d - timedelta(days=7), "A", "B", 1, 0),
          Match("E0", "2324", d, "A", "B", 0, 0)]
    eu = {("E", "A"): [d - timedelta(days=3), d - timedelta(days=10), d],
          ("E", "B"): [d + timedelta(days=1)]}
    eu = {k: sorted(v) for k, v in eu.items()}
    f = elo_form_rest(ms, {"E0"}, eu)[("E0", d, "A", "B")]
    assert f["rest_h"] == 7 and f["rest_all_h"] == 3                  # la liga no lo ve
    assert f["eu_n14_h"] == 2                                          # -3 y -10; el de hoy no
    assert f["rest_all_a"] == 7 and f["eu_n14_a"] == 0                 # el de mañana no existe aún


def test_cambiar_europa_futura_no_mueve_las_features_del_pasado():
    d = date(2024, 1, 6)
    ms = [Match("E0", "2324", d + timedelta(days=7 * i), "A", "B", 1, 0) for i in range(4)]
    eu = {("E", "A"): [d + timedelta(days=10)]}
    otra = {("E", "A"): [d + timedelta(days=10), d + timedelta(days=17), d + timedelta(days=19)]}
    a, b = elo_form_rest(ms, {"E0"}, eu), elo_form_rest(ms, {"E0"}, otra)
    for m in ms[:3]:                                                   # hasta el día 14
        assert a[("E0", m.day, "A", "B")] == b[("E0", m.day, "A", "B")]
    assert a[("E0", ms[3].day, "A", "B")] != b[("E0", ms[3].day, "A", "B")]


def test_sin_feeds_europeos_las_features_quedan_nan_y_nada_se_rompe():
    df = build(LIGA[:1], [LEAGUES["E0"]], ("2324",))
    assert df[FEATURES_EUROPE].isna().all().all()
    assert len(df) == 1


def test_sin_red_ni_cache_ensure_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(europe, "EUROPE_DIR", tmp_path)

    def _caida(*_a, **_k):
        raise OSError("sin red")

    monkeypatch.setattr(data, "_download", _caida)
    assert europe.ensure("champions-league", 2026) is None
    (tmp_path / "champions-league-2026.json").write_text(json.dumps(ROWS), encoding="utf-8")
    assert europe.ensure("champions-league", 2026, force=True) is not None   # usa la caché


def test_la_huella_cambia_si_cambia_un_feed_europeo(tmp_path, monkeypatch):
    monkeypatch.setattr(europe, "EUROPE_DIR", tmp_path)
    feed = tmp_path / "champions-league-2023.json"
    feed.write_text(json.dumps(ROWS), encoding="utf-8")
    antes = dataset.fingerprint([])
    feed.write_text(json.dumps(ROWS[:2]), encoding="utf-8")
    assert dataset.fingerprint([]) != antes
