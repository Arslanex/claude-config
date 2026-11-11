import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = run.PROFILE_AGENTS_DIR / "tester.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]

TARGET_REPO_BLOCK = (
    "## Target repo test rules\n"
    "Before writing or running any test, read the target repo's own test rules, in this order: "
    "CLAUDE.md, .claude/rules/, docs/. Take the test directory, naming scheme and run command from them. "
    "They take precedence over every default in this prompt. Never hardcode a test directory or a test command; "
    "if the repo defines none, report that instead of guessing."
)


class TesterAgentTest(unittest.TestCase):
    """Static checks only: tester is not a *-reviewer, so the FINDING harness (make agent-eval) does not apply to it."""

    def test_frontmatter(self):
        self.assertEqual(set(FIELDS), {"name", "description", "tools", "model", "skills"})
        self.assertEqual(FIELDS["name"], PATH.stem)
        self.assertGreater(len(FIELDS["description"]), 40)
        self.assertEqual(FIELDS["model"], "sonnet")

    def test_tools_are_the_minimal_set(self):
        self.assertEqual(run.agent_tools(FIELDS), [*TOOLS, "mcp__playwright__*", "mcp__context7__*", "Skill"])

    def test_model_matches_the_existing_working_agents(self):
        other, _ = run.parse_agent((run.AGENTS_DIR / "work-verifier.md").read_text(encoding="utf-8"))
        self.assertEqual(FIELDS["model"], other["model"])

    def test_target_repo_test_rules_block_is_verbatim(self):
        self.assertIn(TARGET_REPO_BLOCK, TEXT)

    def test_target_repo_rules_come_before_the_hard_limits(self):
        self.assertLess(TEXT.index("## Target repo test rules"), TEXT.index("## Hard limits"))

    def test_no_hardcoded_test_dir_or_command(self):
        for pattern in (r"\bpytest\b", r"unittest", r"npm (run )?test", r"\bmake (check|test)\b", r"`tests/"):
            self.assertNotRegex(BODY, pattern)

    def test_writes_only_in_the_test_directory(self):
        self.assertRegex(BODY, r"(?i)write only inside the repo's test directory")
        for text in ("`backend/`", "`frontend/`", "compose/Docker/CI"):
            self.assertIn(text, BODY)
        self.assertRegex(BODY, r"(?i)change application source")

    def test_reports_bugs_instead_of_fixing_them(self):
        self.assertRegex(BODY, r"(?i)do NOT fix it")
        self.assertRegex(BODY, r"(?i)which criterion")
        self.assertRegex(BODY, r"(?i)steps to reproduce")

    def test_never_weakens_tests(self):
        self.assertRegex(BODY, r"(?i)never weaken, skip, xfail or delete an existing test")
        self.assertRegex(BODY, r"(?i)never change an assertion to make a run pass")

    def test_unrun_tests_are_unknown_not_passed(self):
        self.assertIn("UNKNOWN", BODY)
        self.assertRegex(BODY, r"(?i)never say it passed")

    def test_red_proof_before_implementation(self):
        self.assertRegex(BODY, r"(?i)failing acceptance tests")
        self.assertRegex(BODY, r"(?i)red run as proof")
        self.assertRegex(BODY, r"(?i)independently of the author")

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

    def test_never_deploys(self):
        self.assertRegex(BODY, r"NEVER deploy")
        self.assertNotRegex(BODY, r"(?i)\byou (may|can|should) deploy\b")

    def test_ask_the_user_gates(self):
        for gate in ("Money", "Security", "Irreversible data operations", "three attempts"):
            self.assertIn(gate, BODY)
        self.assertRegex(BODY, r"(?i)never decide these yourself")

    def test_output_contract(self):
        for section in ("Tests written", "Commands run", "Bugs found", "UNKNOWN", "Needs from the user", "Open risks"):
            self.assertIn(section, BODY)

    def test_browser_check_includes_a_visual_check(self):
        self.assertIn("## Browser check, visual too", BODY)
        self.assertRegex(BODY, r"(?i)screenshot at desktop and at phone width")
        self.assertRegex(BODY, r"(?i)browser-default styling")
        self.assertRegex(BODY, r"(?i)reported like a bug")

    def test_owns_ui_e2e_in_the_container_with_commands_from_team_md(self):
        self.assertIn("## UI e2e (Playwright)", BODY)
        self.assertRegex(BODY, r"run them yourself")
        self.assertRegex(BODY, r"only in the e2e container")
        self.assertIn("`.claude/team.md` (UI e2e)", BODY)
        self.assertRegex(BODY, r"Never run a browser test on the host")

    def test_never_runs_live_tests(self):
        self.assertRegex(BODY, r"Tests always use the fake adapters")
        self.assertRegex(BODY, r"Never run, enable or unskip a test marked live")

    def test_is_not_a_reviewer(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))
        self.assertNotIn("FINDING <ID>", BODY)


if __name__ == "__main__":
    unittest.main()
