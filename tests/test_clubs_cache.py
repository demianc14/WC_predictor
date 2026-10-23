"""Caché de football-data: si un refresco por TTL falla, se sigue con la caché."""
import os
import time

import pytest

from src.clubs import data


def _caida(*_a, **_k):
    raise OSError("football-data no responde")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "_download", _caida)
    return tmp_path


def _vencido(path):
    viejo = time.time() - data.TTL_SECONDS - 60
    os.utime(path, (viejo, viejo))


def test_ttl_vencido_y_sin_red_usa_la_cache(cache, capsys):
    p = cache / f"E0_{data.CURRENT_SEASON}.csv"
    p.write_text("Div,Date\n", encoding="utf-8")
    _vencido(p)
    assert data.ensure_season("E0", data.CURRENT_SEASON) == p
    assert p.read_text(encoding="utf-8") == "Div,Date\n"
    assert "sigo con la caché" in capsys.readouterr().out


def test_sin_red_y_sin_cache_falla(cache):
    with pytest.raises(OSError):
        data.ensure_season("E0", data.CURRENT_SEASON)


def test_un_refresco_forzado_que_falla_no_se_disimula(cache):
    p = cache / "fixtures.csv"
    p.write_text("Div,Date\n", encoding="utf-8")
    with pytest.raises(OSError):
        data.ensure_fixtures(force=True)
