import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = ROOT / "src" / "agents" / "devops.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


class DevopsAgentTest(unittest.TestCase):
    """Static checks only: devops is not a *-reviewer, so the FINDING harness (make agent-eval) does not apply to it."""

    def test_frontmatter(self):
        self.assertEqual(set(FIELDS), {"name", "description", "tools", "model"})
        self.assertEqual(FIELDS["name"], PATH.stem)
        self.assertGreater(len(FIELDS["description"]), 40)
        self.assertEqual(FIELDS["model"], "sonnet")  # same as the other working agents

    def test_tools_are_the_minimal_set(self):
        self.assertEqual(run.agent_tools(FIELDS), TOOLS)

    def test_model_matches_the_existing_working_agents(self):
        other, _ = run.parse_agent((run.AGENTS_DIR / "work-verifier.md").read_text(encoding="utf-8"))
        self.assertEqual(FIELDS["model"], other["model"])

    def test_docker_goes_only_through_dockerw(self):
        self.assertIn("dockerw", BODY)
        self.assertRegex(BODY, r"(?i)only .*dockerw")
        self.assertRegex(BODY, r"(?i)no raw docker, podman or compose")
        for rule in ("no env prefix", "no chain", "no `cd`", "no absolute path"):
            self.assertIn(rule, BODY)

    def test_no_raw_docker_command_is_given_to_the_agent(self):
        raw = re.findall(r"`(?:docker|podman|docker-compose)\s+\w+[^`]*`", BODY)
        self.assertEqual(raw, [], "the agent text must only show dockerw commands")
        for line in BODY.splitlines():
            for cmd in re.findall(r"`([^`]+)`", line):
                first = cmd.split()[0] if cmd.split() else ""
                self.assertNotIn(first, {"docker", "podman", "docker-compose"}, line)

    def test_every_dockerw_command_shown_is_bare_and_known(self):
        known = {"ports", "compose", "ps", "images", "version", "info", "system", "clean"}
        spans = [c for line in BODY.splitlines() for c in re.findall(r"`([^`]+)`", line)]
        for cmd in (c for c in spans if re.search(r"\bdockerw\b", c)):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmd.startswith("dockerw"), "a dockerw command must start with dockerw")
                self.assertNotRegex(cmd, r"[;&|]|^\w+=|/dockerw|\bcd\b")
                parts = cmd.split()
                if len(parts) > 1 and parts[1] != "...":  # "dockerw ..." is the generic form
                    self.assertIn(parts[1], known)

    def test_never_deploys(self):
        self.assertRegex(BODY, r"NEVER deploy")
        self.assertRegex(BODY, r"(?i)deploy packages")
        self.assertRegex(BODY, r"(?i)the user deploys")
        self.assertNotRegex(BODY, r"(?i)\byou (may|can|should) deploy\b")

    def test_dockerw_refusals_are_stated_and_final(self):
        for text in ("`.git`", "`.claude`", "`.env*`", "`secrets`", "`:ro`", "privileged", "`down -v`", "`--rmi`",
                     "`build --ssh`", "`--push`", "<project>-", "<project>/", "`-f -`", "oci://", "`config -o/--output`"):
            self.assertIn(text, BODY)
        self.assertIn("A refusal is final", BODY)
        self.assertRegex(BODY, r"(?i)do not rewrite the command")

    def test_destructive_guardrails_with_the_single_dockerw_clean_exception(self):
        self.assertIn("docker-destructive-guardrails stays the base rule", BODY)
        self.assertRegex(BODY, r"ONLY exception is `dockerw clean`")
        self.assertIn("`dockerw clean --apply`", BODY)
        self.assertRegex(BODY, r"(?i)stopped, labelled containers")

    def test_ask_the_user_gates(self):
        for gate in ("Money", "Security", "Irreversible data operations", "Needing dockerw to do what it refused"):
            self.assertIn(gate, BODY)
        self.assertIn("20 USD/month", BODY)
        self.assertRegex(BODY, r"(?i)never decide these yourself")

    def test_template_rules(self):
        for text in ("node_modules", ".venv", "named volumes", "image: <project>-<service>", ".env.example",
                     "healthcheck", "127.0.0.1", "Rollback notes"):
            self.assertIn(text, BODY)
        self.assertRegex(BODY, r"(?i)secret values are never written")

    def test_output_contract(self):
        for section in ("Prepared files", "dockerw checks run", "Needs from the user", "Open risks"):
            self.assertIn(section, BODY)

    def test_is_not_a_reviewer(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))
        self.assertNotIn("FINDING <ID>", BODY)


if __name__ == "__main__":
    unittest.main()
