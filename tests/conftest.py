"""Fixtures globales: la suite es HERMÉTICA (sin red, sin tocar data/cache/).

`transform()` llama a resiliencia y forma dinámica, que leen/descargan el
historial martj42 y el World.tsv de eloratings. Con el TTL vencido eso baja
datos frescos y PISA data/cache/ (así se perdió la caché pre-torneo del
15/06). En tests forzamos el fallback que el pipeline ya tiene previsto:
resiliencia 0.5 neutra y att/defe desde el CSV.
"""
import socket

import pytest

import src.etl.pipeline as pipeline


def _offline(*_args, **_kwargs):
    raise RuntimeError("red deshabilitada en tests")


@pytest.fixture(autouse=True)
def _etl_offline(monkeypatch):
    """Resiliencia y forma dinámica fallan -> transform() usa su fallback."""
    monkeypatch.setattr(pipeline, "compute_resilience_all", _offline)
    monkeypatch.setattr(pipeline, "compute_dynamic_form", _offline)


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Bloquea cualquier conexión de socket y falla el test si alguien lo intenta.

    El pipeline envuelve la red en `except Exception`, así que un error lanzado
    acá podría tragarse en silencio: por eso registramos el intento y fallamos
    en el teardown aunque el código lo haya capturado.
    """
    intentos: list[object] = []

    def _bloquear(real):
        def _bloqueado(self, address, *args, **kwargs):
            if self.family == socket.AF_UNIX:  # IPC local, no es red
                return real(self, address, *args, **kwargs)
            intentos.append(address)
            raise OSError(f"conexión de red bloqueada en tests: {address!r}")
        return _bloqueado

    monkeypatch.setattr(socket.socket, "connect", _bloquear(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _bloquear(socket.socket.connect_ex))
    yield intentos
    if intentos:
        pytest.fail(f"El test intentó abrir conexiones de red: {intentos}")
