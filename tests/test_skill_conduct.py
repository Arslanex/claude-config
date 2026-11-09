import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "src" / "skills" / "conduct" / "SKILL.md"
AGENTS_DIR = ROOT / "src" / "agents"
TEXT = PATH.read_text(encoding="utf-8")
LINES = TEXT.split("\n")
END = LINES.index("---", 1)
FIELDS = dict(line.partition(":")[::2] for line in LINES[1:END])
FIELDS = {k: v.strip() for k, v in FIELDS.items()}
BODY = "\n".join(LINES[END + 1:])

ROLES = ["architect", "backend", "frontend", "tester", "devops", "devils-advocate",
         "arch-reviewer", "security-reviewer", "work-verifier", "file-explorer", "structure-explorer"]
SIZES = ["XS", "S", "M", "L"]
SECTIONS = ["Size", "Routing", "Task file", "Fix loop", "Ask the user", "Finish", "Safety", "Model choice"]


def section(title):
    m = re.search(rf"^## (?:\d+\. )?{re.escape(title)}\n(.*?)(?=^## |\Z)", BODY, re.S | re.M)
    assert m, title
    return m.group(1)


class ConductSkillTest(unittest.TestCase):
    """Static checks only; the shared skill rules (line limit, known fields, no secrets) live in test_skills.py."""

    def test_file_exists_with_frontmatter(self):
        self.assertTrue(PATH.is_file())
        self.assertEqual(LINES[0], "---")
        self.assertEqual(FIELDS["name"], "conduct")
        self.assertEqual(FIELDS["name"], PATH.parent.name)
        self.assertGreater(len(FIELDS["description"]), 40)
        self.assertLessEqual(len(FIELDS["description"]), 250)
        self.assertEqual(FIELDS["disable-model-invocation"], "true")

    def test_is_short(self):
        self.assertLessEqual(len(LINES), 90)

    def test_sections_in_order(self):
        positions = [BODY.index(f"## {n}. {t}") if t != "Model choice" else BODY.index("## Model choice")
                     for n, t in enumerate(SECTIONS, 1)]
        self.assertEqual(positions, sorted(positions))

    def test_four_sizes(self):
        body = section("Size")
        for size in SIZES:
            self.assertRegex(body, rf"(?m)^- {size}: ")
        self.assertRegex(body, r"(?i)start one size smaller")
        self.assertRegex(body, r"(?i)planning approval once")

    def test_m_flow_order(self):
        body = section("Size")
        m = re.search(r"(?m)^- M: .*$", body).group(0)
        order = ["`architect`", "`devils-advocate`", "user accepts the ADR", "`backend`", "`tester`", "closing round"]
        positions = [m.index(p) for p in order]
        self.assertEqual(positions, sorted(positions))

    def test_routing_roles_match_real_agent_files(self):
        table = section("Routing")
        names = set(re.findall(r"`([a-z]+(?:-[a-z]+)*)`", table))
        routed = names & set(ROLES)
        self.assertEqual(routed, set(ROLES), "every role must be routed")
        for role in routed:
            self.assertTrue((AGENTS_DIR / f"{role}.md").is_file(), role)

    def test_every_backticked_agent_like_name_in_routing_is_a_real_file(self):
        table = section("Routing")
        existing = {p.stem for p in AGENTS_DIR.glob("*.md")}
        for row in table.splitlines():
            if row.startswith("|") and not row.startswith("|---") and not row.startswith("| Work"):
                agent_cell = row.split("|")[2]
                for name in re.findall(r"`([^`]+)`", agent_cell):
                    for part in name.split(" / "):
                        self.assertIn(part, existing, row)

    def test_mlops_is_dormant_with_no_agent(self):
        self.assertRegex(section("Routing"), r"(?i)`mlops` is dormant")
        self.assertFalse((AGENTS_DIR / "mlops.md").exists())

    def test_task_file_template(self):
        body = section("Task file")
        self.assertIn('python3 tools/docs.py new task "<title>"', body)
        for part in ("Goal", "Definition of done", "acceptance criteria", "writable paths", "the role"):
            self.assertIn(part, body)
        self.assertRegex(body, r"(?i)never the whole chat")

    def test_roles_are_the_installed_subagents(self):
        self.assertIn("Roles are the installed subagents (names in the routing table)", BODY)
        self.assertNotIn("src/agents/", BODY)

    def test_task_file_by_hand_when_docs_py_is_missing(self):
        body = section("Task file")
        self.assertIn("If tools/docs.py is missing in the target repo, create the task file by hand under docs/tasks/ "
                      "and leave it untracked; do not commit it.", body)

    def test_preflight_comes_before_size_and_asks_once(self):
        self.assertIn("Pre-flight: before the first role runs, check what the roles will need to run tests "
                      "(installed dependencies, a test command in the repo's rules).", BODY)
        self.assertRegex(BODY, r"ask the user once for all of it in a single message")
        self.assertLess(BODY.index("Pre-flight:"), BODY.index("## 1. Size"))

    def test_fix_loop(self):
        body = section("Fix loop")
        self.assertRegex(body, r"(?i)at most three attempts")
        self.assertRegex(body, r"(?i)ask the user")
        self.assertIn("`tester`", body)
        self.assertRegex(body, r"(?i)author never accepts their own work")

    def test_five_question_points_and_planning_approval(self):
        body = section("Ask the user")
        items = re.findall(r"(?m)^\d+\. ", body)
        self.assertEqual(len(items), 5)
        for gate in ("Money", "Security", "Irreversible data", "critical `devils-advocate` objection", "three attempts"):
            self.assertIn(gate, body)
        self.assertRegex(body, r"(?i)planning approval.*once per project")
        self.assertRegex(body, r"(?i)everything else proceeds without asking")

    def test_preflight_is_the_only_other_question_exception(self):
        body = section("Ask the user")
        self.assertIn("The one-time pre-flight message about missing dependencies is the only other exception.", body)
        self.assertLess(body.index("everything else proceeds without asking"), body.index("only other exception"))
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", body)), 5)

    def test_finish_is_a_short_summary_not_the_role_reports(self):
        body = section("Finish")
        self.assertIn("UNKNOWN", body)
        self.assertRegex(body, r"(?i)do not paste the role reports")
        self.assertRegex(body, r"(?i)do not commit or push unless asked")

    def test_safety(self):
        body = section("Safety")
        self.assertRegex(body, r"(?i)no deploy")
        self.assertIn("`devops` only prepares the package", body)
        self.assertIn("bare `dockerw`", body)
        self.assertIn("`.env*`", body)
        self.assertRegex(body, r"(?i)a role's refusal is final")

    def test_model_choice(self):
        body = section("Model choice")
        self.assertIn("`sonnet`", body)
        self.assertRegex(body, r"`architect` runs `opus`")
        self.assertRegex(body, r"(?i)size L or after three failed attempts")
        self.assertIn("20 USD", body)

    def test_does_not_copy_role_rules(self):
        for phrase in ("A refusal is final", "Never weaken, skip", "Never create, read or write any"):
            self.assertNotIn(phrase, BODY)


if __name__ == "__main__":
    unittest.main()
