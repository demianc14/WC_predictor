"""Ciclo diario: el almacén nunca se sobrescribe y un fallo no deja estado parcial."""
import json
from datetime import date, datetime, timezone

import pytest

from src.clubs.data import Match
from src.clubs.leagues import LEAGUES
from src.pipeline import daily, store

NOW = datetime(2026, 10, 21, 5, 30, tzinfo=timezone.utc)
LG = [LEAGUES["E0"]]


def _pred(mid="E0-2627-A-B", version="v1", p1="0.5000", when="2026-10-21T05:30:00Z"):
    return {"match_id": mid, "league": "E0", "season": "2627", "match_date": "2026-10-24",
            "home": "A", "away": "B", "model": "dixon-coles", "model_version": version,
            "commit": "abc", "predicted_at": when, "p1": p1, "px": "0.2500", "p2": "0.2500"}


def test_una_prediccion_guardada_no_se_sobrescribe():
    rows, added = store.add_predictions([], [_pred()])
    rows, again = store.add_predictions(rows, [_pred(p1="0.9000")])   # el modelo cambió de idea
    assert added == 1 and again == 0 and rows[0]["p1"] == "0.5000"
    rows, otra = store.add_predictions(rows, [_pred(version="v2", p1="0.9000")])
    assert otra == 1 and [r["p1"] for r in rows] == ["0.5000", "0.9000"]


@pytest.mark.parametrize("cambio", ["p1", "predicted_at", "borrar", "resultado"])
def test_check_append_only_rechaza_cualquier_reescritura(cambio):
    old, _ = store.add_predictions([], [_pred()])
    old[0].update(result="H", hg="2", ag="0")
    new = [dict(old[0])]
    if cambio == "borrar":
        new = []
    elif cambio == "resultado":
        new[0]["result"] = "A"
    else:
        new[0][cambio] = "0.1" if cambio == "p1" else "2026-10-22T05:30:00Z"
    with pytest.raises(store.StoreError):
        store.check_append_only(old, new)


def test_save_no_toca_el_archivo_si_se_intenta_sobrescribir(tmp_path):
    path = tmp_path / "p.csv"
    rows, _ = store.add_predictions([], [_pred()])
    store.save(rows, path)
    before = path.read_bytes()
    rows[0]["p1"] = "0.9999"
    with pytest.raises(store.StoreError, match="sobrescribiría"):
        store.save(rows, path)
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["p.csv"]          # sin temporales


def test_resultados_se_completan_una_vez_y_no_se_contradicen():
    rows, _ = store.add_predictions([], [_pred()])
    res = {"E0-2627-A-B": {"result": "H", "hg": 2, "ag": 0, "mk1": "0.6", "mkx": "0.25",
                           "mk2": "0.15"}}
    rows, n = store.record_results(rows, res)
    assert n == 1 and rows[0]["result"] == "H" and rows[0]["mk1"] == "0.6"
    rows, n = store.record_results(rows, res)
    assert n == 0
    with pytest.raises(store.StoreError, match="no coincide"):
        store.record_results(rows, {"E0-2627-A-B": {**res["E0-2627-A-B"], "ag": 3}})


def test_solo_se_predice_antes_del_partido():
    assert daily.predictable(date(2026, 10, 22), NOW)
    assert daily.predictable(date(2026, 10, 21), NOW)                  # hoy, a las 05:30 UTC
    assert not daily.predictable(date(2026, 10, 21), NOW.replace(hour=12))
    assert not daily.predictable(date(2026, 10, 20), NOW)


CSV = "Div,Date,HomeTeam\nE0,24/10/2026,A\n"
CAL = json.dumps([{"HomeTeam": "A", "AwayTeam": "B"}])


def _downloader(fail_at=None, body=None):
    calls = []

    def dl(url, target):
        calls.append(url)
        if fail_at is not None and len(calls) == fail_at:
            raise OSError("HTTP 503")
        target.write_text(body or (CAL if target.suffix == ".json" else CSV), encoding="utf-8")
    return dl, calls


SRCS = [("u1", "E0_2627.csv", "csv"), ("u2", "fixtures.csv", "csv"),
        ("u3", "calendar_epl_2026.json", "json")]


