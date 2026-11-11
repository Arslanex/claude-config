"""
Pure state machine: apply(state, event) returns (new state, result).

The engine never opens files. The CLI reads the project, puts what the engine needs
(document scans, docs hashes, parsed role output, check results) into the event
payload, and the engine decides. Replaying the journal therefore gives the same state.
"""
import copy

from . import checks, registry

SCHEMA_VERSION = checks.SCHEMA_VERSION


class Reject(Exception):
    """A refused command: the state does not change and the journal gets a rejected event."""

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail


# Flow (sürüm 6): name, step, role (None for a fix group), mode, deps, model override.
# Modes are the names the role agents use; design writes the data model, then the system.
FLOW = (
    ("strategy", 1, "strategy-architect", "draft", ("gate:Q1",), None),
    ("catalog", 2, "product-manager", "catalog", ("strategy",), None),
    ("design", 3, "solution-architect", "data,system", ("gate:G1", "gate:G2"), None),
    ("ux", 3, "ux-designer", "draft", ("gate:G1", "gate:G2"), None),
    ("security", 4, "security-architect", "draft", ("design", "ux"), None),
    ("performance", 4, "performance-architect", "draft", ("design", "ux"), None),
    ("fix1", 5, None, "fix", ("security", "performance"), None),
    ("slices", 5, "product-manager", "slices", ("fix1",), None),
    ("quality", 6, "quality-engineer", "draft", ("slices",), None),
    ("critic_review", 6, "plan-critic", "review", ("slices",), "opus"),
    ("fix2", 7, None, "fix", ("quality", "critic_review"), None),
)
FLOW_ROLES = {name: role for name, _, role, _, _, _ in FLOW}
PARALLEL_ROLES = (("solution-architect", "ux-designer"),
                  ("security-architect", "performance-architect"),
                  ("quality-engineer", "plan-critic"))
GATES = ("Q1", "G1", "G2", "Q2", "G3")
GATE_GROUP = {"Q1": "Q1", "G1": "A", "G2": "A", "Q2": "Q2", "G3": "G3"}
GATE_TASKS = {"G1": ("strategy",), "G2": ("catalog",)}
ALL_PREFIXES = registry.ID_PREFIXES + ("S",)
READS = {
    "strategy": ("F",), "catalog": ("F", "INV"),
    "design": ("F", "US", "BR", "INV"), "ux": ("F", "US", "BR", "INV"),
    "security": ("F", "US", "BR", "INV", "D", "E", "API"), "performance": ("F", "US", "BR", "INV", "D", "E", "API"),
    "slices": ("F", "US", "BR", "INV", "D", "E", "API", "SEC", "PERF"),
    "quality": ("F", "US", "BR", "D", "E", "API", "SEC", "PERF", "S"),
    "critic_review": ALL_PREFIXES,
    "closing": ("F", "US", "BR", "INV", "D", "E", "API", "SEC", "PERF", "S"),
}
# Whole earlier docs a first call reads, by doc kind (see doc_kind).
WHOLE_READS = {
    "strategy": ("brief",), "catalog": ("strategy", "inv"),
    "design": ("strategy", "inv", "catalog"), "ux": ("dom", "system", "catalog"),
    "security": ("strategy", "inv", "dom", "system"), "performance": ("strategy", "inv", "dom", "system"),
    "slices": ("catalog",), "quality": ("dom", "system", "catalog"), "closing": ("catalog",),
}
PRICES = {"fable": (10, 50), "opus": (4, 20), "sonnet": (2, 10), "haiku": (0.1, 0.5)}
LIMITS = {"calls": {"cap": 24, "warn": 18, "max": 30, "extended": False},
          "late_features": {"cap": 5, "max": 10, "extended": False}}
# Small plan mode (brief line "Plan boyutu: küçük"): a single-user or small internal tool.
SMALL = "küçük"
SMALL_SKIP = ("performance", "quality")
SMALL_MODELS = {"security-architect": "sonnet"}
SMALL_LIMITS = {"calls": {"cap": 14, "warn": 10, "max": 18}}
# The last calls of the cap are kept for the closing call while it has work (15.10).
CLOSING_RESERVE = {"tam": 2, SMALL: 1}
CLOSING_ROLE = "product-manager"
# Fresh calls for a finished stopped run and for a G3 change after closing.
FINISH_CALLS = 2
G3_FIX_CALLS = 2
RETRY_CAP = 1
GATE_MODIFY_CAP = 1

# Formal transition tables (7.4). Anything else is INVALID_TRANSITION.
TASK_TABLE = {
    "T1": ("pending", "running"), "T1b": ("pending", "blocked"), "T2": ("running", "done"),
    "T3": ("running", "running"), "T4": ("running", "blocked"),
    "T5a": ("blocked", "pending"), "T5b": ("blocked", "done"),
    "T6": ("done", "stale"), "T7": ("stale", "done"), "T8": ("stale", "pending"),
    "T9": ("*", "cancelled"), "T10": ("pending", "done"),
    "T11": ("cancelled", "pending"),
}
GATE_TABLE = {("closed", "open"), ("open", "approved"), ("open", "modify_requested"),
              ("modify_requested", "open"), ("open", "stopped"), ("approved", "open"),
              ("stopped", "modify_requested")}


def move_task(state, name, target, rule, reason=""):
    task = state["tasks"][name]
    src, dst = TASK_TABLE.get(rule, (None, None))
    if dst != target or (src != "*" and src != task["status"]) or (task["status"] == "cancelled" and rule != "T11"):
        raise Reject("INVALID_TRANSITION", f"{name}: {task['status']} -> {target} by {rule} is not allowed")
    task["history"].append([state["state_revision"] + 1, task["status"], target, rule, reason])
    task["status"] = target


def move_gate(state, gate, target, reason=""):
    g = state["gates"][gate]
    if (g["status"], target) not in GATE_TABLE:
        raise Reject("INVALID_TRANSITION", f"{gate}: {g['status']} -> {target} is not allowed")
    g["history"].append([state["state_revision"] + 1, g["status"], target, reason])
    g["status"] = target


# State construction

def _task(name, step, role, mode, deps, model):
    return {"name": name, "step": step, "role": role, "mode": mode, "deps": list(deps),
            "model": model or (registry.ROLES[role]["model"] if role else "-"),
            "is_group": role is None, "expanded": False, "status": "pending",
            "attempts": [], "retries": 0, "retry_cap": RETRY_CAP, "extended": False,
            "scope": [], "snapshot": {}, "reserved": False, "stale_ids": [],
            "findings": [], "history": []}


def _small_model(state, role):
    """The model a role runs on in small mode, or None for its registry model."""
    return SMALL_MODELS.get(role) if state["run"].get("size") == SMALL else None


def new_state(plan_id, size="tam"):
    small = size == SMALL
    tasks = {}
    for name, step, role, mode, deps, model in FLOW:
        tasks[name] = _task(name, step, role, mode, deps, model or (SMALL_MODELS.get(role) if small else None))
    limits = copy.deepcopy(LIMITS)
    if small:
        for key, values in SMALL_LIMITS.items():
            limits[key].update(values)
    gates = {g: {"status": "closed", "round": 1, "modify_rounds": 0, "modify_cap": GATE_MODIFY_CAP,
                 "extended": False, "opened_at": None, "approval_dec": None, "approval_rev": None,
                 "decisions": [], "history": [], "items": []} for g in GATES}
    return {
        "schema_version": SCHEMA_VERSION, "plan_id": plan_id, "applied_seq": 0, "state_revision": 0,
        "run": {"status": "active", "brief": None, "brief_check": None, "blocked": [], "size": size,
                "created_at": None, "stopped_at": None, "closing": None},
        "tasks": tasks, "gates": gates, "decisions": {}, "findings": {}, "ids": {},
        "artifacts": {}, "notes": {"assumptions": [], "opens": [], "questions": [],
                                   "conflicts": [], "late_features": [], "risks": []},
        "recheck_queue": {},
        "budget": {"calls": {"total": 0, "by_step": {}, "by_role": {}, "by_model": {}},
                   "retries": 0, "tokens": {},
                   "cost_estimated": "unknown", "cost_actual": "unknown"},
        "limits": limits,
        "contacts": {"count": 0, "seen": []},
        "critic_model_differs": True,
        "handoff": None, "ops": {}, "cascade": {},
    }


def _now(event):
    return event.get("at")


