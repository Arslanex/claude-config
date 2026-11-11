"""
CLI integration tests: write scopes, late results, gates from documents, next read lists,
handoff recovery and the end-to-end resume from step 0 to handoff.
"""
import json
import shutil
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import (BRIEF, FakeTeam, cli, docs_new, engine, next_lines, run, run_crash, state_of, store,
                                 tmp_project)


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tmp_project()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        code, out = run(self.root, "init", "BRIEF.md", "--op", "init")
        self.assertTrue(out["ok"], out)

    def tearDown(self):
        code, out = run(self.root, "replay", "--verify")
        self.assertTrue(out["ok"], out)

    def out_file(self, name, text):
        p = self.root / ".cache" / "plan" / "attempts" / f"{name}.out"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


class PlanNumberTest(CliTestCase):
    def test_init_and_docs_new_plan_do_not_share_a_number(self):
        run_id = state_of(self.root)["plan_id"]
        doc = docs_new(self.root, "plan", "Catalog")
        self.assertFalse(Path(doc).name.startswith(run_id + "-"), (run_id, doc))


class PlanSizeTest(unittest.TestCase):
    def test_init_stores_the_brief_plan_size_in_run_json(self):
        root = tmp_project(brief=BRIEF.replace("- Veri hacmi: 2 GB\n", "- Veri hacmi: 2 GB\n- Plan boyutu: küçük\n"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        code, out = run(root, "init", "BRIEF.md", "--op", "init")
        self.assertEqual(out["result"]["size"], "küçük")
        run_json = next((root / "docs" / "05-work" / "plans").glob("*.run.json"))
        self.assertEqual(json.loads(run_json.read_text(encoding="utf-8"))["run"]["size"], "küçük")
        code, out = run(root, "status")
        self.assertEqual(out["result"]["size"], "küçük")


class ScopeTest(CliTestCase):
    def to_design(self):
        team = FakeTeam(self.root, findings=False)
        team.run_until("RUN design")
        return team

    def test_overlapping_reservation_is_scope_conflict(self):
        self.to_design()
        plan = docs_new(self.root, "plan", "UX")
        code, out = run(self.root, "start", "ux", "--write", plan)
        self.assertTrue(out["ok"], out)
        code, out = run(self.root, "start", "design", "--write", plan)
        self.assertEqual(out["error"]["code"], "SCOPE_VIOLATION")
        code, out = run(self.root, "start", "catalog", "--write", plan)
        self.assertEqual(out["error"]["code"], "INVALID_TRANSITION")
        state = state_of(self.root)
        state_task = state["tasks"]["ux"]
        self.assertEqual(state_task["scope"], [plan])

    def test_same_path_for_two_roles_conflicts(self):
        team = FakeTeam(self.root, findings=False)
        team.run_until("RUN performance")
        for task, kind, line in (
                ("security", "threat", "FINDING SEC-02 | MAJOR | product-manager | rule missing | BR-01"),
                ("performance", "perf", "FINDING PERF-02 | MINOR | ux-designer | no paging | D-02")):
            path = docs_new(self.root, kind, task)
            code, s = run(self.root, "start", task, "--write", path)
            out = self.out_file(task, f"ATTEMPT {s['result']['attempt']}\n{line}\n")
            code, r = run(self.root, "record", task, "--attempt", s["result"]["attempt"], "--out", out)
            self.assertTrue(r["ok"], r)
        lines = next_lines(self.root)
        # The product-manager fixes its findings in the slices call, so step 5 runs it once.
        self.assertEqual(["RUN fix1.ux-designer ux-designer revise sonnet"], [l for l in lines if l.startswith("RUN")])
        self.assertEqual(state_of(self.root)["tasks"]["slices"]["findings"], ["SEC-02"])
        ux_doc = team.paths["ux"][0]
        code, out = run(self.root, "start", "fix1.ux-designer", "--write", ux_doc)
        self.assertTrue(out["ok"], out)
        state = state_of(self.root)
        self.assertEqual(engine.registry.scope_conflicts([ux_doc], engine._reserved(state)),
                         {ux_doc: "fix1.ux-designer"})

    def test_parallel_files_are_not_violations_and_outside_change_blocks(self):
        team = self.to_design()
        dom, adr = docs_new(self.root, "domain", "Deals"), docs_new(self.root, "adr", "System")
        run(self.root, "alloc", "D", "1", "--owner", "solution-architect")
        code, d = run(self.root, "start", "design", "--write", dom, "--write", adr)
        ux = docs_new(self.root, "plan", "UX")
        code, u = run(self.root, "start", "ux", "--write", ux)
        (self.root / ux).write_text((self.root / ux).read_text() + "\nscreens\n")
        (self.root / dom).write_text((self.root / dom).read_text() + "\n### D-01 ERD\n- deal for F-01\n")
        out = self.out_file("ux", f"ATTEMPT {u['result']['attempt']}\nWROTE {ux}\n")
        code, r = run(self.root, "record", "ux", "--attempt", u["result"]["attempt"], "--out", out)
        self.assertTrue(r["ok"], r)
        out = self.out_file("d", f"ATTEMPT {d['result']['attempt']}\nWROTE {dom}\n")
        code, r = run(self.root, "record", "design", "--attempt", d["result"]["attempt"], "--out", out)
        self.assertTrue(r["ok"], r)
        # Now a role writes outside its scope.
        sec = docs_new(self.root, "threat", "Threat")
        perf = docs_new(self.root, "perf", "Perf")
        code, s = run(self.root, "start", "security", "--write", sec)
        (self.root / dom).write_text((self.root / dom).read_text() + "- sneaky edit\n")
        out = self.out_file("s", f"ATTEMPT {s['result']['attempt']}\nWROTE {sec}\n")
        code, r = run(self.root, "record", "security", "--attempt", s["result"]["attempt"], "--out", out)
        self.assertEqual(r["error"]["code"], "SCOPE_VIOLATION")
        self.assertEqual(r["result"]["paths"], [dom])
        self.assertEqual(state_of(self.root)["tasks"]["security"]["status"], "blocked")
        self.assertIn("ASK security", next_lines(self.root))
        self.assertTrue(perf)


class AttemptTest(CliTestCase):
    def test_late_and_bad_attempts(self):
        team = FakeTeam(self.root)
        paths = team.files_for("strategy")
        argv = [x for p in paths for x in ("--write", p)]
        code, a1 = run(self.root, "start", "strategy", *argv)
        attempt1 = a1["result"]["attempt"]
        self.assertEqual(next_lines(self.root), [f"WAIT {attempt1}"])
        code, out = run(self.root, "timeout", "strategy", "--stopped")
        self.assertTrue(out["ok"], out)
        self.assertTrue(next_lines(self.root)[0].startswith("RUN strategy"))
        code, a2 = run(self.root, "start", "strategy")
        attempt2 = a2["result"]["attempt"]
        self.assertEqual(attempt2, "strategy-a2")
        late = self.out_file("late", f"ATTEMPT {attempt1}\nASSUMPTION old\n")
        code, out = run(self.root, "record", "strategy", "--attempt", attempt1, "--out", late)
        self.assertEqual(out["error"]["code"], "LATE_RESULT")
        bare = self.out_file("bare", "ASSUMPTION no attempt line\n")
        code, out = run(self.root, "record", "strategy", "--attempt", attempt2, "--out", bare)
        self.assertEqual(out["error"]["code"], "BAD_ATTEMPT")
        code, out = run(self.root, "record", "strategy", "--attempt", attempt2, "--out", late)
        self.assertEqual(out["error"]["code"], "BAD_ATTEMPT")
        good = self.out_file("good", f"ATTEMPT {attempt2}\nASSUMPTION fine\n")
        code, out = run(self.root, "record", "strategy", "--attempt", attempt2, "--out", good)
        self.assertTrue(out["ok"], out)
        types = [json.loads(l)["type"] for l in store.Store(self.root, "PLAN-0001").journal.read_text().splitlines()]
        self.assertEqual(types.count("rejected"), 3)

    def test_format_error_then_retry_limit(self):
        team = FakeTeam(self.root)
        argv = [x for p in team.files_for("strategy") for x in ("--write", p)]
        code, a1 = run(self.root, "start", "strategy", *argv)
        junk = self.out_file("junk", f"ATTEMPT {a1['result']['attempt']}\nhello\n")
        code, out = run(self.root, "record", "strategy", "--attempt", a1["result"]["attempt"], "--out", junk)
        self.assertEqual(out["error"]["code"], "CHECK_FAILED")
        self.assertTrue(out["result"]["retry"])
        code, a2 = run(self.root, "retry", "strategy")
        junk = self.out_file("junk2", f"ATTEMPT {a2['result']['attempt']}\nhello\n")
        code, out = run(self.root, "record", "strategy", "--attempt", a2["result"]["attempt"], "--out", junk)
        self.assertFalse(out["result"]["retry"])
        self.assertEqual(state_of(self.root)["tasks"]["strategy"]["status"], "blocked")
        # No retry is left, so next asks the blocked question instead of a RUN line.
        self.assertEqual(next_lines(self.root)[0], "ASK strategy")
        self.assertEqual(state_of(self.root)["budget"]["retries"], 1)


class GateTest(CliTestCase):
    def test_g2_from_doc_needs_every_decision(self):
        team = FakeTeam(self.root)
        team.run_until("ASK")
        catalog = team.paths["catalog"][0]
        text = (self.root / catalog).read_text()
        (self.root / catalog).write_text(text.replace("| R-01 | Export | defer |", "| R-01 | Export | |"))
        code, out = run(self.root, "gate", "G2", "--from-doc", catalog)
        self.assertEqual(out["error"]["code"], "REFUSED")
        code, out = run(self.root, "gate", "G1", "--defaults")
        self.assertTrue(out["ok"], out)
        code, out = run(self.root, "gate", "G2", "--from-doc", catalog)
        self.assertEqual(out["error"]["code"], "CHECK_FAILED")
        (self.root / catalog).write_text(text.replace("| R-01 | Export | defer |", "| R-01 | Export | accept |"))
        code, out = run(self.root, "gate", "G2", "--from-doc", catalog)
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["new_features"], ["F-02"])
        state = state_of(self.root)
        self.assertEqual(state["contacts"]["count"], 1)


class NextTest(CliTestCase):
    def test_read_lists_and_index(self):
        team = FakeTeam(self.root)
        team.run_until("RUN design")
        code, text = run(self.root, "next")
        lines = text.splitlines()
        self.assertEqual(lines[0], "RUN design solution-architect data,system opus")
        reads = [l for l in lines if l.startswith("  READ")]
        self.assertTrue(any(l.endswith(" F-01") and ":" in l for l in reads), reads)
        self.assertTrue(any(l.endswith(" INV-01") for l in reads), reads)
        self.assertIn("  READ docs/05-work/plans/PLAN-0001.index.md", lines)
        index = (self.root / "docs/05-work/plans/PLAN-0001.index.md").read_text()
        self.assertIn("| US-01 | docs/05-work/plans/PLAN-0002-catalog.md |", index)
        self.assertIn("| product-manager | active | F-01 |", index)
        team.run_until("RUN fix1")
        code, text = run(self.root, "next")
        self.assertIn("  FINDINGS SEC-02", text.splitlines())
        code, out = run(self.root, "status")
        self.assertEqual(out["result"]["open_findings"], ["SEC-02"])


class HandoffTest(CliTestCase):
    def to_handoff(self):
        team = FakeTeam(self.root, two_slices=True)
        team.run_until("RUN handoff")
        return team

    def task_files(self):
        return sorted(p.name for p in (self.root / "docs" / "05-work" / "tasks").glob("T-*.md"))

    def test_crash_mid_publish_resumes_without_duplicates(self):
        self.to_handoff()
        code, out = run(self.root, "handoff", "prepare", "--op", "p1")
        self.assertTrue(out["ok"], out)
        self.assertEqual([f["t"] for f in out["result"]["files"]], ["T-0001", "T-0002"])
        code = run_crash(self.root, "mid_publish", "handoff", "publish", "--op", "u1")
        self.assertEqual(code, store.FAILPOINT_EXIT)
        self.assertEqual(len(self.task_files()), 1)
        code, out = run(self.root, "handoff", "prepare", "--op", "p2")
        self.assertEqual(out["result"]["state"], "prepared")
        code, out = run(self.root, "handoff", "publish", "--op", "u2")
        self.assertTrue(out["ok"], out)
        self.assertEqual(self.task_files(), ["T-0001-s0-walking-skeleton-and-board.md", "T-0002-s1-totals.md"])
        code, out = run(self.root, "handoff", "publish", "--op", "u3")
        self.assertEqual(out["result"]["state"], "committed")
        self.assertEqual(len(self.task_files()), 2)
        state = state_of(self.root)
        self.assertEqual(state["run"]["status"], "handed_off")
        manifest = json.loads((self.root / ".cache/plan/handoff" / state["handoff"]["handoff_id"] /
                               "manifest.json").read_text())
        self.assertEqual(manifest["state"], "committed")
        self.assertEqual(next_lines(self.root), ["DONE handed_off"])
        task = (self.root / "docs/05-work/tasks" / self.task_files()[1]).read_text()
        self.assertIn(f"handoff: {state['handoff']['handoff_id']}", task)
        self.assertIn("slice: S1", task)
        self.assertIn("When the board opens, the system shall show totals. (US-02)", task)
        self.assertIn("- Contracts (entities and endpoints): E-01.", task)
        first = (self.root / "docs/05-work/tasks" / self.task_files()[0]).read_text()
        self.assertIn("- Contracts (entities and endpoints): API-01, E-01.", first)

    def test_taken_number_is_renumbered(self):
        self.to_handoff()
        run(self.root, "handoff", "prepare", "--op", "p1")
        other = docs_new(self.root, "task", "Someone else")
        self.assertTrue(other.endswith("T-0001-someone-else.md"))
        squat = self.root / "docs/05-work/tasks/T-0001-s0-walking-skeleton-and-board.md"
        squat.write_text("other content\n")
        code, out = run(self.root, "handoff", "publish", "--op", "u1")
        self.assertEqual(out["error"]["code"], "CHECK_FAILED")
        squat.unlink()
        code, out = run(self.root, "handoff", "prepare", "--op", "p2")
        self.assertEqual([f["t"] for f in out["result"]["files"]], ["T-0002", "T-0003"])
        code, out = run(self.root, "handoff", "publish", "--op", "u2")
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(self.task_files()), 3)

    def test_publish_needs_prepare_and_g3(self):
        team = FakeTeam(self.root)
        team.run_until("RUN design")
        code, out = run(self.root, "handoff", "prepare")
        self.assertEqual(out["error"]["code"], "REFUSED")
        code, out = run(self.root, "handoff", "publish")
        self.assertEqual(out["error"]["code"], "REFUSED")


