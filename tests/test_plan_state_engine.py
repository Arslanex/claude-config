"""
Engine unit tests: transition tables, seeded random event sequences, H policy and budget.
"""
import copy
import json
import random
import unittest

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import (CATALOG, DOM, INV, STRAT, Eng, checks, engine, registry, store,
                                 through_design, through_gate_a)

TASK_STATUSES = checks.TASK_STATUSES


class TaskTableTest(unittest.TestCase):
    def test_every_table_row_is_allowed(self):
        for rule, (src, dst) in engine.TASK_TABLE.items():
            for status in (TASK_STATUSES if src == "*" else (src,)):
                if status == "cancelled":
                    continue
                with self.subTest(rule=rule, status=status):
                    s = engine.new_state("PLAN-0001")
                    s["tasks"]["strategy"]["status"] = status
                    engine.move_task(s, "strategy", dst, rule)
                    self.assertEqual(s["tasks"]["strategy"]["status"], dst)

    def test_every_other_pair_is_invalid(self):
        allowed = {(src, dst, rule) for rule, (src, dst) in engine.TASK_TABLE.items()}
        for rule, (src, dst) in engine.TASK_TABLE.items():
            for status in TASK_STATUSES:
                for target in TASK_STATUSES:
                    ok = (src in ("*", status) and target == dst and (status != "cancelled" or rule == "T11"))
                    if ok:
                        continue
                    with self.subTest(rule=rule, status=status, target=target):
                        s = engine.new_state("PLAN-0001")
                        s["tasks"]["strategy"]["status"] = status
                        with self.assertRaises(engine.Reject) as cm:
                            engine.move_task(s, "strategy", target, rule)
                        self.assertEqual(cm.exception.code, "INVALID_TRANSITION")
        self.assertTrue(allowed)

    def test_gate_table(self):
        statuses = checks.GATE_STATUSES
        for src in statuses:
            for dst in statuses:
                s = engine.new_state("PLAN-0001")
                s["gates"]["G2"]["status"] = src
                with self.subTest(src=src, dst=dst):
                    if (src, dst) in engine.GATE_TABLE:
                        engine.move_gate(s, "G2", dst)
                        self.assertEqual(s["gates"]["G2"]["status"], dst)
                    else:
                        with self.assertRaises(engine.Reject) as cm:
                            engine.move_gate(s, "G2", dst)
                        self.assertEqual(cm.exception.code, "INVALID_TRANSITION")

    def test_commands_out_of_order_are_rejected_and_journaled(self):
        e = Eng()
        r = e.decide("G2", "approve")
        self.assertEqual(r.code, "INVALID_TRANSITION")
        r = e.start("catalog", [CATALOG])
        self.assertEqual(r.code, "DEPS_PENDING")
        r = e.do("timeout", {"task": "strategy", "stopped": True})
        self.assertEqual(r.code, "INVALID_TRANSITION")
        self.assertEqual([ev["type"] for ev in e.events[1:]], ["rejected"] * 3)
        self.assertEqual(e.state["state_revision"], 1)
        self.assertEqual(e.state["applied_seq"], 4)

    def test_rules_by_command(self):
        e = Eng()
        e.start("strategy", [INV, STRAT])
        self.assertEqual(e.state["tasks"]["strategy"]["history"][-1][3], "T1")
        e.do("timeout", {"task": "strategy", "stopped": True})
        e.start("strategy")
        self.assertEqual(e.state["tasks"]["strategy"]["history"][-1][3], "T3")
        e.do("timeout", {"task": "strategy", "stopped": False})
        self.assertEqual(e.status("strategy"), "blocked")
        self.assertEqual(e.state["tasks"]["strategy"]["history"][-1][3], "T4")
        e.decide("strategy", "extend")
        self.assertEqual(e.status("strategy"), "pending")
        self.assertEqual(e.decide("strategy", "extend").code, "REFUSED")
        e.docs[INV] = "- INV-01 Tenant id everywhere.\n"
        res = e.run_task("strategy", {INV: e.docs[INV], STRAT: "x INV-01\n"})
        self.assertEqual(res["status"], "done")
        self.assertEqual(e.state["tasks"]["strategy"]["history"][-1][3], "T2")
        e.decide("run", "stop")
        self.assertEqual(e.state["run"]["status"], "stopped")
        self.assertEqual(e.status("catalog"), "cancelled")
        self.assertEqual(e.state["tasks"]["catalog"]["history"][-1][3], "T9")

    def test_retry_limit_blocks_then_accept_current(self):
        e = Eng()
        e.start("strategy", [INV, STRAT])
        e.do("timeout", {"task": "strategy", "stopped": True})
        e.start("strategy")
        res = e.do("timeout", {"task": "strategy", "stopped": True})
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(engine.next_lines(e.state), [("ASK", ["strategy"])])
        e.decide("strategy", "accept-current")
        self.assertEqual(e.status("strategy"), "done")
        self.assertEqual(e.state["tasks"]["strategy"]["history"][-1][3], "T5b")


