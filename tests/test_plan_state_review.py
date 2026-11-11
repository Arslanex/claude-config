"""
Regression tests for the defects an independent review of the planning process found.

Each test class names the defect it reproduces; the numbers follow the review list.
"""
import shutil
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import (ADR, CATALOG, DOM, INV, PERFDOC, SKILL, STRAT, THREAT, UXDOC, Eng, FakeTeam,
                                 checks, cli, engine, next_lines, registry, run, state_of, through_design,
                                 through_gate_a, tmp_project)

TABLE = ("| ID | Kind | Title | karar |\n|---|---|---|---|\n| F-01 | F | Board | {f} |\n"
         "| M-01 | M | Audit | {m} |\n| R-01 | R | Export | {r} |\n")
CATALOG_TABLE = TABLE + "- US-01 (F-01) As a rep I want the board.\n  - When x, the system shall y.\n"


def finding(severity="MAJOR", owner="product-manager", raised_by="plan-critic", status="open", claim="c",
            evidence="e", cls=None):
    return {"severity": severity, "owner": owner, "claim": claim, "evidence": evidence, "cls": cls,
            "raised_by": raised_by, "task": "x", "status": status, "history": [],
            "reply": None}


def done_until(e, names):
    """Mark every task except names done, then let the scheduler run."""
    for name, t in e.state["tasks"].items():
        if name not in names:
            t["status"] = "done"
    engine.advance(e.state, "now")


