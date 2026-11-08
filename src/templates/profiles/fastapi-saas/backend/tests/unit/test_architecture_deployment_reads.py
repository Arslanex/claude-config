"""ARCH-0002: dagitim modu yalnizca izin verilen dosyalarda okunur."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "__PKG__"
READERS = {
    "tenancy": {"infra/database/router.py", "config/deployment.py"},
    "topology": {"interface/http/tenant.py", "config/deployment.py"},
}


def test_deployment_modes_read_only_in_allowed_files():
    assert SRC.is_dir(), f"paket dizini yok: {SRC}"
    bad = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in READERS and rel not in READERS[node.attr]:
                bad.append(f"{rel}:{node.lineno} .{node.attr}")
    assert not bad, f"izinsiz mod okuma: {bad}"
