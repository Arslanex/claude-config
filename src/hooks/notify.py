#!/usr/bin/env python3
"""macOS notification hook. Always exits 0 and prints nothing, so it never
changes the permission flow (exit 2 on PermissionRequest would deny)."""
import json
import os
import subprocess
import sys

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

event = d.get("hook_event_name", "")
project = os.path.basename((d.get("cwd") or "").rstrip("/")) or "?"


def clip(s, n=110):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


if event == "PermissionRequest":
    tool = d.get("tool_name", "tool")
    ti = d.get("tool_input") or {}
    detail = ti.get("command") or ti.get("file_path") or ti.get("url") or ti.get("query") or ""
    title = f"Onay gerekli · {project}"
    body = clip(f"{tool}: {detail}" if detail else tool)
elif event == "Notification":
    kind = d.get("notification_type", "")
    if kind == "permission_prompt":
        sys.exit(0)  # covered by the PermissionRequest hook
    labels = {"idle_prompt": "Girdi bekliyor", "elicitation_dialog": "Bir soru soruyor"}
    title = f"Claude Code · {project}"
    body = clip(labels.get(kind) or d.get("message") or "Dikkatin gerekiyor")
elif event == "Stop":
    title = f"Claude Code · {project}"
    body = "Görev tamamlandı"
else:
    sys.exit(0)

def tty_path():
    pid = os.getppid()
    for _ in range(8):
        try:
            r = subprocess.run(["ps", "-o", "tty=,ppid=", "-p", str(pid)],
                               capture_output=True, text=True, timeout=3)
            tty, ppid = r.stdout.split()[:2]
        except Exception:
            return None
        if tty not in ("??", "?"):
            return "/dev/" + tty
        pid = int(ppid)
    return None


def clean(s):
    return "".join(c for c in s if c >= " " and c != "\x7f").replace(";", ",")


sent = False
tp = tty_path()
if tp:
    try:
        with open(tp, "w") as f:
            f.write("\033]777;notify;%s;%s\a" % (clean(title), clean(body)))
        sent = True
    except Exception:
        pass
if not sent:
    script = 'on run argv\n display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"\nend run'
    try:
        subprocess.run(["osascript", "-e", script, title, body], capture_output=True, timeout=10)
    except Exception:
        pass
sys.exit(0)