def _deps_ok(state, task):
    if task["step"] >= 6 and state["gates"]["Q2"]["status"] == "open":
        return False
    # No later step runs on top of a restarted earlier task.
    if any(t["step"] < task["step"] and t["status"] not in ("done", "cancelled") for t in state["tasks"].values()):
        return False
    for dep in task["deps"]:
        if dep.startswith("gate:"):
            if state["gates"][dep[5:]]["status"] != "approved":
                return False
        elif state["tasks"][dep]["status"] != "done":
            return False
    return True


def _reserved(state, exclude=None):
    return {n: t["scope"] for n, t in state["tasks"].items()
            if t["reserved"] and t["status"] == "running" and n != exclude}


def _current(task):
    return task["attempts"][-1] if task["attempts"] else None


def _limit_blocked(state, target, reason):
    if not any(b["target"] == target for b in state["run"]["blocked"]):
        state["run"]["blocked"].append({"target": target, "reason": reason})


# Budget

def _charge_call(state, task):
    lim = state["limits"]["calls"]
    calls = state["budget"]["calls"]
    if calls["total"] >= lim["cap"]:
        _limit_blocked(state, "calls", f"role-call cap {lim['cap']} reached")
        return False
    calls["total"] += 1
    for key, val in (("by_step", str(task["step"])), ("by_role", task["role"]), ("by_model", task["model"])):
        calls[key][val] = calls[key].get(val, 0) + 1
    return True


def _attempt_running(task):
    cur = _current(task)
    return task["status"] == "running" and cur is not None and cur["status"] == "running"


def _closing_need(state):
    """
    True while the closing call has work: the delivery slices are missing or not current,
    or a CRITICAL finding of the closing role is open.
    """
    if state["tasks"]["slices"]["status"] != "done" or not checks.live_slices(state):
        return True
    return any(f["owner"] == CLOSING_ROLE and f["severity"] == "CRITICAL" and f["status"] in ("open", "disputed")
               for f in state["findings"].values())


def normal_left(state):
    """
    Calls the normal flow may still start. After sitting A the reserve stays for the closing
    call while it has work.
    """
    held = state["gates"]["G2"]["status"] == "approved" and _closing_need(state)
    reserve = CLOSING_RESERVE.get(state["run"].get("size"), 2) if held else 0
    return state["limits"]["calls"]["cap"] - reserve - state["budget"]["calls"]["total"]


def _charge_tokens(state, model, tokens):
    toks = state["budget"]["tokens"]
    if tokens is None or toks.get(model) == "unknown":
        toks[model] = "unknown"
    else:
        toks[model] = toks.get(model, 0) + int(tokens)
    if any(v == "unknown" for v in toks.values()) or not toks:
        state["budget"]["cost_estimated"] = "unknown"
    else:
        # 12.1 assumption: ten input tokens for every output token.
        cost = sum(v * (10 * PRICES.get(m, (0, 0))[0] + PRICES.get(m, (0, 0))[1]) / 11 / 1e6
                   for m, v in toks.items())
        state["budget"]["cost_estimated"] = round(cost, 2)


def _new_attempt(state, task, payload, at):
    if not _charge_call(state, task):
        return None
    n = len(task["attempts"]) + 1
    attempt = {"id": f"{task['name']}-a{n}", "n": n, "status": "running", "started": at,
               "ended": None, "tokens": "unknown", "model": task["model"]}
    task["attempts"].append(attempt)
    task["snapshot"] = dict(payload.get("tree", {}))
    task["reserved"] = True
    return attempt


def _sync_snapshots(state, name, tree):
    """
    Accept the current hashes of this task's scope in every other running task's snapshot.

    Files of a parallel task are created and written inside that task's reservation, so
    the other tasks must not see them as changes outside their own scope.
    """
    scope = state["tasks"][name]["scope"]
    for other, t in state["tasks"].items():
        if other == name or t["status"] != "running":
            continue
        for path in scope:
            if path in tree:
                t["snapshot"][path] = tree[path]
            else:
                t["snapshot"].pop(path, None)


# Commands

def _start(state, p, at):
    name = p["task"]
    task = state["tasks"].get(name)
    if task is None or task["is_group"]:
        raise Reject("REFUSED", f"unknown task {name}")
    if state["run"]["status"] in ("stopped", "handed_off"):
        raise Reject("REFUSED", f"run is {state['run']['status']}")
    if any(b["target"] == "calls" for b in state["run"]["blocked"]):
        raise Reject("BUDGET", "the role-call budget is used up; decide calls extend or stop")
    if state["run"].get("closing") is None and name != "closing" and normal_left(state) <= 0:
        raise Reject("BUDGET", "the last role calls are reserved for the closing call")
    if task["status"] == "running":
        cur = _current(task)
        if cur and cur["status"] == "running":
            raise Reject("INVALID_TRANSITION", f"{name} already runs attempt {cur['id']}")
        if task["retries"] >= task["retry_cap"]:
            move_task(state, name, "blocked", "T4", "retry limit reached")
            return {"task": name, "status": "blocked", "error": "REFUSED", "reason": "retry limit reached"}
        attempt = _new_attempt(state, task, p, at)
        if attempt is None:
            return {"task": name, "error": "BUDGET", "reason": "role-call cap reached"}
        task["retries"] += 1
        state["budget"]["retries"] += 1
        move_task(state, name, "running", "T3", "retry")
        return {"task": name, "attempt": attempt["id"], "mode": task["mode"], "model": task["model"]}
    if task["status"] != "pending":
        raise Reject("INVALID_TRANSITION", f"{name} is {task['status']}")
    if not _deps_ok(state, task):
        raise Reject("DEPS_PENDING", f"{name} waits for {', '.join(task['deps'])}")
    scope = sorted(set(p.get("scope", [])))
    bad = [s for s in scope if not registry.in_write_map(task["role"], s) or registry.is_state_file(s)]
    if bad:
        raise Reject("SCOPE_VIOLATION", f"{task['role']} may not write {', '.join(bad)}")
    clash = registry.scope_conflicts(scope, _reserved(state, name))
    if clash:
        raise Reject("SCOPE_CONFLICT", "reserved by another task: "
                     + ", ".join(f"{k} ({v})" for k, v in sorted(clash.items())))
    task["scope"] = scope
    attempt = _new_attempt(state, task, p, at)
    if attempt is None:
        return {"task": name, "error": "BUDGET", "reason": "role-call cap reached"}
    _sync_snapshots(state, name, p.get("tree", {}))
    move_task(state, name, "running", "T1")
    return {"task": name, "attempt": attempt["id"], "mode": task["mode"], "model": task["model"]}


def _timeout(state, p, at):
    name = p["task"]
    task = state["tasks"].get(name)
    cur = _current(task) if task else None
    if not task or task["status"] != "running" or not cur or cur["status"] != "running":
        raise Reject("INVALID_TRANSITION", f"{name} has no running attempt")
    cur["ended"] = at
    if p.get("stopped"):
        cur["status"] = "timed_out"
        if task["retries"] >= task["retry_cap"]:
            task["reserved"] = False
            move_task(state, name, "blocked", "T4", "retry limit reached")
            return {"task": name, "attempt": cur["id"], "status": "blocked"}
        return {"task": name, "attempt": cur["id"], "status": "timed_out"}
    cur["status"] = "stopped"
    task["reserved"] = False
    move_task(state, name, "blocked", "T4", "stop of a timed out attempt was not confirmed")
    return {"task": name, "status": "blocked"}


def _fail_attempt(task, at):
    cur = _current(task)
    cur["status"], cur["ended"] = "failed", at


def _id_violations(state, role, scans):
    errors = []
    own = registry.ROLES[role]["prefixes"]
    for path, scan in sorted(scans.items()):
        if scan is None:
            continue
        for id_ in scan["blocks"]:
            prefix = registry.prefix_of(id_)
            rec = state["ids"].get(id_)
            if rec and rec["status"] == "retired":
                errors.append(f"{path}: {id_} is retired and may not be reused")
            elif prefix in registry.ALLOC_PREFIXES and prefix in own:
                if not rec or rec["owner"] != role:
                    errors.append(f"{path}: {id_} is not reserved for {role} (use alloc)")
            elif prefix not in own and not (prefix == "F" and rec and rec["status"] == "active"):
                # Only a feature may be restated (the catalog lists the brief's F ids).
                errors.append(f"{path}: {role} may not define {id_}; a line that starts with an id defines it")
    return errors


