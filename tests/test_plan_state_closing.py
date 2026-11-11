"""
Closing at the role-call budget and the finish of a stopped run (15.10).

The plan always finishes by itself: the last calls of the cap stay for one closing call,
the remaining work becomes risks, and the run reaches G3 instead of stopping.
"""
import shutil
import unittest

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import (ADR, BRIEF3, CATALOG, DOM, INV, PERFDOC, THREAT, UXDOC, DryRunTeam, Eng, append,  # noqa: E402
                                 docs_new, engine, next_lines, registry, run, state_of, through_gate_a,
                                 tmp_project)

SMALL_BRIEF3 = BRIEF3.replace("- 12 aylık büyüme: 30%\n", "- 12 aylık büyüme: 30%\n- Plan boyutu: küçük\n")


class ClosingTeam(DryRunTeam):
    """
    The dry run team, plus the closing call and the user's one-time G3 fix of an open CRITICAL.

    At G3 with open H items the user answers değiştir for each unresolved CRITICAL finding
    once; at the next G3 the user approves as in the dry run.
    """

    def __init__(self, root):
        super().__init__(root)
        self.g3_fixes = []

    def files_for(self, task):
        if task == "closing":
            if "slices" not in self.paths:
                self.paths["slices"] = [docs_new(self.root, "plan", "Slices")]
                self.role_paths.setdefault("product-manager", []).extend(self.paths["slices"])
            return self.paths["slices"]
        return super().files_for(task)

    def step(self):
        lines = next_lines(self.root)
        if lines[0] == "ASK G3" and not self.g3_fixes:
            code, out = run(self.root, "check")
            items = out["result"]["h_items"]
            if items:
                fids = sorted({i.split()[1].rstrip(":") for i in items if i.startswith("H1 ")})
                self.g3_fixes = fids
                final = docs_new(self.root, "plan", "Final draft")
                append(self.root, final, "\n## To decide\n| ID | Item | Default | karar |\n|---|---|---|---|\n"
                       + "".join(f"| {f} | open CRITICAL | değiştir | değiştir |\n" for f in fids))
                code, out = run(self.root, "gate", "G3", "--from-doc", final, "--op", "gate:G3:fix")
                assert out["ok"], out
                return True
        return super().step()

    def write(self, task, attempt, paths):
        if task == "closing":
            if "### S0" in (self.root / paths[0]).read_text(encoding="utf-8"):
                return f"ATTEMPT {attempt}\nWROTE {paths[0]}\nASSUMPTION the slices are current\n"
            return super().write("slices", attempt, paths)
        if task.startswith("fix3."):
            fids = [l.split()[1] for l in self.prompts[task][-1] if l.startswith("FINDING ")]
            return f"ATTEMPT {attempt}\n" + "".join(f"FIX {f} | {paths[0]} | impact: local | fixed at G3\n"
                                                     for f in fids)
        return super().write(task, attempt, paths)


def dry_run(brief, cap, team=ClosingTeam):
    """Run the whole dry run with a lowered call cap. Returns (root, team, state)."""
    key = "tam" if brief is BRIEF3 else "small"
    saved = (engine.LIMITS["calls"]["cap"], engine.SMALL_LIMITS["calls"]["cap"])
    if key == "tam":
        engine.LIMITS["calls"]["cap"] = cap
    else:
        engine.SMALL_LIMITS["calls"]["cap"] = cap
    try:
        root = tmp_project(brief=brief)
        code, out = run(root, "init", "BRIEF.md", "--op", "init")
        assert out["ok"], out
        t = team(root)
        t.run_to_end()
    finally:
        engine.LIMITS["calls"]["cap"], engine.SMALL_LIMITS["calls"]["cap"] = saved
    return root, t, state_of(root)


