"""
Validators: the agent output parser, brief-check, gate values, traceability and H checks.

Everything here is pure. File reading happens in cli.py; these functions get text or
state dicts and return results.
"""
import re

from . import registry

# The journal, run.json and the manifest carry this number; a reader stops on a newer one (10.3).
SCHEMA_VERSION = 1


TASK_STATUSES = ("pending", "running", "done", "blocked", "stale", "cancelled")
GATE_STATUSES = ("closed", "open", "approved", "modify_requested", "stopped")
RUN_STATUSES = ("active", "waiting_user", "blocked", "stopped", "handed_off")
# "fixed" is shown as çözüm önerildi: the owner wrote a solution, the dev team verifies it (15.11).
FINDING_STATUSES = ("open", "fixed", "disputed", "accepted_risk", "descoped")


# Agent output parser (section 9)

def _parts(rest, maxsplit):
    return [p.strip() for p in rest.split("|", maxsplit)]


def _parse_line(kind, rest):
    """Return a parsed line dict, or raise ValueError with the reason."""
    if kind in ("ASSUMPTION", "WROTE"):
        if not rest.strip():
            raise ValueError("empty field")
        return {"text": rest.strip()} if kind == "ASSUMPTION" else {"path": rest.strip()}
    if kind == "QUESTION":
        p = [x.strip() for x in rest.split("|")]
        if len(p) < 7:
            raise ValueError("QUESTION needs id, question, options, REC, WHY and AFFECTS")
        return {"id": p[0], "question": p[1], "fields": p[2:]}
    if kind == "OPEN":
        p = _parts(rest, 4)
        if len(p) == 5 and not p[4].startswith("kind:"):
            p = p[:3] + [p[3] + " | " + p[4]]
        if len(p) < 4 or not p[2].startswith("blocking:") or not p[3].startswith("default:"):
            raise ValueError("OPEN needs id | question | blocking: | default:")
        blocking = p[2].split(":", 1)[1].strip()
        if blocking not in ("yes", "no"):
            raise ValueError("blocking must be yes or no")
        kind_ = p[4].split(":", 1)[1].strip() if len(p) == 5 else None
        return {"id": p[0], "question": p[1], "blocking": blocking == "yes",
                "default": p[3].split(":", 1)[1].strip(), "kind": kind_}
    if kind == "FINDING":
        p = _parts(rest, 5)
        if len(p) == 6 and not p[5].startswith("class:"):
            p = p[:4] + [p[4] + " | " + p[5]]
        if len(p) < 5:
            raise ValueError("FINDING needs id | severity | owner | claim | evidence")
        if p[1] not in ("CRITICAL", "MAJOR", "MINOR"):
            raise ValueError(f"bad severity {p[1]!r}")
        cls = p[5].split(":", 1)[1].strip() if len(p) == 6 else None
        if cls is not None and not re.fullmatch(r"H[1-6]", cls):
            raise ValueError(f"bad class {cls!r}")
        return {"id": p[0], "severity": p[1], "owner": p[2], "claim": p[3], "evidence": p[4], "cls": cls}
    if kind == "FIX":
        p = _parts(rest, 3)
        if len(p) >= 3 and p[2].startswith("impact:"):
            impact = p[2].split(":", 1)[1].strip()
            if impact not in ("local", "contract"):
                raise ValueError(f"bad impact {impact!r}")
            if len(p) < 4:
                raise ValueError("FIX needs a change description")
            return {"id": p[0], "path": p[1], "impact": impact, "change": p[3]}
        p = _parts(rest, 2)
        if len(p) < 3:
            raise ValueError("FIX needs id | path | impact: | change")
        return {"id": p[0], "path": p[1], "impact": None, "change": p[2]}
    if kind == "DISPUTE":
        p = _parts(rest, 1)
        if len(p) < 2:
            raise ValueError("DISPUTE needs id | evidence")
        return {"id": p[0], "evidence": p[1]}
    if kind == "RECHECK":
        p = _parts(rest, 2)
        if len(p) < 3 or p[1] not in ("local", "contract"):
            raise ValueError("RECHECK needs task | local or contract | reason")
        return {"task": p[0], "impact": p[1], "reason": p[2]}
    if kind == "CONFLICT":
        p = _parts(rest, 3)
        if len(p) < 4:
            raise ValueError("CONFLICT needs id | role | path | text")
        return {"id": p[0], "role": p[1], "path": p[2], "text": p[3]}
    raise ValueError("unknown line type")


