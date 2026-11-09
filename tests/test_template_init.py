import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src" / "templates"
INIT = TEMPLATES / "project" / "init.sh"


class InitTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        shutil.copytree(TEMPLATES, self.home / ".claude" / "templates",
                        ignore=shutil.ignore_patterns("__pycache__"))
        self.proj = self.tmp / "proj"
        self.proj.mkdir()

    def init(self, *args):
        env = {**os.environ, "HOME": str(self.home)}
        return subprocess.run(["bash", str(INIT), *args], cwd=self.proj, env=env,
                              capture_output=True, text=True)

    def snapshot(self):
        return {p.relative_to(self.proj).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.proj.rglob("*")) if p.is_file()}

    def set_version(self, path, version):
        text = Path(path).read_text()
        Path(path).write_text(re.sub(r"^DOCS_ENGINE_VERSION = \d+", f"DOCS_ENGINE_VERSION = {version}",
                                     text, flags=re.M))


class TestInit(InitTestCase):
    def test_creates_skeleton_and_engine(self):
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        for rel in ("tools/docs.py", "CLAUDE.md", ".claude/settings.json", "docs/INDEX.md",
                    "docs/00-project/README.md", "docs/01-architecture/README.md",
                    "docs/02-decisions/README.md", "docs/03-domains/README.md",
                    "docs/04-operations/README.md", "docs/05-work/README.md",
                    "docs/99-archive/README.md", "docs/05-work/tasks/.gitkeep",
                    "docs/01-architecture/modules/.gitkeep"):
            self.assertTrue((self.proj / rel).exists(), rel)
        index = (self.proj / "docs/INDEX.md").read_text()
        self.assertIn("<!-- docs:index:start -->", index)
        self.assertIn("<!-- docs:index:end -->", index)

    def test_settings_json_has_allow_rule_and_deny_read(self):
        self.init()
        data = json.loads((self.proj / ".claude/settings.json").read_text())
        self.assertIn("Bash(python3 tools/docs.py *)", data["permissions"]["allow"])
        self.assertTrue(data["sandbox"]["filesystem"]["denyRead"])
        self.assertIn("./secrets", data["sandbox"]["filesystem"]["denyRead"])

    def test_second_run_changes_nothing(self):
        self.init()
        first = self.snapshot()
        r = self.init()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), first)

    def test_gitignore_lines_exactly_once(self):
        (self.proj / ".gitignore").write_text("node_modules/\n.obsidian/\n")
        self.init()
        self.init()
        lines = (self.proj / ".gitignore").read_text().splitlines()
        for l in (".claude/settings.local.json", "CLAUDE.local.md", ".obsidian/"):
            self.assertEqual(lines.count(l), 1, l)
        self.assertIn("node_modules/", lines)

    def test_gitignore_without_trailing_newline_keeps_lines_separate(self):
        (self.proj / ".gitignore").write_text("node_modules")
        self.init()
        self.init()
        lines = (self.proj / ".gitignore").read_text().splitlines()
        self.assertEqual(lines, ["node_modules", ".claude/settings.local.json",
                                 ".claude/session-state.md", "CLAUDE.local.md",
                                 ".obsidian/", ".env", ".env.*"])

    def test_existing_user_files_are_not_overwritten(self):
        (self.proj / "CLAUDE.md").write_text("mine\n")
        (self.proj / "docs/00-project").mkdir(parents=True)
        (self.proj / "docs/00-project/README.md").write_text("custom readme\n")
        (self.proj / "docs/INDEX.md").write_text("custom index\n")
        self.init()
        self.assertEqual((self.proj / "CLAUDE.md").read_text(), "mine\n")
        self.assertEqual((self.proj / "docs/00-project/README.md").read_text(), "custom readme\n")
        self.assertEqual((self.proj / "docs/INDEX.md").read_text(), "custom index\n")
        self.assertTrue((self.proj / "docs/02-decisions/README.md").exists())

    def test_generated_project_lints_clean(self):
        self.init()
        r = subprocess.run(["python3", "tools/docs.py", "lint"], cwd=self.proj,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 error(s)", r.stdout)

    def test_readme_in_area_is_skipped_by_lint(self):
        self.init()
        readme = self.proj / "docs/02-decisions/README.md"
        self.assertTrue(readme.exists())
        self.assertFalse(readme.read_text().startswith("---"))
        r = subprocess.run(["python3", "tools/docs.py", "lint"], cwd=self.proj,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 error(s)", r.stdout)
        self.assertNotIn("README.md", r.stdout)


class TestUpgrade(InitTestCase):
    def test_upgrade_replaces_older_engine_and_keeps_backup(self):
        self.init()
        docs = self.proj / "tools/docs.py"
        self.set_version(docs, 1)
        old_text = docs.read_text()
        r = self.init("--upgrade")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("v1 -> v", r.stdout)
        self.assertEqual((self.proj / "tools/docs.py.bak").read_text(), old_text)
        self.assertEqual(docs.read_bytes(), (TEMPLATES / "project/tools/docs.py").read_bytes())

    def test_upgrade_noop_when_same_version(self):
        self.init()
        before = self.snapshot()
        r = self.init("--upgrade")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.proj / "tools/docs.py.bak").exists())

    def test_upgrade_noop_when_project_is_newer(self):
        self.init()
        docs = self.proj / "tools/docs.py"
        self.set_version(docs, 99)
        before = self.snapshot()
        r = self.init("--upgrade")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.proj / "tools/docs.py.bak").exists())

    def test_upgrade_touches_only_docs_engine(self):
        self.init()
        self.set_version(self.proj / "tools/docs.py", 1)
        (self.proj / "CLAUDE.md").write_text("mine\n")
        (self.proj / "docs/INDEX.md").unlink()
        self.init("--upgrade")
        self.assertEqual((self.proj / "CLAUDE.md").read_text(), "mine\n")
        self.assertFalse((self.proj / "docs/INDEX.md").exists())


if __name__ == "__main__":
    unittest.main()