class ClosingDryRunTest(unittest.TestCase):
    """A dry run that would hit the cap now closes itself and reaches the handoff."""

    def finish(self, brief, cap):
        root, team, state = dry_run(brief, cap)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.assertEqual(state["run"]["status"], "handed_off")
        self.assertEqual(next_lines(root), ["DONE handed_off"])
        self.assertTrue(state["handoff"]["files"])
        return team, state

    def test_tam_cap_reached_after_the_slices_fixes_the_open_critical_at_g3(self):
        team, state = self.finish(BRIEF3, 10)
        # The slices were current, so closing needed no call; fix2 did not run and DA-01 stayed open.
        self.assertNotIn("closing", state["tasks"])
        self.assertEqual(team.g3_fixes, ["DA-01"])
        self.assertEqual(len(state["tasks"]["fix3.solution-architect"]["attempts"]), 1)
        self.assertEqual(state["findings"]["DA-01"]["status"], "fixed")
        self.assertEqual(state["budget"]["calls"]["total"], 11)

    def test_tam_cap_reached_before_the_slices_lets_the_closing_call_write_them(self):
        team, state = self.finish(BRIEF3, 8)
        closing = state["tasks"]["closing"]
        self.assertEqual((closing["role"], closing["mode"], len(closing["attempts"])), ("product-manager", "closing", 1))
        self.assertEqual([f["slice"] for f in state["handoff"]["files"]], ["S0", "S1", "S2"])
        self.assertEqual(state["tasks"]["slices"]["history"][-1][3], "T10")
        risks = [r["task"] for r in state["notes"]["risks"]]
        self.assertIn("quality", risks)
        self.assertIn("critic_review", risks)
        self.assertNotIn("slices", risks)
        # The reserve held 2 calls: 6 normal calls, the closing call, then the G3 fix of SEC-02.
        self.assertEqual(team.g3_fixes, ["SEC-02"])
        self.assertEqual(state["budget"]["calls"]["total"], 8)

    def test_open_non_critical_findings_end_as_risks(self):
        team, state = self.finish(BRIEF3, 8)
        self.assertEqual(state["findings"]["PERF-02"]["status"], "accepted_risk")
        notes = [r for r in state["notes"]["risks"] if r["kind"] == "dev_note"]
        self.assertEqual([r["ids"] for r in notes], [["PERF-02"]])
        s0 = (next(iter(state["handoff"]["files"])))["path"]
        self.assertIn("- PERF-02 (MAJOR) | Risk: no slot index on E-01 | Önerilen çözüm: yok, risk kabul edildi",
                      (team.root / s0).read_text(encoding="utf-8"))

    def test_small_mode_cap_reached_reaches_the_handoff(self):
        team, state = self.finish(SMALL_BRIEF3, 8)
        # The slices were current at the cap, so the reserve was free and closing needed no call.
        self.assertNotIn("closing", state["tasks"])
        self.assertEqual(team.g3_fixes, ["DA-01"])
        self.assertEqual(state["budget"]["calls"]["total"], 9)


class ReserveTest(unittest.TestCase):
    """The reserve is never spent by a recheck or a verdict while the closing call has work."""

    def setUp(self):
        self.e = Eng()
        through_gate_a(self.e)
        self.e.state["budget"]["calls"]["total"] = 21

    def test_run_lines_stop_at_the_reserve(self):
        runs = [f[0] for k, f in engine.next_lines(self.e.state) if k == "RUN"]
        self.assertEqual(runs, ["design"])
        self.e.start("design", [DOM])
        self.assertEqual(self.e.state["budget"]["calls"]["total"], 22)
        self.assertEqual(engine.next_lines(self.e.state), [("WAIT", ["design-a1"])])
        res = self.e.start("ux", [UXDOC])
        self.assertEqual(res.code, "BUDGET")
        self.assertIn("reserved for the closing call", res.message)
        # When design lands, closing starts and ux becomes a risk instead of taking a reserved call.
        self.e.record("design")
        self.assertEqual(self.e.state["run"]["closing"], "active")
        self.assertEqual(self.e.status("ux"), "done")
        self.assertIn("ux", [r["task"] for r in self.e.state["notes"]["risks"]])

    def test_a_recheck_never_takes_the_reserve(self):
        e = self.e
        e.state["tasks"]["strategy"]["status"] = "done"
        engine._restart(e.state, "strategy", "recheck", ["INV-01"], "test")
        e.state["budget"]["calls"]["total"] = 22
        self.assertEqual(e.start("strategy").code, "BUDGET")
        engine.advance(e.state, "now")
        self.assertEqual(e.state["run"]["closing"], "active")
        self.assertEqual(e.status("strategy"), "done")
        self.assertEqual(engine.next_lines(e.state), [("RUN", ["closing", "product-manager", "closing", "sonnet"])])
        self.assertEqual(engine.normal_left(e.state), 0)
        e.start("closing", ["docs/05-work/plans/PLAN-0003-slices.md"])
        self.assertEqual(e.state["budget"]["calls"]["total"], 23)


