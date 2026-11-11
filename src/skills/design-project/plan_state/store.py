"""
Persistence: lock, journal, atomic snapshot, recovery and replay.

This is the only module that writes files. The journal is append-only and is the source
of truth; run.json is derived from it and rebuilt whenever it is missing, torn, older
than the journal or written by an older schema.
"""
import contextlib
import errno
import fcntl
import json
import os
import time
from pathlib import Path

from . import checks, engine

FAILPOINT_ENV = "PLAN_STATE_FAILPOINT"
FAILPOINT_EXIT = 97
EVENT_KEYS = {"schema_version", "seq", "type", "payload"}


class StoreError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def failpoint(name):
    """Exit hard at a named point when the failpoint variable names it (crash tests)."""
    if os.environ.get(FAILPOINT_ENV) == name:
        os._exit(FAILPOINT_EXIT)


def _fsync_dir(path):
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path, text, point=None):
    """Write to a temp file in the same directory, fsync it, then os.replace it into place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = text.encode("utf-8")
    with open(tmp, "wb") as f:
        if point and os.environ.get(FAILPOINT_ENV) == point:
            f.write(data[: len(data) // 2])
            f.flush()
            os.fsync(f.fileno())
            os._exit(FAILPOINT_EXIT)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def remove(path):
    with contextlib.suppress(FileNotFoundError):
        Path(path).unlink()


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, root, plan_id, lock_timeout=10.0):
        self.root = Path(root)
        self.plan_id = plan_id
        self.plans = self.root / "docs" / "05-work" / "plans"
        self.journal = self.plans / f"{plan_id}.journal.jsonl"
        self.snapshot = self.plans / f"{plan_id}.run.json"
        self.lockfile = self.plans / f"{plan_id}.lock"
        self.index = self.plans / f"{plan_id}.index.md"
        self.cache = self.root / ".cache" / "plan"
        self.lock_timeout = lock_timeout

    def rel(self, path):
        return Path(path).relative_to(self.root).as_posix()

    @contextlib.contextmanager
    def lock(self):
        self.plans.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lockfile), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + self.lock_timeout
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                        raise
                    if time.monotonic() >= deadline:
                        raise StoreError("BUSY", f"{self.lockfile.name} is held by another command")
                    time.sleep(0.05)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # Journal

    def read_events(self, repair=False):
        """
        Return the journal events in order.

        A torn last line (no newline or not JSON) belongs to a writer that never got
        success; with repair it is cut off, without repair it is ignored.
        """
        if not self.journal.exists():
            return []
        raw = self.journal.read_bytes()
        lines = raw.split(b"\n")
        tail = lines.pop()
        events, good_len = [], 0
        for i, line in enumerate(lines):
            try:
                ev = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                if i == len(lines) - 1 and not tail:
                    tail = line
                    break
                raise StoreError("CHECK_FAILED", f"journal line {i + 1} is corrupt")
            if not isinstance(ev, dict) or not EVENT_KEYS <= set(ev):
                raise StoreError("CHECK_FAILED", f"journal line {i + 1} is not an event")
            if ev["schema_version"] > checks.SCHEMA_VERSION:
                raise StoreError("SCHEMA_TOO_NEW", f"journal event schema {ev['schema_version']} is too new")
            events.append(ev)
            good_len += len(line) + 1
        if tail and repair:
            with open(self.journal, "r+b") as f:
                f.truncate(good_len)
                f.flush()
                os.fsync(f.fileno())
        return events

    def append(self, event):
        self.plans.mkdir(parents=True, exist_ok=True)
        with open(self.journal, "ab") as f:
            f.write((dumps(event) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        failpoint("after_journal_append")

    # Snapshot

    def load_snapshot(self):
        """Return the snapshot, or None when it must be rebuilt from the journal."""
        try:
            state = json.loads(self.snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        version = state.get("schema_version") if isinstance(state, dict) else None
        if not isinstance(version, int):
            return None
        if version > checks.SCHEMA_VERSION:
            raise StoreError("SCHEMA_TOO_NEW", f"run.json schema {version} is newer than {checks.SCHEMA_VERSION}")
        if version < checks.SCHEMA_VERSION or not isinstance(state.get("applied_seq"), int):
            # Migration path for an older or damaged snapshot: rebuild it from the journal.
            return None
        return state

    def write_snapshot(self, state):
        atomic_write(self.snapshot, json.dumps(state, ensure_ascii=False, sort_keys=True, indent=1),
                     point="during_snapshot")

    def recover(self):
        """Under the lock: repair the journal, bring run.json up to its last event."""
        events = self.read_events(repair=True)
        state = self.load_snapshot()
        last = events[-1]["seq"] if events else 0
        if state is not None and state["applied_seq"] > last:
            state = None
        if state is None:
            state = engine.replay(events) if events else None
            if state is not None:
                self.write_snapshot(state)
            return state, last
        pending = [e for e in events if e["seq"] > state["applied_seq"]]
        if pending:
            for ev in pending:
                if ev["type"] == "rejected":
                    state = dict(state, applied_seq=ev["seq"])
                else:
                    state, _ = engine.apply(state, ev)
            self.write_snapshot(state)
        return state, last

    def read_state(self):
        """Lock-free read for status and next: the snapshot, caught up in memory if behind."""
        events = self.read_events(repair=False)
        state = self.load_snapshot()
        last = events[-1]["seq"] if events else 0
        if state is None or state["applied_seq"] != last:
            state = engine.replay(events) if events else None
        return state

    def write_index(self, text):
        atomic_write(self.index, text)
