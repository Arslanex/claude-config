"""
End-to-end dry run of the planning conductor with the fake team (sürüm 6, 7.7).

The scenario is the realistic run of the second review, which used 35 role calls. Planning
proposes solutions and the dev team verifies them (15.11), so it reaches the handoff in 12 calls
with the contacts A and G3 only; in small mode in 9.
"""
import shutil
import unittest

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import BRIEF3, DryRunTeam, next_lines, run, state_of, tmp_project  # noqa: E402


class DryRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tmp_project(brief=BRIEF3)
        code, out = run(cls.root, "init", "BRIEF.md", "--op", "init")
        assert out["ok"], out
        cls.team = DryRunTeam(cls.root)
        cls.team.run_to_end()
        cls.state = state_of(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_reaches_the_handoff_in_12_calls(self):
        self.assertEqual(self.state["run"]["status"], "handed_off")
        self.assertEqual(next_lines(self.root), ["DONE handed_off"])
        self.assertEqual(self.state["budget"]["calls"]["total"], 12)

    def test_contacts_are_a_and_g3_only(self):
        self.assertEqual(self.state["contacts"]["seen"], [["A", 1], ["G3", 1]])
        self.assertEqual(self.state["gates"]["Q2"]["status"], "closed")

    def test_no_restart_by_added_ids_own_role_or_answered_findings(self):
        attempts = {n: len(t["attempts"]) for n, t in self.state["tasks"].items()}
        # ux finished before design; the IDs design added restart nothing.
        for task in ("strategy", "catalog", "design", "ux", "security", "slices", "quality"):
            self.assertEqual(attempts[task], 1, task)
        # performance: its first call and one recheck for the outside line of the Jobs section.
        self.assertEqual(attempts["performance"], 2)
        self.assertEqual(self.state["tasks"]["performance"]["mode"], "recheck")
        self.assertEqual(self.state["tasks"]["performance"]["stale_ids"], ["E-03"])

    def test_no_verdict_call_and_proposed_solutions_go_to_the_tasks(self):
        self.assertFalse([n for n in self.state["tasks"] if "verdict" in n])
        self.assertEqual({k: f["status"] for k, f in self.state["findings"].items()},
                         {"DA-01": "fixed", "PERF-02": "fixed", "SEC-02": "fixed"})
        files = self.state["handoff"]["files"]
        texts = [(self.root / f["path"]).read_text(encoding="utf-8") for f in files]
        section = [t.split("## Doğrulanacak riskler\n", 1)[1].split("\n\n", 1)[0] for t in texts]
        self.assertEqual(section[0].splitlines(), [
            "- PERF-02 (MAJOR) | Risk: no slot index on E-01 | Önerilen çözüm: added the slot index to E-01 | "
            "Doğrulama: çözümü bir testle dene, kanıtı Evidence satırına yaz",
            "- SEC-02 (CRITICAL, mutlaka doğrula) | Risk: E-01 has no tenant_id | Önerilen çözüm: added "
            "tenant_id to E-01 | Doğrulama: çözümü bir testle dene, kanıtı Evidence satırına yaz"])
        self.assertEqual(section[1], "- yok")
        self.assertTrue(section[2].startswith("- DA-01 (CRITICAL, mutlaka doğrula) | Risk: two reminder runs"))

    def test_tasks_carry_the_one_hop_inputs(self):
        files = self.state["handoff"]["files"]
        self.assertEqual([f["slice"] for f in files], ["S0", "S1", "S2"])
        s0 = (self.root / files[0]["path"]).read_text(encoding="utf-8")
        inputs = next(l for l in s0.splitlines() if l.startswith("- Inputs:"))
        for id_ in ("F-01", "BR-01", "INV-01", "D-01", "D-02", "SEC-01"):
            self.assertIn(id_, inputs)
        self.assertIn("E-01", s0)


SMALL_BRIEF = BRIEF3.replace("- 12 aylık büyüme: 30%\n", "- 12 aylık büyüme: 30%\n- Plan boyutu: küçük\n")


class SmallDryRunTest(unittest.TestCase):
    """Small mode skips performance and quality and reaches the handoff in clearly fewer calls (15.9)."""

    def test_small_mode_reaches_the_handoff_in_fewer_calls(self):
        root = tmp_project(brief=SMALL_BRIEF)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code, out = run(root, "init", "BRIEF.md", "--op", "init")
        self.assertEqual(out["result"]["size"], "küçük")
        DryRunTeam(root).run_to_end()
        state = state_of(root)
        self.assertEqual(state["run"]["status"], "handed_off")
        self.assertEqual(state["budget"]["calls"]["total"], 9)
        by_role = state["budget"]["calls"]["by_role"]
        self.assertNotIn("performance-architect", by_role)
        self.assertNotIn("quality-engineer", by_role)
        self.assertEqual(state["tasks"]["security"]["attempts"][-1]["model"], "sonnet")


if __name__ == "__main__":
    unittest.main()