def _finding_violations(state, role, lines):
    errors = []
    prefix = registry.FINDING_PREFIX.get(role)
    for line in lines:
        if line["type"] == "FINDING":
            if registry.prefix_of(line["id"]) != prefix:
                errors.append(f"{role} may not raise {line['id']}")
            if not registry.ROLES.get(line["owner"], {}).get("writes"):
                errors.append(f"{line['id']}: unknown owner {line['owner']}")
            rec = state["ids"].get(line["id"])
            if rec and rec["status"] == "retired":
                errors.append(f"{line['id']} is retired")
    return errors


def _register_ids(state, role, rev):
    defined = {}
    for path, art in sorted(state["artifacts"].items()):
        for id_ in art["blocks"]:
            defined.setdefault(id_, path)
    for id_, path in defined.items():
        rec = state["ids"].get(id_)
        if rec is None:
            owner = state["artifacts"][path]["role"]
            state["ids"][id_] = {"prefix": registry.prefix_of(id_), "owner": owner, "doc": path,
                                 "first_rev": rev, "status": "active", "origin": None, "decision": None}
        elif rec["status"] == "reserved":
            rec.update(status="active", doc=path, first_rev=rev)
        elif rec["status"] == "active" and rec["doc"] not in state["artifacts"]:
            rec["doc"] = path
    retired = []
    for id_, rec in state["ids"].items():
        if rec["status"] == "active" and rec["doc"] and id_ not in defined:
            rec["status"] = "retired"
            retired.append(id_)
    return sorted(retired)


def _owner_task_of(state, path):
    art = state["artifacts"].get(path)
    return art["owner_task"] if art else None


def _restart(state, name, mode, stale_ids, reason):
    """Move a done task through stale to pending with the given mode (T6 then T8)."""
    move_task(state, name, "stale", "T6", reason)
    task = state["tasks"][name]
    task["stale_ids"] = sorted(set(stale_ids))
    move_task(state, name, "pending", "T8", reason)
    task["mode"], task["retries"] = mode, 0


def _round_key(state):
    """The fix round a cascade restart counts in: 0 until fix1 is done, then 1 (fix2)."""
    return "1" if state["tasks"]["fix1"]["status"] == "done" else "0"


def _cascade_revise(state, name, ids, reason, critical=False, retired=False):
    """
    Restart a done task in revise mode because of another role's contract change (15.10).

    After sitting A each role gets one such revise per fix round. A further one restarts
    nothing and becomes a dev-team note, unless the change answers a CRITICAL finding or
    the task references a retired ID (H4 would block the handoff). Returns True on a restart.
    """
    role = state["tasks"][name]["role"]
    if state["gates"]["G2"]["status"] == "approved" and not critical and not retired:
        used = state.setdefault("cascade", {}).setdefault(_round_key(state), [])
        if role in used:
            _risk(state, name, ids, f"sözleşme etkisi: {role} {', '.join(sorted(ids)) or 'no id'} "
                                    f"({reason}; bu turda ikinci revise açılmadı)", "dev_note")
            return False
        used.append(role)
    _restart(state, name, "revise", ids, reason)
    return True


def _impact(state, task_name, old_arts, scans, declared, restated=(), answered=(), critical=False):
    """
    Mark the dependents of a change (7.7).

    Only changed or removed blocks, and the blocks of a section whose outside text
    moved, count; an added ID marks nothing. A task is never marked by a change of
    its own role. In a fix round (steps 5 and 7) the role whose finding the fix answers
    gets no recheck (the dev team verifies the proposed solution, 15.11), and every other
    dependent gets one queued recheck that the round flushes when its fix group is done
    (see _flush_rechecks).
    """
    diffs = {path: registry.compare(old_arts.get(path), scan, restated) for path, scan in scans.items()}
    cls = registry.classify(diffs, declared)
    task = state["tasks"][task_name]
    changed, hit_ids, additive, outside_ids = set(), set(), set(), set()
    for d in diffs.values():
        changed |= set(d["added"]) | set(d["removed"]) | set(d["changed"])
        hit_ids |= set(d["removed"]) | set(d["changed"])
        additive |= set(d["additive"])
        outside_ids |= set(d.get("sections", []))
    effects = {"class": cls, "changed": sorted(changed), "stale": [], "revalidated": [],
               "revise": [], "recheck": [], "queued": []}
    if cls == "local":
        return effects
    targets = hit_ids | outside_ids
    fix_round = task["step"] in (5, 7)
    hits = {}
    for path in registry.dependents(state["artifacts"], targets, exclude_paths=set(scans)):
        owner = _owner_task_of(state, path)
        hits.setdefault(owner, set()).update(set(state["artifacts"][path]["refs"]) & targets)
    queue = state.setdefault("recheck_queue", {})
    for owner, hit in sorted(hits.items()):
        dep = state["tasks"].get(owner)
        if not dep or owner == task_name or dep["role"] == task["role"] or dep["status"] != "done":
            continue
        if fix_round and dep["role"] in answered:
            continue
        retired_hit = any(state["ids"].get(i, {}).get("status") == "retired" for i in hit)
        revise = retired_hit or bool(hit & (hit_ids - additive))
        if not revise and not hit & outside_ids:
            move_task(state, owner, "stale", "T6", f"contract change by {task_name}")
            dep["stale_ids"] = sorted(hit)
            move_task(state, owner, "done", "T7", "additive change passed the script check")
            effects["stale"].append(owner)
            effects["revalidated"].append(owner)
        elif fix_round:
            queue[owner] = sorted(set(queue.get(owner, [])) | hit)
            effects["queued"].append(owner)
        elif revise:
            if _cascade_revise(state, owner, hit, f"{cls} change by {task_name}", critical, retired_hit):
                effects["stale"].append(owner)
                effects["revise"].append(owner)
            else:
                effects.setdefault("noted", []).append(owner)
        else:
            _restart(state, owner, "recheck", hit, f"{cls} change by {task_name}")
            effects["stale"].append(owner)
            effects["recheck"].append(owner)
    return effects


def _flush_rechecks(state):
    """
    Turn the queued rechecks into calls once no fix group is in progress.

    Every dependent gets one recheck task. Returns True when something moved.
    """
    queue = state.get("recheck_queue")
    if not queue or any(t["is_group"] and t["expanded"] and t["status"] == "pending"
                        for t in state["tasks"].values()):
        return False
    for owner, ids in sorted(queue.items()):
        dep = state["tasks"][owner]
        if dep["status"] == "pending":
            dep["stale_ids"] = sorted(set(dep["stale_ids"]) | set(ids))
            continue
        if dep["status"] == "done":
            _restart(state, owner, "recheck", ids, "batched recheck after the fix round")
    state["recheck_queue"] = {}
    return True


def _risk(state, task, ids, text, kind="closing"):
    risks = state["notes"].setdefault("risks", [])
    if not any(r["text"] == text for r in risks):
        risks.append({"task": task, "ids": sorted(ids), "kind": kind, "text": text})


def _begin_closing(state, reason):
    """
    Switch the run to closing (15.10). The remaining normal work becomes risks; one closing
    call by the product-manager writes the delivery slices when they are missing or not current.
    """
    state["run"]["closing"] = "active"
    state["run"]["closing_reason"] = reason
    if not _closing_need(state):
        return
    t = state["tasks"].get("closing")
    if t is None:
        t = state["tasks"]["closing"] = _task("closing", 8, CLOSING_ROLE, "closing", (), None)
    elif t["status"] == "done":
        _restart(state, "closing", "closing", [], reason)
    t["stale_ids"] = sorted(state["tasks"]["slices"]["stale_ids"])
    t["findings"] = sorted(i for i, f in state["findings"].items() if f["owner"] == CLOSING_ROLE
                           and f["severity"] == "CRITICAL" and f["status"] in ("open", "disputed"))


def _settle(state, name, reason):
    """Mark a task done without its call (T10, or T4 then T5b for a failed or blocked one)."""
    t = state["tasks"][name]
    if t["status"] == "running":
        t["reserved"] = False
        move_task(state, name, "blocked", "T4", reason)
    if t["status"] == "blocked":
        move_task(state, name, "done", "T5b", reason)
    elif t["status"] == "stale":
        move_task(state, name, "done", "T7", reason)
    elif t["status"] == "pending":
        move_task(state, name, "done", "T10", reason)


