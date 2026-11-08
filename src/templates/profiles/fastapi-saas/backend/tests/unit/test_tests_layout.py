from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
GROUPS = {"unit", "integration", "e2e", "smoke"}
ALLOWED = GROUPS | {"support", "conftest.py", "__init__.py", "__pycache__"}


def test_top_level_layout():
    extra = {p.name for p in TESTS.iterdir()} - ALLOWED
    assert not extra, f"tests/ altinda tanimsiz oge: {sorted(extra)}"


def test_no_test_files_outside_groups():
    stray = list(TESTS.glob("test_*.py"))
    assert not stray, f"test dosyalari bir gruba tasinmali: {stray}"


def test_group_files_are_named_test():
    bad = [
        p
        for g in GROUPS
        for p in (TESTS / g).rglob("*.py")
        if p.name not in ("__init__.py", "conftest.py")
        and not p.name.startswith("test_")
    ]
    assert not bad, f"test_ ile baslamayan dosya: {bad}"
