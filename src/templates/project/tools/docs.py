#!/usr/bin/env python3
"""Project knowledge base engine: new / lint / index / graph / stale for docs/.

Python 3 stdlib only, no network. Run `docs.py --help` for usage.
"""
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

DOCS_ENGINE_VERSION = 3

REQUIRED = ("id", "title", "status", "area", "updated")
STATUSES = ("draft", "accepted", "superseded", "archived")
LIST_FIELDS = ("depends_on", "related", "code_paths")
REF_FIELDS = ("depends_on", "related", "superseded_by")
# superseded_by takes one ID or an inline list; every other field is a plain scalar.
LIST_OR_SCALAR = ("superseded_by",)

MAX_DOC_LINES = 300
MAX_INDEX_LINES = 100

INDEX_START = "<!-- docs:index:start -->"
INDEX_END = "<!-- docs:index:end -->"

# The single source of truth for the docs layout: area -> (folder, ID prefixes it holds).
AREAS = {
    "project": ("00-project", ()),
    "architecture": ("01-architecture", ("ARCH",)),
    "decisions": ("02-decisions", ("ADR",)),
    "domains": ("03-domains", ("DOM",)),
    "operations": ("04-operations", ()),
    "work": ("05-work", ("T", "PLAN", "HO", "LOG")),
    "archive": ("99-archive", ()),
}
PREFIX_DIR = {p: folder for folder, prefixes in AREAS.values() for p in prefixes}
DOMAINS_DIR = AREAS["domains"][0]
ARCHIVE_DIR = AREAS["archive"][0]
GRAPH_PATH = f"{AREAS['architecture'][0]}/graph.md"

# kind -> (id prefix, subfolder inside the prefix's area folder)
KINDS = {
    "adr": ("ADR", ""),
    "task": ("T", "tasks"),
    "module": ("ARCH", "modules"),
    "domain": ("DOM", ""),
    "plan": ("PLAN", "plans"),
    "handoff": ("HO", "handoffs"),
    "log": ("LOG", "log"),
}

BODIES = {
    "adr": "## Context\n\n## Decision\n\n## Consequences\n",
    "task": "## Goal\n\n## Definition of done\n\n## Notes\n",
    "module": "## Purpose\n\n## Interfaces\n\n## Dependencies\n",
    "domain": "## Overview\n\n## Rules\n\n## Open questions\n",
    "plan": "## Objective\n\n## Steps\n\n## Risks\n",
    "handoff": "## State\n\n## Next steps\n\n## Gotchas\n",
    "log": "## Summary\n\n## Details\n",
}


class DocsError(Exception):
    """User-facing error; printed without a traceback."""


class FrontMatterError(DocsError):
    pass


# --------------------------------------------------------------------------
# Front matter parser: a strict subset of YAML.
#   key: value            plain or quoted ("..." / '...') scalar
#   key: [A, B]           inline list of scalars
#   # comment             full-line or trailing (preceded by whitespace)
# Everything else (nesting, block lists, flow maps, block scalars) is rejected.
# --------------------------------------------------------------------------

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:(?:\s+(.*))?$")


def _err(lineno, msg):
    return FrontMatterError(f"front matter line {lineno}: {msg}")


def _after_value(rest, lineno):
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise _err(lineno, f"unexpected text after value: {rest!r}")


def _parse_scalar(s, lineno):
    """Parse one scalar from the start of s. Returns (value, remainder)."""
    s = s.lstrip()
    if s and s[0] in "\"'":
        end = s.find(s[0], 1)
        if end == -1:
            raise _err(lineno, "unterminated quoted string")
        return s[1:end], s[end + 1:]
    m = re.match(r"[^,\]#]*", s)  # plain item inside a list
    return m.group(0).strip(), s[m.end():]


