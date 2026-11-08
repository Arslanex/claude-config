#!/usr/bin/env python3
"""PreToolUse (Bash): yeni bagimlilik ekleyen komutlarda insana sorar (tedarik zinciri).
Kilit dosyasindan geri yukleme ve calistirma komutlari serbest. Hata olursa sessizce gecer."""
import json
import re
import sys


def adds_package(t):
    if not t:
        return False
    if t[0] == "uv" and len(t) > 1:
        return t[1] == "add" or t[1:3] == ["pip", "install"]
    if t[0] in ("pip", "pip3"):
        return t[1:2] == ["install"]
    if t[0] in ("python", "python3"):
        return t[1:4] == ["-m", "pip", "install"]
    if t[0] in ("npm", "pnpm", "bun") and len(t) > 1 and t[1] in ("add", "install", "i"):
        return any(not a.startswith("-") for a in t[2:])
    if t[0] == "yarn":
        return t[1:2] == ["add"]
    if t[0] == "cargo":
        return t[1:2] in (["add"], ["install"])
    if t[0] in ("brew", "gem"):
        return t[1:2] == ["install"]
    if t[0] == "go":
        return t[1:2] in (["get"], ["install"])
    return False


try:
    d = json.load(sys.stdin)
    cmd = (d.get("tool_input") or {}).get("command") or ""
except Exception:
    sys.exit(0)

cmd = re.sub(r"'[^']*'|\"[^\"]*\"", "''", cmd)
for seg in re.split(r"&&|\|\||;|\||\n", cmd):
    toks = seg.split()
    while toks and re.match(r"^\w+=", toks[0]):
        toks.pop(0)
    if adds_package(toks):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "Yeni bagimlilik (tedarik zinciri onayi): " + " ".join(toks)[:120],
        }}, ensure_ascii=False))
        break
