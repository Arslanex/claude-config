import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = run.PROFILE_AGENTS_DIR / "frontend.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def section(title):
    m = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", BODY, re.S | re.M)
    assert m, title
    return m.group(1).strip("\n")


class FrontendAgentTest(unittest.TestCase):
    """Static checks only: frontend is not a *-reviewer, so the FINDING harness (make agent-eval) does not apply to it."""

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

    def test_stays_inside_the_task_scope(self):
        self.assertRegex(BODY, r"(?i)paths you may write")
        self.assertIn("under `frontend/`", BODY)
        self.assertRegex(BODY, r"(?i)smallest change")
        self.assertRegex(BODY, r"(?i)no file outside the task's paths")
        self.assertRegex(BODY, r"(?i)read the relevant code first")

    def test_does_not_touch_other_roles_areas(self):
        for text in ("`backend/`", "compose/Docker/CI", "e2e"):
            self.assertIn(text, BODY)

    def test_never_decides_architecture(self):
        self.assertRegex(BODY, r"(?i)do not make architecture decisions")
        self.assertIn("Architect", BODY)
        self.assertRegex(BODY, r"(?i)do not decide it")
        self.assertRegex(BODY, r"(?i)never change the backend contract alone")

    def test_target_repo_rules_come_first_and_no_hardcoded_commands(self):
        self.assertIn("`frontend/CLAUDE.md`", BODY)
        self.assertIn("`.claude/rules`", BODY)
        self.assertRegex(BODY, r"(?i)they take precedence over everything below")
        self.assertRegex(BODY, r"(?i)never hardcode one")
        self.assertRegex(BODY, r"(?i)where the repo's rules differ from the common stack below, the repo wins")
        for pattern in (r"npm (run )?\w+", r"\bnpx\b", r"\bvitest run\b", r"\byarn\b", r"\bpnpm\b"):
            self.assertNotRegex(BODY, pattern)

    def test_common_stack_is_short_and_not_a_copy_of_repo_rules(self):
        body = section("Common stack (glc and evalos agree on these)")
        lines = [l for l in body.splitlines() if l.strip()]
        self.assertLessEqual(len(lines), 10)
        for part in ("React", "TypeScript", "Vitest", "TanStack Query", "no `any`", "API client"):
            self.assertIn(part, body)
        for forbidden in ("Tailwind 4.3", "@ds", "@lib", "msg(", "audit:", "oxlint@"):
            self.assertNotIn(forbidden, body)

    def test_skills_are_loaded_only_when_relevant(self):
        body = section("Skills (load only when the task needs them)")
        self.assertRegex(body, r"`frontend-design`: only for")
        self.assertRegex(body, r"`react-best-practices`: only for")
        self.assertRegex(body, r"`ui-design`: only for a task that names a design flow step")
        self.assertRegex(body, r"(?i)do not load any of them for a routine edit")

    def test_design_flow_uses_the_approved_design_system(self):
        body = section("Design flow")
        self.assertIn("`ui-design`", body)
        self.assertRegex(body, r"user approval, once per project")
        self.assertRegex(body, r"tokens from its tokens file")
        self.assertRegex(BODY, r"Playwright e2e tests of a page belong to the Tester")

    def test_every_screen_handles_states_and_accessibility(self):
        body = section("Every screen")
        for state in ("loading", "error", "empty"):
            self.assertIn(state, body)
        self.assertRegex(body, r"(?i)accessibility")
        self.assertRegex(body, r"(?i)keyboard")
        self.assertRegex(body, r"(?i)no empty state before the first load ends")

    def test_never_weakens_tests(self):
        self.assertRegex(BODY, r"(?i)never weaken, skip or delete an existing test")

    def test_unrun_tests_are_unknown_not_passed(self):
        self.assertIn("UNKNOWN", BODY)
        self.assertRegex(BODY, r"(?i)never say it passed")

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

    def test_dot_env_is_never_touched_and_vite_values_are_public(self):
        self.assertRegex(BODY, r"Never create, read or write any `\.env\*` file")
        self.assertRegex(BODY, r"(?i)secret values are never written")
        self.assertRegex(BODY, r"every `VITE_` value reaches the browser")

    def test_new_dependency_is_an_architect_question(self):
        self.assertRegex(BODY, r"(?i)adding a dependency is a question for the Architect")

    def test_never_deploys(self):
        self.assertRegex(BODY, r"NEVER deploy")
        self.assertNotRegex(BODY, r"(?i)\byou (may|can|should) deploy\b")

    def test_ask_the_user_gates(self):
        for gate in ("Money", "Security", "Irreversible data operations", "three attempts"):
            self.assertIn(gate, BODY)
        self.assertRegex(BODY, r"(?i)never decide these yourself")

    def test_output_contract(self):
        for part in ("Changed files", "Commands run", "UNKNOWN", "Needs from the user", "Open risks"):
            self.assertIn(part, BODY)

    def test_is_not_a_reviewer(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))
        self.assertNotIn("FINDING <ID>", BODY)


if __name__ == "__main__":
    unittest.main()
