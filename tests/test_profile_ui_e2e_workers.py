"""
Pins the fastapi-saas UI design flow, the UI e2e container and the fake worker mode.

Static checks only: the scaffold's own pytest suite (run by profile-fastapi-saas.sh) covers WorkerSettings itself.
"""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "src" / "templates" / "profiles" / "fastapi-saas"
TEAM = (PROFILE / "team" / "team.md").read_text(encoding="utf-8")
TEST_STACK = (PROFILE / "deploy" / "compose.test.yaml").read_text(encoding="utf-8")
PROD_STACK = (PROFILE / "deploy" / "compose.production.yaml").read_text(encoding="utf-8")
MAKEFILE = (PROFILE / "Makefile").read_text(encoding="utf-8")
STACK = "dockerw compose -f deploy/compose.yaml -f deploy/compose.test.yaml --profile e2e"

sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("dockerw", ROOT / "tools" / "dockerw.py")
dockerw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dockerw)


def team_section(title):
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", TEAM, re.S | re.M)
    assert m, title
    return m.group(1)


class DesignFlowTest(unittest.TestCase):
    def test_flow_steps_in_order(self):
        body = team_section("UI design flow (frontend M and L)")
        order = ["UI architecture", "3 most used pages", "Design system", "Mockups of all other pages",
                 "builds the pages one by one", "Playwright e2e tests"]
        self.assertEqual([body.index(p) for p in order], sorted(body.index(p) for p in order))
        self.assertIn("same tokens file", body)

    def test_design_system_approval_is_a_once_per_project_gate(self):
        gates = team_section("Gates: the only reasons to ask the User")
        self.assertRegex(gates, r"(?m)^7\. Design system approval, once per project")

    def test_skill_exists_and_is_on_demand_for_frontend(self):
        self.assertTrue((PROFILE / "team" / "skills" / "ui-design" / "SKILL.md").is_file())
        row = next(l for l in TEAM.splitlines() if l.startswith("| Frontend | "))
        self.assertIn("ui-design", row)


class UiE2eTest(unittest.TestCase):
    def test_playwright_image_is_pinned_to_an_exact_version(self):
        self.assertRegex(TEST_STACK, r"image: mcr\.microsoft\.com/playwright:v\d+\.\d+\.\d+-noble\n")

    def test_e2e_stack_uses_fake_workers_and_mounts_frontend_read_only(self):
        self.assertIn("WORKER_MODE: fake", TEST_STACK)
        self.assertNotIn("WORKER_MODE: live", TEST_STACK)
        self.assertIn("- ../frontend:/app:ro", TEST_STACK)

    def test_team_md_gives_the_bare_dockerw_commands(self):
        body = team_section("UI e2e")
        self.assertIn(f"`{STACK} run --rm e2e`", body)
        self.assertIn(f"`{STACK} down`", body)
        self.assertNotIn("down -v", body)

    def test_dockerw_allows_the_commands(self):
        for cmd in (f"{STACK} run --rm e2e", f"{STACK} down"):
            with self.subTest(cmd=cmd):
                reason, _ = dockerw.check(cmd.split()[1:], ROOT, ROOT)
                self.assertIsNone(reason)

    def test_user_targets_exist(self):
        self.assertRegex(MAKEFILE, r"(?m)^test-ui:\n\tdocker compose .* --profile e2e run --rm e2e$")
        self.assertRegex(MAKEFILE, r"(?m)^test-live:\n.*pytest -m live$")


class WorkerModeTest(unittest.TestCase):
    def test_roles_always_run_with_fake_workers(self):
        self.assertIn("Roles always run with fake workers.", TEAM)
        self.assertIn("only the User runs them (`make test-live`", TEAM)

    def test_env_example_documents_fake(self):
        self.assertIn("\nWORKER_MODE=fake\n", (PROFILE / "deploy" / "env.example").read_text(encoding="utf-8"))

    def test_production_is_always_live(self):
        self.assertEqual(PROD_STACK.count("WORKER_MODE: live"), 2)

    def test_setting_defaults_to_fake_and_tests_force_it(self):
        backend = PROFILE / "backend"
        setting = (backend / "src" / "PKG_NAME" / "config" / "workers.py").read_text(encoding="utf-8")
        self.assertIn('Literal["fake", "live"] = Field(default="fake", alias="WORKER_MODE")', setting)
        conftest = (backend / "tests" / "conftest.py").read_text(encoding="utf-8")
        self.assertIn('monkeypatch.setenv("WORKER_MODE", "fake")', conftest)
        self.assertIn('os.environ.get("WORKER_MODE") == "live"', conftest)


class TestLocalRunScripts(unittest.TestCase):
    def test_scripts_exist_are_executable_and_parse(self):
        import os
        import subprocess
        for name in ("local.sh", "start.sh", "stop.sh", "restart.sh"):
            f = PROFILE / "deploy" / name
            self.assertTrue(os.access(f, os.X_OK), name)
            self.assertEqual(subprocess.run(["bash", "-n", str(f)]).returncode, 0, name)

    def test_local_run_builds_no_app_image_and_keeps_dev_data(self):
        local = (PROFILE / "deploy" / "local.sh").read_text(encoding="utf-8")
        self.assertIn("up -d --wait postgres redis", local)
        self.assertNotIn("build", local)
        self.assertNotIn('"${COMPOSE[@]}" down', local)
        self.assertIn('WORKER_MODE="${WORKER_MODE:-fake}"', local)

    def test_no_anonymous_volumes_pile_up(self):
        dev = (PROFILE / "deploy" / "compose.development.yaml").read_text(encoding="utf-8")
        self.assertIn("pgdata:/var/lib/postgresql/data", dev)
        self.assertIn("redisdata:/data", dev)
        self.assertIn('tmpfs: ["/data"]', TEST_STACK)
        self.assertIn('tmpfs: ["/var/lib/postgresql/data"]', TEST_STACK)

    def test_team_keeps_scripts_user_run_until_docker_switch(self):
        section = team_section("Local run")
        self.assertIn("No role runs these scripts", section)
        self.assertIn("bash -n deploy/local.sh", section)
        self.assertIn("switch to Docker", section)

    def test_e2e_cleans_untagged_images(self):
        self.assertIn("`dockerw clean --apply`", team_section("UI e2e"))


if __name__ == "__main__":
    unittest.main()