def _closing_step(state):
    """
    Start or continue closing (15.10). Returns True when something moved.

    Closing starts when the normal flow has no call left and work remains. Every waiting
    task, fix group and queued recheck becomes a risk, the closing call runs, and at the end
    every unresolved non-CRITICAL finding is handed to the dev team as an accepted risk.
    A CRITICAL finding stays open and G3 shows it.
    """
    run, tasks = state["run"], state["tasks"]
    if run["status"] in ("stopped", "handed_off") or run.get("closing") == "done":
        return False
    changed = False
    if run.get("closing") is None:
        # Closing waits until the calls in flight have landed, so it decides on their results.
        if any(_attempt_running(t) for t in tasks.values()) or normal_left(state) > 0 \
                or state["gates"]["G2"]["status"] != "approved":
            return False
        if all(t["status"] in ("done", "cancelled") for t in tasks.values()):
            return False
        _begin_closing(state, "role-call budget reached")
        changed = True
    rev = state["state_revision"] + 1
    closing = tasks.get("closing")
    folded = closing is not None and closing["status"] not in ("done", "cancelled")
    reason = "closing: " + run["closing_reason"]
    for name in ordered(state):
        t = tasks[name]
        if name == "closing" or t["status"] in ("done", "cancelled") or _attempt_running(t):
            continue
        ids = sorted(set(t["stale_ids"]) | set(assigned_findings(state, name)))
        if t["is_group"]:
            t["history"].append([rev, t["status"], "done", "group", reason])
            t["status"] = "done"
        else:
            _settle(state, name, reason)
        if not t["is_group"] and not (name == "slices" and folded):
            _risk(state, name, ids, f"{name} ({t['mode']}) did not run: the plan closed at the role-call "
                                    f"budget ({', '.join(ids) or 'no id'})")
        changed = True
    for owner, ids in sorted(state.get("recheck_queue", {}).items()):
        _risk(state, owner, ids, f"recheck of {owner} did not run: the plan closed at the role-call "
                                 f"budget ({', '.join(ids) or 'no id'})")
        changed = True
    state["recheck_queue"] = {}
    kept = [b for b in run["blocked"] if b["target"] != "calls"]
    if kept != run["blocked"]:
        run["blocked"] = kept
        changed = True
    if closing is not None and closing["status"] in ("running", "blocked") and not _attempt_running(closing) \
            and (closing["status"] == "blocked"
                 or state["budget"]["calls"]["total"] >= state["limits"]["calls"]["cap"]):
        _settle(state, "closing", reason)
        _risk(state, "closing", [], "the closing call did not finish; the delivery slices stay as they are")
        changed = True
    if all(t["status"] in ("done", "cancelled") for t in tasks.values()):
        for fid, f in sorted(state["findings"].items()):
            if f["status"] in checks.UNRESOLVED and f["severity"] != "CRITICAL":
                _risk(state, f["task"], [fid], f"geliştirme ekibine not: {fid} {f['severity']} kapanışta "
                                               f"{f['status']} kaldı: {f['claim']} ({f['evidence']})", "dev_note")
                f["history"].append([rev, "accepted_risk", reason])
                f["status"] = "accepted_risk"
        run["closing"] = "done"
        changed = True
    return changed


def _check_call(task):
    """
    True for a call that checks earlier work: a recheck or revise call.

    Such a call opens a new finding only when it is CRITICAL.
    """
    return task["mode"] in ("recheck", "revise")


def _apply_lines(state, task, lines, rev):
    role = task["role"]
    notes = state["notes"]
    result = {"findings": [], "warnings": []}
    for line in lines:
        kind = line["type"]
        if kind == "FINDING":
            fid = line["id"]
            f = state["findings"].get(fid)
            if f is None and line["severity"] != "CRITICAL" and _check_call(task):
                # A check call opens no new blocking work: the finding becomes a note for the dev team.
                notes.setdefault("risks", []).append(
                    {"task": task["name"], "ids": [fid], "kind": "dev_note",
                     "text": f"geliştirme ekibine not: {fid} {line['severity']} {line['claim']} ({line['evidence']})"})
                result["warnings"].append(f"{fid}: a new {line['severity']} finding in a check call became a dev-team note")
            elif f is None:
                state["findings"][fid] = {
                    "severity": line["severity"], "owner": line["owner"], "claim": line["claim"],
                    "evidence": line["evidence"], "cls": line["cls"], "raised_by": role,
                    "task": task["name"], "status": "open", "history": [[rev, "open"]],
                    "reply": None}
                state["ids"].setdefault(fid, {"prefix": registry.prefix_of(fid), "owner": role, "doc": None,
                                              "first_rev": rev, "status": "active", "origin": None,
                                              "decision": None})
                result["findings"].append(fid)
            else:
                result["warnings"].append(f"{fid} already exists; repeated FINDING ignored")
        elif kind in ("FIX", "DISPUTE"):
            f = state["findings"].get(line["id"])
            if not f or f["owner"] != role:
                result["warnings"].append(f"{line['id']}: not a finding owned by {role}")
                continue
            if kind == "FIX":
                # "fixed" means a proposed solution (çözüm önerildi); the dev team verifies it (15.11).
                f["status"] = "fixed"
                f["reply"] = f"FIX {line['change']}"
            else:
                f["status"] = "disputed"
                f["reply"] = f"DISPUTE {line['evidence']}"
            f["history"].append([rev, f["status"]])
        elif kind == "OPEN":
            notes["opens"].append({"id": line["id"], "task": task["name"], "step": task["step"],
                                   "question": line["question"], "blocking": line["blocking"],
                                   "default": line["default"]})
            if line["kind"] == "feature":
                notes["late_features"].append(line["id"])
        elif kind == "ASSUMPTION":
            notes["assumptions"].append({"task": task["name"], "text": line["text"]})
        elif kind == "QUESTION":
            notes["questions"].append({"task": task["name"], "id": line["id"], "question": line["question"]})
        elif kind == "CONFLICT":
            notes["conflicts"].append({"task": task["name"], **{k: line[k] for k in ("id", "role", "path", "text")}})
    return result


def _record(state, p, at, rev):
    name = p["task"]
    task = state["tasks"].get(name)
    if task is None or task["is_group"]:
        raise Reject("REFUSED", f"unknown task {name}")
    out = p["output"]
    cur = _current(task)
    if not out.get("attempt_id"):
        raise Reject("BAD_ATTEMPT", "the output has no ATTEMPT line")
    if task["status"] != "running" or not cur or cur["id"] != out["attempt_id"] or cur["status"] != "running":
        raise Reject("LATE_RESULT", f"{out['attempt_id']} is not the current attempt of {name}")
    model = p.get("model") or task["model"]
    cur["tokens"] = p.get("tokens") if p.get("tokens") is not None else "unknown"
    cur["model"] = model
    _charge_tokens(state, model, p.get("tokens"))
    if task["role"] == "plan-critic" and task["mode"] == "review" and model != "opus":
        state["critic_model_differs"] = False
    # Scope check: changed files must be in this scope or in another running reservation.
    tree = p.get("tree", {})
    changed = registry.changed_paths(task["snapshot"], tree)
    allowed = set(task["scope"]).union(*_reserved(state, name).values())
    violations = [c for c in changed if c not in allowed]
    _sync_snapshots(state, name, tree)
    if violations:
        _fail_attempt(task, at)
        task["reserved"] = False
        move_task(state, name, "blocked", "T4", "changed outside its scope: " + ", ".join(violations))
        return {"task": name, "status": "blocked", "error": "SCOPE_VIOLATION", "paths": violations}
    content = [l for l in out["lines"]]
    scans = {k: v for k, v in p.get("scans", {}).items() if k in task["scope"]}
    errors = [] if content else ["no valid content line"]
    errors += _id_violations(state, task["role"], scans) + _finding_violations(state, task["role"], content)
    if task["mode"] == "recheck" and not any(l["type"] == "RECHECK" for l in content):
        errors.append("recheck mode needs a RECHECK line")
    if errors:
        _fail_attempt(task, at)
        retry = task["retries"] < task["retry_cap"]
        if not retry:
            task["reserved"] = False
            move_task(state, name, "blocked", "T4", "retry limit reached")
        return {"task": name, "error": "CHECK_FAILED", "errors": errors + out.get("warnings", []),
                "retry": retry}
    old_arts = {k: copy.deepcopy(state["artifacts"].get(k)) for k in scans}
    restated = {i for p, a in state["artifacts"].items() if p not in scans for i in a["blocks"]
                if state["ids"].get(i, {}).get("status") == "active"}
    for path, scan in scans.items():
        if scan is None:
            state["artifacts"].pop(path, None)
            continue
        prev = state["artifacts"].get(path)
        owner = prev["owner_task"] if prev else name
        role = prev["role"] if prev else task["role"]
        state["artifacts"][path] = {"owner_task": owner, "role": role, **scan}
    retired = _register_ids(state, task["role"], rev)
    applied = _apply_lines(state, task, content, rev)
    cur["status"], cur["ended"] = "succeeded", at
    task["reserved"] = False
    task["snapshot"] = {}
    move_task(state, name, "done", "T2")
    declared = [l["impact"] for l in content if l["type"] == "FIX"]
    answered = {state["findings"][l["id"]]["raised_by"] for l in content
                if l["type"] in ("FIX", "DISPUTE") and l["id"] in state["findings"]}
    critical = any(l["type"] == "FIX" and state["findings"].get(l["id"], {}).get("severity") == "CRITICAL"
                   for l in content)
    effects = _impact(state, name, old_arts, scans, declared, restated, answered, critical)
    effects["retired"] = retired
    recheck = next((l for l in content if l["type"] == "RECHECK"), None)
    if task["mode"] == "recheck" and recheck and recheck["impact"] == "contract":
        if _cascade_revise(state, name, task["stale_ids"], "recheck said contract", critical):
            effects["revise"].append(name)
    if effects["class"] == "contract":
        g3 = state["gates"]["G3"]
        if g3["status"] == "approved":
            move_gate(state, "G3", "open", f"contract change by {name} after approval")
            g3["round"] += 1
    late = state["limits"]["late_features"]
    if len(state["notes"]["late_features"]) > late["cap"]:
        _limit_blocked(state, "late_features", f"more than {late['cap']} late features")
    return {"task": name, "status": state["tasks"][name]["status"], "impact": effects,
            "findings": applied["findings"], "warnings": out.get("warnings", []) + applied["warnings"]}


