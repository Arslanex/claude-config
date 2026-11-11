#!/usr/bin/env python3
"""
PreToolUse (Edit|Write|MultiEdit): dogrulamayi zayiflatabilecek duzenlemelerde insana sorar.
Ekip dosyalarini (rol, skill, team.md) ekip kendisi gelistirir: yetki alanlari (tools, allowed-tools,
permissionMode, mcpServers, hooks) degismiyorsa duzenleme sorulmadan onaylanir, degisiyorsa sorulur.
Yollar proje kokune goredir. Hata olursa sessizce gecer; asla bloklamaz.
"""
import fnmatch
import json
import os
import re
import sys

ALWAYS = [
    "backend/.importlinter",
    "backend/tests/unit/test_architecture_*.py",
    "backend/tests/unit/test_tests_layout.py",
    "tools/git-hooks/pre-push",
    ".claude/rules/*.md",
]
# Profille gelen rol ve ekip tanimlari: ekip gelistirir, ama yetkisini genisletemez.
TEAM = [
    ".claude/agents/*.md",
    ".claude/skills/*",
    ".claude/team.md",
    ".claude/profile",
]
PERM_KEYS = ("tools", "disallowedTools", "allowed-tools", "permissionMode", "mcpServers", "hooks")
MAKE_WORDS = re.compile(r"check|lint|arch|test-unit|cov-fail-under")
# pyproject.toml: bagimlilik eklemek serbest, arac ayarini (ruff/mypy/pytest/coverage) degistirmek sorulur.
PYPROJECT = ("pyproject.toml", "backend/pyproject.toml")
TOOL_WORDS = re.compile(r"\[tool\.(?!hatch)|select|ignore|D10[04]|fail[-_]under|omit|exclude|strict|addopts")

def after_edit(path, tool, ti):
    """Dosyanin duzenlemeden sonraki hali; okunamazsa None."""
    if tool == "Write":
        return ti.get("content") or ""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    for e in ti.get("edits") or [ti]:
        old, new = e.get("old_string") or "", e.get("new_string") or ""
        if old not in text:
            return None
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def perm_fields(text):
    """Frontmatter'daki yetki satirlari, girintili devam satirlariyla birlikte."""
    if not text.startswith("---\n"):
        return []
    head = text[4:].split("\n---", 1)[0]
    out, inside = [], False
    for line in head.splitlines():
        if line[:1] not in (" ", "\t", "-"):
            inside = line.split(":", 1)[0].strip() in PERM_KEYS
        if inside:
            out.append(line.rstrip())
    return out


def team_decision(path, tool, ti):
    """Yetki alanlari ayni kaliyorsa allow, degisiyor ya da anlasilamiyorsa ask."""
    try:
        with open(path, encoding="utf-8") as f:
            before = f.read()
    except OSError:
        before = ""
    after = after_edit(path, tool, ti)
    if after is not None and perm_fields(before) == perm_fields(after):
        return "allow", "ekip dosyasi; yetki alanlari degismiyor"
    return "ask", "ekip dosyasinda yetki alani (tools, allowed-tools, permissionMode, mcpServers, hooks) degisiyor"


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
elif any(fnmatch.fnmatch(rel, pat) for pat in TEAM):
    decision, reason = team_decision(path if os.path.isabs(path) else os.path.join(cwd, path), d.get("tool_name"), ti)
    if decision == "allow":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": f"{rel}: {reason}",
        }}, ensure_ascii=False))
        sys.exit(0)
    why = f"{rel}: {reason}"
elif rel == "Makefile" or rel in PYPROJECT:
    words, what = (MAKE_WORDS, "check/lint/arch/test-unit") if rel == "Makefile" else (TOOL_WORDS, "lint/tip/test araci ayari")
    if d.get("tool_name") == "Write":
        why = f"{rel} bastan yaziliyor; {what} etkilenebilir"
    else:
        changed = (ti.get("old_string") or "") + (ti.get("new_string") or "")
        for e in ti.get("edits") or []:
            changed += (e.get("old_string") or "") + (e.get("new_string") or "")
        if words.search(changed):
            why = f"{rel} icinde {what} ile ilgili satir degisiyor"

if why:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": "Korunan dosya: " + why,
    }}, ensure_ascii=False))
