"""
Shared fixtures for the plan_state tests: a temp project, an in-process CLI runner,
a subprocess runner for crash tests and fake role outputs.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "src" / "skills" / "design-project"
PLAN_STATE_PY = SKILL / "plan_state.py"
DOCS_PY = REPO / "src" / "templates" / "project" / "tools" / "docs.py"
sys.path.insert(0, str(SKILL))

from plan_state import checks, cli, engine, registry, store  # noqa: E402,F401

BRIEF = """---
id: BRIEF-0001
title: "Deal board"
status: draft
area: general
updated: 2026-11-10
---

# Deal board

## 1. Ürün özeti
- Problem: sales teams lose track of open deals.
- Hedef kullanıcılar: sales reps.
- İlk başarı ölçüsü: every open deal is on the board.

## 2. Kapsam dışı
- Invoicing.

## 3. Stack
- Zorunlu: Python, PostgreSQL.
- Profil: fastapi-saas

## 4. Dağıtım ve ölçek
- Dağıtım: saas
- Kiracı sayısı: 50
- Kullanıcı sayısı: 500
- Eşzamanlı kullanıcı: 40
- Veri hacmi: 2 GB
- 12 aylık büyüme: 30%

## 5. Özellikler

### F-01 Pipeline board
- Amaç: reps see open deals by stage.
- Kim: sales rep.
- Öncelik: P1
- Davranışlar:
  - A dragged card changes the stage.