def test_fetch_es_todo_o_nada(tmp_path):
    (tmp_path / "E0_2627.csv").write_text("viejo", encoding="utf-8")
    dl, calls = _downloader(fail_at=3)
    with pytest.raises(daily.SourceError, match="503"):
        daily.fetch(SRCS, tmp_path, dl)
    assert (tmp_path / "E0_2627.csv").read_text(encoding="utf-8") == "viejo"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["E0_2627.csv"]   # ni temporales
    assert len(calls) == 3                                               # una vez cada una


def test_fetch_rechaza_una_pagina_de_error(tmp_path):
    dl, _ = _downloader(body="<html>Service unavailable</html>")
    with pytest.raises(daily.SourceError, match="no es un CSV"):
        daily.fetch(SRCS, tmp_path, dl)
    assert list(tmp_path.iterdir()) == []


def test_fetch_ok_reemplaza_la_cache(tmp_path):
    daily.fetch(SRCS, tmp_path, _downloader()[0])
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(n for _, n, _ in SRCS)


def _out():
    return {"next": [{"day": "2026-10-24", "home": "A", "away": "B", "model": [0.5, 0.3, 0.2]},
                     {"day": "2026-10-20", "home": "C", "away": "D", "model": [0.4, 0.3, 0.3]}]}


def _cycle(tmp_path, monkeypatch, played=(), builder=None, fetcher=None, version="v1", now=NOW):
    monkeypatch.setattr(daily.data, "load_matches", lambda divs, seasons: list(played))
    return daily.cycle(now, LG, fetcher=fetcher or (lambda: None),
                       builder=builder or (lambda lg, today: _out()), version=version,
                       commit="abc", store_path=tmp_path / "p.csv", out_dir=tmp_path / "out")


def test_un_fallo_a_mitad_no_deja_nada_escrito(tmp_path, monkeypatch):
    _cycle(tmp_path, monkeypatch)
    snapshot = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}

    def roto(lg, today):
        raise RuntimeError("el ajuste no convergió")
    with pytest.raises(RuntimeError):
        _cycle(tmp_path, monkeypatch, builder=roto, version="v2")

    def caida():
        raise daily.SourceError("football-data caído")
    with pytest.raises(daily.SourceError):
        _cycle(tmp_path, monkeypatch, fetcher=caida, version="v2")
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == snapshot


def test_ciclo_completo_predice_registra_y_mide(tmp_path, monkeypatch):
    r1 = _cycle(tmp_path, monkeypatch)
    assert r1["added"] == 1                     # el partido del 20-oct ya pasó: no se predice
    assert _cycle(tmp_path, monkeypatch)["added"] == 0
    jugado = Match("E0", "2627", date(2026, 10, 24), "A", "B", 1, 1, odds=(2.0, 3.5, 4.0))
    later = NOW.replace(day=25)
    r3 = _cycle(tmp_path, monkeypatch, played=[jugado], now=later)
    rows = store.load(tmp_path / "p.csv")
    assert r3["filled"] == 1 and rows[0]["result"] == "D" and rows[0]["p1"] == "0.5000"
    live = json.loads((tmp_path / "out" / "live.json").read_text(encoding="utf-8"))
    assert live["all"]["n"] == 1 and live["all"]["same_sample"]["n"] == 1
    assert live["all"]["model"]["brier"] == pytest.approx(0.5 ** 2 + 0.7 ** 2 + 0.2 ** 2)
    assert (tmp_path / "out" / "clubs_E0.json").exists()


def test_metricas_en_vivo_usan_la_primera_prediccion():
    a = {**_pred(when="2026-10-21T05:30:00Z", p1="0.6000"), "result": "H", "hg": "1", "ag": "0",
         "mk1": "", "mkx": "", "mk2": ""}
    b = {**a, "model_version": "v2", "predicted_at": "2026-10-22T05:30:00Z", "p1": "0.1000"}
    live = daily.live_metrics([b, a], NOW)
    assert live["all"]["n"] == 1 and live["n_predictions"] == 2
    assert live["all"]["model"]["brier"] == pytest.approx(0.4 ** 2 + 0.25 ** 2 + 0.25 ** 2)
