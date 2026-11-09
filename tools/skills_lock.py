#!/usr/bin/env python3
"""Pin and verify third-party skills and MCP servers recorded in skills.lock.

status: candidate (not pinned) -> pinned (commit + content hash) -> approved (a person read it).
Re-pinning drops the approval because the content may have changed.
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "skills.lock"
KEYS = {"name", "kind", "source", "subpath", "branch", "ref", "sha256", "version", "status",
        "reviewed", "reviewed_by", "notes"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def tree_hash(directory):
    d = Path(directory)
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if ".git" in rel.parts or not p.is_file():
            continue
        h.update(rel.as_posix().encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def validate(data):
    problems = []
    seen = set()
    for i, e in enumerate(data.get("skills", [])):
        n = e.get("name", f"#{i}")
        if n in seen:
            problems.append(f"{n}: duplicate name")
        seen.add(n)
        extra = set(e) - KEYS
        if extra:
            problems.append(f"{n}: unknown keys {sorted(extra)}")
        for k in ("name", "kind", "source", "status"):
            if not e.get(k):
                problems.append(f"{n}: missing {k}")
        if e.get("kind") not in ("skill", "mcp"):
            problems.append(f"{n}: kind must be skill or mcp")
        st = e.get("status")
        if st not in ("candidate", "pinned", "approved"):
            problems.append(f"{n}: status must be candidate, pinned or approved")
            continue
        if st in ("pinned", "approved"):
            if e.get("kind") == "mcp":
                if not e.get("version"):
                    problems.append(f"{n}: pinned mcp needs version")
            else:
                if not SHA40.match(e.get("ref", "")):
                    problems.append(f"{n}: pinned skill needs a 40-hex ref")
                if not SHA64.match(e.get("sha256", "")):
                    problems.append(f"{n}: pinned skill needs a 64-hex sha256")
        if st == "approved":
            if not DATE.match(e.get("reviewed", "")):
                problems.append(f"{n}: approved needs reviewed date YYYY-MM-DD")
            if not e.get("reviewed_by"):
                problems.append(f"{n}: approved needs reviewed_by")
    return problems


def find(data, name):
    for e in data["skills"]:
        if e["name"] == name:
            return e
    raise SystemExit(f"no such entry: {name}")


def pin(data, name):
    e = find(data, name)
    if e["kind"] != "skill":
        raise SystemExit(f"{name}: only skills are pinned by content; set version for mcp by hand")
    tmp = Path(tempfile.mkdtemp(prefix="skillpin."))
    try:
        cmd = ["git", "clone", "--depth", "1"]
        if e.get("branch"):
            cmd += ["--branch", e["branch"]]
        subprocess.run(cmd + [e["source"], str(tmp / "r")], check=True, capture_output=True, text=True)
        ref = subprocess.run(["git", "-C", str(tmp / "r"), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True).stdout.strip()
        target = tmp / "r" / e.get("subpath", "")
        if not target.is_dir():
            raise SystemExit(f"{name}: subpath not found: {e.get('subpath')}")
        e["ref"], e["sha256"], e["status"] = ref, tree_hash(target), "pinned"
        for k in ("reviewed", "reviewed_by"):
            e.pop(k, None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return e


def check_installed(data, skills_dir):
    out = []
    for e in data.get("skills", []):
        if e.get("kind") != "skill" or e.get("status") not in ("pinned", "approved"):
            continue
        d = Path(skills_dir) / e["name"]
        if d.is_dir() and tree_hash(d) != e["sha256"]:
            out.append(f"{e['name']}: installed copy differs from the pinned hash")
    return out


def load(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--lock", default=str(LOCK))
    v.add_argument("--installed", help="skills directory to compare against pinned hashes")
    p = sub.add_parser("pin")
    p.add_argument("name")
    p.add_argument("--lock", default=str(LOCK))
    a = sub.add_parser("approve")
    a.add_argument("name")
    a.add_argument("--by", required=True)
    a.add_argument("--date", default=datetime.date.today().isoformat())
    a.add_argument("--lock", default=str(LOCK))
    args = ap.parse_args(argv)
    data = load(args.lock)
    if args.cmd == "verify":
        problems = validate(data)
        if args.installed:
            problems += check_installed(data, args.installed)
        for line in problems:
            print("FAIL:", line)
        counts = {}
        for e in data["skills"]:
            counts[e["status"]] = counts.get(e["status"], 0) + 1
        print("skills.lock:", counts, "problems:", len(problems))
        return 1 if problems else 0
    if args.cmd == "pin":
        e = pin(data, args.name)
        save(args.lock, data)
        print(f"pinned {e['name']} {e['ref'][:12]} {e['sha256'][:12]}")
        return 0
    e = find(data, args.name)
    if e["status"] != "pinned":
        raise SystemExit(f"{args.name}: pin it first (status is {e['status']})")
    e.update(status="approved", reviewed=args.date, reviewed_by=args.by)
    problems = validate(data)
    if problems:
        raise SystemExit("; ".join(problems))
    save(args.lock, data)
    print(f"approved {args.name} by {args.by} on {args.date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
