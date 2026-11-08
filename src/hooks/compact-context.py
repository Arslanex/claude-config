#!/usr/bin/env python3
"""SessionStart (compact): sikistirmadan sonra kalici bellegi ajana geri verir.
docs/05-work altindaki son devir notu, acik is dosyalari ve git durumu. Hata olursa sessiz gecer."""
import json
import os
import subprocess
import sys
from pathlib import Path

MAX_HANDOFF = 1500
MAX_TOTAL = 4000


def newest(d, n):
    try:
        fs = [p for p in d.iterdir() if p.is_file() and p.name != ".gitkeep"]
        return sorted(fs, key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    except Exception:
        return []


def git(cwd, *a):
    try:
        r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


try:
    data = json.load(sys.stdin)
    cwd = (data.get("cwd") if isinstance(data, dict) else None) or os.getcwd()
    root = Path(cwd)
    if not (root / "docs" / "INDEX.md").is_file():
        sys.exit(0)
    work = root / "docs" / "05-work"
    out = ["Baglam sikistirildi. Devam etmeden once docs/INDEX.md'yi oku, asagidaki durumu kontrol et."]

    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = len(git(cwd, "status", "--porcelain").splitlines())
    log = git(cwd, "log", "--oneline", "-3")
    if branch:
        out.append(f"Git: dal {branch}, {dirty} degisen dosya.\n{log}")

    hand = newest(work / "handoffs", 1)
    if hand:
        txt = hand[0].read_text(errors="replace")[:MAX_HANDOFF]
        out.append(f"Son devir notu ({hand[0].relative_to(root)}):\n{txt}")

    for sub, n in (("tasks", 10), ("plans", 3), ("log", 1)):
        fs = newest(work / sub, n)
        if fs:
            out.append(f"Son {sub}:\n" + "\n".join(str(p.relative_to(root)) for p in fs))

    ctx = "\n\n".join(out)[:MAX_TOTAL]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": ctx,
    }}, ensure_ascii=False))
except Exception:
    sys.exit(0)