LINE_TYPES = ("QUESTION", "ASSUMPTION", "WROTE", "OPEN", "FINDING", "FIX", "DISPUTE",
              "RECHECK", "CONFLICT")


def parse_output(text):
    """Parse a role output into {attempt_id, lines, warnings}."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    out = {"attempt_id": None, "lines": [], "warnings": []}
    if lines and lines[0].startswith("ATTEMPT "):
        out["attempt_id"] = lines[0].split(None, 1)[1].strip()
        lines = lines[1:]
    for n, line in enumerate(lines, 1):
        if line.strip() in ("NO QUESTIONS", "NO FINDINGS"):
            out["lines"].append({"type": line.strip().replace(" ", "_")})
            continue
        kind, _, rest = line.strip().partition(" ")
        if kind not in LINE_TYPES:
            out["warnings"].append(f"line {n}: unrecognised: {line[:80]}")
            continue
        try:
            item = _parse_line(kind, rest)
        except ValueError as e:
            out["warnings"].append(f"line {n}: {kind}: {e}")
            continue
        item["type"] = kind
        out["lines"].append(item)
    return out


# brief-check (5.4)

REQUIRED_SECTIONS = {1: "Ürün özeti", 2: "Kapsam dışı", 3: "Stack", 4: "Dağıtım ve ölçek", 5: "Özellikler"}
NUMERIC_LABELS = ("kiracı", "kullanıcı", "eşzamanlı", "veri hacmi", "büyüme")
SECTION_RE = re.compile(r"^##\s+(\d+)\.?\s*(.*)$")
FEATURE_RE = re.compile(r"^###\s+(F-\d+)\b")


def _meaningful(lines):
    return [l for l in lines if l.strip() and not l.strip().startswith("<!--")
            and not re.fullmatch(r"\s*[-*]?\s*[^:]+:\s*", l)]


def brief_check(text):
    """Return {ok, missing, questions, features}; missing and questions go to Q1."""
    sections, current = {}, None
    for line in registry.strip_comments(text).splitlines():
        m = SECTION_RE.match(line)
        if m:
            current = int(m.group(1))
            sections[current] = []
        elif line.startswith("## "):
            current = None
        elif current is not None:
            sections[current].append(line)
    missing, questions = [], []
    for n, name in REQUIRED_SECTIONS.items():
        if n not in sections or not _meaningful(sections[n]):
            missing.append(f"section {n} ({name}) is missing or empty")
    features, seen = [], set()
    for line in sections.get(5, []):
        m = FEATURE_RE.match(line)
        if m:
            if m.group(1) in seen:
                missing.append(f"duplicate feature id {m.group(1)}")
            seen.add(m.group(1))
            features.append(m.group(1))
    if 5 in sections and not any(re.search(r"(Öncelik|Priority)\s*:\s*P1\b", l) for l in sections[5]):
        missing.append("no P1 feature")
    for line in sections.get(4, []):
        m = re.match(r"^\s*[-*]\s*([^:]+):\s*(.*)$", line)
        if not m or not any(k in m.group(1).lower() for k in NUMERIC_LABELS):
            continue
        value = m.group(2).strip()
        if value.lower().startswith("bilmiyorum"):
            questions.append(f"section 4: {m.group(1).strip()} is unknown")
        elif not re.match(r"^[~≈<>]?\s*\d", value):
            missing.append(f"section 4: {m.group(1).strip()} must be a number or 'bilmiyorum'")
    return {"ok": not missing and not questions, "missing": missing, "questions": questions,
            "features": features}


PLAN_SIZE_RE = re.compile(r"^\s*[-*]\s*Plan boyutu\s*:\s*(\S+)", re.I | re.M)


def plan_size(text):
    """The brief's plan size: küçük for a single-user or small internal tool, tam (the default) otherwise."""
    m = PLAN_SIZE_RE.search(registry.strip_comments(text))
    return "küçük" if m and m.group(1).lower() in ("küçük", "kucuk") else "tam"