- Kurallar: another tenant's deal is never visible.
"""


def tmp_project(with_docs_tool=True, brief=BRIEF):
    base = Path(tempfile.mkdtemp(prefix="plan-state-", dir=os.environ.get("TMPDIR"))).resolve()
    (base / "docs").mkdir()
    if with_docs_tool:
        (base / "tools").mkdir()
        shutil.copy(DOCS_PY, base / "tools" / "docs.py")
    (base / "BRIEF.md").write_text(brief, encoding="utf-8")
    return base


def run(root, *argv):
    """Run the CLI in process. Returns (exit code, parsed JSON or raw text)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main([str(a) for a in argv] + ["--root", str(root)])
    text = out.getvalue()
    try:
        return code, json.loads(text.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return code, text


def run_crash(root, failpoint, *argv):
    """Run the CLI in a subprocess with a failpoint; returns the exit code."""
    env = dict(os.environ, **{store.FAILPOINT_ENV: failpoint})
    r = subprocess.run([sys.executable, str(PLAN_STATE_PY), *[str(a) for a in argv], "--root", str(root)],
                       env=env, capture_output=True, text=True, timeout=60)
    return r.returncode


def docs_new(root, kind, title):
    tool = cli.load_docs_tool(root)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        tool.main(["new", kind, title, "--root", str(Path(root) / "docs")])
    return Path(out.getvalue().strip()).resolve().relative_to(root).as_posix()


def write_doc(root, rel, rel_body):
    """Create or overwrite a doc with valid front matter."""
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(rel_body, encoding="utf-8")


def append(root, rel, text):
    p = Path(root) / rel
    p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8")


def state_of(root):
    return store.Store(root, cli.find_plan(root, None)).read_state()


def next_lines(root):
    code, text = run(root, "next")
    return [l for l in text.splitlines() if l and not l.startswith(" ") and not l.startswith("#")]


class FakeTeam:
    """
    Plays the Lead and every role with fixed outputs, one step per call.

    Each step runs one plan_state command. With crash set, the command first runs in a
    subprocess that dies at a failpoint, then runs again with the same op id.
    """

    DOCS = {
        "strategy": [("module", "Invariants"), ("adr", "Strategy")],
        "catalog": [("plan", "Catalog")],
        "design": [("domain", "Deals"), ("adr", "System")],
        "ux": [("plan", "UX")],
        "security": [("threat", "Threat model")],
        "performance": [("perf", "Performance")],
        "slices": [("plan", "Slices")],
        "quality": [("quality", "Quality plan")],
    }

    def __init__(self, root, crash=False, findings=True, two_slices=False):
        self.root = Path(root)
        self.two_slices = two_slices
        self.crash = crash
        self.findings = findings
        self.paths = {}
        self.role_paths = {}
        self.steps = 0
        self.failpoints = ("after_journal_append", "during_snapshot")

    def cmd(self, *argv, op):
        if self.crash:
            fp = self.failpoints[self.steps % 2]
            code = run_crash(self.root, fp, *argv, "--op", op)
            assert code == store.FAILPOINT_EXIT, (argv, code)
        self.steps += 1
        return run(self.root, *argv, "--op", op)

    def files_for(self, task):
        base = task.split(".")[0]
        if task in self.paths:
            return self.paths[task]
        if base.startswith("fix"):
            return self.role_paths.get(task.split(".")[-1], [])
        paths = [docs_new(self.root, k, t) for k, t in self.DOCS.get(base, [])]
        self.paths[task] = paths
        role = engine.FLOW_ROLES[base]
        self.role_paths.setdefault(role, []).extend(paths)
        return paths

    def write(self, task, attempt, paths):
        base = task.split(".")[0]
        lines = [f"ATTEMPT {attempt}"]
        if base == "strategy":
            append(self.root, paths[0], "\n## Invariants\n- INV-01 Every row carries tenant_id.\n")
            append(self.root, paths[1], "\nModular monolith; see INV-01.\n")
        elif base == "catalog":
            append(self.root, paths[0], (
                "\n## Features\n### F-01 Pipeline board\n"
                "- US-01 As a rep, I want the board, so that I see deals. F-01\n"
                "  - When a card moves, the system shall record the stage.\n"
                "- BR-01 A deal belongs to one tenant. INV-01\n"
                + ("- US-02 As a manager I see totals. F-01\n"
                   "  - When the board opens, the system shall show totals.\n" if self.two_slices else "")
                + "\n"
                "## Suggestions\n| ID | Title | karar |\n|---|---|---|\n| R-01 | Export | defer |\n"))
        elif base == "design":
            append(self.root, paths[0], "\n### D-01 ERD\n- deal(id, tenant_id, stage) for F-01 and US-01.\n"
                                        "\n### E-01 deal\n- Fields: id, tenant_id, stage. F-01\n")
            append(self.root, paths[1], "\n## Components\nAPI and worker for F-01.\n"
                                        "\n## API endpoints and events\n- API-01 GET board: lists deals for US-01.\n")
        elif base == "ux":
            append(self.root, paths[0], "\n### D-02 Board journey\n- Flow for US-01 and F-01.\n")
        elif base == "security":
            append(self.root, paths[0], "\n### SEC-01 Tenant isolation\n- RLS on deal, D-01.\n")
            if self.findings:
                lines.append("FINDING SEC-02 | MAJOR | solution-architect | no audit trail | D-01 has no audit field")
        elif base == "performance":
            append(self.root, paths[0], "\n### PERF-01 Board p95 under 300 ms\n- Index on stage for D-01.\n"
                                        "- deferred: perf-team\n")
        elif base == "fix1":
            dom = [p for p in paths if "03-domains" in p][0]
            text = (self.root / dom).read_text(encoding="utf-8")
            (self.root / dom).write_text(text.replace("stage) for F-01 and US-01.\n",
                                                      "stage) for F-01 and US-01.\n- audit(at, actor)\n"),
                                         encoding="utf-8")
            lines.append(f"FIX SEC-02 | {dom} | impact: contract | added the audit fields")
        elif base == "slices":
            append(self.root, paths[0], "\n### S0 Walking skeleton and board\n- Covers US-01, SEC-01.\n"
                                        "- Doğrulama: tenant isolation test.\n")
            if self.two_slices:
                append(self.root, paths[0], "\n### S1 Totals\n- Covers US-02.\n- Doğrulama: unit test of totals.\n")
        elif base == "quality":
            append(self.root, paths[0], "\n## Review\nMatrix reviewed.\n")
            lines.append("ASSUMPTION the matrix is complete")
        elif base == "critic_review":
            if self.findings:
                lines.append("FINDING DA-01 | MAJOR | product-manager | S0 lacks deploy | S0 block")
            else:
                lines.append("ASSUMPTION nothing to add")
        elif base == "fix2":
            slices = self.paths["slices"][0]
            text = (self.root / slices).read_text(encoding="utf-8")
            (self.root / slices).write_text(text.replace("- Covers US-01, SEC-01.\n",
                                                         "- Covers US-01, SEC-01.\n- Deploy to staging.\n"),
                                            encoding="utf-8")
            lines.append(f"FIX DA-01 | {slices} | impact: local | added the deploy step")
        for p in paths:
            lines.append(f"WROTE {p}")
        if len(lines) == 1:
            lines.append("ASSUMPTION nothing changed")
        return "\n".join(lines) + "\n"

    def step(self):
        """Do one Lead action. Returns False when next says DONE."""
        lines = next_lines(self.root)
        first = lines[0].split()
        kind = first[0]
        if kind == "DONE":
            return False
        if kind == "ASK":
            gate = first[1]
            code, out = self.cmd("gate", gate, "--defaults", op=f"gate:{gate}:{self.steps}")
            assert out["ok"], out
            return True
        if kind == "RUN" and first[1] == "handoff":
            if first[3] == "publish" and self.crash:
                code = run_crash(self.root, "mid_publish", "handoff", "publish", "--op", "pub")
                assert code in (0, store.FAILPOINT_EXIT), code
            code, out = run(self.root, "handoff", first[3], "--op", f"handoff:{first[3]}")
            assert out["ok"], out
            return True
        if kind == "RUN":
            task, role, mode = first[1], first[2], first[3]
            attempt, paths = self.start_task(task, role)
            self.record_task(task, mode, attempt, paths)
            return True
        raise AssertionError(f"unexpected next output: {lines}")

    def start_task(self, task, role):
        """Start one task (with the D alloc before step 3). Returns (attempt id, paths)."""
        state = state_of(self.root)
        t = state["tasks"][task]
        paths = self.files_for(task)
        if task in ("design", "ux") and t["status"] == "pending" and not t["attempts"]:
            code, out = self.cmd("alloc", "D", 1, "--owner", role, op=f"alloc:{task}")
            assert out["ok"], out
        n = len(t["attempts"]) + 1
        argv = ["start", task] + [x for p in paths for x in ("--write", p)]
        code, out = self.cmd(*argv, op=f"start:{task}:{n}")
        assert out["ok"], out
        return out["result"]["attempt"], paths

    def output(self, task, mode, attempt, paths):
        if mode == "recheck":
            return f"ATTEMPT {attempt}\nRECHECK {task} | local | still consistent\n"
        if mode == "revise" and not task.startswith("fix"):
            return f"ATTEMPT {attempt}\n" + "".join(f"WROTE {p}\n" for p in paths) + "ASSUMPTION revised\n"
        return self.write(task, attempt, paths)

    def record_task(self, task, mode, attempt, paths):
        out_file = self.root / ".cache" / "plan" / "attempts" / f"{attempt}.out"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(self.output(task, mode, attempt, paths), encoding="utf-8")
        code, out = self.cmd("record", task, "--attempt", attempt, "--out", out_file, "--tokens", 1000,
                             op=f"rec:{attempt}")
        assert out["ok"], out
        return out

    def run_until(self, prefix, limit=80):
        """Step until the first next line starts with prefix."""
        for _ in range(limit):
            if next_lines(self.root)[0].startswith(prefix):
                return
            if not self.step():
                break
        raise AssertionError(f"never reached {prefix}")

    def run_to_end(self, limit=80):
        for _ in range(limit):
            if not self.step():
                return True
        raise AssertionError("the flow did not finish")


class Eng:
    """
    Drives the pure engine directly with in-memory documents (no files, no CLI).
    """

    def __init__(self, brief=BRIEF):
        self.state, self.events, self.seq, self.docs = None, [], 0, {}
        self.brief = brief
        self.do("init", {"plan_id": "PLAN-0001", "brief": "BRIEF.md", "brief_check": checks.brief_check(brief),
                         "brief_scan": registry.scan_doc(brief), "size": checks.plan_size(brief)})

    def do(self, etype, payload, op=None):
        self.seq += 1
        event = {"schema_version": 1, "seq": self.seq, "op_id": op or f"op{self.seq}", "at": "2026-11-10T10:00:00+00:00",
                 "actor": "test", "type": etype, "payload": payload, "expect_rev": None, "args_hash": str(payload)[:50]}
        try:
            self.state, result = engine.apply(self.state, event)
            self.events.append(event)
            return result
        except engine.Reject as r:
            self.events.append({**event, "type": "rejected", "op_id": "",
                                "payload": {"command": etype, "code": r.code, "message": r.message}})
            self.state = dict(self.state, applied_seq=self.seq)
            return r

    def tree(self):
        return {p: registry.sha(t) for p, t in self.docs.items()}

    def start(self, task, scope=()):
        return self.do("start", {"task": task, "scope": list(scope), "tree": self.tree()})

    def record(self, task, lines=("ASSUMPTION ok",), attempt=None, tokens=100, model=None):
        t = self.state["tasks"][task]
        attempt = attempt or t["attempts"][-1]["id"]
        out = checks.parse_output(f"ATTEMPT {attempt}\n" + "\n".join(lines) + "\n")
        scans = {p: (registry.scan_doc(self.docs[p]) if p in self.docs else None) for p in t["scope"]}
        return self.do("record", {"task": task, "output": out, "tokens": tokens, "model": model,
                                  "tree": self.tree(), "scans": scans})

    def decide(self, target, action, **kw):
        return self.do("decide", {"target": target, "action": action, "rows": kw.pop("rows", []), **kw})

    def run_task(self, task, docs=None, lines=("ASSUMPTION ok",), **kw):
        """Write docs (path to text), start, record."""
        res = self.start(task, sorted(docs or {}))
        assert not isinstance(res, engine.Reject), (task, res.code, res.message)
        self.docs.update(docs or {})
        return self.record(task, lines, **kw)

    def status(self, task):
        return self.state["tasks"][task]["status"]


DOM = "docs/03-domains/deals/DOM-0001-deals.md"
ADR = "docs/02-decisions/ADR-0002-system.md"
INV = "docs/01-architecture/modules/ARCH-0001-invariants.md"
STRAT = "docs/02-decisions/ADR-0001-strategy.md"
CATALOG = "docs/05-work/plans/PLAN-0001-catalog.md"
UXDOC = "docs/05-work/plans/PLAN-0002-ux.md"
THREAT = "docs/01-architecture/security/ARCH-0002-threat.md"
PERFDOC = "docs/01-architecture/performance/ARCH-0003-perf.md"

CATALOG_TEXT = ("### F-01 Pipeline board\n- US-01 As a rep I want the board. F-01\n"
                "  - When a card moves, the system shall record the stage.\n- BR-01 One tenant per deal. INV-01\n")


def through_gate_a(e):
    """Run strategy and catalog and approve G1 and G2 on an Eng."""
    e.run_task("strategy", {INV: "- INV-01 Every row has tenant_id.\n", STRAT: "Monolith. INV-01\n"})
    e.run_task("catalog", {CATALOG: CATALOG_TEXT})
    e.decide("G1", "approve")
    e.decide("G2", "approve", defaults=True)


def through_design(e, dom=None):
    through_gate_a(e)
    e.do("alloc", {"prefix": "D", "n": 1, "owner": "solution-architect"})
    e.do("alloc", {"prefix": "D", "n": 1, "owner": "ux-designer"})
    e.start("design", [DOM, ADR])
    e.start("ux", [UXDOC])
    e.docs[DOM] = dom or "### D-01 ERD\n- account(id, tenant_id) for F-01 and US-01.\n"
    e.docs[ADR] = "API for F-01.\n"
    e.docs[UXDOC] = "### D-02 Journey\n- Board flow for US-01 and F-01.\n"
    e.record("design")
    e.record("ux")


BRIEF3 = BRIEF.split("## 5. Özellikler")[0] + """## 5. Özellikler

### F-01 Booking
- Amaç: the front desk books a slot.
- Kim: receptionist.
- Öncelik: P1
- Davranışlar:
  - A booked slot is not offered again.
- Kurallar: another tenant's booking is never visible.

### F-02 Patient card
- Amaç: the front desk sees past visits.
- Kim: receptionist.
- Öncelik: P2
- Davranışlar:
  - The card lists the visits.
- Kurallar: none.

### F-03 Reminders
- Amaç: patients get one reminder a day before.
- Kim: patient.
- Öncelik: P2
- Davranışlar:
  - One reminder per booking.
- Kurallar: none.
"""


class DryRunTeam(FakeTeam):
    """
    The realistic dry run of the planning review: three features, a CRITICAL SEC and a PERF
    finding with a solution proposed in the same E block, a CRITICAL DA finding with a proposed
    solution in step 7, and ux finishing before design. Nobody verifies a proposed solution (15.11).

    It starts every RUN line of a step, then records them in reverse order, and plays the
    user at the contacts: G1 approve, G2 from the catalog, G3 from a final package.
    """

    def __init__(self, root):
        super().__init__(root)
        self.prompts = {}
        self.final = None

    def step(self):
        code, text = run(self.root, "next")
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        first = lines[0].split()
        if first[0] == "RUN" and first[1] != "handoff":
            runs, current = [], None
            for line in lines:
                if line.startswith("RUN "):
                    current = line.split()
                    runs.append(current)
                    self.prompts.setdefault(current[1], []).append([])
                elif line.startswith("  ") and current:
                    self.prompts[current[1]][-1].append(line.strip())
            started = [(r[1], r[3], *self.start_task(r[1], r[2])) for r in runs]
            for task, mode, attempt, paths in reversed(started):
                self.record_task(task, mode, attempt, paths)
            return True
        if first[0] == "ASK" and first[1] == "G1":
            code, out = run(self.root, "decide", "G1", "approve", "--op", "gate:G1:1")
            assert out["ok"], out
            return True
        if first[0] == "ASK" and first[1] == "G2":
            code, out = run(self.root, "gate", "G2", "--from-doc", self.paths["catalog"][0], "--op", "gate:G2:1")
            assert out["ok"], out
            return True
        if first[0] == "ASK" and first[1] == "G3":
            self.final = docs_new(self.root, "plan", "Final package")
            append(self.root, self.final, "\n## To decide\n| ID | Item | Default | karar |\n|---|---|---|---|\n"
                                          "| quality: matrix | the matrix is complete | onayla | onayla |\n")
            code, out = run(self.root, "gate", "G3", "--from-doc", self.final, "--op", "gate:G3:1")
            assert out["ok"], out
            return True
        if first[0] == "ASK":
            raise AssertionError(f"unexpected contact: {lines}")
        return super().step()

    def edit(self, rel, old, new):
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        assert old in text, (rel, old)
        p.write_text(text.replace(old, new), encoding="utf-8")

    def write(self, task, attempt, paths):
        lines = [f"ATTEMPT {attempt}"]
        dom = next((p for p in self.role_paths.get("solution-architect", []) if "03-domains" in p), None)
        if task == "strategy":
            append(self.root, paths[0], "\n## Invariants\n- INV-01 Every row carries tenant_id.\n"
                                        "- INV-02 Times are stored in UTC.\n")
            append(self.root, paths[1], "\nModular monolith; see INV-01 and INV-02.\n")
        elif task == "catalog":
            append(self.root, paths[0], (
                "\n## Features\n### F-01 Booking\n"
                "- US-01 As a receptionist, I book a slot. F-01 BR-01\n"
                "  - When a slot is booked, the system shall reject an overlapping booking.\n"
                "- BR-01 A booking belongs to one tenant. INV-01\n"
                "### F-02 Patient card\n"
                "- US-02 As a receptionist, I see the patient card. F-02\n"
                "  - When the card opens, the system shall list the past visits.\n"
                "### F-03 Reminders\n"
                "- US-03 As a patient, I get a reminder. F-03\n"
                "  - When a booking is one day away, the system shall send one reminder.\n\n"
                "## Suggestions\n| ID | Title | karar |\n|---|---|---|\n| R-01 | SMS reminders | ertele |\n"))
        elif task == "design":
            append(self.root, paths[0], (
                "\n## Entities\nEntities of the booking area.\n"
                "### D-01 ERD\n- booking, patient and reminder for F-01, F-02, F-03, US-01, US-02 and US-03.\n"
                "### E-01 booking\n- Fields: id, slot, patient_id. F-01\n"
                "### E-02 patient\n- Fields: id, name. F-02\n\n"
                "## Jobs\nThe reminder job runs every hour.\n"
                "### E-03 reminder\n- Fields: id, booking_id. F-03\n"))
            append(self.root, paths[1], "\n## Components\nAPI and worker for F-01.\n\n## API endpoints and events\n"
                                        "- API-01 POST booking: books a slot for US-01. E-01\n"
                                        "- API-02 GET card: the card for US-02. E-02\n")
        elif task == "ux":
            append(self.root, paths[0], "\n### D-02 Front desk journey\n- Flow for US-01, US-02, US-03, "
                                        "F-01, F-02 and F-03.\n")
        elif task == "security":
            append(self.root, paths[0], "\n### SEC-01 Tenant isolation\n- RLS on E-01 and E-02.\n")
            lines.append("FINDING SEC-02 | CRITICAL | solution-architect | E-01 has no tenant_id | E-01 | class: H3")
        elif task == "performance":
            append(self.root, paths[0], "\n### PERF-01 Week view p95 under 300 ms\n- Slot index on E-01; "
                                        "the reminder scan reads E-03.\n- deferred: perf-team\n")
            lines.append("FINDING PERF-02 | MAJOR | solution-architect | no slot index on E-01 | E-01")
        elif task == "fix1.solution-architect":
            self.edit(dom, "- Fields: id, slot, patient_id. F-01\n",
                      "- Fields: id, tenant_id, slot, patient_id. F-01\n- Index: (tenant_id, slot).\n")
            lines.append(f"FIX SEC-02 | {dom} | impact: contract | added tenant_id to E-01")
            lines.append(f"FIX PERF-02 | {dom} | impact: contract | added the slot index to E-01")
        elif task == "slices":
            append(self.root, paths[0], "\n### S0 Walking skeleton and booking\n- Covers US-01, SEC-01.\n"
                                        "- Doğrulama: tenant isolation test.\n"
                                        "\n### S1 Patient card\n- Covers US-02.\n- Doğrulama: card view test.\n"
                                        "\n### S2 Reminders\n- Covers US-03.\n- Doğrulama: reminder job test.\n")
        elif task == "quality":
            append(self.root, paths[0], "\n## Review\nMatrix reviewed.\n")
            lines.append("ASSUMPTION the matrix is complete")
        elif task == "critic_review":
            lines.append("FINDING DA-01 | CRITICAL | solution-architect | two reminder runs can mark the same "
                         "booking and lose the second change | E-03")
        elif task == "fix2.solution-architect":
            self.edit(dom, "- Fields: id, booking_id. F-03\n", "- Fields: id, booking_id, sent_at. F-03\n")
            lines.append(f"FIX DA-01 | {dom} | impact: contract | added sent_at to E-03")
        else:
            raise AssertionError(f"no output for {task}")
        for p in paths:
            lines.append(f"WROTE {p}")
        return "\n".join(lines) + "\n"