def _alloc(state, p, rev):
    prefix, n, owner = p["prefix"], int(p["n"]), p["owner"]
    if prefix not in registry.ALLOC_PREFIXES:
        raise Reject("REFUSED", f"alloc hands out only {', '.join(registry.ALLOC_PREFIXES)}")
    if owner not in registry.ROLES or prefix not in registry.ROLES[owner]["prefixes"]:
        raise Reject("REFUSED", f"{owner} may not hold {prefix} ids")
    if not 1 <= n <= 20:
        raise Reject("REFUSED", "n must be between 1 and 20")
    ids = _next_ids(state, prefix, n)
    for i in ids:
        state["ids"][i] = {"prefix": prefix, "owner": owner, "doc": None, "first_rev": rev,
                           "status": "reserved", "origin": None, "decision": None}
    return {"ids": ids}


def _next_ids(state, prefix, n):
    used = [registry.number_of(i) for i in state["ids"] if registry.prefix_of(i) == prefix]
    start = max(used, default=0) + 1
    return [registry.format_id(prefix, k) for k in range(start, start + n)]


def _decision(state, p, at, rev):
    dec = _next_ids(state, "DEC", 1)[0]
    target, action = p["target"], p["action"]
    gate = target if target in GATES else None
    prev = sorted((d for d, r in state["decisions"].items() if r["target"] == target), key=registry.number_of)
    state["decisions"][dec] = {"gate": gate, "round": state["gates"][gate]["round"] if gate else None,
                               "target": target, "action": action, "note": p.get("note"),
                               "item": p.get("item"), "rows": p.get("rows"),
                               "supersedes": prev[-1] if prev else None, "at": at, "rev": rev}
    state["ids"][dec] = {"prefix": "DEC", "owner": "plan_state", "doc": None, "first_rev": rev,
                         "status": "active", "origin": None, "decision": None}
    key = [GATE_GROUP.get(target, target), state["gates"][gate]["round"] if gate else rev]
    if key not in state["contacts"]["seen"]:
        state["contacts"]["seen"].append(key)
        state["contacts"]["count"] += 1
    return dec


def _finish(state, p, at, rev):
    """
    Reopen a stopped run and close it with a small fresh allowance (15.10).

    The tasks the stop cancelled come back (T11) and closing turns them into risks, except
    the delivery slices, which the closing call writes. G3 opens when closing is done.
    """
    run = state["run"]
    if run["status"] != "stopped":
        raise Reject("REFUSED", f"run is {run['status']}; only a stopped run can be finished")
    if state["gates"]["G2"]["status"] != "approved":
        raise Reject("REFUSED", "the run stopped before sitting A; start a new run with the brief")
    dec = _decision(state, p, at, rev)
    for name, t in state["tasks"].items():
        if t["status"] == "cancelled":
            for a in t["attempts"]:
                if a["status"] == "running":
                    a["status"], a["ended"] = "stopped", a["ended"] or at
            move_task(state, name, "pending", "T11", f"finish ({dec})")
            t["reserved"], t["scope"] = False, []
    lim = state["limits"]["calls"]
    lim["cap"] = max(lim["cap"], state["budget"]["calls"]["total"] + FINISH_CALLS)
    lim["max"] = max(lim["max"], lim["cap"])
    run["blocked"] = [b for b in run["blocked"] if b["target"] != "calls"]
    run["status"], run["stopped_at"] = "active", None
    g3 = state["gates"]["G3"]
    if g3["status"] in ("open", "stopped"):
        move_gate(state, "G3", "modify_requested", f"finish ({dec})")
        g3["round"] += 1
    _begin_closing(state, f"finish ({dec})")
    return {"decision": dec, "run": "active", "cap": lim["cap"],
            "closing_call": "closing" in state["tasks"] and state["tasks"]["closing"]["status"] == "pending"}


def _g3_fix(state, items):
    """
    The one-time fix of CRITICAL findings at G3: a fix call by each owner of an open or
    disputed one. Nobody judges the answer; a proposed solution goes to the dev team (15.11).
    Returns the new tasks.
    """
    found = [i for i in items if i in state["findings"] and state["findings"][i]["severity"] == "CRITICAL"
             and state["findings"][i]["status"] in checks.UNRESOLVED]
    if not found:
        return []
    if state["run"].get("g3_fix"):
        raise Reject("REFUSED", "the one-time G3 fix was used; descope the affected feature or stop")
    state["run"]["g3_fix"] = True
    tasks, made = state["tasks"], []
    fixes = {}
    for fid in found:
        fixes.setdefault(state["findings"][fid]["owner"], []).append(fid)
    for owner, fids in sorted(fixes.items()):
        name = f"fix3.{owner}"
        tasks[name] = _task(name, 7, owner, "revise", (), _small_model(state, owner))
        tasks[name]["findings"] = sorted(fids)
        made.append(name)
    return made


def _stop(state, at, reason):
    for name, t in state["tasks"].items():
        if t["status"] in ("pending", "running", "blocked", "stale"):
            move_task(state, name, "cancelled", "T9", reason)
            t["reserved"] = False
    state["run"]["stopped_at"] = at
    state["run"]["status"] = "stopped"


def _freeze(state, rows, rev):
    """Apply G2 decisions and give every accepted M, G or R row a permanent F id."""
    values = dict(rows)
    created = []
    origins = {rec.get("origin") for rec in state["ids"].values()}
    for id_, rec in sorted(state["ids"].items(), key=lambda kv: (kv[1]["prefix"], registry.number_of(kv[0]))):
        if rec["prefix"] not in ("F", "M", "G", "R") or rec["status"] != "active" or rec.get("origin"):
            continue
        value = values.get(id_) or ("defer" if rec["prefix"] == "R" else "accept")
        rec["decision"] = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}.get(value, value)
        if rec["prefix"] != "F" and rec["decision"] == "accepted" and id_ not in origins:
            fid = _next_ids(state, "F", 1)[0]
            state["ids"][fid] = {"prefix": "F", "owner": "plan_state", "doc": None, "first_rev": rev,
                                 "status": "active", "origin": id_, "decision": "accepted"}
            created.append(fid)
    return created


def _defining_task(state, id_):
    for path, art in sorted(state["artifacts"].items()):
        if id_ in art["blocks"] and art["owner_task"] in state["tasks"]:
            return art["owner_task"]
    return None


def _gate_modify(state, gate, tasks_to_revise, reason, dec):
    """
    Open a modify round. A G1 modify takes G2 into the same round, so sitting A has one round.
    """
    gates = [gate] + (["G2"] if gate == "G1" and state["gates"]["G2"]["status"] == "open" else [])
    g = state["gates"][gate]
    if g["modify_rounds"] >= g["modify_cap"]:
        raise Reject("REFUSED", f"{gate} modify limit reached; decide {gate} extend, approve or stop")
    for name in gates:
        g = state["gates"][name]
        g["modify_rounds"] += 1
        move_gate(state, name, "modify_requested", reason)
        g["round"] += 1
    for name in tasks_to_revise:
        if state["tasks"][name]["status"] == "done":
            _restart(state, name, "revise", [], f"{gate} modify ({dec})")
    return {"gate": gate, "status": "modify_requested", "revise": list(tasks_to_revise)}