def _parse_list(s, lineno):
    items = []
    rest = s[1:].lstrip()
    if rest.startswith("]"):
        _after_value(rest[1:], lineno)
        return items
    while True:
        if rest[:1] in ("[", "{"):
            raise _err(lineno, "nested lists/maps are not supported")
        value, rest = _parse_scalar(rest, lineno)
        if value == "":
            raise _err(lineno, "empty item in inline list")
        if any(c in value for c in "[]{}"):
            raise _err(lineno, f"unsupported characters in list item {value!r}")
        items.append(value)
        rest = rest.lstrip()
        if rest.startswith(","):
            rest = rest[1:].lstrip()
        elif rest.startswith("]"):
            _after_value(rest[1:], lineno)
            return items
        else:
            raise _err(lineno, "unterminated inline list (missing ']')")


def _parse_value(s, lineno):
    s = s.strip()
    if s == "" or s.startswith("#"):
        return ""
    if s[0] == "[":
        return _parse_list(s, lineno)
    if s[0] == "{":
        raise _err(lineno, "inline maps '{...}' are not supported")
    if s[0] in "|>":
        raise _err(lineno, "block scalars ('|' / '>') are not supported")
    if s[0] in "\"'":
        value, rest = _parse_scalar(s, lineno)
        _after_value(rest, lineno)
        return value
    value = re.split(r"\s#", s, maxsplit=1)[0].strip()
    if ": " in value or value.endswith(":"):
        raise _err(lineno, "nested mappings are not supported (quote the value if it contains ':')")
    return value


