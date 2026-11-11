"""
Read the plan docs and the run state into the model that the review page shows.

IDs, their blocks and line ranges come from plan_state's registry.scan_doc. Owners, decisions, findings, gates,
budget, traceability and handoff eligibility come from the run state (<PLAN-id>.run.json) through plan_state.
This module adds only what plan_state does not keep: Mermaid blocks, card text (titles, bullets, stories with their
EARS lines, table cells) and the ERD entity grid. It writes no HTML. Python 3 stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from plan_state import checks, engine, registry

MERMAID = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
KEY_VALUE = re.compile(r"^\**([^:*|]{1,40}?)\**\s*:\s*(.*)$")
SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
# Any ID shape, so prefixes that plan_state adds later still link and group.
ANY_ID = re.compile(r"(?<![\w-])([A-Z]{1,5}-\d{1,4}|S\d{1,3})(?![\w-])")
HCODE = re.compile(r"\bH[1-6]\b")
FINDING_KINDS, CARD_KINDS = ("SEC", "PERF", "QA", "DA"), ("F", "M", "G", "R")
DEFAULT_CALL_LIMIT, DEFAULT_CALL_WARN = engine.LIMITS["calls"]["cap"], engine.LIMITS["calls"]["warn"]
DEFAULT_CONTACT_LIMIT = 4
STEPS = ["Girdi kontrolü", "Strateji ve yük modeli", "Özellik kataloğu", "Tasarım ve UX", "Güvenlik ve performans",
         "Düzeltme ve teslim dilimleri", "Kalite ve şeytanın avukatı", "Düzeltme turu ve karar", "Devir"]
# Status of a track node with several members: the first status in this list that any member has wins.
STATUS_ORDER = ("blocked", "stopped", "open", "running", "stale", "modify_requested", "pending")
CARD_FIELDS = ("title", "priority", "slice", "status", "origin", "owner", "karar")
FIELDS = {
    "title": "başlık baslik title ad adı isim name özellik feature öneri kural rule açıklama description özet summary "
             "hikaye story madde konu risk",
    "priority": "öncelik oncelik priority prio", "slice": "dilim slice", "status": "durum status state",
    "origin": "origin köken", "karar": "karar decision", "owner": "sahip owner", "id": "id kimlik kod code no",
    # Reference columns and lines: the block refs already carry these IDs.
    "skip": "d diyagram diyagramlar diagram diagrams f özellikler features refs references covers kapsar bağlar",
}
KEY_OF = {alias: key for key, aliases in FIELDS.items() for alias in aliases.split()}
# Tasks the small plan mode skips (engine.SMALL_SKIP), as the step track names them.
SKIPPED_LABEL = {"performance": "performans", "quality": "kalite planı"}
# Finding states: still open, fixed by its owner but not yet verified, and closed by a verdict.
OPEN_STATES, UNVERIFIED_STATES = ("open", "disputed"), ("fixed",)


# Reading

def clean(text) -> str:
    """Plain cell text: links become their label and bold marks go; backticks stay for code spans."""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", str(text or "")).replace("**", "").strip()


def norm(text) -> str:
    """Comparable key of a header, a field name or a status (`accepted risk` and accepted_risk match)."""
    return clean(text).replace("`", "").replace("İ", "i").lower().strip(" :*").replace(" ", "_")


def split_row(line: str) -> list[str]:
    """Cells of one Markdown table row; an escaped pipe stays in its cell."""
    line = line.strip().removeprefix("|")
    line = line[:-1] if line.endswith("|") and not line.endswith("\\|") else line
    return [cell.replace("\\|", "|").strip() for cell in re.split(r"(?<!\\)\|", line)]


def keys_of(headers: list[str]) -> list[str]:
    """Field per column; with two `karar` columns the last one holds the decision and the first one names it."""
    keys = [KEY_OF.get(norm(h), "") for h in headers]
    if keys.count("karar") > 1:
        last = len(keys) - 1 - keys[::-1].index("karar")
        keys = ["title" if k == "karar" and n != last else k for n, k in enumerate(keys)]
    return [k if k not in keys[:n] or k == "skip" else "" for n, k in enumerate(keys)]


def dig(data, *keys, default=None):
    """A nested run.json value, or the default when a level is missing or has another shape."""
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return default if data is None or (isinstance(default, dict) and not isinstance(data, dict)) else data


def num(value, default: float = 0) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def id_key(item_id: str):
    digits = re.findall(r"\d+", item_id)
    return registry.prefix_of(item_id), int(digits[-1]) if digits else 0


class Doc:
    """One Markdown doc: its lines, front matter, plan_state ID blocks and tables."""

    def __init__(self, path: Path, base: Path):
        self.path = path.resolve()
        try:
            self.rel = self.path.relative_to(base.resolve()).as_posix()
        except ValueError:
            self.rel = str(path)
        try:
            self.text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            self.text = ""
        self.lines = self.text.splitlines()
        front = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*$", self.text, re.MULTILINE | re.DOTALL)
        self.meta = {k.lower(): v.strip().strip("\"'") for k, v in
                     re.findall(r"^([A-Za-z][\w-]*):[ \t]*(.*)$", front.group(1) if front else "", re.MULTILINE)}
        self.fenced, inside = set(range(front.group(0).count("\n") + 1 if front else 0)), False
        for number, line in enumerate(self.lines):
            inside = inside != bool(FENCE.match(line))
            if inside or FENCE.match(line):
                self.fenced.add(number)
        self.blocks = registry.scan_doc(self.text)["blocks"]
        h1 = next((line[2:] for n, line in enumerate(self.lines) if line.startswith("# ") and n not in self.fenced), "")
        self.title = self.meta.get("title") or clean(h1) or path.stem
        self.tables, self.row_headers, table = [], {}, None
        for number, line in enumerate(self.lines):
            if number in self.fenced or not line.strip().startswith("|"):
                table = None
            elif table is None and number + 1 < len(self.lines) and SEPARATOR.match(self.lines[number + 1]):
                table = (number + 1, split_row(line), [])
                self.tables.append(table)
            elif table is not None and not SEPARATOR.match(line):
                table[2].append((number + 1, split_row(line)))
                self.row_headers[number + 1] = table[1]

    def heading_before(self, line: int) -> str:
        for number in range(line - 2, -1, -1):
            match = HEADING.match(self.lines[number]) if number not in self.fenced else None
            if match:
                return clean(match.group(1))
        return self.title


def read_block(doc: Doc, item_id: str, block: dict) -> dict:
    """Card text of one ID block: title, fields, detail lines and the sub bullets (EARS lines of a story)."""
    first = doc.lines[block["start"] - 1] if block["start"] <= len(doc.lines) else ""
    item = {"id": item_id, "where": f"{doc.rel}:{block['start']}-{block['end']}", "doc": doc, "line": block["start"],
            "refs": list(block["refs"]), "details": [], "sub": []}
    if first.strip().startswith("|"):
        headers = doc.row_headers.get(block["start"], [])
        keys, cells = keys_of(headers), [clean(c) for c in split_row(first)]
        if "title" not in keys:
            spare = next((n for n, c in enumerate(cells) if n and c and not ANY_ID.fullmatch(c)), None)
            keys = ["title" if n == spare else k for n, k in enumerate(keys + [""] * len(cells))]
        for n, cell in enumerate(cells):
            key = keys[n] if n < len(keys) else ""
            if key in CARD_FIELDS:
                item[key] = cell
            elif not key and n and cell and n < len(headers):
                item["details"].append((clean(headers[n]), [cell]))
        item["has_karar"] = "karar" in keys
    else:
        match = HEADING.match(first) or BULLET.match(first)
        text = clean(match.group(match.lastindex) if match else first)
        item["title"] = re.sub(rf"^[`*]*{re.escape(item_id)}[`*]*\s*[:.)\-]?\s*", "", text)
    current, base = None, None
    for number in range(block["start"], min(block["end"], len(doc.lines))):
        line = doc.lines[number]
        if number in doc.fenced or not line.strip() or line.strip().startswith("|") or HEADING.match(line):
            continue
        bullet = BULLET.match(line)
        body = clean(bullet.group(2) if bullet else line)
        if bullet:
            item["sub"].append(body)
            base = len(bullet.group(1)) if base is None else base
            if len(bullet.group(1)) > base and current is not None:
                current.append(body)
                continue
        pair = KEY_VALUE.match(body)
        key = KEY_OF.get(norm(pair.group(1)), "") if pair else ""
        if key in CARD_FIELDS[1:]:
            item[key], item["has_karar"] = clean(pair.group(2)), item.get("has_karar") or key == "karar"
        if key == "skip" or key in CARD_FIELDS[1:]:
            current = None
            continue
        current = ([clean(pair.group(2))] if pair.group(2) else []) if pair else [body]
        item["details"].append((clean(pair.group(1)) if pair else "", current))
    return item


def er_entities(code: str) -> tuple[dict, list]:
    """Entities with attributes, and relations, of an erDiagram."""
    entities, relations, current = {}, [], None
    for line in (raw.strip() for raw in code.splitlines()):
        attr = re.match(r'^([\w.,()-]+)\s+([\w-]+)\s*((?:PK|FK|UK)(?:\s*,\s*(?:PK|FK|UK))*)?\s*(?:"(.*)")?$', line)
        start = re.match(r"^([\w-]+)\s*(?:\[[^\]]*\])?\s*\{\s*$", line)
        relation = re.match(r'^([\w-]+)\s+([|}o{.\-]+)\s+([\w-]+)\s*:\s*"?([^"]*)"?\s*$', line)
        if current is not None:
            current = None if line.startswith("}") else current
            if current and attr:
                entities[current].append(attr.groups(""))
        elif start:
            current = start.group(1)
            entities.setdefault(current, [])
        elif relation:
            relations.append(relation.groups())
            entities.setdefault(relation.group(1), [])
            entities.setdefault(relation.group(3), [])
    return entities, relations


def merge(item: dict, other: dict) -> None:
    """Add a second block of the same ID: its refs and details, and the fields the first block left empty."""
    item["refs"] += [r for r in other["refs"] if r not in item["refs"]]
    item["details"] += other["details"]
    item.update({k: v for k, v in other.items() if v and not item.get(k)})


class Model:
    """Everything the page shows: docs, ID items, diagrams, findings, pending decisions and the run state."""

    def __init__(self, docs: list[Doc], state: dict, state_note: str = ""):
        self.docs, self.state, self.state_note = docs, state, state_note
        self.items, self.diagrams, self.pending, self.decision_tables = {}, [], [], []
        records = dig(state, "ids", default={})
        reads = {}
        for doc in docs:
            for item_id, block in doc.blocks.items():
                reads.setdefault(item_id, []).append(read_block(doc, item_id, block))
            self.read_decisions(doc)
        for item_id, found in reads.items():
            # The block in the doc plan_state names for the ID comes first; the others add what it lacks.
            home = dig(records, item_id, "doc")
            found.sort(key=lambda i: i["doc"].rel != home)
            for other in found[1:]:
                merge(found[0], other)
            self.items[item_id] = found[0]
        findings = dig(state, "findings", default={})
        for item_id, record in records.items():
            if registry.prefix_of(item_id) == "DEC" or not isinstance(record, dict) or item_id in findings:
                continue
            born = record.get("origin") and record.get("owner") == "plan_state"
            if born or (item_id not in self.items and record.get("status") == "active"):
                self.items[item_id] = self.born_item(item_id, record.get("origin"))
            item = self.items.get(item_id, {})
            for key, name in (("owner", "owner"), ("origin", "origin"), ("status", "decision")):
                item[key] = record.get(name) or item.get(key, "")
        self.findings = {}
        for item_id, f in findings.items():
            if not isinstance(f, dict):
                continue
            history = f.get("history") if isinstance(f.get("history"), list) else []
            self.findings[item_id] = {
                "id": item_id, "title": f.get("claim", ""), "severity": str(f.get("severity") or "").upper(),
                "hclass": " ".join(HCODE.findall(str(f.get("cls") or ""))), "owner": f.get("owner", ""),
                "state": f.get("status", "open"), "evidence": f.get("evidence") or "", "reply": f.get("reply") or "",
                "raised_by": f.get("raised_by") or "", "task": f.get("task") or "",
                "history": [h for h in history if isinstance(h, list) and len(h) >= 2]}
        for doc in docs:
            self.read_diagrams(doc)
        for diagram in self.diagrams:
            own = {r for r in self.items.get(diagram["id"], {}).get("refs", []) if r.startswith("F-")}
            diagram["features"] = sorted(own | {i for i in self.items if i.startswith("F-") and diagram["id"]
                                                and diagram["id"] in self.items[i]["refs"]}, key=id_key)

    def born_item(self, item_id: str, origin: str | None) -> dict:
        """
        A feature that plan_state created at G2 from an M, G or R row has no row of its own. Its title and fields
        come from that origin row; a line elsewhere that only starts with the ID mentions it and never defines it.
        Without an origin title the item says its title is missing instead of guessing one.
        """
        source = self.items.get(origin or "", {})
        item = {"id": item_id, "title": source.get("title", ""), "where": source.get("where", ""),
                "doc": source.get("doc"), "line": source.get("line"), "refs": list(source.get("refs", [])),
                "details": list(source.get("details", [])), "sub": []}
        item.update({k: source[k] for k in ("priority", "slice") if source.get(k)})
        item["missing_title"] = not item["title"]
        return item

    def read_decisions(self, doc: Doc) -> None:
        """Empty `karar` cells: ID rows through plan_state's gate parser, named rows from a decision table."""
        self.pending += [{"id": i, "where": doc.rel} for i, value in checks.decision_rows(doc.text) if not value]
        for start, headers, rows in doc.tables:
            keys = keys_of(headers)
            named = [(line, cells + [""] * len(keys)) for line, cells in rows
                     if "karar" in keys and not ANY_ID.fullmatch(clean(cells[0]).strip("`"))]
            if named:
                self.decision_tables.append({"doc": doc, "start": start, "headers": headers, "keys": keys,
                                             "rows": named, "heading": doc.heading_before(start)})
            self.pending += [{"id": "", "label": clean(cells[0]), "title": doc.heading_before(start),
                              "where": f"{doc.rel}:{line}", "anchor": f"karar-{Path(doc.rel).stem}-{line}"}
                             for line, cells in named if not clean(cells[keys.index("karar")])]

    def read_diagrams(self, doc: Doc) -> None:
        """A card per Mermaid block (with the D whose block holds it) and per D block without Mermaid."""
        for match in MERMAID.finditer(doc.text):
            line = doc.text.count("\n", 0, match.start()) + 1
            taken = {d["id"] for d in self.diagrams}
            diagram_id = next((i for i, b in doc.blocks.items() if i.startswith("D-") and i not in taken
                               and b["start"] <= line <= b["end"]), "")
            code = match.group(1).rstrip()
            body = [c.strip() for c in code.splitlines() if c.strip() and not c.strip().startswith("%%")]
            self.add_diagram(doc, diagram_id, line, code, body[0].split()[0] if body else "diagram")
        for diagram_id, block in doc.blocks.items():
            if diagram_id.startswith("D-") and diagram_id not in {d["id"] for d in self.diagrams}:
                self.add_diagram(doc, diagram_id, block["start"], "", "")

    def add_diagram(self, doc: Doc, diagram_id: str, line: int, code: str, kind: str) -> None:
        item = self.items.get(diagram_id, {})
        self.diagrams.append({"id": diagram_id, "anchor": diagram_id or f"diagram-{len(self.diagrams) + 1}",
                              "title": item.get("title") or doc.heading_before(line), "doc": doc, "kind": kind,
                              "line": line, "where": f"{doc.rel}:{line}", "code": code,
                              "details": item.get("details", []),
                              "entities": er_entities(code) if kind == "erDiagram" else None})

    def of_kind(self, *prefixes) -> list[dict]:
        return sorted((i for i in self.items.values() if registry.prefix_of(i["id"]) in prefixes),
                      key=lambda i: (prefixes.index(registry.prefix_of(i["id"])), id_key(i["id"])))

    def stories_of(self, item: dict) -> list[dict]:
        names = {item["id"], item.get("origin") or item["id"]}
        return [s for s in self.of_kind("US") if names & set(s["refs"])]

    def entity_groups(self) -> list[dict]:
        """
        Per doc, its E items with the ERD attributes and relations of the entity of the same name. An ERD entity
        that no E item names stays under the doc of its diagram without an ID.
        """
        attrs, relations, home = {}, [], {}
        for diagram in (d for d in self.diagrams if d["entities"]):
            entities, rels = diagram["entities"]
            for name, found in entities.items():
                if found or name not in attrs:
                    attrs[name] = found
                home.setdefault(name, diagram)
            relations += [r for r in rels if r not in relations]
        groups, named = {}, set()

        def add(doc, row):
            group = groups.setdefault(doc.rel if doc else "", {"doc": doc, "rows": []})
            row["relations"] = [r for r in relations if row["name"] in (r[0], r[2])]
            row["attrs"], row["diagram"] = attrs.get(row["name"], []), home.get(row["name"])
            group["rows"].append(row)

        for item in self.of_kind("E"):
            name = (item.get("title") or "").split(" ")[0].strip("`")
            named.add(name)
            add(item.get("doc"), {"id": item["id"], "name": name, "item": item})
        for name, diagram in home.items():
            if name not in named:
                add(diagram["doc"], {"id": "", "name": name, "item": None})
        return sorted(groups.values(), key=lambda g: g["doc"].rel if g["doc"] else "")