# Decision columns read by the gate command from a document

def decision_rows(text, named=False):
    """
    Return [(id, value)] from every table that has a 'karar' or 'decision' column.

    With named, a row whose first cell is not an ID (an ASSUMPTION or risk row of the
    final package) comes back with that cell as its name.
    """
    rows, col = [], None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            col = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        lowered = [c.lower() for c in cells]
        if col is None:
            for name in ("karar", "decision"):
                if name in lowered:
                    col = lowered.index(name)
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        m = registry.ID_RE.fullmatch(cells[0]) if cells else None
        if (m or (named and cells and cells[0])) and col < len(cells):
            rows.append((cells[0], cells[col].lower()))
    return rows


# Gate decision values: the fixed English words and the Turkish words the user sees.
GATE_VALUES = {
    "G2": {"accept": ("kabul",), "reject": ("ret", "reddet"), "modify": ("değiştir",),
           "defer": ("ertele",), "add": ("ekle",)},
    "G3": {"approve": ("onayla",), "accept-risk": ("risk kabul",), "modify": ("değiştir",),
           "descope": ("kapsamdan çıkar",)},
}


def normalize_value(gate, value):
    """Return the fixed value for a decision cell, or None when the gate does not accept it."""
    value = " ".join(value.lower().split())
    for fixed, words in GATE_VALUES.get(gate, {}).items():
        if value == fixed or value in words:
            return fixed
    return None


# Traceability (10.4) and H checks (7.8)

# A finding with no proposed solution: still open, or disputed by its owner (15.11).
UNRESOLVED = ("open", "disputed")
OUT_OF_SCOPE = ("rejected", "deferred", "descoped")


def _blocks(state):
    """Map id -> list of (path, block) over every artifact."""
    found = {}
    for path, art in state["artifacts"].items():
        for id_, b in art["blocks"].items():
            found.setdefault(id_, []).append((path, b))
    return found


def in_scope_features(state):
    return sorted((i for i, rec in state["ids"].items()
                   if registry.prefix_of(i) == "F" and rec["status"] == "active"
                   and rec.get("decision") not in OUT_OF_SCOPE), key=registry.number_of)


def out_of_scope(state, id_):
    """
    True when an F, US or BR is out of scope: its own decision, or for a US or BR every F it names.
    """
    rec = state["ids"].get(id_)
    if rec is None:
        return False
    if rec.get("decision") in OUT_OF_SCOPE:
        return True
    if rec["prefix"] in ("US", "BR"):
        feats = [r for _, b in _blocks(state).get(id_, []) for r in b["refs"] if registry.prefix_of(r) == "F"]
        return bool(feats) and all(out_of_scope(state, f) for f in feats)
    return False


def live_slices(state):
    """
    Delivery slices in order, without a slice whose every story is out of scope (a G3 descope).
    """
    blocks = _blocks(state)
    out = []
    for s in sorted((i for i in blocks if registry.prefix_of(i) == "S"), key=registry.number_of):
        stories = {r for _, b in blocks[s] for r in b["refs"] if registry.prefix_of(r) == "US"}
        if not stories or not all(out_of_scope(state, us) for us in stories):
            out.append(s)
    return out


def slice_errors(state):
    """
    Rules every delivery slice keeps; G3 eligibility and the handoff precheck share them.

    A slice lists a planned verification and at least one story with an acceptance criterion.
    """
    errors = []
    blocks = _blocks(state)
    slices = live_slices(state)
    if not slices:
        errors.append("H6 no delivery slice")
    for s in slices:
        bl = blocks[s]
        if not any("verification" in b["flags"] for _, b in bl):
            errors.append(f"H6 {s}: no planned verification")
        stories = [r for _, b in bl for r in b["refs"] if registry.prefix_of(r) == "US"]
        if not any("criterion" in b["flags"] for us in stories for _, b in blocks.get(us, [])):
            errors.append(f"H6 {s}: no acceptance criterion")
    return errors


