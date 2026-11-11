import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PATH = ROOT / "src" / "agents" / "devils-advocate.md"
TEXT = PATH.read_text(encoding="utf-8")
FIELDS, BODY = run.parse_agent(TEXT)
TOOLS = ["Read", "Grep", "Glob"]
IDS = ["HIDDEN-ASSUMPTION", "MISSED-FAILURE", "DATA-LOSS-RISK", "SECURITY-RISK",
       "OVER-ENGINEERING", "CRITERIA-MISMATCH", "RULE-VIOLATION"]
LEVELS = ["CRITICAL", "MAJOR", "MINOR"]


def declared_ids():
    return {line[2:].split(":")[0] for line in BODY.splitlines()
            if line.startswith("- ") and line[2:].split(":")[0].isupper()}


class DevilsAdvocateAgentTest(unittest.TestCase):
    """Static checks only: the model is never called here; the cases run through `make agent-eval`."""

    def test_frontmatter(self):
        self.assertEqual(set(FIELDS), {"name", "description", "tools", "model"})
        self.assertEqual(FIELDS["name"], PATH.stem)
        self.assertEqual(FIELDS["name"], "devils-advocate")
        self.assertGreater(len(FIELDS["description"]), 40)
        self.assertEqual(FIELDS["model"], "sonnet")

    def test_tools_are_read_only(self):
        self.assertEqual(run.agent_tools(FIELDS), TOOLS)
        for tool in ("Bash", "Edit", "Write", "NotebookEdit"):
            self.assertNotIn(tool, run.agent_tools(FIELDS))

    def test_finding_id_dictionary(self):
        self.assertEqual(declared_ids(), set(IDS))

    def test_finding_format_and_levels(self):
        self.assertIn("`FINDING <ID> <level> <file>:<line> <short description>`", BODY)
        self.assertIn("(level: CRITICAL, MAJOR or MINOR)", BODY)
        self.assertIn("the single line `NO FINDINGS`", BODY)
        self.assertRegex(BODY, r"(?i)nothing else \(no prose, no markdown\)")

    def test_severity_levels_are_defined(self):
        for level in LEVELS:
            self.assertIn(level, BODY)
        self.assertIn("CRITICAL is the only level that blocks and goes to the user: data loss,", BODY)

    def test_severity_is_not_a_dictionary_id(self):
        self.assertFalse(set(LEVELS) & declared_ids())

    def test_evidence_is_required_and_findings_are_capped(self):
        self.assertRegex(BODY, r"(?i)no evidence, no finding")
        self.assertRegex(BODY, r"(?i)at most 7 findings")
        self.assertRegex(BODY, r"(?i)`NO FINDINGS` is a valid answer; never invent an objection")

    def test_covers_the_objection_topics(self):
        for topic in ("hidden", "failure", "security", "data", "over-engineering", "acceptance criteria"):
            self.assertRegex(BODY + FIELDS["description"], rf"(?i){topic}")

    def test_reads_target_repo_rules_and_violations_are_findings(self):
        self.assertIn("CLAUDE.md, `.claude/rules/`", BODY)
        self.assertRegex(BODY, r"(?i)a contradiction with them is a concrete finding")

    def test_decides_and_fixes_nothing(self):
        self.assertRegex(BODY, r"(?i)do not decide, fix or write anything")
        self.assertRegex(BODY, r"(?i)never modify files or run state-changing commands")

    def test_no_env_deploy_or_docker(self):
        self.assertRegex(BODY, r"Never read any `\.env\*` file")
        self.assertRegex(BODY, r"(?i)no deploy, no docker")

    def test_is_not_a_reviewer_file_so_the_reviewer_glob_skips_it(self):
        self.assertFalse(PATH.name.endswith("-reviewer.md"))

    def test_cases_exist_and_are_wired_to_the_dictionary(self):
        mine = [c for c in run.load_cases() if c["agent"] == "devils-advocate"]
        self.assertTrue(any(c["expect"] for c in mine))
        self.assertTrue(any(c["clean"] for c in mine))
        for c in mine:
            for i in c["expect"] + c["forbid"]:
                self.assertIn(i, IDS, c["name"])

    def test_defective_case_expects_data_loss_and_over_engineering(self):
        case = next(c for c in run.load_cases() if c["name"] == "adr-data-loss")
        self.assertEqual(set(case["expect"]), {"DATA-LOSS-RISK", "OVER-ENGINEERING"})
        self.assertFalse(case["clean"])
        self.assertIn("status: draft", case["patch"])
        self.assertIn("yedek alınmaz", case["patch"])

    def test_clean_case_forbids_the_whole_dictionary(self):
        case = next(c for c in run.load_cases() if c["name"] == "clean-adr")
        self.assertTrue(case["clean"])
        self.assertEqual(case["expect"], [])
        self.assertEqual(set(case["forbid"]), set(IDS))


if __name__ == "__main__":
    unittest.main()