def _decide(state, p, at, rev):
    target, action = p["target"], p["action"]
    run = state["run"]
    if action == "finish":
        if target != "run":
            raise Reject("REFUSED", "finish takes the target run")
        return _finish(state, p, at, rev)
    if run["status"] in ("stopped", "handed_off"):
        raise Reject("REFUSED", f"run is {run['status']}")
    if action == "stop":
        dec = _decision(state, p, at, rev)
        if target in GATES and state["gates"][target]["status"] == "open":
            move_gate(state, target, "stopped", dec)
        _stop(state, at, f"stop ({dec})")
        return {"decision": dec, "run": "stopped"}
    if target in GATES:
        return _decide_gate(state, p, at, rev)
    if target in state["findings"]:
        f = state["findings"][target]
        if action != "accept-risk":
            raise Reject("REFUSED", f"a finding takes accept-risk (or a descope of its feature at G3)")
        if f["severity"] == "CRITICAL" or f["status"] not in checks.UNRESOLVED:
            raise Reject("REFUSED", f"{target} is non-waivable or not open; it must be closed or descoped")
        dec = _decision(state, p, at, rev)
        f["status"] = "accepted_risk"
        f["history"].append([rev, "accepted_risk", dec])
        return {"decision": dec, "finding": target, "status": "accepted_risk"}
    if target in ("calls", "late_features"):
        return _decide_limit(state, p, at, rev)
    h = state["handoff"]
    if target == "handoff" and h and h["state"] == "failed" and action == "extend":
        if state["run"].get("handoff_retried"):
            raise Reject("REFUSED", "the handoff was already retried once; decide G3 modify, descope or stop")
        dec = _decision(state, p, at, rev)
        state["run"]["handoff_retried"] = True
        state["handoff"] = None
        return {"decision": dec, "handoff": "retry"}
    task = state["tasks"].get(target)
    if task and task["status"] == "blocked":
        if action == "extend":
            if task["extended"]:
                raise Reject("REFUSED", f"{target} was already extended once")
            dec = _decision(state, p, at, rev)
            task["extended"], task["retry_cap"], task["retries"] = True, task["retry_cap"] + 1, 0
            move_task(state, target, "pending", "T5a", dec)
            task["scope"] = []
            return {"decision": dec, "task": target, "status": "pending"}
        if action == "accept-current":
            dec = _decision(state, p, at, rev)
            move_task(state, target, "done", "T5b", dec)
            return {"decision": dec, "task": target, "status": "done"}
    raise Reject("REFUSED", f"{action} is not a valid answer for {target}")


def _decide_limit(state, p, at, rev):
    target, action = p["target"], p["action"]
    lim = state["limits"][target]
    blocked = [b for b in state["run"]["blocked"] if b["target"] == target]
    if not blocked:
        raise Reject("REFUSED", f"{target} is not blocked")
    if action == "extend":
        if lim["extended"]:
            raise Reject("REFUSED", f"{target} was already extended once; decide {target} stop")
        dec = _decision(state, p, at, rev)
        lim["extended"], lim["cap"] = True, lim["max"]
    elif action == "accept-current" and target != "calls":
        dec = _decision(state, p, at, rev)
    else:
        raise Reject("REFUSED", f"{action} is not a valid answer for {target}")
    state["run"]["blocked"] = [b for b in state["run"]["blocked"] if b["target"] != target]
    return {"decision": dec, "limit": target, "cap": lim["cap"]}


def _rescan(state, scans):
    """Store the scans the CLI made after a gate changed a doc (decision cells, INV status)."""
    for path, scan in (scans or {}).items():
        art = state["artifacts"].get(path)
        if art and scan:
            state["artifacts"][path] = {"owner_task": art["owner_task"], "role": art["role"], **scan}


def _decide_gate(state, p, at, rev):
    target, action = p["target"], p["action"]
    g = state["gates"][target]
    if action == "extend":
        if g["extended"]:
            raise Reject("REFUSED", f"{target} was already extended once")
        dec = _decision(state, p, at, rev)
        g["extended"], g["modify_cap"] = True, g["modify_cap"] + 1
        return {"decision": dec, "gate": target, "modify_cap": g["modify_cap"]}
    if target == "G3" and action in ("modify", "descope") and g["status"] == "approved" \
            and state["handoff"] and state["handoff"]["state"] == "failed":
        move_gate(state, "G3", "open", "handoff prepare failed")
        g["round"] += 1
        state["handoff"] = None
    if g["status"] != "open":
        raise Reject("INVALID_TRANSITION", f"{target} is {g['status']}, not open")
    if target == "G2" and state["gates"]["G1"]["status"] != "approved":
        raise Reject("REFUSED", "G2 is recorded only after G1 is approved")
    if p.get("from_doc") and not p.get("rows"):
        raise Reject("CHECK_FAILED", "the document has no decision column rows")
    raw = [tuple(r) for r in p.get("rows") or []]
    empty = [i for i, v in raw if not v.strip()]
    if empty:
        raise Reject("CHECK_FAILED", "empty decision for " + ", ".join(empty))
    rows = [(i, checks.normalize_value(target, v)) for i, v in raw]
    bad = [f"{i} ({v})" for (i, v), (_, n) in zip(raw, rows) if n is None]
    if bad:
        words = ", ".join(w for k, ws in checks.GATE_VALUES.get(target, {}).items() for w in (k,) + ws)
        raise Reject("CHECK_FAILED", f"unknown decision for {', '.join(bad)}; use one of: {words}")
    _rescan(state, p.get("doc_scans"))
    if action == "approve" and any(v in ("modify", "add") for _, v in rows):
        action = "modify"
    if action == "approve":
        dec = _decision(state, p, at, rev)
        if target == "G3":
            # Descope rows apply first, so the eligibility check sees the smaller scope.
            for i, v in rows:
                if v == "descope":
                    _descope(state, i, rev, dec)
            items = checks.h_items(state, p["lint"]) if "lint" in p else (p.get("checks") or [])
            if items:
                raise Reject("REFUSED", "handoff eligibility is false; G3 offers modify, descope or stop",
                             {"h_items": items})
            bad = [i for i, v in rows if v == "accept-risk" and i in state["findings"] and
                   state["findings"][i]["severity"] == "CRITICAL"]
            if bad:
                raise Reject("REFUSED", "non-waivable findings cannot be accepted as risk: " + ", ".join(bad))
        created = []
        if target == "G2":
            created = _freeze(state, rows, rev)
        if target == "Q1" and p.get("brief_scan"):
            state["run"]["brief_check"] = p["brief_check"]
            state["artifacts"][state["run"]["brief"]] = {"owner_task": "brief", "role": "user", **p["brief_scan"]}
            _register_ids(state, "user", rev)
        if target == "G3":
            for i, v in rows:
                if v == "accept-risk" and i in state["findings"]:
                    state["findings"][i]["status"] = "accepted_risk"
        move_gate(state, target, "approved", dec)
        g["approval_dec"], g["approval_rev"] = dec, rev
        g["decisions"].append(dec)
        return {"decision": dec, "gate": target, "status": "approved", "new_features": created}
    if action == "descope":
        # A descope restarts nothing: the handoff leaves the out-of-scope items out (8.3).
        if target != "G3" or not p.get("item"):
            raise Reject("REFUSED", "descope takes G3 and an --item")
        dec = _decision(state, p, at, rev)
        g["decisions"].append(dec)
        _descope(state, p["item"], rev, dec)
        return {"decision": dec, "gate": target, "status": g["status"], "descoped": [p["item"]]}
    if action == "modify":
        if target in ("Q1", "Q2"):
            raise Reject("REFUSED", f"{target} takes approve (answers or defaults) or stop")
        dec = _decision(state, p, at, rev)
        g["decisions"].append(dec)
        for i, v in rows:
            if v == "descope":
                _descope(state, i, rev, dec)
        items = [i for i, v in rows if v in ("modify", "add")] or ([p["item"]] if p.get("item") else [])
        if target in GATE_TASKS:
            revise = list(GATE_TASKS[target])
        else:
            if not items:
                raise Reject("REFUSED", f"{target} modify needs a target id")
            unknown = [i for i in items if i not in state["ids"] and i not in state["findings"]
                       and _target_task(state, i) is None]
            if unknown:
                raise Reject("CHECK_FAILED", "a değiştir row needs an ID or the task that wrote it "
                             "(for example `quality: <item>`): " + ", ".join(unknown))
            revise = sorted({t for t in (_target_task(state, i) for i in items) if t})
        result = {"decision": dec, **_gate_modify(state, target, revise, f"{action} {', '.join(items)}", dec)}
        if target == "G3":
            # A G3 change brings its own calls and the closing reserve; closing may run again.
            result["fix"] = _g3_fix(state, items)
            lim = state["limits"]["calls"]
            lim["cap"] = max(lim["cap"], state["budget"]["calls"]["total"] + G3_FIX_CALLS
                             + CLOSING_RESERVE.get(state["run"].get("size"), 2))
            lim["max"] = max(lim["max"], lim["cap"])
            state["run"]["closing"] = None
        return result
    raise Reject("REFUSED", f"{action} is not a valid answer for {target}")


