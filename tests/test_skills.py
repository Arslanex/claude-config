import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "src" / "skills"
# Global skills plus the ones a profile ships into the project (team/skills).
SKILL_DIRS = [SKILLS_DIR, *sorted((ROOT / "src" / "templates" / "profiles").glob("*/team/skills"))]
DOCS_PY = ROOT / "src" / "templates" / "project" / "tools" / "docs.py"

spec = importlib.util.spec_from_file_location("docs_engine", DOCS_PY)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)

# Fields documented at code.claude.com/docs/en/skills
KNOWN_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools",
    "disallowed-tools", "model", "effort", "context", "agent", "background",
    "hooks", "paths", "shell", "metadata", "license", "compatibility",
}
SECRET_RE = re.compile(r"ghp_|sk-|Bearer")
NEW_KIND_RE = re.compile(r"docs\.py new (\S+)")


def parse(path):
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines[0] != "---":
        raise ValueError("frontmatter must start on line 1")
    end = lines.index("---", 1)
    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or key != key.strip():
            raise ValueError(f"bad frontmatter line: {line!r}")
        fields[key] = value.strip()
    return fields


class SkillsTest(unittest.TestCase):
    def skill_files(self):
        files = sorted(f for d in SKILL_DIRS for f in d.glob("*/SKILL.md"))
        self.assertTrue(files, "no skills found")
        return files

    def test_every_skill_dir_has_skill_md(self):
        for base in SKILL_DIRS:
            for d in base.iterdir():
                if d.is_dir():
                    self.assertTrue((d / "SKILL.md").is_file(), f"{d.name}: missing SKILL.md")

    def test_frontmatter(self):
        for f in self.skill_files():
            with self.subTest(skill=f.parent.name):
                fm = parse(f)
                self.assertEqual(fm.get("name"), f.parent.name)
                self.assertTrue(fm.get("description"))
                self.assertLessEqual(len(fm["description"]), 250)
                self.assertFalse(set(fm) - KNOWN_FIELDS, f"unknown fields: {set(fm) - KNOWN_FIELDS}")

    def test_line_limit(self):
        for f in self.skill_files():
            with self.subTest(skill=f.parent.name):
                self.assertLessEqual(len(f.read_text(encoding="utf-8").splitlines()), 80)

    def test_no_secret_patterns(self):
        for f in self.skill_files():
            with self.subTest(skill=f.parent.name):
                self.assertIsNone(SECRET_RE.search(f.read_text(encoding="utf-8")))

    def test_docs_kinds_exist(self):
        for f in self.skill_files():
            with self.subTest(skill=f.parent.name):
                for kind in NEW_KIND_RE.findall(f.read_text(encoding="utf-8")):
                    self.assertIn(kind, docs.KINDS)


if __name__ == "__main__":
    unittest.main()


class PromoteSkillTest(unittest.TestCase):
    BODY = (SKILLS_DIR / "promote" / "SKILL.md").read_text(encoding="utf-8")

    def test_targets_the_repo_never_the_installed_copy(self):
        self.assertIn("~/.claude/config-source", self.BODY)
        self.assertIn("Never edit `~/.claude` directly", self.BODY)
        self.assertRegex(self.BODY, r"Never commit, push or run `install.sh`")

    def test_keeps_project_only_changes_local(self):
        self.assertIn("Project only:", self.BODY)
        self.assertIn("Keep it local and stop", self.BODY)

    def test_maps_project_files_to_their_source(self):
        for part in ("team/...", "`PKG_NAME`", "src/templates/project/", "`src/hooks/`", "status: draft"):
            self.assertIn(part, self.BODY)

    def test_global_instructions_point_to_it(self):
        self.assertIn("with the `promote` skill", (ROOT / "src" / "CLAUDE.md").read_text(encoding="utf-8"))
