import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise RuntimeError("unit testlerinde ag/DB erisimi yasak")

    monkeypatch.setattr(socket.socket, "connect", blocked)