def _target_task(state, item):
    """The task a G3 modify row sends back: the one defining the ID, or the task a named row starts with."""
    if item in state["ids"] or item in state["findings"]:
        return _defining_task(state, item)
    name = item.split(":")[0].strip()
    task = state["tasks"].get(name)
    return name if task and not task["is_group"] else None


def _descope(state, id_, rev, dec):
    rec = state["ids"].get(id_)
    if rec is None or rec["prefix"] not in ("F", "US", "BR"):
        raise Reject("REFUSED", f"descope takes an F, US or BR id, not {id_}")
    rec["decision"] = "descoped"
    for fid, f in state["findings"].items():
        refs = [r for r in registry.ID_RE.findall(f["claim"] + " " + f["evidence"])
                if registry.prefix_of(r) in ("F", "US", "BR")]
        if f["status"] in checks.UNRESOLVED and id_ in refs and all(checks.out_of_scope(state, r) for r in refs):
            f["status"] = "descoped"
            f["history"].append([rev, "descoped", dec])


# Handoff (8.3)

def _handoff_prepare(state, p, at, rev):
    g3 = state["gates"]["G3"]
    if g3["status"] != "approved":
        raise Reject("REFUSED", "handoff needs an approved G3")
    h = state["handoff"]
    if h and h["handoff_id"] == p["handoff_id"] and h["state"] == "failed":
        return {"handoff_id": h["handoff_id"], "state": "failed", "error": "CHECK_FAILED", "errors": h["errors"]}
    if h and h["handoff_id"] == p["handoff_id"] and h["state"] in ("prepared", "committed"):
        return {"handoff_id": h["handoff_id"], "state": h["state"], "files": h["files"]}
    errors = list(p.get("checks") or []) + [e for e in p.get("precheck") or [] if e not in (p.get("checks") or [])]
    if errors:
        # A failed prepare stops here; next asks the user instead of preparing again (8.3).
        state["handoff"] = {"schema_version": SCHEMA_VERSION, "handoff_id": p["handoff_id"], "state": "failed",
                            "approval_dec": g3["approval_dec"], "state_revision": g3["approval_rev"],
                            "files": p["files"], "errors": errors}
        return {"handoff_id": p["handoff_id"], "state": "failed", "error": "CHECK_FAILED", "errors": errors}
    state["handoff"] = {"schema_version": SCHEMA_VERSION, "handoff_id": p["handoff_id"], "state": "prepared",
                        "approval_dec": g3["approval_dec"], "state_revision": g3["approval_rev"],
                        "files": p["files"], "prepared_at": at}
    return {"handoff_id": p["handoff_id"], "state": "prepared", "files": p["files"]}


def _handoff_file(state, p):
    h = state["handoff"]
    if not h or h["handoff_id"] != p["handoff_id"] or h["state"] != "prepared":
        raise Reject("INVALID_TRANSITION", "no prepared handoff with this id")
    for f in h["files"]:
        if f["path"] == p["path"]:
            if p.get("conflict"):
                h["state"] = "conflict"
                f["status"] = "conflict"
                return {"path": p["path"], "status": "conflict", "error": "CHECK_FAILED"}
            f["status"] = "published"
            return {"path": p["path"], "status": "published"}
    raise Reject("REFUSED", f"{p['path']} is not in the manifest")


def _handoff_commit(state, p, at):
    h = state["handoff"]
    if not h or h["handoff_id"] != p["handoff_id"]:
        raise Reject("INVALID_TRANSITION", "no handoff with this id")
    if h["state"] == "committed":
        return {"handoff_id": h["handoff_id"], "state": "committed"}
    if h["state"] != "prepared" or any(f["status"] != "published" for f in h["files"]):
        raise Reject("INVALID_TRANSITION", "every file must be published before commit")
    h["state"], h["committed_at"] = "committed", at
    state["run"]["status"] = "handed_off"
    return {"handoff_id": h["handoff_id"], "state": "committed"}


# Scheduling: expand fix groups, open gates, derive the run status.

def _expand(state, name):
    """
    Give each owner of open findings one fix task. In step 5 the product-manager's findings go
    to the slices call instead, so it runs once.
    """
    task = state["tasks"][name]
    open_ = {i: f for i, f in state["findings"].items() if f["status"] == "open"}
    owners = sorted({f["owner"] for f in open_.values()})
    if name == "fix1" and "product-manager" in owners:
        owners.remove("product-manager")
        state["tasks"]["slices"]["findings"] = sorted(i for i, f in open_.items() if f["owner"] == "product-manager")
    for role in owners:
        child = f"{name}.{role}"
        t = _task(child, task["step"], role, "revise", (), _small_model(state, role))
        t["findings"] = sorted(i for i, f in open_.items() if f["owner"] == role)
        state["tasks"][child] = t
    task["expanded"] = True
    task["children"] = [f"{name}.{r}" for r in owners]


def p1_ids(state):
    """P1 features and the stories and rules that name them."""
    blocks = checks._blocks(state)
    feats = {i for i, bl in blocks.items() if registry.prefix_of(i) == "F" and any("p1" in b["flags"] for _, b in bl)}
    return feats | {i for i, bl in blocks.items() if registry.prefix_of(i) in ("US", "BR")
                    and any(feats & set(b["refs"]) for _, b in bl)}


def q2_items(state):
    """
    Items for short question 2: blocking OPEN items on P1 work from step 3 on, and the
    CRITICAL findings that fix1 left open or disputed, while step 6 has not started.
    """
    p1 = p1_ids(state)
    items = [{"id": o["id"], "text": o["question"], "default": o["default"]} for o in state["notes"]["opens"]
             if o["blocking"] and o.get("step", 0) >= 3
             and p1 & set(registry.ID_RE.findall(" ".join((o["id"], o["question"], o["default"]))))]
    if state["tasks"]["fix1"]["status"] == "done" \
            and not any(state["tasks"][t]["attempts"] for t in ("quality", "critic_review")):
        items += [{"id": i, "text": f["claim"], "default": ""} for i, f in sorted(state["findings"].items())
                  if f["severity"] == "CRITICAL" and f["status"] in ("open", "disputed")]
    return items


def _gate_ready(state, gate):
    if gate == "Q1":
        return True
    if gate in ("G1", "G2"):
        return all(state["tasks"][t]["status"] == "done" for t in ("strategy", "catalog"))
    if gate == "Q2":
        return False
    tasks = [t for t in state["tasks"].values() if t["status"] != "cancelled"]
    return all(t["status"] == "done" for t in tasks) and not state["run"]["blocked"]


