#!/usr/bin/env python3
"""SessionStart hook: pyproject.toml'da fastapi varsa ve .claude/profile yoksa
tek satırlık ipucu ekler. Hata olursa sessizce çıkar, oturumu asla bloklamaz."""
import json
import os
import sys

try:
    d = json.load(sys.stdin)
    cwd = d.get("cwd") or os.getcwd() if isinstance(d, dict) else os.getcwd()
    if os.path.exists(os.path.join(cwd, ".claude", "profile")):
        sys.exit(0)
    with open(os.path.join(cwd, "pyproject.toml"), encoding="utf-8") as f:
        if "fastapi" not in f.read().lower():
            sys.exit(0)
except Exception:
    sys.exit(0)

hint = ("Bu dizin bir FastAPI projesi gibi görünüyor ve .claude/profile yok. "
        "Kullanıcıya şunu öner: 'cinit --kind fastapi-saas'. Kendiliğinden uygulama.")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": hint}}, ensure_ascii=False))
