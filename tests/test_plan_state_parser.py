"""
Parser, brief-check, ID block scan and impact analysis tests (sections 5.4, 7.7, 9).
"""
import unittest

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import (ADR, BRIEF, DOM, PERFDOC, THREAT, UXDOC, Eng, checks, engine,
                                 registry, through_design)


class ParserTest(unittest.TestCase):
    def parse(self, *lines, attempt="design-a1"):
        head = [f"ATTEMPT {attempt}"] if attempt else []
        return checks.parse_output("\n".join(head + list(lines)) + "\n")

    def test_every_line_type(self):
        out = self.parse(
            "QUESTION PM-1.1 | Which record? | A: company | B: person | C: both | REC: A | WHY: scope | AFFECTS: Account",
            "ASSUMPTION Currency is tenant wide.",
            "WROTE docs/05-work/plans/PLAN-0001-x.md",
            "OPEN Q-1 | Need export? | blocking: no | default: no export | kind: feature",
            "OPEN Q-2 | Region? | blocking: yes | default: eu",
            "FINDING SEC-01 | CRITICAL | solution-architect | cross tenant read | D-01 has no tenant_id | class: H3",
            "FIX SEC-01 | docs/03-domains/x/DOM-0001-x.md | impact: contract | added tenant_id",
            "DISPUTE SEC-02 | the field exists in D-01",
            "RECHECK ux | local | names unchanged",
            "CONFLICT SEC-01 | ux-designer | docs/x.md | the screen shows all tenants",
            "NO QUESTIONS",
        )
        self.assertEqual(out["attempt_id"], "design-a1")
        self.assertEqual(out["warnings"], [])
        types = [l["type"] for l in out["lines"]]
        self.assertEqual(types, ["QUESTION", "ASSUMPTION", "WROTE", "OPEN", "OPEN", "FINDING", "FIX", "DISPUTE",
                                 "RECHECK", "CONFLICT", "NO_QUESTIONS"])
        self.assertEqual(out["lines"][3]["kind"], "feature")
        self.assertTrue(out["lines"][4]["blocking"])
        self.assertEqual(out["lines"][5]["cls"], "H3")
        self.assertEqual(out["lines"][6]["impact"], "contract")
        self.assertEqual(out["lines"][8]["reason"], "names unchanged")

    def test_free_last_field_keeps_pipes(self):
        out = self.parse("FINDING DA-01 | MAJOR | product-manager | S0 lacks deploy | see a | b | c",
                         "FIX DA-01 | docs/a.md | impact: local | moved x | y",
                         "DISPUTE DA-02 | a | b",
                         "OPEN Q-1 | q | blocking: no | default: a | b")
        f, fix, dispute, open_ = out["lines"]
        self.assertEqual(f["evidence"], "see a | b | c")
        self.assertIsNone(f["cls"])
        self.assertEqual(fix["change"], "moved x | y")
        self.assertEqual(dispute["evidence"], "a | b")
        self.assertEqual(open_["default"], "a | b")
        self.assertIsNone(open_["kind"])

    def test_fix_without_impact_is_ambiguous(self):
        line = self.parse("FIX SEC-01 | docs/a.md | changed text")["lines"][0]
        self.assertIsNone(line["impact"])
        self.assertEqual(registry.classify({}, [line["impact"]]), "ambiguous")

    def test_missing_attempt_and_bad_lines(self):
        out = self.parse("ASSUMPTION a", attempt=None)
        self.assertIsNone(out["attempt_id"])
        out = self.parse("hello there", "FINDING X | HUGE | a | b | c", "VERDICT DA-01 | maybe")
        self.assertEqual(out["lines"], [])
        self.assertEqual(len(out["warnings"]), 3)


class BriefCheckTest(unittest.TestCase):
    def test_valid_brief(self):
        r = checks.brief_check(BRIEF)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["features"], ["F-01"])

    def test_problems(self):
        text = BRIEF.replace("- Invoicing.\n", "").replace("Öncelik: P1", "Öncelik: P2")
        text = text.replace("Kiracı sayısı: 50", "Kiracı sayısı: bilmiyorum").replace(
            "Eşzamanlı kullanıcı: 40", "Eşzamanlı kullanıcı: many")
        text += "\n### F-01 Again\n"
        r = checks.brief_check(text.replace("## 9.", "## 9."))
        self.assertFalse(r["ok"])
        joined = " ".join(r["missing"])
        self.assertIn("section 2", joined)
        self.assertIn("no P1 feature", joined)
        self.assertIn("duplicate feature id F-01", joined)
        self.assertIn("Eşzamanlı kullanıcı must be a number", joined)
        self.assertEqual(r["questions"], ["section 4: Kiracı sayısı is unknown"])

    def test_template_example_in_comment_is_ignored(self):
        from plan_state_fixtures import SKILL
        text = (SKILL / "templates" / "brief.md").read_text(encoding="utf-8")
        self.assertEqual(checks.brief_check(text)["features"], ["F-01"])
        self.assertEqual(list(registry.scan_doc(text)["blocks"]), ["F-01"])


