import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

TEAM = ROOT / "src" / "templates" / "profiles" / "fastapi-saas" / "team"
TEAM_MD = (TEAM / "team.md").read_text(encoding="utf-8")
SKILL = (TEAM / "skills" / "saas-fastapi" / "SKILL.md").read_text(encoding="utf-8")
CRITICAL = ("data loss, an authorization or tenant-isolation bypass, a secret or personal-data leak, "
            "losing or charging money, or code that does not build or fails its acceptance tests")
REVIEWERS = ["devils-advocate", "security-reviewer", "arch-reviewer"]


def body(name):
    return run.parse_agent(run.agent_file(name).read_text(encoding="utf-8"))[1]


class ProportionateReviewTest(unittest.TestCase):
    """A re-review checks the earlier findings only; only CRITICAL blocks, the rest is a follow-up."""

    def test_team_principles_define_critical_and_the_re_review_rule(self):
        self.assertIn("11. Review is proportionate. CRITICAL is the only level that blocks a merge or a handoff: "
                      + CRITICAL + ".", TEAM_MD)
        self.assertIn("A logic bug at an edge or a limit and a convenience problem are at most MAJOR", TEAM_MD)
        self.assertIn("raises a new finding only when it is CRITICAL; anything else goes to the follow-ups list "
                      "in the handoff, never blocks and opens no new round.", TEAM_MD)
        self.assertIn("12. Roles build only what the task's acceptance criteria need: no extra abstraction, "
                      "config or feature \"for later\".", TEAM_MD)

    def test_gate_four_uses_the_critical_definition_and_two_rounds_stay(self):
        self.assertIn("4. A critical Devil's Advocate objection (CRITICAL as in principle 11)", TEAM_MD)
        self.assertIn("at most 2 rounds", TEAM_MD)

    def test_each_reviewer_has_the_critical_definition_and_the_re_review_rule(self):
        for name in REVIEWERS:
            with self.subTest(name=name):
                text = body(name)
                self.assertIn(CRITICAL, text)
                self.assertIn("- Re-review (the input lists your earlier findings): check only whether each one is fixed", text)
                self.assertIn("which the Conductor lists as a follow-up", text)

    def test_tester_re_verification_blocks_only_on_critical(self):
        text = body("tester")
        self.assertIn("Re-verification after a fix: check only the reported findings and the acceptance tests. "
                      "A new bug blocks only when it is CRITICAL", text)
        self.assertIn("- Follow-ups:", text)

    def test_conductor_runs_re_reviews_on_the_earlier_findings_only(self):
        self.assertIn("A re-review or re-verification gets the earlier findings and checks only those. "
                      "A new finding blocks only when it is CRITICAL", SKILL)
        self.assertIn("every UNKNOWN, the follow-ups, the risk results", SKILL)



class PlanningRisksTest(unittest.TestCase):
    """Planning finds risks and proposes solutions; the dev team tries them and closes them."""

    RESULTS = ("`doğrulandı` with the test id", "`başarısız, denenen: <alternative>`")

    def test_team_spec_routes_and_closes_the_risks(self):
        self.assertIn("a task from `/design-project` has a section `Doğrulanacak riskler`", TEAM_MD)
        self.assertIn("The Conductor passes it to the roles. Backend and Frontend build the proposed solution, "
                      "or a better one with a note.", TEAM_MD)
        for result in self.RESULTS:
            self.assertIn(result, TEAM_MD)
        self.assertIn("`risk kabul` (only with the User's approval, never for a must-verify item)", TEAM_MD)
        self.assertIn("A must-verify item that is not `doğrulandı` blocks acceptance; any other open item goes to "
                      "the follow-ups.", TEAM_MD)
        self.assertIn("The handoff summary lists the results in one short table: ID, result, evidence.", TEAM_MD)
        self.assertLess(TEAM_MD.index("## Acceptance rule"), TEAM_MD.index("Doğrulanacak riskler"))

    def test_conductor_passes_risks_blocks_on_must_verify_and_reports_a_table(self):
        self.assertIn("Pass its `Doğrulanacak riskler` section to every role", SKILL)
        self.assertIn("never while a `must-verify` risk is not `doğrulandı`; other open risks go to the follow-ups",
                      SKILL)
        self.assertIn("the risk results as one short table (ID, result, evidence)", SKILL)
        self.assertIn("`risk kabul` only with the user's approval and never for `must-verify`", SKILL)

    def test_tester_records_one_result_line_per_risk(self):
        text = body("tester")
        self.assertIn("- `Doğrulanacak riskler` in the task file: verify each item with a test (red first where "
                      "possible)", text)
        for result in self.RESULTS:
            self.assertIn(result, text)
        self.assertIn("Write `risk kabul` only when the task file records the User's approval, never for a "
                      "`must-verify` item.", text)


if __name__ == "__main__":
    unittest.main()
