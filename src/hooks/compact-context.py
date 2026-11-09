#!/usr/bin/env python3
"""SessionStart (compact): sikistirmadan sonra kalici bellegi ajana geri verir.
docs/05-work altindaki son devir notu, acik is dosyalari ve git durumu. Hata olursa sessiz gecer.
Devir notu anlik goruntudur: basliginda tarihi ve uyari verilir; celiskide ajan guncel belgelere ve koda guvenir."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MAX_HANDOFF = 1500
MAX_TOTAL = 4000


def newest(d, n):
    """Ada gore en yuksek n dosya (HO-0007 > HO-0006). mtime degil: merge/checkout mtime'i bozar."""
    try:
        fs = [p for p in d.iterdir() if p.is_file() and p.name != ".gitkeep"]
        return sorted(fs, key=lambda p: p.name, reverse=True)[:n]
    except Exception:
        return []


def git(cwd, *a):
    try:
        r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def cut_lines(txt, limit):
    """Sinira sigmiyorsa son tam satirda keser, kelime ortasinda degil."""
    if len(txt) <= limit:
        return txt
    head = txt[:limit]
    nl = head.rfind("\n")
    return (head[:nl] if nl > 0 else head) + "\n[...kisaltildi]"


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
        full = hand[0].read_text(errors="replace")
        m = re.search(r"^updated:\s*(\S+)", full, re.M)
        date = m.group(1) if m else "?"
        out.append(
            f"Son devir notu ({hand[0].relative_to(root)}, updated: {date}). "
            "ANLIK GORUNTU: yazildigi andaki durumu anlatir. "
            "Guncel gercek ADR/ARCH/README/RUN ve koddur; celisirse onlara ve git durumuna guven:\n"
            + cut_lines(full, MAX_HANDOFF)
        )

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
