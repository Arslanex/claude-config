"""
Artifact registry: ID blocks, contract surface, write maps, scopes and impact analysis.

Every function here is pure. The registry owns no state: it reads and returns plain
dicts that the engine stores in the journal-derived state.
"""
import fnmatch
import hashlib
import re

# ID prefixes the plan tracks. S marks a delivery slice (S0, S1, ...). E is an entity (domain doc)
# and API an endpoint or event (system ADR), so a change to either is a contract change.
ID_PREFIXES = ("F", "M", "G", "R", "US", "BR", "INV", "D", "E", "API", "SEC", "PERF", "QA", "DA", "DEC")
ID_RE = re.compile(r"(?<![A-Za-z0-9_-])((?:%s)-\d+|S\d+)(?![A-Za-z0-9_])" % "|".join(ID_PREFIXES))
HEADING_RE = re.compile(r"^(#{1,6})\s+(\S+)")
LIST_RE = re.compile(r"^ ?[-*]\s+(\S+)")
ROW_RE = re.compile(r"^\|\s*([^|\s]+)\s*\|")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ROW_LEVEL = 7
# Markers the traceability checks need, so the state never has to keep block text.
FLAGS = {
    "verification": re.compile(r"(?i)\b(doğrulama|verification)\s*:\s*\S"),
    "d_none": re.compile(r"\bD:\s*none\s*\S"),
    "deferred": re.compile(r"deferred:\s*perf-team"),
    "criterion": re.compile(r"^\s{2,}[-*]\s+\S"),
    "p1": re.compile(r"\bP1\b"),
}
# The decision column of a table: the user fills it at a gate, so it is not part of any hash.
DECISION_COLUMNS = ("karar", "decision")

# Roles: model, the ID prefixes they may define, and the docs they may write.
ROLES = {
    "user": {"model": "-", "prefixes": ("F",), "writes": ()},
    "strategy-architect": {"model": "sonnet", "prefixes": ("INV",),
                           "writes": ("docs/02-decisions/ADR-*", "docs/01-architecture/modules/ARCH-*")},
    "product-manager": {"model": "sonnet", "prefixes": ("M", "G", "R", "US", "BR", "S"),
                        "writes": ("docs/05-work/plans/PLAN-*",)},
    "solution-architect": {"model": "opus", "prefixes": ("D", "E", "API"),
                           "writes": ("docs/03-domains/*DOM-*", "docs/02-decisions/ADR-*")},
    "ux-designer": {"model": "sonnet", "prefixes": ("D",),
                    "writes": ("docs/05-work/plans/PLAN-*",)},
    "security-architect": {"model": "opus", "prefixes": ("SEC",),
                           "writes": ("docs/01-architecture/security/ARCH-*",)},
    "performance-architect": {"model": "sonnet", "prefixes": ("PERF",),
                              "writes": ("docs/01-architecture/performance/ARCH-*",)},
    "quality-engineer": {"model": "haiku", "prefixes": ("QA",),
                         "writes": ("docs/05-work/plans/quality/PLAN-*",)},
    "plan-critic": {"model": "opus", "prefixes": ("DA",), "writes": ()},
}
# Prefixes handed out only through alloc (D) or by plan_state itself (F at freeze, DEC).
ALLOC_PREFIXES = ("D",)
FINDING_PREFIX = {"security-architect": "SEC", "performance-architect": "PERF",
                  "quality-engineer": "QA", "plan-critic": "DA"}

# Files plan_state writes itself under docs/; they are never part of a write scope.
STATE_PATTERNS = ("docs/05-work/plans/*.journal.jsonl", "docs/05-work/plans/*.run.json",
                  "docs/05-work/plans/*.lock", "docs/05-work/plans/*.index.md",
                  "docs/05-work/plans/*.tmp")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prefix_of(id_):
    return "S" if re.fullmatch(r"S\d+", id_) else id_.split("-")[0]


def number_of(id_):
    return int(re.findall(r"\d+", id_)[-1])


def format_id(prefix, n):
    return f"{prefix}-{n:02d}"


def is_state_file(rel):
    return any(fnmatch.fnmatch(rel, p) for p in STATE_PATTERNS)


def _norm(line):
    return " ".join(line.split())


def _definition(line):
    """Return (id, level) when the line defines an ID, else None."""
    m = HEADING_RE.match(line)
    if m:
        token, level = m.group(2), len(m.group(1))
    else:
        m = LIST_RE.match(line) or ROW_RE.match(line)
        if not m:
            return None
        token, level = m.group(1), ROW_LEVEL
    m = ID_RE.fullmatch(token.rstrip(":.,"))
    return (m.group(1), level) if m else None


