"""Stateless kurali (ARCH-0002): surec ici degisebilir durum tutulmaz.
Sezgisel kontrol: kasitli istisna gerekirse bu testi gerekcesiyle duzenle."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "__PKG__"
MUTABLE_CALLS = {"list", "dict", "set"}


def _sources():
    assert SRC.is_dir(), f"paket dizini yok: {SRC}"
    return sorted(SRC.rglob("*.py"))


def _is_mutable(node):
    return isinstance(node, (ast.List, ast.Dict, ast.Set)) or (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in MUTABLE_CALLS
    )


def test_no_module_level_mutable_state():
    bad = []
    for path in _sources():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and _is_mutable(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [t.id for t in targets if isinstance(t, ast.Name)]
                if any(not (n.isupper() or n == "__all__") for n in names):
                    bad.append(f"{path}:{node.lineno}")
    assert not bad, f"modul seviyesinde degisebilir durum: {bad}"


def test_no_global_statement():
    bad = [
        f"{p}:{n.lineno}" for p in _sources()
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.Global)
    ]
    assert not bad, f"'global' kullanimi: {bad}"