class ScanTest(unittest.TestCase):
    def test_blocks_lines_and_refs(self):
        text = ("---\nid: PLAN-0001\n---\n# Plan\nIntro text.\n## Stories\n"
                "- US-01 As a rep. F-01\n  - When x, the system shall y.\n"
                "- US-02 Another. F-02\n## Rules\n| BR-01 | one tenant | INV-01 |\n"
                "```mermaid\n- D-09 not a definition\n```\n")
        scan = registry.scan_doc(text)
        self.assertEqual(sorted(scan["blocks"]), ["BR-01", "US-01", "US-02"])
        self.assertEqual((scan["blocks"]["US-01"]["start"], scan["blocks"]["US-01"]["end"]), (7, 8))
        self.assertEqual(scan["blocks"]["US-01"]["refs"], ["F-01"])
        self.assertIn("criterion", scan["blocks"]["US-01"]["flags"])
        self.assertEqual(scan["blocks"]["BR-01"]["refs"], ["D-09", "INV-01"])
        self.assertNotIn("ADR", " ".join(registry.ID_RE.findall("see ADR-0001 and PERF-01 and S0")))
        self.assertEqual(registry.ID_RE.findall("see ADR-0001 and PERF-01 and S0"), ["PERF-01", "S0"])

    def test_decision_rows(self):
        text = "| ID | Title | karar |\n|---|---|---|\n| M-01 | Audit | accept |\n| R-02 | Export | |\n"
        self.assertEqual(checks.decision_rows(text), [("M-01", "accept"), ("R-02", "")])

    def test_parallel_write_maps_are_disjoint(self):
        self.assertEqual(registry.validate_parallel_maps(engine.PARALLEL_ROLES), [])
        self.assertTrue(registry.validate_parallel_maps([("product-manager", "ux-designer")]))


