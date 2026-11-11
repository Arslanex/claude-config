import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src" / "templates"
PROFILE = TEMPLATES / "profiles" / "fastapi-saas"
QUIET = PROFILE / "tools" / "quiet.sh"
MAKEFILE = (PROFILE / "Makefile").read_text(encoding="utf-8")
TEAM = PROFILE / "team"
QUIET_TARGETS = ["lint", "typecheck", "arch", "test-unit", "test-integration", "test-e2e", "test-smoke",
                 "migrate-check", "openapi-check", "docs-lint"]


def recipe(target):
    return re.search(rf"(?ms)^{target}:\n(.*?)(?=^\S)", MAKEFILE).group(1)


class QuietScriptTest(unittest.TestCase):
    """tools/quiet.sh keeps check output short and puts the full output in .cache/logs/."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "tools").mkdir()
        shutil.copy2(QUIET, self.tmp / "tools" / "quiet.sh")

    def run_quiet(self, name, script):
        return subprocess.run([str(self.tmp / "tools" / "quiet.sh"), name, "bash", "-c", script],
                              cwd=self.tmp, capture_output=True, text=True, timeout=30)

    def test_is_executable_and_strict(self):
        self.assertTrue(os.access(QUIET, os.X_OK))
        self.assertIn("set -euo pipefail", QUIET.read_text(encoding="utf-8"))

    def test_pass_prints_one_ok_line_and_keeps_the_full_log(self):
        r = self.run_quiet("lint", "for i in $(seq 200); do echo noise $i; done")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "lint: ok\n")
        self.assertIn("noise 200", (self.tmp / ".cache" / "logs" / "lint.log").read_text())

    def test_failure_prints_only_capped_matching_lines_and_the_log_path(self):
        script = ("for i in $(seq 300); do echo noise $i; done; "
                  "for i in $(seq 100); do echo \"FAILED tests/unit/test_x.py::test_$i - assert 1 == 2\"; done; exit 3")
        r = self.run_quiet("test-unit", script)
        self.assertEqual(r.returncode, 3)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], "test-unit: FAILED (exit 3)")
        self.assertEqual(lines[-1], "full log: .cache/logs/test-unit.log")
        self.assertNotIn("noise", r.stdout)
        self.assertIn("FAILED tests/unit/test_x.py::test_1 ", r.stdout)
        self.assertNotIn("test_61 ", r.stdout)
        self.assertLessEqual(len(lines), 63)
        self.assertIn("noise 300", (self.tmp / ".cache" / "logs" / "test-unit.log").read_text())

    def test_failure_without_known_lines_shows_the_tail(self):
        r = self.run_quiet("docs-lint", "for i in $(seq 100); do echo line $i; done; exit 1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("line 100", r.stdout)
        self.assertNotIn("line 70\n", r.stdout)


class MakefileQuietTest(unittest.TestCase):
    def test_checks_go_through_quiet_unless_v_is_set(self):
        self.assertIn("ifeq ($(V),1)", MAKEFILE)
        self.assertIn("RUN = $(CURDIR)/tools/quiet.sh $@", MAKEFILE)
        for target in QUIET_TARGETS:
            with self.subTest(target=target):
                self.assertIn("$(RUN) ", recipe(target))

    def test_pytest_output_is_small_and_the_coverage_gate_stays(self):
        self.assertIn("PYTEST := uv run pytest -q --tb=short", MAKEFILE)
        unit = recipe("test-unit")
        self.assertIn("--cov-fail-under=100 --cov-report=term-missing:skip-covered", unit)
        for target in ("test-unit", "test-integration"):
            self.assertIn("$(if $(T),$(T),", recipe(target))

    def test_init_copies_quiet_with_its_exec_bit(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        home, proj = tmp / "home", tmp / "proj"
        shutil.copytree(TEMPLATES, home / ".claude" / "templates",
                        ignore=shutil.ignore_patterns("__pycache__", ".cache", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"))
        proj.mkdir()
        r = subprocess.run(["bash", str(TEMPLATES / "project" / "init.sh"), "--kind", "fastapi-saas", "--pkg", "demo"],
                           cwd=proj, capture_output=True, text=True, env={**os.environ, "HOME": str(home)}, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.access(proj / "tools" / "quiet.sh", os.X_OK))


class QuietRulesTest(unittest.TestCase):
    def test_team_principles(self):
        team = (TEAM / "team.md").read_text(encoding="utf-8")
        self.assertIn("13. Checks stay few and quiet. During work a role runs only the affected tests "
                      "(`make test-unit T=<test file or test id>`, the same for `test-integration`) and the full "
                      "`make check` once before handing off.", team)
        self.assertIn("The Tester runs its full verification once; after a fix it reruns only the failing tests "
                      "plus `make check`.", team)
        self.assertIn("never the whole log", team)
        self.assertIn("14. Tests cover the acceptance criteria, the real edge cases from the plan and every bug "
                      "found (red first).", team)

    def test_roles_run_affected_tests_read_logs_narrowly_and_write_no_duplicate_tests(self):
        for role in ("backend", "frontend", "tester"):
            body = (TEAM / "agents" / f"{role}.md").read_text(encoding="utf-8")
            with self.subTest(role=role):
                self.assertIn("read only the failing part of `.cache/logs/<target>.log` with grep or a line range, "
                              "never the whole log", body)
                self.assertIn("No duplicate of what another test already covers, no test of framework or library "
                              "behaviour; prefer one parametrized test over copies.", body)
                self.assertIn("`.claude/team.md` principle 13", body)

    def test_conductor_reverifies_with_failing_tests_only(self):
        skill = (TEAM / "skills" / "saas-fastapi" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("`tester` re-verifies with only the failing tests plus `make check`", skill)


if __name__ == "__main__":
    unittest.main()
