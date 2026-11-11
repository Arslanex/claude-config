"""
Store tests: crash recovery with failpoints, torn journal lines, idempotency, schema
compatibility, the lock and replay --verify.
"""
import json
import shutil
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent))

from plan_state_fixtures import CATALOG, INV, STRAT, cli, engine, run, run_crash, state_of, store, tmp_project


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tmp_project()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        code, out = run(self.root, "init", "BRIEF.md", "--op", "init")
        self.assertTrue(out["ok"], out)
        self.st = store.Store(self.root, "PLAN-0001")

    def tearDown(self):
        if self.st.journal.exists():
            code, out = run(self.root, "replay", "--verify")
            self.assertTrue(out["ok"], out)

    def start_strategy(self, op="s1"):
        return run(self.root, "start", "strategy", "--write", INV, "--write", STRAT, "--op", op)


class CrashTest(StoreTestCase):
    def test_crash_after_journal_append_then_same_op(self):
        code = run_crash(self.root, "after_journal_append", "start", "strategy", "--write", INV, "--write", STRAT,
                         "--op", "s1")
        self.assertEqual(code, store.FAILPOINT_EXIT)
        snap = json.loads(self.st.snapshot.read_text())
        self.assertEqual(snap["tasks"]["strategy"]["status"], "pending")
        self.assertEqual(len(self.st.read_events()), 2)
        self.assertEqual(state_of(self.root)["tasks"]["strategy"]["status"], "running")
        code, out = self.start_strategy("s1")
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["result"]["attempt"], "strategy-a1")
        self.assertEqual(len(self.st.read_events()), 2)
        self.assertEqual(json.loads(self.st.snapshot.read_text())["tasks"]["strategy"]["status"], "running")

    def test_crash_during_snapshot_write(self):
        code = run_crash(self.root, "during_snapshot", "start", "strategy", "--write", INV, "--write", STRAT,
                         "--op", "s1")
        self.assertEqual(code, store.FAILPOINT_EXIT)
        tmp = self.st.snapshot.with_name(self.st.snapshot.name + ".tmp")
        self.assertTrue(tmp.exists())
        self.assertEqual(json.loads(self.st.snapshot.read_text())["applied_seq"], 1)
        code, out = run(self.root, "alloc", "D", "1", "--owner", "solution-architect", "--op", "a1")
        self.assertTrue(out["ok"], out)
        snap = json.loads(self.st.snapshot.read_text())
        self.assertEqual(snap["applied_seq"], 3)
        self.assertEqual(snap["tasks"]["strategy"]["status"], "running")

    def test_torn_last_line_is_dropped(self):
        with open(self.st.journal, "ab") as f:
            f.write(b'{"schema_version": 1, "seq": 2, "op_id": "half"')
        self.assertEqual(len(self.st.read_events()), 1)
        code, out = self.start_strategy("s1")
        self.assertTrue(out["ok"], out)
        lines = self.st.journal.read_bytes().split(b"\n")
        self.assertEqual(lines[-1], b"")
        self.assertEqual([json.loads(l)["seq"] for l in lines[:-1]], [1, 2])

    def test_corrupt_middle_line_stops(self):
        self.start_strategy("s1")
        data = self.st.journal.read_bytes().split(b"\n")
        data[0] = b"not json"
        self.st.journal.write_bytes(b"\n".join(data))
        code, out = run(self.root, "alloc", "D", "1", "--owner", "solution-architect")
        self.assertEqual(out["error"]["code"], "CHECK_FAILED")
        self.st.journal.unlink()

    def test_deleted_snapshot_is_rebuilt(self):
        self.start_strategy("s1")
        before = json.loads(self.st.snapshot.read_text())
        self.st.snapshot.unlink()
        code, out = run(self.root, "status")
        self.assertEqual(out["result"]["tasks"]["strategy"], "running")
        run(self.root, "alloc", "D", "1", "--owner", "solution-architect", "--op", "a1")
        after = json.loads(self.st.snapshot.read_text())
        self.assertEqual(after["tasks"]["strategy"], before["tasks"]["strategy"])


