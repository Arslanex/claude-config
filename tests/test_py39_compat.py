"""
Keeps the global scripts importable on the system Python of a fresh Mac (3.9).

Hooks, skills and tools run with the bare `python3`. A union annotation such as `str | None`
fails at import there unless the module defers annotations.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPE = r"(?:str|int|float|bool|bytes|dict|list|tuple|set|Path|None)(?:\[[^\]]*\])?"
# A def line or an annotated name whose annotation is a union of builtin types, e.g. `x: str | None`.
UNION = re.compile(rf"^\s*(?:def .*|\w+\s*:\s*){TYPE}\s*\|\s*{TYPE}", re.MULTILINE)


class Py39CompatTest(unittest.TestCase):
    def test_union_annotations_are_deferred(self):
        files = [*ROOT.glob("src/skills/**/*.py"), *ROOT.glob("src/hooks/*.py"), *ROOT.glob("tools/*.py")]
        bad = [str(f.relative_to(ROOT)) for f in files
               if UNION.search(f.read_text(encoding="utf-8"))
               and "from __future__ import annotations" not in f.read_text(encoding="utf-8")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
