"""Marker'lar dizinden otomatik atanir: unit, integration, e2e, smoke."""

from pathlib import Path

import pytest

GROUPS = ("unit", "integration", "e2e", "smoke")


def pytest_configure(config):
    for g in GROUPS:
        config.addinivalue_line("markers", f"{g}: {g} test grubu (dizinden otomatik)")


def pytest_collection_modifyitems(items):
    root = Path(__file__).parent
    for item in items:
        group = Path(item.fspath).relative_to(root).parts[0]
        if group in GROUPS:
            item.add_marker(getattr(pytest.mark, group))