class KararColumnTest(unittest.TestCase):
    """1: filling the karar cells must not change any row hash; the gate stores the rescan."""

    def test_karar_cells_are_not_part_of_the_block_hash(self):
        empty = registry.scan_doc(CATALOG_TABLE.format(f="", m="", r=""))
        filled = registry.scan_doc(CATALOG_TABLE.format(f="kabul", m="accept", r="ertele"))
        diff = registry.compare(empty, filled)
        self.assertEqual((diff["added"], diff["removed"], diff["changed"], diff["outside"]), ([], [], [], False))
        changed = registry.scan_doc(CATALOG_TABLE.format(f="", m="", r="").replace("Audit", "Audit log"))
        self.assertEqual(registry.compare(empty, changed)["changed"], ["M-01"])

    def test_gate_from_doc_keeps_the_post_decision_scan(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 Tenant id.\n", STRAT: "Monolith. INV-01 F-01\n"})
        e.run_task("catalog", {CATALOG: CATALOG_TABLE.format(f="", m="", r="")})
        e.decide("G1", "approve")
        filled = CATALOG_TABLE.format(f="kabul", m="kabul", r="ertele")
        scan = registry.scan_doc(filled)
        res = e.decide("G2", "approve", rows=checks.decision_rows(filled), from_doc=True,
                       doc_scans={CATALOG: scan})
        self.assertEqual(res["status"], "approved")
        self.assertEqual(e.state["artifacts"][CATALOG]["hash"], scan["hash"])
        self.assertEqual(e.state["ids"]["M-01"]["decision"], "accepted")
        self.assertEqual(e.state["ids"]["R-01"]["decision"], "deferred")
        self.assertEqual(e.status("strategy"), "done")


class RestatedIdTest(unittest.TestCase):
    """2: the catalog restating the brief's F-01 is not an added ID and leaves strategy done."""

    def test_restated_feature_is_not_a_contract_change(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 Tenant id.\n", STRAT: "Monolith for F-01. INV-01\n"})
        res = e.run_task("catalog", {CATALOG: "### F-01 Pipeline board\n- US-01 (F-01) As a rep.\n"
                                              "  - When x, the system shall y.\n"})
        self.assertNotIn("strategy", res["impact"]["stale"])
        self.assertEqual(e.status("strategy"), "done")


class TemplateIdsTest(unittest.TestCase):
    """3: every template, filled with its own example IDs, passes the ID checks (no H4)."""

    PATHS = {"brief.md": ("docs/05-work/plans/BRIEF-0001-x.md", "brief", "user"),
             "strategy.md": (STRAT, "strategy", "strategy-architect"),
             "invariants.md": (INV, "strategy", "strategy-architect"),
             "catalog.md": (CATALOG, "catalog", "product-manager"),
             "domain.md": (DOM, "design", "solution-architect"),
             "system.md": (ADR, "design", "solution-architect"),
             "ux.md": (UXDOC, "ux", "ux-designer"),
             "threat.md": (THREAT, "security", "security-architect"),
             "performance.md": (PERFDOC, "performance", "performance-architect"),
             "slices.md": ("docs/05-work/plans/PLAN-0003-slices.md", "slices", "product-manager"),
             "quality.md": ("docs/05-work/plans/quality/PLAN-0004-q.md", "quality", "quality-engineer")}

    def test_templates_have_no_id_errors(self):
        state = engine.new_state("PLAN-0001")
        for name, (path, task, role) in self.PATHS.items():
            text = (SKILL / "templates" / name).read_text(encoding="utf-8")
            scan = registry.scan_doc(text)
            self.assertEqual(scan["duplicates"], [], name)
            own = registry.ROLES[role]["prefixes"]
            for id_ in scan["blocks"]:
                with self.subTest(template=name, id=id_):
                    self.assertTrue(registry.prefix_of(id_) in own or registry.prefix_of(id_) == "F", id_)
            state["artifacts"][path] = {"owner_task": task, "role": role, **scan}
        engine._register_ids(state, "user", 1)
        self.assertEqual(checks.id_errors(state), [])

    def test_catalog_rationale_does_not_define_m_ids(self):
        text = (SKILL / "templates" / "catalog.md").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^- M-\d+")


class CriticNoFindingsTest(unittest.TestCase):
    """4: NO FINDINGS is valid; no verdict task exists at all (15.11)."""

    def test_no_findings_line_is_content(self):
        out = checks.parse_output("ATTEMPT critic_review-a1\nNO FINDINGS\n")
        self.assertEqual(out["lines"], [{"type": "NO_FINDINGS"}])
        self.assertEqual(out["warnings"], [])

    def test_a_proposed_solution_gets_no_verdict_task(self):
        e = Eng()
        e.state["findings"]["DA-01"] = finding(severity="CRITICAL", status="fixed")
        done_until(e, ("fix2",))
        self.assertEqual(e.status("fix2"), "done")
        self.assertFalse([n for n in e.state["tasks"] if "verdict" in n])
        self.assertEqual(e.state["gates"]["G3"]["status"], "open")
        self.assertFalse([i for i in checks.h_items(e.state) if i.startswith("H1")])


class ReadListTest(unittest.TestCase):
    """5: whole earlier docs in the read lists; E and API IDs are contract IDs."""

    def test_entity_and_endpoint_ids(self):
        self.assertEqual(registry.ID_RE.findall("E-01, API-02, SPEC-01 and PERF-01"), ["E-01", "API-02", "PERF-01"])
        self.assertIn("E", registry.ROLES["solution-architect"]["prefixes"])
        self.assertIn("API", registry.ROLES["solution-architect"]["prefixes"])
        for name, pattern in (("domain.md", r"(?m)^### E-01 "), ("system.md", r"(?m)^- API-01 ")):
            self.assertRegex((SKILL / "templates" / name).read_text(encoding="utf-8"), pattern)

    def test_deleted_at_on_an_entity_is_a_contract_change(self):
        e = Eng()
        dom = "### E-01 account\n- Fields: id, tenant_id. F-01\n"
        through_design(e, dom=dom)
        e.docs[UXDOC] = e.docs[UXDOC]
        e.run_task("security", {THREAT: "### SEC-01 Isolation\n- RLS on E-01.\n"},
                   lines=["FINDING SEC-02 | MAJOR | solution-architect | no soft delete | E-01"])
        e.run_task("performance", {PERFDOC: "### PERF-01 p95\n- Index on E-01.\n- deferred: perf-team\n"})
        e.start("fix1.solution-architect", [DOM, ADR])
        e.docs[DOM] = dom + "- deleted_at: soft delete time.\n"
        res = e.record("fix1.solution-architect", [f"FIX SEC-02 | {DOM} | impact: local | added deleted_at"])
        self.assertEqual(res["impact"]["class"], "contract")
        self.assertEqual(res["impact"]["stale"], ["performance"])

    def test_whole_doc_reads(self):
        root = tmp_project()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run(root, "init", "BRIEF.md", "--op", "init")
        team = FakeTeam(root, findings=False)
        brief = state_of(root)["run"]["brief"]
        code, text = run(root, "next")
        self.assertIn(f"  READ {brief}", text.splitlines())
        team.run_until("RUN design")
        lines = run(root, "next")[1].splitlines()
        strategy, inv = team.paths["strategy"][1], team.paths["strategy"][0]
        for path in (team.paths["catalog"][0], strategy, inv):
            self.assertIn(f"  READ {path}", lines)
        team.run_until("RUN security")
        lines = run(root, "next")[1].splitlines()
        for path in team.paths["design"]:
            self.assertIn(f"  READ {path}", lines)


class GateOrderTest(unittest.TestCase):
    """6: G2 waits for G1; G1 modify takes G2 into the same round."""

    def at_a(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"})
        e.run_task("catalog", {CATALOG: "### F-01 x\n"})
        return e

    def test_g2_refused_and_hidden_until_g1_is_approved(self):
        e = self.at_a()
        self.assertEqual(engine.next_lines(e.state), [("ASK", ["G1"])])
        self.assertEqual(e.decide("G2", "approve", defaults=True).code, "REFUSED")
        e.decide("G1", "approve")
        self.assertEqual(engine.next_lines(e.state), [("ASK", ["G2"])])
        self.assertEqual(e.decide("G2", "approve", defaults=True)["status"], "approved")
        self.assertEqual(e.state["contacts"]["count"], 1)

    def test_g1_modify_takes_g2_into_the_same_round(self):
        e = self.at_a()
        e.decide("G1", "modify", note="tenant per schema")
        self.assertEqual(e.state["gates"]["G2"]["status"], "modify_requested")
        e.run_task("strategy", {})
        self.assertEqual(e.state["gates"]["G1"]["status"], "open")
        self.assertEqual(e.state["gates"]["G2"]["status"], "open")
        self.assertEqual(e.decide("G2", "modify", item="F-01").code, "REFUSED")
        e.decide("G1", "approve")
        self.assertEqual(e.decide("G2", "modify", rows=[["F-01", "modify"]]).code, "REFUSED")


class CriticalAndDescopeTest(unittest.TestCase):
    """7: every unresolved CRITICAL is an H item; descope clears only fully out-of-scope findings."""

    def test_critical_of_any_prefix_is_h1(self):
        e = Eng()
        e.state["findings"]["DA-01"] = finding(severity="CRITICAL")
        self.assertTrue(any(i.startswith("H1 DA-01") for i in checks.h_items(e.state)))

    def test_descope_needs_every_referenced_item_out_of_scope(self):
        e = Eng()
        through_gate_a(e)
        e.state["ids"]["F-02"] = dict(e.state["ids"]["F-01"], doc=None)
        e.state["findings"]["DA-01"] = finding(claim="F-01 and F-02 conflict")
        e.state["findings"]["DA-02"] = finding(claim="F-02 has no screen")
        e.state["gates"]["G3"]["status"] = "open"
        e.decide("G3", "descope", item="F-02")
        self.assertEqual(e.state["findings"]["DA-01"]["status"], "open")
        self.assertEqual(e.state["findings"]["DA-02"]["status"], "descoped")


class HandoffFailureTest(unittest.TestCase):
    """8: a failed prepare asks the user instead of looping; one rule for G3 and the precheck."""

    def test_failed_prepare_asks_once_with_errors(self):
        root = tmp_project()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run(root, "init", "BRIEF.md", "--op", "init")
        FakeTeam(root).run_until("RUN handoff")
        (root / "docs" / "bad.md").write_text("no front matter\n", encoding="utf-8")
        code, out = run(root, "handoff", "prepare", "--op", "p1")
        self.assertFalse(out["ok"])
        code, text = run(root, "next")
        lines = text.splitlines()
        self.assertEqual(lines[0], "ASK handoff")
        self.assertTrue(any(l.startswith("  ERROR H4 lint") for l in lines), lines)

    def test_slice_without_criterion_fails_design_traceability(self):
        e = Eng()
        through_gate_a(e)
        e.state["artifacts"]["docs/05-work/plans/PLAN-0009-s.md"] = {
            "owner_task": "slices", "role": "product-manager",
            **registry.scan_doc("### S0 Skeleton\n- Doğrulama: smoke test.\n")}
        errors = checks.traceability(e.state)
        self.assertIn("H6 S0: no acceptance criterion", errors)


class CriticRoundTest(unittest.TestCase):
    """9: product-manager runs once in step 5; Q2."""

    def test_product_manager_runs_once_in_step_5(self):
        e = Eng()
        e.state["findings"]["SEC-02"] = finding(owner="product-manager", raised_by="security-architect")
        e.state["findings"]["SEC-03"] = finding(owner="solution-architect", raised_by="security-architect")
        done_until(e, ("fix1", "slices", "quality", "critic_review", "fix2"))
        self.assertNotIn("fix1.product-manager", e.state["tasks"])
        self.assertEqual(e.status("fix1.solution-architect"), "pending")
        self.assertEqual(engine.assigned_findings(e.state, "slices"), ["SEC-02"])

    def test_q2_batches_blocking_p1_items_once(self):
        e = Eng()
        through_design(e)
        e.state["findings"]["SEC-01"] = finding(severity="CRITICAL", owner="solution-architect",
                                                raised_by="security-architect")
        e.start("security", [THREAT])
        e.record("security", ["OPEN Q-7 | Is F-01 per tenant? | blocking: yes | default: yes"])
        self.assertIn(("ASK", ["Q2"]), engine.next_lines(e.state))
        # fix1 has not run, so the CRITICAL finding is not a question yet.
        self.assertEqual(sorted(i["id"] for i in e.state["gates"]["Q2"]["items"]), ["Q-7"])
        e.decide("Q2", "approve", note="F-01 is per tenant")
        self.assertEqual(e.state["gates"]["Q2"]["status"], "approved")
        e.start("performance", [PERFDOC])
        e.record("performance", ["OPEN Q-8 | F-01 cache? | blocking: yes | default: no"])
        self.assertNotIn(("ASK", ["Q2"]), engine.next_lines(e.state))
        self.assertEqual(e.state["gates"]["Q2"]["status"], "approved")

    def test_q2_asks_a_critical_only_when_fix1_left_it_open(self):
        e = Eng()
        e.state["findings"]["SEC-01"] = finding(severity="CRITICAL", owner="solution-architect",
                                                raised_by="security-architect", status="fixed")
        for gate in ("Q1", "G1", "G2"):
            e.state["gates"][gate]["status"] = "approved"
        done_until(e, ("slices", "quality", "critic_review", "fix2"))
        self.assertEqual(e.state["gates"]["Q2"]["status"], "closed")
        e.state["findings"]["SEC-01"]["status"] = "disputed"
        engine.advance(e.state, "now")
        self.assertEqual([i["id"] for i in e.state["gates"]["Q2"]["items"]], ["SEC-01"])

    def test_non_p1_blocking_open_goes_to_b(self):
        e = Eng()
        through_design(e)
        e.start("security", [THREAT])
        e.record("security", ["OPEN Q-7 | Export format? | blocking: yes | default: csv"])
        self.assertEqual(e.state["gates"]["Q2"]["status"], "closed")


class CheckCallFindingTest(unittest.TestCase):
    """15.9: a check call opens a new finding only when it is CRITICAL; any other one is a dev-team note."""

    def at_security_revise(self):
        e = Eng()
        done_until(e, ())
        engine._restart(e.state, "security", "revise", ["E-01"], "test")
        e.start("security")
        return e

    def test_non_critical_finding_in_a_revise_becomes_a_dev_note(self):
        e = self.at_security_revise()
        res = e.record("security", [
            "ASSUMPTION revised",
            "FINDING SEC-05 | MAJOR | solution-architect | the 3 hour gap check misses midnight | E-01"])
        self.assertNotIn("SEC-05", e.state["findings"])
        self.assertEqual(res["findings"], [])
        risk = e.state["notes"]["risks"][-1]
        self.assertEqual((risk["task"], risk["ids"], risk["kind"]), ("security", ["SEC-05"], "dev_note"))
        self.assertTrue(risk["text"].startswith("geliştirme ekibine not: SEC-05 MAJOR"))
        self.assertFalse([n for n, t in e.state["tasks"].items() if t["status"] == "pending"])
        self.assertEqual(e.state["gates"]["G3"]["status"], "open")
        self.assertFalse([i for i in checks.h_items(e.state) if "SEC-" in i])

    def test_critical_finding_in_a_revise_still_opens_and_blocks(self):
        e = self.at_security_revise()
        e.record("security", [
            "ASSUMPTION revised",
            "FINDING SEC-06 | CRITICAL | solution-architect | a restore loses the last day | E-01"])
        self.assertEqual(e.state["findings"]["SEC-06"]["status"], "open")
        self.assertIn("H1 SEC-06: unresolved CRITICAL finding", checks.h_items(e.state))

    def test_non_critical_finding_in_a_recheck_becomes_a_dev_note(self):
        e = Eng()
        done_until(e, ("fix2",))
        engine._restart(e.state, "security", "recheck", ["E-01"], "test")
        e.start("security")
        e.record("security", ["RECHECK security | local | still valid",
                              "FINDING SEC-08 | MINOR | solution-architect | idle timer resets on poll | E-01"])
        self.assertNotIn("SEC-08", e.state["findings"])
        self.assertEqual(e.state["notes"]["risks"][-1]["ids"], ["SEC-08"])

    def test_first_draft_still_raises_any_finding(self):
        e = Eng()
        through_design(e)
        e.start("security", [THREAT])
        e.record("security", ["FINDING SEC-02 | MINOR | solution-architect | weak audit | E-01"])
        self.assertEqual(e.state["findings"]["SEC-02"]["status"], "open")


SMALL_BRIEF = Eng().brief.replace("- 12 aylık büyüme: 30%\n", "- 12 aylık büyüme: 30%\n- Plan boyutu: küçük\n")


class SmallModeTest(unittest.TestCase):
    """15.9: the küçük plan size skips performance and quality, runs security on sonnet and caps calls at 14."""

    def test_plan_size_comes_from_the_brief(self):
        self.assertEqual(checks.plan_size(SMALL_BRIEF), "küçük")
        self.assertEqual(checks.plan_size(Eng().brief), "tam")
        template = (SKILL / "templates" / "brief.md").read_text(encoding="utf-8")
        self.assertEqual(checks.plan_size(template), "tam")
        self.assertEqual(checks.plan_size(template.replace("Plan boyutu: tam", "Plan boyutu: küçük")), "küçük")

    def test_small_run_skips_and_limits(self):
        e = Eng(SMALL_BRIEF)
        self.assertEqual(e.state["run"]["size"], "küçük")
        for name in ("performance", "quality"):
            self.assertEqual(e.status(name), "done")
            self.assertTrue(e.state["tasks"][name]["skipped"])
        self.assertEqual(e.state["tasks"]["security"]["model"], "sonnet")
        self.assertEqual({k: e.state["limits"]["calls"][k] for k in ("cap", "warn", "max")},
                         {"cap": 14, "warn": 10, "max": 18})
        through_design(e)
        runs = [f for k, f in engine.next_lines(e.state) if k == "RUN"]
        self.assertEqual(runs, [["security", "security-architect", "draft", "sonnet"]])

    def test_tam_run_is_unchanged(self):
        e = Eng()
        self.assertEqual(e.state["run"]["size"], "tam")
        self.assertEqual(e.state["limits"], engine.LIMITS)
        self.assertEqual(e.state["tasks"]["security"]["model"], "opus")
        self.assertEqual(e.status("performance"), "pending")

    def test_small_call_cap_is_14_with_one_closing_call_reserved(self):
        e = Eng(SMALL_BRIEF)
        self.assertEqual(e.state["limits"]["calls"]["cap"], 14)
        e.state["gates"]["G2"]["status"] = "approved"
        e.state["budget"]["calls"]["total"] = 13
        res = e.start("strategy")
        self.assertEqual(res.code, "BUDGET")
        self.assertIn("reserved for the closing call", res.message)
        e.state["budget"]["calls"]["total"] = 12
        self.assertEqual(e.start("strategy")["attempt"], "strategy-a1")


class GateValueTest(unittest.TestCase):
    """11: only fixed decision values and their Turkish words are accepted."""

    def at_g2(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"})
        e.run_task("catalog", {CATALOG: TABLE.format(f="", m="", r="")})
        e.decide("G1", "approve")
        return e

    def test_turkish_words(self):
        e = self.at_g2()
        res = e.decide("G2", "approve", rows=[["F-01", "Kabul"], ["M-01", "kabul"], ["R-01", "ertele"]])
        self.assertEqual(res["status"], "approved")
        self.assertEqual(e.state["ids"]["R-01"]["decision"], "deferred")
        self.assertEqual(checks.normalize_value("G3", "kapsamdan  çıkar"), "descope")
        self.assertEqual(checks.normalize_value("G3", "onayla"), "approve")

    def test_bad_cells_are_listed(self):
        e = self.at_g2()
        res = e.decide("G2", "approve", rows=[["F-01", "ok"], ["M-01", "kabul"], ["R-01", "later"]])
        self.assertEqual(res.code, "CHECK_FAILED")
        self.assertIn("F-01", res.message)
        self.assertIn("R-01", res.message)


class CliFlowTest(unittest.TestCase):
    """12, 14, 15: INV accepted at G1, FINDINGS details in next, the brief doc made at init."""

    def setUp(self):
        self.root = tmp_project()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        code, out = run(self.root, "init", "BRIEF.md", "--op", "init")
        self.assertTrue(out["ok"], out)

    def test_brief_doc_is_created_at_init(self):
        state = state_of(self.root)
        self.assertEqual(state["run"]["brief"], "docs/05-work/plans/BRIEF-0001-deal-board.md")
        self.assertFalse((self.root / "BRIEF.md").exists())
        self.assertIn("id: BRIEF-0001", (self.root / state["run"]["brief"]).read_text())
        code, out = run(self.root, "init", state["run"]["brief"])
        self.assertEqual(out["error"]["code"], "REFUSED")

    def test_g1_approve_accepts_the_inv_doc(self):
        team = FakeTeam(self.root)
        team.run_until("ASK")
        inv = team.paths["strategy"][0]
        self.assertIn("status: draft", (self.root / inv).read_text())
        code, out = run(self.root, "decide", "G1", "approve", "--op", "gate:G1:1")
        self.assertTrue(out["ok"], out)
        self.assertIn("status: accepted", (self.root / inv).read_text())
        state = state_of(self.root)
        self.assertEqual(state["artifacts"][inv]["hash"], registry.sha((self.root / inv).read_text()))

    def test_next_shows_claim_evidence_and_last_reply(self):
        team = FakeTeam(self.root)
        team.run_until("RUN fix1")
        lines = run(self.root, "next")[1].splitlines()
        self.assertIn("  FINDING SEC-02 | MAJOR | no audit trail | D-01 has no audit field", lines)


class InitWithoutDocsToolTest(unittest.TestCase):
    """15: without tools/docs.py init fails and tells the user to run cinit."""

    def test_init_needs_the_docs_tool(self):
        root = tmp_project(with_docs_tool=False)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code, out = run(root, "init", "BRIEF.md")
        self.assertEqual(out["error"]["code"], "REFUSED")
        self.assertIn("cinit", out["error"]["message"])
        self.assertTrue((root / "BRIEF.md").exists())
        self.assertFalse((root / "docs" / "05-work" / "plans").exists())


class SkillTextTest(unittest.TestCase):
    """10 and 14: the SKILL timeout steps, the calls answer, the op ids and the code legend."""

    def test_skill_text(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("timeout <task> --stopped", text)
        self.assertIn("within 2 minutes", text)
        self.assertIn("--op rec:<attempt>", text)
        self.assertIn("--op gate:<gate>:<round>", text)
        self.assertIn("F özellik, M eksik, G ara, R öneri", text)
        self.assertNotIn("A gate whose modify round is used up offers extend, approve or stop.\n  Record", text)


if __name__ == "__main__":
    unittest.main()


class SecondReviewTest(unittest.TestCase):
    """The defects of the second review (items 3, 4, 7, 9 and 10 of its list)."""

    def test_error_result_is_not_cached_so_the_op_works_after_extend(self):
        e = Eng()
        e.start("strategy", [INV, STRAT])
        # After closing (a later G3 change) the plain cap applies again.
        e.state["run"]["closing"] = "done"
        e.state["budget"]["calls"]["total"] = 24
        e.state["tasks"]["strategy"]["attempts"][-1]["status"] = "failed"
        res = e.do("start", {"task": "strategy", "scope": [], "tree": {}}, op="start:strategy:2")
        self.assertEqual(res["error"], "BUDGET")
        self.assertNotIn("start:strategy:2", e.state["ops"])
        e.decide("calls", "extend")
        res = e.do("start", {"task": "strategy", "scope": [], "tree": {}}, op="start:strategy:2")
        self.assertEqual(res["attempt"], "strategy-a2")
        self.assertIn("start:strategy:2", e.state["ops"])

    def test_cap_reached_by_rechecks_drops_them_as_risks(self):
        # The literal dry run: the cap is reached while only rechecks wait; closing drops them (15.10).
        e = Eng()
        done_until(e, ())
        for gate in ("G1", "G2", "G3"):
            e.state["gates"][gate]["status"] = "closed" if gate == "G3" else "approved"
        for name in ("design", "ux"):
            t = e.state["tasks"][name]
            t["status"], t["mode"], t["stale_ids"] = "pending", "recheck", ["E-03"]
        e.state["limits"]["calls"].update(cap=30, extended=True)
        e.state["budget"]["calls"]["total"] = 29
        engine.advance(e.state, "now")
        for name in ("design", "ux"):
            self.assertEqual(e.status(name), "done")
            self.assertEqual(e.state["tasks"][name]["history"][-1][3], "T10")
        self.assertEqual([r["task"] for r in e.state["notes"]["risks"]], ["design", "ux"])
        # The slices have no S block, so the one call left is the closing call.
        self.assertEqual(engine.next_lines(e.state), [("RUN", ["closing", "product-manager", "closing", "sonnet"])])

    def test_calls_extend_only_once(self):
        e = Eng()
        e.state["run"]["blocked"].append({"target": "calls", "reason": "cap"})
        self.assertEqual(e.decide("calls", "extend")["cap"], 30)
        e.state["run"]["blocked"].append({"target": "calls", "reason": "cap"})
        self.assertIn("decide calls stop", e.decide("calls", "extend").message)

    def test_g3_named_rows_are_read_and_a_change_is_not_ignored(self):
        final = ("| ID | Item | Default | karar |\n|---|---|---|---|\n"
                 "| quality: matrix | the matrix is complete | onayla | değiştir |\n| SEC-02 | x | | risk kabul |\n")
        self.assertEqual(checks.decision_rows(final), [("SEC-02", "risk kabul")])
        rows = checks.decision_rows(final, named=True)
        self.assertEqual(rows[0], ("quality: matrix", "değiştir"))
        e = Eng()
        done_until(e, ())
        e.state["gates"]["G3"]["status"] = "open"
        bad = e.decide("G3", "approve", rows=[["Varsayım 1", "değiştir"]], from_doc=True)
        self.assertEqual(bad.code, "CHECK_FAILED")
        res = e.decide("G3", "approve", rows=[["quality: matrix", "değiştir"]], from_doc=True)
        self.assertEqual(res["revise"], ["quality"])
        self.assertEqual(e.state["tasks"]["quality"]["mode"], "revise")

    def test_g3_descope_reaches_the_handoff_without_the_slice(self):
        root = tmp_project()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run(root, "init", "BRIEF.md", "--op", "init")
        FakeTeam(root, findings=False, two_slices=True).run_until("ASK G3")
        code, out = run(root, "decide", "G3", "descope", "--item", "US-02", "--op", "g3:descope")
        self.assertTrue(out["ok"], out)
        self.assertEqual(state_of(root)["gates"]["G3"]["status"], "open")
        self.assertEqual(state_of(root)["tasks"]["slices"]["status"], "done")
        code, out = run(root, "decide", "G3", "approve", "--op", "g3:approve")
        self.assertTrue(out["ok"], out)
        code, out = run(root, "handoff", "prepare", "--op", "hp")
        self.assertTrue(out["ok"], out)
        self.assertEqual([f["slice"] for f in out["result"]["files"]], ["S0"])
        code, out = run(root, "handoff", "publish", "--op", "hpub")
        self.assertTrue(out["ok"], out)
        self.assertEqual(state_of(root)["run"]["status"], "handed_off")

    def test_read_list_has_the_origin_row_of_a_promoted_feature(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 Tenant id.\n", STRAT: "Monolith. INV-01 F-01\n"})
        e.run_task("catalog", {CATALOG: CATALOG_TABLE.format(f="kabul", m="kabul", r="ertele")})
        e.decide("G1", "approve")
        e.decide("G2", "approve", rows=checks.decision_rows(CATALOG_TABLE.format(f="kabul", m="kabul", r="ertele")))
        promoted = [i for i, r in e.state["ids"].items() if r.get("origin") == "M-01"]
        self.assertEqual(len(promoted), 1)
        self.assertIn("M-01", [x[3] for x in engine.read_list(e.state, "security")])

    def test_repeated_init_returns_the_first_result(self):
        root = tmp_project()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code, first = run(root, "init", "BRIEF.md", "--op", "init")
        code, again = run(root, "init", "BRIEF.md", "--op", "init")
        self.assertTrue(again["ok"], again)
        self.assertEqual(again["result"], first["result"])

    def test_check_prints_the_traceability_rate(self):
        root = tmp_project()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run(root, "init", "BRIEF.md", "--op", "init")
        FakeTeam(root, findings=False).run_until("ASK G3")
        code, out = run(root, "check")
        self.assertEqual(out["result"]["traceability"], "1/1 (100%)")

    def test_templates_match_the_gates(self):
        strategy = (SKILL / "templates" / "strategy.md").read_text(encoding="utf-8")
        self.assertNotIn("karar", strategy)
        self.assertIn("- Kept (INV-01): ", (SKILL / "templates" / "system.md").read_text(encoding="utf-8"))
        self.assertIn("`quality: ", (SKILL / "templates" / "final.md").read_text(encoding="utf-8"))