class EndToEndTest(CliTestCase):
    def check_finished(self):
        state = state_of(self.root)
        self.assertEqual(state["run"]["status"], "handed_off")
        self.assertEqual(state["handoff"]["state"], "committed")
        self.assertEqual(state["gates"]["G3"]["status"], "approved")
        self.assertTrue(all(t["status"] == "done" for t in state["tasks"].values()))
        # The owners proposed solutions; nobody verifies them in planning (15.11).
        self.assertEqual(state["findings"]["SEC-02"]["status"], "fixed")
        self.assertEqual(state["findings"]["DA-01"]["status"], "fixed")
        self.assertEqual(state["budget"]["calls"]["by_role"]["security-architect"], 1)
        self.assertFalse([n for n in state["tasks"] if "verdict" in n])
        self.assertLessEqual(state["budget"]["calls"]["total"], 12)
        self.assertEqual(state["contacts"]["count"], 2)
        self.assertLessEqual({group for group, _ in state["contacts"]["seen"]}, {"Q1", "A", "G3"})
        tasks = sorted((self.root / "docs/05-work/tasks").glob("T-*.md"))
        self.assertEqual(len(tasks), 1)
        tool = cli.load_docs_tool(self.root)
        errors, _ = tool.lint(self.root / "docs")
        self.assertEqual(errors, [])
        return state

    def test_flow_from_step_0_to_handoff(self):
        FakeTeam(self.root).run_to_end()
        state = self.check_finished()
        steps = {n: t["step"] for n, t in state["tasks"].items()}
        self.assertEqual([steps[n] for n in ("strategy", "catalog", "design", "ux", "security", "slices",
                                             "quality", "fix2")], [1, 2, 3, 3, 4, 5, 6, 7])
        self.assertEqual(state["tasks"]["critic_review"]["model"], "opus")
        self.assertTrue(state["critic_model_differs"])

    def test_killed_at_every_step_resumes(self):
        team = FakeTeam(self.root, crash=True)
        team.run_to_end()
        state = self.check_finished()
        clean = tmp_project()
        self.addCleanup(shutil.rmtree, clean, ignore_errors=True)
        run(clean, "init", "BRIEF.md", "--op", "init")
        FakeTeam(clean).run_to_end()
        other = state_of(clean)
        for key in ("tasks", "findings", "budget", "gates"):
            a = {k: v for k, v in state[key].items()}
            b = {k: v for k, v in other[key].items()}
            self.assertEqual(store.dumps(a).count("done"), store.dumps(b).count("done"), key)
        self.assertEqual(state["state_revision"], other["state_revision"])
        self.assertEqual(sorted(state["ids"]), sorted(other["ids"]))

    def test_stop_at_a_gate_cancels_open_work(self):
        team = FakeTeam(self.root)
        team.run_until("ASK")
        code, out = run(self.root, "decide", "G1", "stop")
        self.assertTrue(out["ok"], out)
        self.assertEqual(next_lines(self.root), ["DONE stopped"])
        self.assertEqual(state_of(self.root)["tasks"]["design"]["status"], "cancelled")
        self.assertTrue((self.root / state_of(self.root)["run"]["brief"]).exists())


if __name__ == "__main__":
    unittest.main()