def advance(state, at):
    if state["run"]["status"] == "stopped":
        return
    changed = True
    while changed:
        changed = _closing_step(state)
        for name, task in list(state["tasks"].items()):
            if not task["is_group"] or task["status"] != "pending":
                continue
            if not task["expanded"] and _deps_ok(state, task):
                _expand(state, name)
                changed = True
            if task["expanded"] and all(state["tasks"][c]["status"] == "done" for c in task["children"]):
                task["history"].append([state["state_revision"] + 1, "pending", "done", "group", ""])
                task["status"] = "done"
                changed = True
        if _flush_rechecks(state):
            changed = True
        q2 = state["gates"]["Q2"]
        if q2["status"] == "open":
            q2["items"] = q2_items(state) or q2["items"]
        elif q2["status"] == "closed" and state["gates"]["G2"]["status"] == "approved" \
                and state["gates"]["G3"]["status"] == "closed" and not state["run"].get("closing"):
            items = q2_items(state)
            if items:
                move_gate(state, "Q2", "open", "blocking P1 question or CRITICAL finding")
                q2["items"], q2["opened_at"] = items, at
                changed = True
        for gate in GATES:
            g = state["gates"][gate]
            if g["status"] in ("closed", "modify_requested") and _gate_ready(state, gate):
                if gate == "Q1" and g["status"] == "closed" and state["run"]["brief_check"] \
                        and state["run"]["brief_check"]["ok"]:
                    move_gate(state, gate, "open", "brief check passed")
                    move_gate(state, gate, "approved", "brief check passed, no question")
                else:
                    move_gate(state, gate, "open", "stage exit passed")
                    g["opened_at"] = at
                changed = True
    run = state["run"]
    if run["status"] in ("stopped", "handed_off"):
        return
    statuses = [t["status"] for t in state["tasks"].values()]
    if run["blocked"] or "blocked" in statuses:
        run["status"] = "blocked"
    elif any(g["status"] == "open" for g in state["gates"].values()) and "running" not in statuses \
            and not runnable(state):
        run["status"] = "waiting_user"
    else:
        run["status"] = "active"


def ordered(state):
    """Task names in flow order (step, then name); the snapshot sorts dict keys."""
    return sorted(state["tasks"], key=lambda n: (state["tasks"][n]["step"], n))


def runnable(state):
    out = []
    for name in ordered(state):
        t = state["tasks"][name]
        if t["is_group"]:
            continue
        cur = _current(t)
        if t["status"] == "pending" and _deps_ok(state, t):
            out.append(name)
        elif t["status"] == "running" and cur and cur["status"] != "running":
            out.append(name)
    return out


# apply

def init_event(state, p, at):
    if state is not None:
        raise Reject("REFUSED", "the run already exists")
    state = new_state(p["plan_id"], p.get("size", "tam"))
    state["run"].update(brief=p["brief"], brief_check=p["brief_check"], created_at=at)
    if state["run"]["size"] == SMALL:
        for name in SMALL_SKIP:
            move_task(state, name, "done", "T10", "skipped in small mode")
            state["tasks"][name]["skipped"] = True
    if p.get("brief_scan"):
        state["artifacts"][p["brief"]] = {"owner_task": "brief", "role": "user", **p["brief_scan"]}
        _register_ids(state, "user", 1)
    return state, {"plan_id": p["plan_id"], "brief_check": p["brief_check"], "size": state["run"]["size"]}


def apply(state, event):
    """Apply one journal event. Returns (new_state, result) or raises Reject."""
    etype, p, at = event["type"], event["payload"], _now(event)
    if event.get("schema_version", 1) > SCHEMA_VERSION:
        raise Reject("SCHEMA_TOO_NEW", f"event schema {event['schema_version']} is newer than {SCHEMA_VERSION}")
    if etype == "init":
        state, result = init_event(state, p, at)
    else:
        if state is None:
            raise Reject("REFUSED", "no run; call init first")
        state = copy.deepcopy(state)
        if etype == "rejected":
            state["applied_seq"] = event["seq"]
            return state, None
        rev = state["state_revision"] + 1
        if etype == "start":
            result = _start(state, p, at)
        elif etype == "record":
            result = _record(state, p, at, rev)
        elif etype == "timeout":
            result = _timeout(state, p, at)
        elif etype == "alloc":
            result = _alloc(state, p, rev)
        elif etype == "decide":
            result = _decide(state, p, at, rev)
        elif etype == "handoff_prepare":
            result = _handoff_prepare(state, p, at, rev)
        elif etype == "handoff_file":
            result = _handoff_file(state, p)
        elif etype == "handoff_commit":
            result = _handoff_commit(state, p, at)
        else:
            raise Reject("REFUSED", f"unknown event type {etype}")
    state["state_revision"] += 1
    state["applied_seq"] = event["seq"]
    advance(state, at)
    # An error result is not cached, so the same op can succeed later (after an extend).
    if event.get("op_id") and not (isinstance(result, dict) and result.get("error")):
        state["ops"][event["op_id"]] = {"hash": event.get("args_hash"), "result": copy.deepcopy(result)}
    return state, result


def replay(events):
    state = None
    for ev in events:
        if ev["type"] == "rejected":
            if state is not None:
                state = copy.deepcopy(state)
                state["applied_seq"] = ev["seq"]
            continue
        state, _ = apply(state, ev)
    return state


# Read-only views

def doc_kind(path, art):
    """brief, strategy, inv, catalog, dom or system for the docs later calls read whole."""
    task = art["owner_task"]
    if task in ("brief", "catalog"):
        return task
    if task == "strategy":
        return "strategy" if "/02-decisions/" in path else "inv"
    if task == "design":
        return "dom" if "/03-domains/" in path else "system"
    return None


def whole_reads(state, name):
    """Whole earlier docs a first call of this task reads, by doc kind."""
    task = state["tasks"][name]
    if task["mode"] in ("revise", "recheck"):
        return []
    kinds = WHOLE_READS.get(name.split(".")[0], ())
    return sorted(p for p, a in state["artifacts"].items() if doc_kind(p, a) in kinds)


def read_list(state, name):
    """ID blocks (path, start, end, id) the role of this task needs, outside its whole reads."""
    task = state["tasks"][name]
    base = name.split(".")[0]
    wanted_ids = set(task["stale_ids"])
    for fid in assigned_findings(state, name):
        f = state["findings"][fid]
        wanted_ids |= {fid} | set(registry.ID_RE.findall(f["claim"] + " " + f["evidence"]))
    prefixes = READS.get(base, ())
    if "F" in prefixes:
        # A feature promoted at G2 has no block; its M, G or R row is the text to read.
        wanted_ids |= {rec["origin"] for rec in state["ids"].values() if rec["prefix"] == "F" and rec.get("origin")}
    whole = set(whole_reads(state, name))
    out = []
    for path, art in sorted(state["artifacts"].items()):
        if path in whole:
            continue
        for id_, b in art["blocks"].items():
            if registry.prefix_of(id_) in prefixes or id_ in wanted_ids:
                out.append((path, b["start"], b["end"], id_))
    return sorted(out)


def assigned_findings(state, name):
    return state["tasks"][name]["findings"]


def next_lines(state):
    """Return (kind, fields) tuples: RUN, ASK, WAIT or DONE."""
    if state["run"]["status"] in ("stopped", "handed_off"):
        return [("DONE", [state["run"]["status"]])]
    lines = []
    for name in ordered(state):
        t = state["tasks"][name]
        cur = _current(t)
        if t["status"] == "running" and cur and cur["status"] == "running":
            lines.append(("WAIT", [cur["id"]]))
    blocked_calls = any(b["target"] == "calls" for b in state["run"]["blocked"])
    if not blocked_calls:
        # Only as many normal calls as the budget leaves outside the closing reserve.
        left = normal_left(state) if state["run"].get("closing") is None else None
        for name in runnable(state):
            t = state["tasks"][name]
            if left is not None and name != "closing":
                if left <= 0:
                    continue
                left -= 1
            lines.append(("RUN", [name, t["role"], t["mode"], t["model"]]))
    for b in state["run"]["blocked"]:
        lines.append(("ASK", [b["target"]]))
    for name in ordered(state):
        if state["tasks"][name]["status"] == "blocked":
            lines.append(("ASK", [name]))
    for g in GATES:
        # Sitting A shows both gates; G2 is recorded only after G1 is approved.
        if state["gates"][g]["status"] == "open" and not (g == "G2" and state["gates"]["G1"]["status"] != "approved"):
            lines.append(("ASK", [g]))
    g3 = state["gates"]["G3"]
    h = state["handoff"]
    if g3["status"] == "approved" and not lines:
        if h and h["state"] == "failed":
            lines.append(("ASK", ["handoff"]))
        elif not h or h["state"] == "conflict":
            lines.append(("RUN", ["handoff", "lead", "prepare", "-"]))
        elif h["state"] == "prepared":
            lines.append(("RUN", ["handoff", "lead", "publish", "-"]))
    return lines or [("WAIT", ["none"])]


def warnings(state):
    out = []
    lim, calls = state["limits"]["calls"], state["budget"]["calls"]["total"]
    if calls >= lim["warn"]:
        out.append(f"budget: {calls} of {lim['cap']} role calls used")
    if state["budget"]["cost_estimated"] == "unknown":
        out.append("tokens unknown: cost is not estimated")
    if not state["critic_model_differs"]:
        out.append("plan-critic review did not run on opus")
    return out
