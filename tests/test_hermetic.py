"""La suite no depende de red ni muta data/cache/ (ver tests/conftest.py)."""
import socket

import pytest

from src.etl.pipeline import extract, transform, validate_rows


def test_socket_bloqueado(_sin_red):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="bloqueada"):
            s.connect(("127.0.0.1", 9))
    finally:
        s.close()
    assert _sin_red == [("127.0.0.1", 9)]
    _sin_red.clear()  # intento deliberado: que el teardown no lo marque como fallo


def test_transform_usa_fallback_del_csv():
    teams = validate_rows(extract())
    strengths = transform(teams)
    avg_xgf = sum(t.xg_for for t in teams) / len(teams)
    avg_xga = sum(t.xg_against for t in teams) / len(teams)
    by_code = {t.fifa_code: t for t in teams}
    for s in strengths:
        assert s.resilience == 0.5
        assert s.att == round(by_code[s.fifa_code].xg_for / avg_xgf, 4)
        assert s.defe == round(by_code[s.fifa_code].xg_against / avg_xga, 4)