def strip_comments(text):
    """Blank out HTML comments and keep the line count, so line numbers stay true."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def _body_lines(text):
    """Yield (lineno, line) after the front matter."""
    lines = strip_comments(text).splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is not None:
            start = end + 1
    for i in range(start, len(lines)):
        yield i + 1, lines[i]


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def scan_doc(text):
    """
    Split a document into ID blocks.

    A block starts at a line that defines an ID (a heading, a top-level list item or a
    table row whose first token is the ID) and ends before the next definition line or
    before a heading of the same or a higher level. Text outside blocks forms the
    outside hash, which marks a change as ambiguous when it moves. The outside text is
    also hashed per heading (the last heading outside a block), and every block keeps
    that heading, so an ambiguous change targets only the blocks of its own section.
    The cells of a decision column (karar) are left out of every hash.
    """
    blocks, outside, current, in_fence = {}, [], None, False
    duplicates, decision_col, section, sections = [], None, "", {}
    for lineno, line in _body_lines(text):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        d = None if in_fence else _definition(line)
        h = None if in_fence else HEADING_RE.match(line)
        if d or (h and current and len(h.group(1)) <= current["level"]):
            current = None
        if d:
            id_, level = d
            if id_ in blocks:
                duplicates.append(id_)
                id_ = None
            if id_:
                current = {"id": id_, "level": level, "start": lineno, "end": lineno, "lines": [],
                           "heading": section}
                blocks[id_] = current
        elif h and current is None:
            section = _norm(line)
        hashed = line
        if line.strip().startswith("|") and not in_fence:
            cells = _cells(line)
            lowered = [c.lower() for c in cells]
            if decision_col is None and any(c in DECISION_COLUMNS for c in lowered):
                decision_col = next(i for i, c in enumerate(lowered) if c in DECISION_COLUMNS)
            elif decision_col is not None and decision_col < len(cells):
                hashed = "| " + " | ".join(c for i, c in enumerate(cells) if i != decision_col) + " |"
        else:
            decision_col = None
        if current is not None:
            current["end"] = lineno
            if line.strip():
                current["lines"].append(_norm(hashed))
                current.setdefault("raw", []).append(line)
        elif line.strip():
            outside.append(_norm(hashed))
            sections.setdefault(section, []).append(_norm(hashed))
    result = {}
    for id_, b in blocks.items():
        refs = sorted({m for line in b["lines"] for m in ID_RE.findall(line)} - {id_})
        raw = b.get("raw", [])
        flags = sorted(k for k, rx in FLAGS.items() if any(rx.search(x) for x in raw))
        result[id_] = {"start": b["start"], "end": b["end"], "hash": sha("\n".join(b["lines"])),
                       "lines": [sha(x)[:12] for x in b["lines"]], "refs": refs, "flags": flags,
                       "heading": b["heading"]}
    doc_refs = sorted({r for b in result.values() for r in b["refs"]}
                      | {m for line in outside for m in ID_RE.findall(line)})
    return {"hash": sha(text), "outside": sha("\n".join(outside)), "blocks": result,
            "refs": doc_refs, "duplicates": sorted(set(duplicates)),
            "sections": {k: sha("\n".join(v)) for k, v in sections.items()}}


# Write maps and scopes

def in_write_map(role, rel):
    return any(fnmatch.fnmatch(rel, p) for p in ROLES.get(role, {}).get("writes", ()))


def maps_overlap(role_a, role_b):
    """True when one role's write pattern can match a path of the other."""
    for a in ROLES[role_a]["writes"]:
        for b in ROLES[role_b]["writes"]:
            if fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
                return True
    return False


def validate_parallel_maps(groups):
    """Return error strings for parallel groups whose write maps are not disjoint."""
    errors = []
    for group in groups:
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if maps_overlap(a, b):
                    errors.append(f"write maps of {a} and {b} overlap")
    return errors


def scope_conflicts(scope, reserved):
    """Paths of scope already reserved by another running task: {path: task}."""
    return {p: owner for p in scope for owner, paths in reserved.items() if p in paths}


def changed_paths(before, after):
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


# Impact analysis (7.7)

RANK = {"local": 0, "ambiguous": 1, "contract": 2}


def compare(old, new, restated=()):
    """
    Compare two scans of one document.

    Returns added, removed and changed IDs, the IDs whose change only added lines,
    whether text outside every block changed (more than whitespace) and the blocks of
    the sections whose outside text changed. On a first scan an ID in restated (already
    active in another doc) is not counted as added.
    """
    old_b = old["blocks"] if old else {}
    new_b = new["blocks"] if new else {}
    added = sorted(set(new_b) - set(old_b) - (set(restated) if not old else set()))
    removed = sorted(set(old_b) - set(new_b))
    changed = sorted(i for i in set(old_b) & set(new_b) if old_b[i]["hash"] != new_b[i]["hash"])
    additive = sorted(i for i in changed if set(old_b[i]["lines"]) <= set(new_b[i]["lines"]))
    outside = bool(old) and bool(new) and old["outside"] != new["outside"]
    sections = []
    if outside and "sections" in old and "sections" in new:
        moved = {k for k in set(old["sections"]) | set(new["sections"])
                 if old["sections"].get(k) != new["sections"].get(k)}
        sections = sorted({i for b in (old_b, new_b) for i, x in b.items() if x.get("heading") in moved})
    elif outside:
        # A scan from before the per-heading hashes: every block of the doc.
        sections = sorted(set(old_b) | set(new_b))
    return {"added": added, "removed": removed, "changed": changed,
            "additive": additive, "outside": outside, "sections": sections}


def classify(diffs, declared):
    """
    Merge per-file diffs with the role's FIX declarations into one impact class.

    declared is a list of 'local', 'contract' or None (a FIX line without impact).
    The more impactful class wins.
    """
    cls = "local"
    for d in diffs.values():
        if d["added"] or d["removed"] or d["changed"]:
            cls = "contract"
        elif d["outside"] and RANK[cls] < RANK["ambiguous"]:
            cls = "ambiguous"
    for decl in declared:
        want = decl if decl in ("local", "contract") else "ambiguous"
        if RANK[want] > RANK[cls]:
            cls = want
    return cls


def dependents(artifacts, ids, exclude_paths=()):
    """Paths of artifacts outside exclude_paths whose text references any of ids."""
    ids = set(ids)
    return sorted(p for p, a in artifacts.items()
                  if p not in exclude_paths and ids & set(a.get("refs", [])))