class IdempotencyTest(StoreTestCase):
    def test_same_op_same_payload_returns_first_result(self):
        code, first = self.start_strategy("s1")
        code, again = self.start_strategy("s1")
        self.assertEqual(first, again)
        self.assertEqual(len(self.st.read_events()), 2)

    def test_same_op_other_payload_is_op_conflict(self):
        self.start_strategy("s1")
        code, out = run(self.root, "start", "strategy", "--write", INV, "--op", "s1")
        self.assertEqual(out["error"]["code"], "OP_CONFLICT")
        self.assertEqual(code, 1)

    def test_rejected_op_is_journaled_but_not_remembered(self):
        code, out = run(self.root, "start", "catalog", "--write", CATALOG, "--op", "c1")
        self.assertEqual(out["error"]["code"], "DEPS_PENDING")
        events = self.st.read_events()
        self.assertEqual(events[-1]["type"], "rejected")
        self.assertEqual(state_of(self.root)["state_revision"], 1)
        self.assertNotIn("c1", state_of(self.root)["ops"])


class SchemaTest(StoreTestCase):
    def test_snapshot_too_new(self):
        snap = json.loads(self.st.snapshot.read_text())
        snap["schema_version"] = 99
        self.st.snapshot.write_text(json.dumps(snap))
        code, out = run(self.root, "alloc", "D", "1", "--owner", "solution-architect")
        self.assertEqual(out["error"]["code"], "SCHEMA_TOO_NEW")
        snap["schema_version"] = 1
        self.st.snapshot.write_text(json.dumps(snap))

    def test_event_too_new(self):
        line = json.dumps({"schema_version": 2, "seq": 2, "op_id": "x", "at": "t", "actor": "a",
                           "type": "alloc", "payload": {}})
        with open(self.st.journal, "a") as f:
            f.write(line + "\n")
        code, out = run(self.root, "status")
        self.assertEqual(out["error"]["code"], "SCHEMA_TOO_NEW")
        self.st.journal.write_text(self.st.journal.read_text().splitlines()[0] + "\n")

    def test_older_snapshot_is_migrated_by_replay(self):
        self.start_strategy("s1")
        snap = json.loads(self.st.snapshot.read_text())
        old = {"schema_version": 0, "plan_id": "PLAN-0001", "applied_seq": 2, "tasks": {}}
        self.st.snapshot.write_text(json.dumps(old))
        run(self.root, "alloc", "D", "1", "--owner", "solution-architect", "--op", "a1")
        new = json.loads(self.st.snapshot.read_text())
        self.assertEqual(new["schema_version"], 1)
        self.assertEqual(new["tasks"]["strategy"], snap["tasks"]["strategy"])


class LockTest(StoreTestCase):
    def test_busy_when_the_lock_is_held(self):
        with self.st.lock():
            code, out = run(self.root, "alloc", "D", "1", "--owner", "solution-architect", "--lock-timeout", "0.2")
        self.assertEqual(out["error"]["code"], "BUSY")
        code, out = run(self.root, "alloc", "D", "1", "--owner", "solution-architect")
        self.assertTrue(out["ok"])

    def test_readers_do_not_lock(self):
        with self.st.lock():
            code, out = run(self.root, "status")
        self.assertTrue(out["ok"])


class ReplayTest(StoreTestCase):
    def test_verify_detects_a_tampered_snapshot(self):
        self.start_strategy("s1")
        snap = json.loads(self.st.snapshot.read_text())
        snap["contacts"]["count"] = 7
        self.st.snapshot.write_text(json.dumps(snap))
        code, out = run(self.root, "replay", "--verify")
        self.assertFalse(out["ok"])
        self.assertIn("contacts", out["result"]["differs"])
        self.st.write_snapshot(engine.replay(self.st.read_events()))


if __name__ == "__main__":
    unittest.main()
