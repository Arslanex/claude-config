"""
Marker'lar dizinden otomatik atanir: unit, integration, e2e, smoke.

`live` elle yazilan tek marker'dir: gercek dis servisi (LLM, odeme, mail) cagiran test. Ortamda WORKER_MODE=live
yoksa atlanir; bu testleri yalniz kullanici `make test-live` ile calistirir. Diger her test WORKER_MODE=fake ile
calisir, ortamda ne yazarsa yazsin (ARCH-0007).
"""

import os
from pathlib import Path

import pytest

GROUPS = ("unit", "integration", "e2e", "smoke")


def pytest_configure(config):
    for g in GROUPS:
        config.addinivalue_line("markers", f"{g}: {g} test grubu (dizinden otomatik)")
    config.addinivalue_line("markers", "live: gercek dis servisi cagirir; yalniz WORKER_MODE=live ile calisir")


def pytest_collection_modifyitems(items):
    root = Path(__file__).parent
    live = os.environ.get("WORKER_MODE") == "live"
    skip_live = pytest.mark.skip(reason="gercek servis testi: yalniz kullanici WORKER_MODE=live ile calistirir")
    for item in items:
        group = Path(item.fspath).relative_to(root).parts[0]
        if group in GROUPS:
            item.add_marker(getattr(pytest.mark, group))
        if not live and item.get_closest_marker("live"):
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _fake_workers(request, monkeypatch):
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("WORKER_MODE", "fake")
