#!/usr/bin/env python3
"""PreToolUse (Edit|Write|MultiEdit): dogrulamayi zayiflatabilecek duzenlemelerde insana sorar.
Yollar proje kokune goredir. Hata olursa sessizce gecer; asla bloklamaz."""
import fnmatch
import json
import os
import re
import sys

ALWAYS = [
    "backend/.importlinter",
    "backend/tests/unit/test_architecture_*.py",
    "backend/tests/unit/test_tests_layout.py",
]
MAKE_WORDS = re.compile(r"check|lint|arch|test-unit|cov-fail-under")

try:
    d = json.load(sys.stdin)
    ti = d.get("tool_input") or {}
    path = ti.get("file_path") or ""
    cwd = d.get("cwd") or os.getcwd()
    rel = os.path.relpath(path, cwd) if os.path.isabs(path) else path
    rel = rel.replace(os.sep, "/")
except Exception:
    sys.exit(0)

why = None
if any(fnmatch.fnmatch(rel, pat) for pat in ALWAYS):
    why = f"{rel} dogrulamanin parcasi; zayiflatma riski"
elif rel == "Makefile":
    if d.get("tool_name") == "Write":
        why = "Makefile bastan yaziliyor; check/lint/arch hedefleri etkilenebilir"
    else:
        changed = (ti.get("old_string") or "") + (ti.get("new_string") or "")
        for e in ti.get("edits") or []:
            changed += (e.get("old_string") or "") + (e.get("new_string") or "")
        if MAKE_WORDS.search(changed):
            why = "Makefile'da check/lint/arch/test-unit ile ilgili satir degisiyor"

if why:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": "Dogrulama dosyasi: " + why,
    }}, ensure_ascii=False))
