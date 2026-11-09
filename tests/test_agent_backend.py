import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = ROOT / "src" / "agents" / "backend.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


class BackendAgentTest(unittest.TestCase):
    """Static checks only: backend is not a *-reviewer, so the FINDING harness (make agent-eval) does not apply to it."""

    def test_frontmatter(self):
        self.assertEqual(set(FIELDS), {"name", "description", "tools", "model"})
        self.assertEqual(FIELDS["name"], PATH.stem)
        self.assertGreater(len(FIELDS["description"]), 40)
        self.assertEqual(FIELDS["model"], "sonnet")

    def test_tools_are_the_minimal_set(self):
        self.assertEqual(run.agent_tools(FIELDS), TOOLS)

    def test_model_matches_the_existing_working_agents(self):
        other, _ = run.parse_agent((run.AGENTS_DIR / "work-verifier.md").read_text(encoding="utf-8"))
        self.assertEqual(FIELDS["model"], other["model"])

    def test_stays_inside_the_task_scope(self):
        self.assertRegex(BODY, r"(?i)paths you may write")
        self.assertIn("under `backend/`", BODY)
        self.assertRegex(BODY, r"(?i)smallest change")
        self.assertRegex(BODY, r"(?i)no file outside the task's paths")
        self.assertRegex(BODY, r"(?i)read the relevant code first")

    def test_never_decides_architecture(self):
        self.assertRegex(BODY, r"(?i)do not make architecture decisions|not make architecture decisions")
        self.assertIn("Architect", BODY)
        self.assertRegex(BODY, r"(?i)do not decide it")

    def test_follows_the_file_structure_standard(self):
        self.assertIn("ARCH-0001", BODY)
        self.assertIn("ARCH-0003", BODY)
        self.assertRegex(BODY, r"(?i)follow the repo's current file naming")
        self.assertRegex(BODY, r"(?i)in a new project follow ARCH-0001 and ARCH-0003")
        self.assertRegex(BODY, r"(?i)before the first edit")
        self.assertRegex(BODY, r"(?i)never `utils\.py`")
        self.assertRegex(BODY, r"(?i)prefer editing an existing file")

    def test_target_repo_rules_come_first(self):
        self.assertIn("read CLAUDE.md, `.claude/rules` and the architecture and coding-rule files under docs first", BODY)
        self.assertRegex(BODY, r"(?i)they take precedence over this standard")

    def test_feature_trio_and_helpers(self):
        self.assertIn("`service.py`, `schema.py` and `errors.py` together", BODY)
        self.assertRegex(BODY, r"(?i)everything that is not a service lives under `helpers/`, in files named by purpose")
        self.assertNotRegex(BODY, r"(?i)only when they have real content")

    def test_no_empty_skeleton_or_single_function_files(self):
        self.assertRegex(BODY, r"(?i)never create an empty skeleton file or a file for a single function")

    def test_database_layout_follows_the_repo(self):
        self.assertRegex(BODY, r"(?i)database models and repos: follow the repo")
        self.assertIn("glc pairs files by the same name", BODY)
        self.assertIn("evalos groups models by domain and repos by table", BODY)

    def test_split_hint_is_600_lines_and_not_a_hard_rule(self):
        self.assertRegex(BODY, r"(?i)about 600 lines is a hint to consider splitting it by purpose, not a hard rule")
        self.assertNotRegex(BODY, r"(?i)400 lines|under about 30 lines|is merged into its neighbour")

    def test_package_exposure_and_imports_only_through_the_package(self):
        self.assertRegex(BODY, r"(?i)package exposure and imports go only through the package")
        self.assertRegex(BODY, r"(?i)not from a file path")

    def test_header_follows_the_repo_without_fixed_labels(self):
        self.assertRegex(BODY, r"(?i)header: follow the repo's file header format")
        self.assertNotIn("What:", BODY)
        self.assertNotIn("How:", BODY)

    def test_adr_0003_is_a_short_default(self):
        adr = ROOT / "docs" / "decisions" / "ARCH-0003-dosya-yapisi.md"
        text = adr.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 25)
        for part in ("service.py", "schema.py", "errors.py", "helpers/", "utils.py", "Ne yapar:", "Nasıl:",
                     "D100", "D104", "~600", "repoyu izle", "glc", "evalos", "önceliklidir"):
            self.assertIn(part, text)
        self.assertNotIn("içeriği olunca", text)
        self.assertNotIn("What:", text)
        self.assertNotRegex(text, r"(?i)en çok 4 satır|toplam en çok")

    def test_never_weakens_tests(self):
        self.assertRegex(BODY, r"(?i)never weaken, skip or delete an existing test")

    def test_unrun_tests_are_unknown_not_passed(self):
        self.assertIn("UNKNOWN", BODY)
        self.assertRegex(BODY, r"(?i)never say it passed")
        self.assertRegex(BODY, r"(?i)project's test command")

    def test_docker_only_through_bare_dockerw(self):
        self.assertIn("`dockerw`", BODY)
        for rule in ("no env prefix", "no chain", "no `cd`", "no absolute path"):
            self.assertIn(rule, BODY)
        self.assertRegex(BODY, r"(?i)no raw docker, podman or compose")
        self.assertIn("A refusal is final", BODY)

    def test_no_raw_docker_command_is_given_to_the_agent(self):
        for line in BODY.splitlines():
            for cmd in re.findall(r"`([^`]+)`", line):
                first = cmd.split()[0] if cmd.split() else ""
                self.assertNotIn(first, {"docker", "podman", "docker-compose"}, line)
                if re.search(r"\bdockerw\b", cmd):
                    self.assertEqual(cmd, "dockerw", "only the bare dockerw name is shown")

    def test_dot_env_is_never_touched(self):
        self.assertRegex(BODY, r"Never create, read or write any `\.env\*` file")
        self.assertRegex(BODY, r"(?i)secret values are never written")

    def test_migrations_are_written_never_run(self):
        self.assertRegex(BODY, r"(?i)you only WRITE them")
        self.assertRegex(BODY, r"(?i)never run, apply or roll back a migration")
        self.assertRegex(BODY, r"(?i)migration is not applied")

    def test_never_deploys(self):
        self.assertRegex(BODY, r"NEVER deploy")
        self.assertNotRegex(BODY, r"(?i)\byou (may|can|should) deploy\b")

    def test_does_not_own_infrastructure_areas(self):
        for text in ("compose/Docker/CI", "`frontend/`"):
            self.assertIn(text, BODY)

    def test_ask_the_user_gates(self):
        for gate in ("Money", "Security", "Irreversible data operations", "three attempts"):
            self.assertIn(gate, BODY)
        self.assertRegex(BODY, r"(?i)never decide these yourself")

    def test_output_contract(self):
        for section in ("Changed files", "Tests run", "UNKNOWN", "Needs from the user", "Open risks"):
            self.assertIn(section, BODY)

    def test_is_not_a_reviewer(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))
        self.assertNotIn("FINDING <ID>", BODY)


if __name__ == "__main__":
    unittest.main()