def traceability(state):
    """Design traceability errors: F, US, criteria or BR, D or justified none, slice, verification."""
    errors = []
    blocks = _blocks(state)

    def referencing(prefix, targets):
        targets = set(targets)
        return sorted(i for i, bl in blocks.items() if registry.prefix_of(i) == prefix
                      and any(targets & set(b["refs"]) for _, b in bl))

    for f in in_scope_features(state):
        names = [f] + ([state["ids"][f]["origin"]] if state["ids"][f].get("origin") else [])
        stories = referencing("US", names)
        if not stories:
            errors.append(f"H6 {f}: no user story references it")
        for us in stories:
            flags = {x for _, b in blocks[us] for x in b["flags"]}
            if "criterion" not in flags and not any(registry.prefix_of(r) == "BR"
                                                    for _, b in blocks[us] for r in b["refs"]):
                errors.append(f"H6 {us}: no acceptance criterion or BR")
            if not referencing("S", [us]):
                errors.append(f"H6 {us}: in no slice")
        f_flags = {x for _, b in blocks.get(f, []) for x in b["flags"]}
        if not referencing("D", names) and "d_none" not in f_flags:
            errors.append(f"H6 {f}: no diagram and no 'D: none' reason")
    if in_scope_features(state):
        errors.extend(slice_errors(state))
    for i, bl in sorted(blocks.items()):
        if registry.prefix_of(i) in ("SEC", "PERF") and not referencing("S", [i]) \
                and not any("deferred" in b["flags"] for _, b in bl):
            errors.append(f"H6 {i}: in no slice and not deferred: perf-team")
    return errors


def traceability_rate(state):
    """
    Traced in-scope features: no H6 error names the feature or one of its stories.

    Returns (traced, total).
    """
    blocks = _blocks(state)
    bad = {i for e in traceability(state) for i in registry.ID_RE.findall(e.split(":")[0])}
    features = in_scope_features(state)
    traced = 0
    for f in features:
        names = {f, state["ids"][f].get("origin")} - {None}
        stories = {i for i, bl in blocks.items() if registry.prefix_of(i) == "US"
                   and any(names & set(b["refs"]) for _, b in bl)}
        traced += not ({f} | stories) & bad
    return traced, len(features)


def id_errors(state):
    """References to retired or unknown IDs and duplicate slice ownership of stories."""
    errors = []
    ids = state["ids"]
    for path, art in sorted(state["artifacts"].items()):
        for ref in art["refs"]:
            p = registry.prefix_of(ref)
            if p in ("S", "DEC"):
                continue
            rec = ids.get(ref)
            if rec is None:
                errors.append(f"H4 {path}: references unknown id {ref}")
            elif rec["status"] == "retired":
                errors.append(f"H4 {path}: references retired id {ref}")
        for dup in art.get("duplicates", []):
            errors.append(f"H4 {path}: {dup} is defined twice")
    owners = {}
    for i, bl in _blocks(state).items():
        if registry.prefix_of(i) == "S":
            for _, b in bl:
                for r in b["refs"]:
                    if registry.prefix_of(r) == "US":
                        owners.setdefault(r, set()).add(i)
    for us, sl in sorted(owners.items()):
        if len(sl) > 1:
            errors.append(f"H4 {us}: in more than one slice ({', '.join(sorted(sl))})")
    return errors


def h_items(state, external=()):
    """
    Return the open non-waivable items as 'Hn reason' strings.

    external holds failures computed outside the state (docs lint), which count as H4.
    """
    items = []
    for fid, f in sorted(state["findings"].items()):
        # Only a CRITICAL finding with no proposed solution blocks; its class names the H code next to H1.
        if f["status"] not in UNRESOLVED or f["severity"] != "CRITICAL":
            continue
        items.append(f"H1 {fid}: unresolved CRITICAL finding")
        if f.get("cls") and f["cls"] != "H1":
            items.append(f"{f['cls']} {fid}: {f['claim'][:80]}")
    items.extend(id_errors(state))
    items.extend(f"H4 lint: {e}" for e in external)
    items.extend(traceability(state))
    return items