class ImpactTest(unittest.TestCase):
    """The examples of 7.7, run through the engine."""

    def setup_dependents(self):
        e = Eng()
        through_design(e, dom="### D-01 ERD\n- account(id, tenant_id) for F-01 and US-01.\n")
        e.run_task("security", {THREAT: "### SEC-01 Isolation\n- RLS on account in D-01.\n"},
                   lines=["FINDING SEC-02 | MAJOR | solution-architect | no soft delete | D-01"])
        e.run_task("performance", {PERFDOC: "### PERF-01 p95\n- Index on account in D-01.\n"
                                            "- deferred: perf-team\n"})
        self.assertEqual(e.status("fix1.solution-architect"), "pending")
        return e

    def fix(self, e, new_dom, impact="contract", adr=None):
        e.start("fix1.solution-architect", [DOM, ADR])
        e.docs[DOM] = new_dom
        if adr is not None:
            e.docs[ADR] = adr
        decl = f"impact: {impact} | " if impact else ""
        return e.record("fix1.solution-architect", [f"FIX SEC-02 | {DOM} | {decl}changed"])

    def test_added_field_is_contract_and_additive_dependents_pass_by_script(self):
        e = self.setup_dependents()
        res = self.fix(e, "### D-01 ERD\n- account(id, tenant_id) for F-01 and US-01.\n- account.deleted_at\n")
        self.assertEqual(res["impact"]["class"], "contract")
        # security raised SEC-02, so the proposed solution sends it no recheck (15.11).
        self.assertEqual(res["impact"]["stale"], ["performance"])
        self.assertEqual(res["impact"]["revalidated"], ["performance"])
        self.assertEqual(e.status("ux"), "done")
        self.assertEqual(e.status("security"), "done")
        self.assertEqual(e.state["tasks"]["performance"]["history"][-2][3], "T6")
        self.assertEqual(e.state["tasks"]["performance"]["history"][-1][3], "T7")

    def test_changed_line_in_a_fix_round_queues_one_recheck(self):
        e = self.setup_dependents()
        res = self.fix(e, "### D-01 ERD\n- account(id, tenant_id, deleted_at) for F-01 and US-01.\n")
        self.assertEqual(res["impact"]["queued"], ["performance"])
        self.assertEqual(res["impact"]["revise"], [])
        self.assertEqual(e.status("security"), "done")
        # fix1 is done, so the queue is flushed: one recheck, not a revise.
        self.assertEqual(e.state["tasks"]["performance"]["mode"], "recheck")
        self.assertEqual(e.state["tasks"]["performance"]["stale_ids"], ["D-01"])
        self.assertEqual(e.state["recheck_queue"], {})
        self.assertIn(("RUN", ["performance", "performance-architect", "recheck", "sonnet"]),
                      engine.next_lines(e.state))
        # slices (step 5) waits for the restarted step 4 task.
        self.assertNotIn("slices", engine.runnable(e.state))

    def test_changed_contract_outside_a_fix_round_needs_a_revise(self):
        e = Eng()
        e.run_task("strategy", {"docs/01-architecture/modules/ARCH-0001-invariants.md": "- INV-01 Tenant id.\n",
                                "docs/02-decisions/ADR-0001-strategy.md": "Monolith. INV-01\n"})
        e.run_task("catalog", {"docs/05-work/plans/PLAN-0001-catalog.md":
                               "### F-01 Board\n- BR-01 One tenant per deal. INV-01\n"})
        e.decide("G1", "modify", note="tenant per schema")
        self.assertEqual(e.status("catalog"), "done")
        res = e.run_task("strategy", {"docs/01-architecture/modules/ARCH-0001-invariants.md":
                                      "- INV-01 Tenant per schema.\n"})
        self.assertEqual(res["impact"]["revise"], ["catalog"])
        self.assertEqual(e.state["tasks"]["catalog"]["mode"], "revise")

    def test_whitespace_outside_blocks_is_local_and_a_word_is_ambiguous(self):
        e = self.setup_dependents()
        res = self.fix(e, e.docs[DOM], impact="local", adr="API  for F-01. \n\n")
        self.assertEqual(res["impact"]["class"], "local")
        self.assertEqual(res["impact"]["stale"], [])
        e2 = self.setup_dependents()
        res = self.fix(e2, e2.docs[DOM], impact="local", adr="APIs for F-01.\n")
        self.assertEqual(res["impact"]["class"], "ambiguous")

    def test_local_claim_with_outside_change_is_ambiguous_and_rechecks(self):
        e = self.setup_dependents()
        dom = "Sequence: the worker locks account first.\n" + e.docs[DOM]
        res = self.fix(e, dom, impact="local")
        self.assertEqual(res["impact"]["class"], "ambiguous")
        self.assertEqual(res["impact"]["queued"], ["performance"])
        self.assertEqual(e.state["tasks"]["performance"]["mode"], "recheck")
        e.start("performance", [PERFDOC])
        self.assertEqual(e.record("performance", ["ASSUMPTION fine"])["error"], "CHECK_FAILED")
        e.start("performance")
        res = e.record("performance", ["RECHECK performance | contract | the lock order changes the index"])
        self.assertEqual(e.status("performance"), "pending")
        self.assertEqual(e.state["tasks"]["performance"]["mode"], "revise")

    def test_ambiguous_change_targets_only_its_section(self):
        old = registry.scan_doc("## Data\n### E-01 a\n- x\n## Jobs\nRuns hourly.\n### E-02 b\n- y\n")
        new = registry.scan_doc("## Data\n### E-01 a\n- x\n## Jobs\nRuns hourly with a lock.\n### E-02 b\n- y\n")
        diff = registry.compare(old, new)
        self.assertTrue(diff["outside"])
        self.assertEqual(diff["sections"], ["E-02"])
        self.assertEqual(new["blocks"]["E-02"]["heading"], "## Jobs")

    def test_added_ids_mark_nothing(self):
        e = self.setup_dependents()
        orig = e.docs[DOM]
        res = self.fix(e, orig + "\n### D-03 Audit\n- audit rows for D-01\n")
        self.assertEqual(res["error"], "CHECK_FAILED")  # D-03 is not reserved
        e.do("alloc", {"prefix": "D", "n": 1, "owner": "solution-architect"})
        e.start("fix1.solution-architect")
        e.docs[DOM] = orig + "\n### D-03 Audit\n- audit rows\n"
        res = e.record("fix1.solution-architect", ["FIX SEC-02 | x | impact: contract | added D-03"])
        self.assertEqual(res["impact"]["changed"], ["D-03"])
        self.assertEqual((res["impact"]["stale"], res["impact"]["queued"]), ([], []))

    def test_fix_without_impact_is_ambiguous(self):
        e = self.setup_dependents()
        res = self.fix(e, e.docs[DOM], impact=None)
        self.assertEqual(res["impact"]["class"], "ambiguous")

    def test_deleted_id_is_retired_and_references_fail(self):
        e = self.setup_dependents()
        res = self.fix(e, "### D-03 Other\n- nothing\n")
        self.assertEqual(res["error"], "CHECK_FAILED")
        e.start("fix1.solution-architect")
        e.docs[DOM] = "No diagram any more.\n"
        res = e.record("fix1.solution-architect", ["FIX SEC-02 | x | impact: contract | removed D-01"])
        self.assertEqual(res["impact"]["retired"], ["D-01"])
        self.assertEqual(e.state["ids"]["D-01"]["status"], "retired")
        self.assertEqual(res["impact"]["queued"], ["performance"])
        errors = checks.id_errors(e.state)
        self.assertIn(f"H4 {THREAT}: references retired id D-01", errors)
        e.do("alloc", {"prefix": "D", "n": 1, "owner": "solution-architect"})
        self.assertNotIn("D-01", [i for i, r in e.state["ids"].items() if r["status"] == "reserved"])

    def test_contract_change_reopens_an_approved_g3(self):
        e = self.setup_dependents()
        e.state["gates"]["G3"]["status"] = "approved"
        self.fix(e, "### D-01 ERD\n- account(id) only.\n")
        self.assertEqual(e.state["gates"]["G3"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