class BudgetAndPolicyTest(unittest.TestCase):
    def test_call_cap_switches_to_closing_instead_of_asking(self):
        e = Eng()
        through_gate_a(e)
        for _ in range(20):
            e.start("design", [DOM])
            e.state["tasks"]["design"]["retries"] = 0
            e.do("timeout", {"task": "design", "stopped": True})
        # Two calls stay for closing: no retry, no extend question, no stop.
        self.assertEqual(e.state["budget"]["calls"]["total"], 22)
        self.assertEqual(e.state["run"]["closing"], "active")
        self.assertEqual(e.status("design"), "done")
        self.assertEqual(e.status("ux"), "done")
        self.assertIn("ux", [r["task"] for r in e.state["notes"]["risks"]])
        self.assertNotIn(("ASK", ["calls"]), engine.next_lines(e.state))
        self.assertEqual(engine.next_lines(e.state), [("RUN", ["closing", "product-manager", "closing", "sonnet"])])
        self.assertNotEqual(e.state["run"]["status"], "stopped")
        self.assertIn("budget: 22 of 24 role calls used", engine.warnings(e.state))

    def test_unknown_tokens_make_cost_unknown(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"}, tokens=None)
        self.assertEqual(e.state["budget"]["tokens"]["sonnet"], "unknown")
        self.assertEqual(e.state["budget"]["cost_estimated"], "unknown")
        self.assertEqual(e.state["budget"]["cost_actual"], "unknown")
        e2 = Eng()
        e2.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"}, tokens=88000)
        self.assertEqual(e2.state["budget"]["tokens"]["sonnet"], 88000)
        self.assertIsInstance(e2.state["budget"]["cost_estimated"], float)

    def _with_finding(self, line):
        e = Eng()
        through_design(e)
        e.start("security", ["docs/01-architecture/security/ARCH-0002-threat.md"])
        e.record("security", [line])
        return e

    def test_h_findings_are_not_waivable(self):
        cases = {"FINDING SEC-01 | CRITICAL | solution-architect | leak | evidence": "H1",
                 "FINDING SEC-01 | CRITICAL | solution-architect | cross tenant read | e | class: H3": "H3",
                 "FINDING SEC-01 | CRITICAL | solution-architect | breaks INV-01 | e | class: H2": "H2"}
        for line, code in cases.items():
            with self.subTest(code=code):
                e = self._with_finding(line)
                self.assertTrue(any(i.startswith(code) for i in checks.h_items(e.state)))
                self.assertEqual(e.decide("SEC-01", "accept-risk").code, "REFUSED")
                self.assertEqual(e.state["findings"]["SEC-01"]["status"], "open")

    def test_only_critical_blocks_whatever_its_class(self):
        for line in ("FINDING SEC-01 | MINOR | solution-architect | cross tenant read | e | class: H3",
                     "FINDING SEC-01 | MAJOR | solution-architect | orphan rows | e | class: H5"):
            with self.subTest(line=line):
                e = self._with_finding(line)
                self.assertFalse([i for i in checks.h_items(e.state) if "SEC-01" in i])
                self.assertEqual(e.decide("SEC-01", "accept-risk")["status"], "accepted_risk")

    def test_major_without_class_can_be_accepted_as_risk(self):
        e = self._with_finding("FINDING SEC-01 | MAJOR | solution-architect | weak audit | evidence")
        self.assertFalse([i for i in checks.h_items(e.state) if i.startswith("H1")])
        res = e.decide("SEC-01", "accept-risk")
        self.assertEqual(res["status"], "accepted_risk")

    def test_g3_approve_refused_while_not_eligible(self):
        e = Eng()
        through_gate_a(e)
        e.state["gates"]["G3"]["status"] = "open"
        res = e.decide("G3", "approve", checks=["H1 SEC-01: unresolved CRITICAL security finding"])
        self.assertEqual(res.code, "REFUSED")
        self.assertEqual(e.state["gates"]["G3"]["status"], "open")

    def test_missing_traceability_is_h6_and_lint_is_h4(self):
        e = Eng()
        through_gate_a(e)
        items = checks.h_items(e.state, ["docs/x.md: missing required field 'id'"])
        self.assertTrue(any(i.startswith("H6 F-01") for i in items))
        self.assertTrue(any(i.startswith("H4 lint") for i in items))

    def test_a_proposed_solution_does_not_block_and_nobody_verifies_it(self):
        e = Eng()
        e.state["findings"]["SEC-01"] = {"severity": "CRITICAL", "owner": "solution-architect", "claim": "leak",
                                         "evidence": "e", "cls": None, "raised_by": "security-architect",
                                         "task": "security", "status": "open", "history": []}
        self.assertTrue(any(i.startswith("H1 SEC-01") for i in checks.h_items(e.state)))
        e.state["findings"]["SEC-01"]["status"] = "disputed"
        self.assertTrue(any(i.startswith("H1 SEC-01") for i in checks.h_items(e.state)))
        e.state["findings"]["SEC-01"]["status"] = "fixed"
        self.assertFalse(any(i.startswith("H1") for i in checks.h_items(e.state)))
        for name, t in e.state["tasks"].items():
            if name != "fix2":
                t["status"] = "done"
        engine.advance(e.state, "now")
        self.assertEqual(e.status("fix2"), "done")
        self.assertFalse([n for n in e.state["tasks"] if "verdict" in n])

    def test_gate_modify_round_limit(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"})
        e.run_task("catalog", {CATALOG: "### F-01 x\n"})
        res = e.decide("G1", "modify")
        self.assertEqual(res["status"], "modify_requested")
        self.assertEqual(e.status("strategy"), "pending")
        self.assertEqual(e.state["tasks"]["strategy"]["mode"], "revise")
        e.run_task("strategy", {})
        self.assertEqual(e.state["gates"]["G1"]["status"], "open")
        self.assertEqual(e.decide("G1", "modify").code, "REFUSED")
        e.decide("G1", "extend")
        self.assertEqual(e.decide("G1", "modify")["status"], "modify_requested")

    def test_freeze_gives_permanent_f_ids(self):
        e = Eng()
        e.run_task("strategy", {INV: "- INV-01 a\n", STRAT: "b\n"})
        e.run_task("catalog", {CATALOG: "| ID | T | karar |\n|---|---|---|\n| M-01 | Audit | |\n"
                                         "| R-01 | Export | |\n| G-01 | Gap | |\n"})
        e.decide("G1", "approve")
        res = e.decide("G2", "approve", rows=[["M-01", "accept"], ["R-01", "accept"], ["G-01", "reject"]])
        self.assertEqual(res["new_features"], ["F-02", "F-03"])
        self.assertEqual(e.state["ids"]["F-02"]["origin"], "M-01")
        self.assertEqual(e.state["ids"]["G-01"]["decision"], "rejected")
        self.assertEqual(e.decide("G2", "approve", rows=[["M-01", ""]]).code, "INVALID_TRANSITION")


class RandomSequenceTest(unittest.TestCase):
    """Seeded random event sequences: replay equals the snapshot, no ID reuse, budget kept."""

    PATHS = {"strategy-architect": [INV, STRAT], "product-manager": [CATALOG],
             "solution-architect": [DOM], "ux-designer": ["docs/05-work/plans/PLAN-0002-ux.md"],
             "security-architect": ["docs/01-architecture/security/ARCH-0002-threat.md"],
             "performance-architect": ["docs/01-architecture/performance/ARCH-0003-perf.md"],
             "quality-engineer": ["docs/05-work/plans/quality/PLAN-0004-q.md"], "plan-critic": []}

    def random_doc(self, rng, role, state):
        own = [p for p in registry.ROLES[role]["prefixes"] if p != "S"]
        lines = []
        for _ in range(rng.randint(0, 3)):
            prefix = rng.choice(own) if own else "F"
            if prefix == "D":
                reserved = [i for i, r in state["ids"].items() if r["prefix"] == "D" and r["owner"] == role]
                if not reserved:
                    continue
                id_ = rng.choice(reserved)
            else:
                id_ = registry.format_id(prefix, rng.randint(1, 4))
            refs = " ".join(rng.sample(["F-01", "US-01", "INV-01", "D-01", "BR-01"], 2))
            lines.append(f"- {id_} text {rng.random():.3f} {refs}")
        return "\n".join(lines) + ("\n" if lines else "")

    def random_lines(self, rng, role, state):
        lines = [rng.choice(["ASSUMPTION a", "OPEN Q-1 | q | blocking: no | default: d"])]
        prefix = registry.FINDING_PREFIX.get(role)
        if prefix and rng.random() < 0.5:
            sev = rng.choice(["CRITICAL", "MAJOR", "MINOR"])
            lines.append(f"FINDING {prefix}-{rng.randint(1, 3):02d} | {sev} | "
                         f"{rng.choice(['product-manager', 'solution-architect'])} | claim | ev")
        for fid, f in state["findings"].items():
            if f["owner"] == role and rng.random() < 0.7:
                lines.append(rng.choice([f"FIX {fid} | x | impact: local | done", f"DISPUTE {fid} | no"]))
        return lines

    def step(self, rng, e):
        state = e.state
        choice = rng.random()
        runnable = engine.runnable(state)
        running = [n for n, t in state["tasks"].items() if t["status"] == "running"
                   and t["attempts"] and t["attempts"][-1]["status"] == "running"]
        if choice < 0.35 and runnable:
            name = rng.choice(runnable)
            t = state["tasks"][name]
            if t["role"] in ("solution-architect", "ux-designer") and rng.random() < 0.5:
                e.do("alloc", {"prefix": "D", "n": rng.randint(1, 2), "owner": t["role"]})
            e.start(name, self.PATHS[t["role"]] if rng.random() < 0.9 else [CATALOG, DOM])
        elif choice < 0.75 and running:
            name = rng.choice(running)
            t = state["tasks"][name]
            for p in t["scope"]:
                if rng.random() < 0.8:
                    e.docs[p] = self.random_doc(rng, t["role"], state)
            if rng.random() < 0.05:
                e.docs["docs/other.md"] = str(rng.random())
            attempt = t["attempts"][-1]["id"] if rng.random() < 0.9 else f"{name}-a99"
            e.record(name, self.random_lines(rng, t["role"], state), attempt=attempt,
                     tokens=rng.choice([None, 500, 1000]))
        elif choice < 0.8 and running:
            e.do("timeout", {"task": rng.choice(running), "stopped": rng.random() < 0.8})
        else:
            lines = engine.next_lines(state)
            asks = [f for k, f in lines if k == "ASK"]
            if asks and rng.random() < 0.9:
                target = rng.choice(asks)[0]
                action = rng.choice(["approve", "approve", "approve", "modify", "extend", "accept-current"])
                e.decide(target, action, defaults=True, checks=checks.h_items(state))
            else:
                target = rng.choice(list(state["findings"]) + ["G1", "G2", "G3", "calls", "strategy"])
                e.decide(target, rng.choice(["accept-risk", "extend", "approve", "modify"]), item="F-01")

    def test_seeded_sequences(self):
        for seed in range(40):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                e = Eng()
                retired_seen, allocated = set(), set()
                for _ in range(rng.randint(40, 160)):
                    before = copy.deepcopy(e.state["ids"])
                    if rng.random() < 0.3:
                        # The CLI reloads a key-sorted snapshot; results must not depend on dict order.
                        e.state = json.loads(store.dumps(e.state))
                    self.step(rng, e)
                    if e.state["run"]["status"] == "stopped":
                        break
                    ids = e.state["ids"]
                    for i, rec in before.items():
                        if rec["status"] == "retired":
                            self.assertEqual(ids[i]["status"], "retired", f"{i} came back")
                    for i, rec in ids.items():
                        if i not in before and rec["status"] == "reserved":
                            self.assertNotIn(i, allocated)
                            allocated.add(i)
                        if rec["status"] == "retired":
                            retired_seen.add(i)
                    calls = e.state["budget"]["calls"]["total"]
                    self.assertLessEqual(calls, e.state["limits"]["calls"]["cap"])
                    self.assertLessEqual(calls, e.state["limits"]["calls"]["max"])
                    self.assertTrue(all(t["status"] in TASK_STATUSES for t in e.state["tasks"].values()))
                replayed = engine.replay(e.events)
                self.assertEqual(store.dumps(replayed), store.dumps(e.state))


if __name__ == "__main__":
    unittest.main()
