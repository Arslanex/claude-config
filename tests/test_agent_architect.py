import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = ROOT / "src" / "agents" / "architect.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob", "Edit", "Write"]


class ArchitectAgentTest(unittest.TestCase):
    """Static checks only: architect is not a *-reviewer, so the FINDING harness (make agent-eval) does not apply to it."""

    def test_frontmatter(self):
        self.assertEqual(set(FIELDS), {"name", "description", "tools", "model"})
        self.assertEqual(FIELDS["name"], PATH.stem)
        self.assertGreater(len(FIELDS["description"]), 40)

    def test_model_is_opus(self):
        self.assertEqual(FIELDS["model"], "opus")

    def test_tools_are_the_minimal_set_without_bash(self):
        self.assertEqual(run.agent_tools(FIELDS), TOOLS)
        self.assertNotIn("Bash", run.agent_tools(FIELDS))

    def test_decides_architecture_topics(self):
        for topic in ("module boundaries", "data model", "API contract", "new dependency", "security/auth model"):
            self.assertIn(topic, BODY)
        self.assertRegex(BODY, r"(?i)not mine to decide")

    def test_writes_docs_only_never_code_or_tests(self):
        self.assertRegex(BODY, r"(?i)do not write application code or tests")
        self.assertRegex(BODY, r"(?i)write only under `docs/decisions/`")
        self.assertRegex(BODY, r"(?i)architecture document the task file names")
        for text in ("`backend/`", "`frontend/`", "compose/Docker/CI"):
            self.assertIn(text, BODY)

    def test_adr_status_is_draft_only(self):
        self.assertIn("`Durum: Taslak` only", BODY)
        self.assertRegex(BODY, r"(?i)`Kabul` is given only by the user, never by you")

    def test_adr_numbering_continues_the_highest(self):
        self.assertRegex(BODY, r"(?i)find the highest existing `ARCH-NNNN` and use the next one")

    def test_never_edits_an_existing_adr(self):
        self.assertRegex(BODY, r"(?i)never edit an existing ADR")
        self.assertIn("ARCH-000X'in yerine geçer", BODY)

    def test_reads_before_deciding_and_never_contradicts(self):
        self.assertRegex(BODY, r"(?i)read the relevant code, the existing ADRs")
        self.assertIn("CLAUDE.md, `.claude/rules`", BODY)
        self.assertRegex(BODY, r"(?i)do not contradict them")
        self.assertRegex(BODY, r"(?i)ask the user which wins")

    def test_adr_sections_and_size(self):
        order = ["Bağlam", "Karar", "Seçenekler", "Sonuçlar", "Doğrulama"]
        positions = [BODY.index(s) for s in order]
        self.assertEqual(positions, sorted(positions))
        self.assertRegex(BODY, r"(?i)at most 40 lines")
        self.assertRegex(BODY, r"(?i)only when there is a real decision")
        self.assertRegex(BODY, r"(?i)list of items that need the user's approval")

    def test_docker_is_not_used(self):
        self.assertRegex(BODY, r"(?i)docker is not used")
        self.assertNotRegex(BODY, r"(?i)only through the bare")

    def test_dot_env_is_never_touched(self):
        self.assertRegex(BODY, r"Never create, read or write any `\.env\*` file")
        self.assertRegex(BODY, r"(?i)secret values are never written")

    def test_never_deploys(self):
        self.assertRegex(BODY, r"NEVER deploy")
        self.assertNotRegex(BODY, r"(?i)\byou (may|can|should) deploy\b")

    def test_ask_the_user_gates(self):
        for gate in ("Money", "Security", "Irreversible data operations", "three attempts", "Devil's Advocate"):
            self.assertIn(gate, BODY)
        self.assertRegex(BODY, r"(?i)never decide these yourself")

    def test_output_contract(self):
        for section in ("ADRs", "Decisions", "Needs from the user", "Open risks"):
            self.assertIn(section, BODY)

    def test_is_not_a_reviewer(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))
        self.assertNotIn("FINDING <ID>", BODY)


if __name__ == "__main__":
    unittest.main()