class CriticalAtG3Test(unittest.TestCase):
    """An open CRITICAL finding shows at G3 with its two options; the run does not stop."""

    def test_critical_stays_open_and_the_fix_is_one_time(self):
        root, team, state = dry_run(BRIEF3, 10, team=CriticalTeam)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.assertEqual(next_lines(root), ["ASK G3"])
        self.assertEqual(state["run"]["status"], "waiting_user")
        code, out = run(root, "check")
        self.assertIn("H1 DA-01: unresolved CRITICAL finding", out["result"]["h_items"])
        code, out = run(root, "decide", "G3", "approve", "--op", "g3:1")
        self.assertEqual(out["error"]["code"], "REFUSED")
        code, out = run(root, "decide", "G3", "modify", "--item", "DA-01", "--op", "g3:2")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["fix"], ["fix3.solution-architect"])
        state = state_of(root)
        self.assertGreaterEqual(state["limits"]["calls"]["cap"] - state["budget"]["calls"]["total"], 2)
        self.assertEqual(next_lines(root), ["RUN fix3.solution-architect solution-architect revise opus"])

    def test_second_fix_is_refused(self):
        e = Eng()
        e.state["gates"]["G3"]["status"] = "open"
        e.state["findings"]["DA-01"] = {"severity": "CRITICAL", "owner": "solution-architect", "claim": "c",
                                        "evidence": "e", "cls": None, "raised_by": "plan-critic", "task": "x",
                                        "status": "open", "history": [], "reply": None}
        res = e.decide("G3", "modify", item="DA-01")
        self.assertEqual(res["fix"], ["fix3.solution-architect"])
        e.state["gates"]["G3"]["status"] = "open"
        e.state["gates"]["G3"]["modify_cap"] = 5
        self.assertIn("one-time", e.decide("G3", "modify", item="DA-01").message)


class CriticalTeam(ClosingTeam):
    """Stops at G3 so the test plays the user."""

    def step(self):
        if next_lines(self.root)[0] == "ASK G3":
            return False
        return super().step()


class FinishTest(unittest.TestCase):
    """A stopped run with work left, like the linkedin run, is finished and reaches the handoff."""

    def test_finish_reopens_a_stopped_run_and_reaches_the_handoff(self):
        root = tmp_project(brief=BRIEF3)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        run(root, "init", "BRIEF.md", "--op", "init")
        team = ClosingTeam(root)
        team.run_until("RUN slices")
        code, out = run(root, "decide", "run", "finish", "--op", "finish:0")
        self.assertEqual(out["error"]["code"], "REFUSED")
        # The Lead answered a calls question with stop, as in the linkedin run.
        code, out = run(root, "decide", "calls", "stop", "--op", "gate:calls:1")
        self.assertTrue(out["ok"], out)
        state = state_of(root)
        self.assertEqual(state["run"]["status"], "stopped")
        self.assertEqual(state["gates"]["G3"]["status"], "closed")
        code, out = run(root, "status")
        self.assertTrue(out["result"]["can_finish"])
        calls = state["budget"]["calls"]["total"]
        code, out = run(root, "decide", "run", "finish", "--op", "finish:1")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["cap"], max(24, calls + 2))
        self.assertTrue(out["result"]["closing_call"])
        self.assertEqual(next_lines(root), ["RUN closing product-manager closing sonnet"])
        team.run_to_end()
        state = state_of(root)
        self.assertEqual(state["run"]["status"], "handed_off")
        self.assertEqual([f["slice"] for f in state["handoff"]["files"]], ["S0", "S1", "S2"])
        risks = [r["task"] for r in state["notes"]["risks"]]
        self.assertIn("quality", risks)
        self.assertIn("critic_review", risks)

    def test_finish_needs_sitting_a(self):
        e = Eng()
        e.decide("run", "stop")
        self.assertIn("before sitting A", e.decide("run", "finish").message)


