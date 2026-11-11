"""
Old names after the rename (docs/design/planning-process.md 3.1): no text under src/ or tests/ names them.

Allowed: install.sh's RETIRED list and init.sh's RETIRED_TEAM list, which remove the old installed files,
files under docs/design/, and this test. The patterns are built from parts so this file does not match itself when it is scanned.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_PLAN = "plan" + "-product"
OLD_DEV = "con" + "duct"
PATTERNS = [
    re.compile(re.escape("/" + OLD_PLAN)),
    re.compile(re.escape("/" + OLD_DEV) + r"(?![A-Za-z])"),
    re.compile(re.escape(OLD_PLAN)),
    re.compile(re.escape("skills/" + OLD_DEV) + r"(?![A-Za-z])"),
]
SKIP_PARTS = {"__pycache__", ".cache", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}


def scanned_files():
    for top in ("src", "tests"):
        for path in sorted((ROOT / top).rglob("*")):
            if not path.is_file() or SKIP_PARTS & set(path.parts) or path.name == ".DS_Store":
                continue
            if path == Path(__file__).resolve() or "docs/design" in path.as_posix():
                continue
            yield path
    yield ROOT / "install.sh"


def without_retired_list(text, name="RETIRED"):
    """The script minus the lines of its NAME=( ... ) array."""
    return re.sub(r"(?ms)^%s=\(\n.*?^\)$" % name, "", text)


class OldNamesTest(unittest.TestCase):
    def test_no_old_command_or_skill_names(self):
        hits = []
        for path in scanned_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if path.name == "install.sh" and path.parent == ROOT:
                text = without_retired_list(text)
            if path == ROOT / "src/templates/project/init.sh":
                text = without_retired_list(text, "RETIRED_TEAM")
            for n, line in enumerate(text.splitlines(), 1):
                if any(p.search(line) for p in PATTERNS):
                    hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
        self.assertEqual(hits, [])

    def test_retired_list_still_removes_the_old_installed_files(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        block = text.split("RETIRED=(", 1)[1].split(")", 1)[0].split()
        for name in ("SKILL.md", "preview.py", "protocol.md", "question-bank.md", "diagrams.md"):
            self.assertIn(f"skills/{OLD_PLAN}/{name}", block)
        self.assertTrue(any(r.startswith(f"skills/{OLD_PLAN}/templates/") for r in block))
        self.assertIn(f"skills/{OLD_DEV}/SKILL.md", block)

    def test_new_names_exist(self):
        self.assertTrue((ROOT / "src/skills/design-project/SKILL.md").is_file())
        self.assertTrue((ROOT / "src/templates/profiles/fastapi-saas/team/skills/saas-fastapi/SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