def parse_front_matter(text):
    """Return (data, body). data maps key -> str | list[str]."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].rstrip() != "---":
        raise FrontMatterError("missing front matter: file must start with '---'")
    end = next((i for i, l in enumerate(lines[1:], 1) if l.rstrip() == "---"), None)
    if end is None:
        raise FrontMatterError("front matter is not closed: missing second '---'")
    data = {}
    for i in range(1, end):
        raw, lineno = lines[i], i + 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[0] in " \t":
            raise _err(lineno, "indented line: nested structures are not supported")
        if raw.startswith("-"):
            raise _err(lineno, "block lists ('- item') are not supported; use an inline list [A, B]")
        m = _KEY_RE.match(raw.rstrip())
        if not m:
            raise _err(lineno, f"expected 'key: value', got {raw.strip()!r}")
        key = m.group(1)
        if key in data:
            raise _err(lineno, f"duplicate key {key!r}")
        data[key] = _parse_value(m.group(2) or "", lineno)
    return data, "\n".join(lines[end + 1:])


# --------------------------------------------------------------------------
# Git helpers (everything degrades gracefully when git is missing)
# --------------------------------------------------------------------------

def _git(args, cwd):
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def repo_info(root):
    """Return (toplevel, root prefix relative to it) or None if not in a git repo."""
    root = Path(root).resolve()
    cwd = root
    while not cwd.exists():
        cwd = cwd.parent
    r = _git(["rev-parse", "--show-toplevel"], cwd)
    if r is None or r.returncode != 0:
        return None
    top = Path(r.stdout.strip()).resolve()
    try:
        prefix = root.relative_to(top).as_posix()
    except ValueError:
        return None
    return top, ("" if prefix == "." else prefix)


# --------------------------------------------------------------------------
# Document model
# --------------------------------------------------------------------------

class Doc:
    def __init__(self, path, root):
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        self.text = path.read_text(encoding="utf-8")
        self.data = {}
        self.error = None
        try:
            self.data, _ = parse_front_matter(self.text)
        except FrontMatterError as e:
            self.error = str(e)

    def get(self, key):
        v = self.data.get(key, "")
        return v if isinstance(v, str) else ""

    def refs(self, key):
        v = self.data.get(key, [])
        return [v] if isinstance(v, str) and v else (v if isinstance(v, list) else [])

    @property
    def id(self):
        return self.get("id")


def _is_generated(path, root):
    # INDEX.md and graph.md are generated; README.md files are plain guides without
    # front matter, so none of them are treated as documents (not linted, not indexed).
    rel = path.relative_to(root).as_posix()
    return path.name in ("INDEX.md", "README.md") or rel == GRAPH_PATH


def load_docs(root):
    root = Path(root)
    if not root.is_dir():
        raise DocsError(f"docs root not found: {root}")
    return [Doc(p, root) for p in sorted(root.rglob("*.md")) if not _is_generated(p, root)]


def _id_key(doc_id):
    m = re.match(r"^(.*?)-(\d+)$", doc_id)
    return (m.group(1), int(m.group(2))) if m else (doc_id, 0)


def _doc_sort_key(doc):
    return (*_id_key(doc.id), doc.rel)


# --------------------------------------------------------------------------
# Marked-block writer shared by index and graph
# --------------------------------------------------------------------------

def write_marked(path, content, header):
    """Replace the text between the docs:index markers; keep everything else."""
    block = f"{INDEX_START}\n{content.rstrip()}\n{INDEX_END}"
    path = Path(path)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        s, e = text.find(INDEX_START), text.find(INDEX_END)
        if text.count(INDEX_START) > 1 or text.count(INDEX_END) > 1:
            raise DocsError(f"{path}: more than one docs:index marker pair")
        if s == -1 and e == -1:
            new = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
        elif s == -1 or e == -1 or e < s:
            raise DocsError(f"{path}: unbalanced docs:index markers")
        else:
            new = text[:s] + block + text[e + len(INDEX_END):]
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = f"{header}\n\n{block}\n"
        text = None
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


# --------------------------------------------------------------------------
# new
# --------------------------------------------------------------------------

def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def _scan_ids(text, prefix, found):
    for m in re.finditer(rf"^id:\s*[\"']?{re.escape(prefix)}-(\d+)", text, re.M):
        found.add(int(m.group(1)))


def used_numbers(root, prefix):
    """Numbers already taken for prefix: working tree plus every local/remote branch."""
    found = set()
    root = Path(root)
    if root.is_dir():
        for p in root.rglob("*.md"):
            _scan_ids(p.read_text(encoding="utf-8", errors="replace"), prefix, found)
    info = repo_info(root)
    if info:
        top, rel = info
        refs = _git(["for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes"], top)
        pathspec = (rel + "/" if rel else "") + "*.md"
        for ref in (refs.stdout.split() if refs and refs.returncode == 0 else []):
            r = _git(["grep", "-h", "-I", "-E", "^id:", ref, "--", pathspec], top)
            if r and r.returncode == 0:
                _scan_ids(r.stdout, prefix, found)
    return found


def _quote(value):
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    raise DocsError("title may not contain both single and double quotes")


def cmd_new(args):
    prefix, sub = KINDS[args.kind]
    folder = f"{PREFIX_DIR[prefix]}/{sub}" if sub else PREFIX_DIR[prefix]
    title = args.title.strip()
    if not title or "\n" in title:
        raise DocsError("title must be a non-empty single line")
    root = Path(args.root)
    number = max(used_numbers(root, prefix), default=0) + 1
    doc_id = f"{prefix}-{number:04d}"
    slug = slugify(title)
    area = args.area or (slug if args.kind == "domain" else "general")
    target_dir = root / folder / (slugify(area) if args.kind == "domain" else "")
    path = target_dir / f"{doc_id}-{slug}.md"
    content = (
        "---\n"
        f"id: {doc_id}\n"
        f"title: {_quote(title)}\n"
        "status: draft\n"
        f"area: {area}\n"
        "owner:\n"
        f"updated: {datetime.date.today().isoformat()}\n"
        "depends_on: []\n"
        "related: []\n"
        "superseded_by:\n"
        "code_paths: []\n"
        "---\n\n"
        f"# {title}\n\n{BODIES[args.kind]}"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        raise DocsError(f"refusing to overwrite {path}")
    print(path)
    return 0


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------

def _valid_date(s):
    try:
        datetime.date.fromisoformat(s)
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))
    except ValueError:
        return False


def lint(root):
    """Return (errors, warnings) as lists of 'path: message' strings."""
    docs = load_docs(root)
    errors, warnings = [], []
    first_seen = {}

    for d in docs:
        if d.error:
            errors.append(f"{d.rel}: {d.error}")
            continue
        for key in REQUIRED:
            if key not in d.data or d.data[key] in ("", []):
                errors.append(f"{d.rel}: missing required field '{key}'")
        for key, v in d.data.items():
            if isinstance(v, list) and key not in LIST_FIELDS + LIST_OR_SCALAR:
                errors.append(f"{d.rel}: field '{key}' must be a scalar, not a list")
            elif isinstance(v, str) and key in LIST_FIELDS and v:
                errors.append(f"{d.rel}: field '{key}' must be an inline list like [A, B]")
        status = d.get("status")
        if status and status not in STATUSES:
            errors.append(f"{d.rel}: invalid status {status!r} (expected one of {', '.join(STATUSES)})")
        if d.get("updated") and not _valid_date(d.get("updated")):
            errors.append(f"{d.rel}: 'updated' must be a YYYY-MM-DD date, got {d.get('updated')!r}")
        if d.id:
            if d.id in first_seen:
                errors.append(f"{d.rel}: duplicate id {d.id} (also in {first_seen[d.id]})")
            else:
                first_seen[d.id] = d.rel

    for d in docs:
        if d.error:
            continue
        for key in REF_FIELDS:
            for ref in d.refs(key):
                if ref not in first_seen:
                    errors.append(f"{d.rel}: {key} references unknown id {ref}")

    for d in docs:
        if len(d.text.splitlines()) > MAX_DOC_LINES:
            warnings.append(f"{d.rel}: longer than {MAX_DOC_LINES} lines")
        if not d.error and d.get("status") == "superseded" and d.rel.split("/")[0] != ARCHIVE_DIR:
            warnings.append(f"{d.rel}: status is superseded but file is outside {ARCHIVE_DIR}")
    for p in sorted(Path(root).rglob("INDEX.md")):
        if len(p.read_text(encoding="utf-8").splitlines()) > MAX_INDEX_LINES:
            warnings.append(f"{p.relative_to(root).as_posix()}: longer than {MAX_INDEX_LINES} lines")

    info = repo_info(root)
    if info:
        top = info[0]
        for d in docs:
            if d.error or not _valid_date(d.get("updated")):
                continue
            for code in d.refs("code_paths"):
                r = _git(["log", "-1", "--format=%cs", "--", code], top)
                last = r.stdout.strip() if r and r.returncode == 0 else ""
                if last and last > d.get("updated"):
                    warnings.append(
                        f"{d.rel}: code_paths '{code}' changed on {last}, after updated {d.get('updated')}")
    return errors, warnings


def cmd_lint(args):
    errors, warnings = lint(args.root)
    for m in errors:
        print(f"ERROR {m}")
    for m in warnings:
        print(f"WARN  {m}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------

def _cell(s):
    return s.replace("|", "\\|")


def _table(docs, base):
    lines = ["| ID | Title | Status | Updated |", "| --- | --- | --- | --- |"]
    for d in sorted(docs, key=_doc_sort_key):
        link = (Path(d.rel).relative_to(base) if base else Path(d.rel)).as_posix()
        lines.append(f"| [{d.id}]({link}) | {_cell(d.get('title'))} | {d.get('status')} | {d.get('updated')} |")
    return "\n".join(lines)


def cmd_index(args):
    root = Path(args.root)
    docs = [d for d in load_docs(root) if not d.error and d.id]
    for d in load_docs(root):
        if d.error:
            print(f"skipped {d.rel}: {d.error}", file=sys.stderr)
    changed = []

    def emit(path, content, header):
        if write_marked(path, content, header):
            changed.append(path)

    sections = sorted({d.rel.split("/")[0] for d in docs if "/" in d.rel})
    top_docs = [d for d in docs if "/" not in d.rel]
    for sec in sections:
        sec_docs = [d for d in docs if d.rel.startswith(sec + "/")]
        emit(root / sec / "INDEX.md", _table(sec_docs, sec), f"# {sec}")
    for area in sorted({d.rel.split("/")[1] for d in docs
                        if d.rel.startswith(DOMAINS_DIR + "/") and d.rel.count("/") >= 2}):
        base = f"{DOMAINS_DIR}/{area}"
        emit(root / base / "INDEX.md",
             _table([d for d in docs if d.rel.startswith(base + "/")], base), f"# {area}")

    lines = ["| Section | Docs |", "| --- | --- |"]
    for sec in sections:
        count = sum(1 for d in docs if d.rel.startswith(sec + "/"))
        lines.append(f"| [{sec}]({sec}/INDEX.md) | {count} |")
    content = "\n".join(lines)
    if top_docs:
        content += "\n\n" + _table(top_docs, "")
    emit(root / "INDEX.md", content, "# Documentation Index")

    for p in changed:
        print(f"updated {p}")
    if not changed:
        print("indexes already up to date")
    return 0


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def _node(doc_id):
    return re.sub(r"[^A-Za-z0-9_]", "_", doc_id)


def build_graph(docs):
    by_id = {d.id: d for d in docs if not d.error and d.id}
    edges = sorted({(d.id, dep) for d in by_id.values() for dep in d.refs("depends_on")
                    if dep in by_id and dep != d.id}, key=lambda e: (_id_key(e[0]), _id_key(e[1])))
    nodes = sorted({i for e in edges for i in e}, key=_id_key)
    lines = ["```mermaid", "graph LR"]
    for i in nodes:
        label = by_id[i].get("title").replace('"', "'")
        lines.append(f'    {_node(i)}["{i} - {label}"]')
    for a, b in edges:
        lines.append(f"    {_node(a)} --> {_node(b)}")
    lines.append("```")
    return "\n".join(lines)


def cmd_graph(args):
    root = Path(args.root)
    target = root / GRAPH_PATH
    changed = write_marked(target, build_graph(load_docs(root)), "# Dependency graph")
    print(f"{'updated' if changed else 'unchanged'} {target}")
    return 0


# --------------------------------------------------------------------------
# stale
# --------------------------------------------------------------------------

STALE_STATUSES = ("draft", "accepted")


def cmd_stale(args):
    if args.today:
        if not _valid_date(args.today):
            raise DocsError(f"--today must be a YYYY-MM-DD date, got {args.today!r}")
        today = datetime.date.fromisoformat(args.today)
    else:
        today = datetime.date.today()
    checked = stale = 0
    for d in load_docs(args.root):
        if d.error:
            print(f"WARN  {d.rel}: {d.error}")
            continue
        if d.get("status") not in STALE_STATUSES:
            continue
        checked += 1
        updated = d.get("updated")
        if not _valid_date(updated):
            print(f"WARN  {d.rel}: missing or invalid 'updated' date {updated!r}")
            continue
        age = (today - datetime.date.fromisoformat(updated)).days
        if age > args.days:
            stale += 1
            print(f"STALE {d.id} {d.get('status')} {updated} {age}d {d.rel}")
    print(f"{stale} stale of {checked} checked")
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="docs.py", description=f"docs engine v{DOCS_ENGINE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--root", default="docs", help="docs directory (default: docs)")
        return p

    p = add("new", help="create a document from a template")
    p.add_argument("kind", choices=sorted(KINDS))
    p.add_argument("title")
    p.add_argument("--area", help="area field (default: general; domain: slug of title)")
    p.set_defaults(func=cmd_new)
    p = add("lint", help="validate front matter and links")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.set_defaults(func=cmd_lint)
    add("index", help="regenerate INDEX.md files").set_defaults(func=cmd_index)
    add("graph", help="regenerate the Mermaid dependency graph").set_defaults(func=cmd_graph)
    p = add("stale", help="list draft/accepted docs not updated for N days (report only)")
    p.add_argument("--days", type=int, default=90, help="age threshold in days (default: 90)")
    p.add_argument("--today", help="reference date YYYY-MM-DD (default: real today)")
    p.set_defaults(func=cmd_stale)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DocsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