class CascadeTest(unittest.TestCase):
    """
    The linkedin chain: design, performance and strategy reopen each other with contract changes.

    After sitting A each role gets one revise per fix round from another role's change; a
    further contract change becomes a dev-team note, so the chain ends in a bounded number of calls.
    """

    DOCS = {"strategy": (INV, "- INV-01 Every row has tenant_id. PERF-01\n"),
            "design": (DOM, "### D-01 ERD\n- account for F-01 and US-01. INV-01 PERF-01\n"),
            "performance": (PERFDOC, "### PERF-01 Board p95\n- Index on D-01. INV-01\n- deferred: perf-team\n")}

    def chain(self, critical=False):
        e = Eng()
        through_gate_a(e)
        e.do("alloc", {"prefix": "D", "n": 1, "owner": "solution-architect"})
        e.do("alloc", {"prefix": "D", "n": 1, "owner": "ux-designer"})
        e.run_task("design", {DOM: self.DOCS["design"][1], ADR: "API for F-01.\n"})
        e.run_task("ux", {UXDOC: "### D-02 Journey\n- Board flow for US-01 and F-01.\n"})
        e.run_task("security", {THREAT: "### SEC-01 Tenant isolation\n- RLS everywhere.\n"})
        e.run_task("performance", {PERFDOC: self.DOCS["performance"][1]})
        self.assertEqual(e.status("fix1"), "done")
        # The strategy doc now names PERF-01 too, so the three roles depend on each other.
        e.docs[INV] = self.DOCS["strategy"][1]
        e.state["artifacts"][INV].update(registry.scan_doc(e.docs[INV]))
        e.state["artifacts"][INV]["owner_task"] = "strategy"
        engine._restart(e.state, "performance", "revise", ["PERF-01"], "test: a fix changed PERF-01")
        calls, n = [], 0
        while True:
            runs = [f[0] for k, f in engine.next_lines(e.state) if k == "RUN"
                    and f[0] in ("catalog", "strategy", "design", "performance")]
            if not runs or n > 20:
                break
            name = runs[0]
            n += 1
            if name == "catalog":
                # The catalog names INV-01; its recheck-like revise changes nothing.
                path = CATALOG
            else:
                path, text = self.DOCS[name]
                e.docs[path] = text.replace("\n", f" v{n}\n", 1)
            res = e.start(name, [path])
            self.assertNotIsInstance(res, engine.Reject, getattr(res, "message", ""))
            e.record(name, ["ASSUMPTION revised"])
            calls.append(name)
        return e, calls

    def test_chain_ends_in_a_bounded_number_of_calls(self):
        e, calls = self.chain()
        # The first revise and one revise per other role; the next contract answers become notes.
        self.assertEqual(calls, ["performance", "strategy", "catalog", "design", "performance"])
        notes = [r["text"] for r in e.state["notes"]["risks"] if r["text"].startswith("sözleşme etkisi")]
        self.assertTrue(any(n.startswith("sözleşme etkisi: solution-architect") for n in notes), notes)
        self.assertTrue(any(n.startswith("sözleşme etkisi: strategy-architect") for n in notes), notes)
        self.assertEqual(e.status("design"), "done")
        self.assertEqual(e.status("strategy"), "done")

    def test_without_the_rule_only_the_budget_ends_the_chain(self):
        original = engine._cascade_revise

        def always(state, name, ids, reason, critical=False, retired=False):
            return original(state, name, ids, reason, critical=True)

        engine._cascade_revise = always
        try:
            e, calls = self.chain()
        finally:
            engine._cascade_revise = original
        # Only the call budget ends it: 16 revise calls, then closing.
        self.assertEqual(len(calls), 16)
        self.assertEqual(e.state["run"]["closing"], "active")

    def test_a_critical_fix_may_restart_a_role_again(self):
        e = Eng()
        through_gate_a(e)
        for _ in range(2):
            e.state["tasks"]["strategy"]["status"] = "done"
            self.assertTrue(engine._cascade_revise(e.state, "strategy", ["INV-01"], "test", critical=True))
        e.state["tasks"]["strategy"]["status"] = "done"
        self.assertTrue(engine._cascade_revise(e.state, "strategy", ["INV-01"], "test"))
        e.state["tasks"]["strategy"]["status"] = "done"
        self.assertFalse(engine._cascade_revise(e.state, "strategy", ["INV-01"], "test"))


if __name__ == "__main__":
    unittest.main()