# Run state views

def eligibility(state: dict) -> tuple[bool | None, list[str]]:
    """Handoff eligibility once G3 has opened: no open H item (plan_state.checks.h_items)."""
    if dig(state, "run", "status") == "stopped":
        return None, []
    if dig(state, "gates", "G3", "status", default="closed") == "closed":
        return None, []
    try:
        items = checks.h_items(state)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        return None, []
    return not items, items


def traceability(model: Model) -> tuple[float | None, list[str]]:
    """Share of in-scope features whose feature and story lines have no H6 error, and those errors."""
    try:
        errors, features = checks.traceability(model.state), checks.in_scope_features(model.state)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        return None, []
    bad = {i for e in errors for i in ANY_ID.findall(e.split(":")[0])}
    traced = [f for f in features if f not in bad
              and not bad & {s["id"] for s in model.stories_of(model.items.get(f, {"id": f}))}]
    return (100.0 * len(traced) / len(features) if features else None), errors


def out_of_sync(state: dict, task: str) -> dict | None:
    """
    A task that was done once and is no longer done (stale, cancelled or pending again): its status, the
    transition that took it out of done and the last transition, as plan_state recorded them.
    """
    record = dig(state, "tasks", task, default={})
    status = record.get("status", "")
    history = [h for h in record.get("history") or [] if isinstance(h, list) and len(h) >= 3]
    left = next((h for h in reversed(history) if h[1] == "done"), None)
    if status == "done" or left is None:
        return None
    return {"task": task, "status": status, "left": left, "last": history[-1]}


