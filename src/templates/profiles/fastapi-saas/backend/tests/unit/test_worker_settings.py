"""ARCH-0007: worker modu varsayilan olarak sahtedir; yalniz secilen adaptor kurulur."""

import pytest
from pydantic import ValidationError

from PKG_NAME.config import WorkerSettings


def _never() -> str:
    raise AssertionError("secilmeyen adaptor kuruldu")


def test_tests_run_in_fake_mode():
    assert WorkerSettings().worker_mode == "fake"


def test_default_is_fake(monkeypatch):
    monkeypatch.delenv("WORKER_MODE", raising=False)
    assert WorkerSettings().pick(live=_never, fake=lambda: "fake") == "fake"


def test_live_mode_builds_only_the_live_adapter(monkeypatch):
    monkeypatch.setenv("WORKER_MODE", "live")
    assert WorkerSettings().pick(live=lambda: "live", fake=_never) == "live"


def test_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("WORKER_MODE", "sandbox")
    with pytest.raises(ValidationError):
        WorkerSettings()