def combine(found: list[str]) -> str:
    found = [f for f in found if f and f != "cancelled"]
    approved = all(f == "approved" for f in found)
    return next((s for s in STATUS_ORDER if s in found), "approved" if approved else "done") if found else ""


def track_of(state: dict) -> list[dict]:
    """Steps and gates in flow order with a status each; the open gate or running step is current."""
    tasks, gates, handoff = dig(state, "tasks", default={}), dig(state, "gates", default={}), dig(state, "handoff", default={})

    def gate(*names):
        return combine([s for s in (dig(gates, g, "status", default="") for g in names) if s != "closed"])

    def step(n):
        return combine([t.get("status", "") for t in tasks.values() if isinstance(t, dict) and t.get("step") == n
                        and not (t.get("is_group") and t.get("expanded"))])

    done = handoff.get("state") == "committed" or dig(state, "run", "status") == "handed_off"
    # Any other gate (Q2, the second question round) holds back step 6, so it sits after step 5.
    track = [("0", STEPS[0], "step", gate("Q1")), ("1", STEPS[1], "step", step(1)), ("2", STEPS[2], "step", step(2)),
             ("A", "Kapı A", "gate", gate("G1", "G2"))] + [(str(n), STEPS[n], "step", step(n)) for n in range(3, 6)]
    track += [(g, f"Kapı {g}", "gate", gate(g)) for g in gates if g not in ("Q1", "G1", "G2", "G3")]
    track += [(str(n), STEPS[n], "step", step(n)) for n in (6, 7)] + [("G3", "Kapı G3", "gate", gate("G3")),
              ("8", STEPS[8], "step", "done" if done else "running" if handoff.get("state") else "")]
    nodes = [{"id": i, "name": name, "kind": kind, "status": status} for i, name, kind, status in track]
    for node in nodes:
        node["skipped"] = sorted(SKIPPED_LABEL.get(n, n) for n, t in tasks.items() if isinstance(t, dict)
                                 and t.get("skipped") and node["kind"] == "step" and str(t.get("step")) == node["id"])
    index = next((n for n, node in enumerate(nodes) if node["kind"] == "gate" and node["status"] == "open"),
                 next((n for n, node in enumerate(nodes) if node["status"] in ("running", "blocked")), None))
    for n, node in enumerate(nodes):
        node["current"] = n == index
        node["status"] = node["status"] or ("done" if index is not None and n < index else "")
    return nodes


# Input discovery

def build(paths: list[Path], plan: str | None = None) -> Model:
    """Docs from the given roots, folders and files, and the newest run.json of the plan next to them."""
    files, base, runs = [], None, []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(str(path))
        runs += (path if path.is_dir() else path.parent).rglob(f"{plan or ''}*.run.json")
        docs = path / "docs" if (path / "docs").is_dir() else path
        base = base or (path if path.is_dir() else path.parent)
        files += sorted(p for p in docs.rglob("*.md") if not any(x.startswith(".") for x in p.parts[-3:])) \
            if path.is_dir() else [path]
    state, note = {}, ""
    run = max(set(runs), key=lambda r: r.stat().st_mtime) if runs else None
    if run is not None:
        try:
            state = json.loads(run.read_text(encoding="utf-8"))
            state = state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            print(f"note: could not read {run}", file=sys.stderr)
            note = f"Durum dosyası okunamadı: {run.name}. Süreç sayaçları run.json düzelince görünür."
        base = run.parents[3] if run.parent.parent.parent.name == "docs" else base
    docs = [Doc(p, base) for p in dict.fromkeys(files) if not p.name.endswith(".index.md")]
    return Model(docs, state, note)
