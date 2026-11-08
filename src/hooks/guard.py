#!/usr/bin/env python3
"""PreToolUse guard for the Bash tool.

Blocks (exit 2) commands that spend money or weaken security so autonomous
agents can run freely everywhere else. Fails open on malformed input.
Heuristic regexes on the command text; the sandbox and permission rules
remain the primary controls.
"""
import json
import re
import subprocess
import sys

try:
    data = json.load(sys.stdin)
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or None
except Exception:
    sys.exit(0)

# Start of a command segment (allows ENV=1 prefixes)
A = r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+)*"
PROTECTED = {"main", "master", "production", "prod"}


def block(kind, why):
    print(
        f"BLOCKED [{kind}]: {why}. Do not retry or work around this. "
        "Stop and ask the user for explicit approval.",
        file=sys.stderr,
    )
    sys.exit(2)


RULES = [
    ("security", "sudo is not allowed", A + r"sudo\b"),
    ("security", "force push is not allowed",
     r"\bgit\s+push\b[^;&|\n]*(?:\s--force\b|\s-f\b|--force-with-lease|\s\+\S)"),
    ("security", "push to a protected branch (main/master/production)",
     r"\bgit\s+push\b[^;&|\n]*\b(?:main|master|production|prod)\b"),
    ("security", "piping a download into a shell",
     r"\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"),
    ("security", "git reset --hard / git clean -f discards work",
     r"\bgit\s+(?:reset\s+--hard|clean\s+-\w*f)"),
    ("security", "recursive delete of a broad path",
     r"\brm\s+(?:-\w+\s+)*-\w*[rR]\w*\s+(?:-\w+\s+)*"
     r"(?:/|/\*|~|~/|~/\*|\$HOME|\$HOME/|\.\.|\.\./\S*|\*)(?=\s|$)"),
    ("security", "destructive SQL",
     r"\b(?:drop\s+(?:table|database|schema)|truncate\s+table)\b"),
    ("money", "terraform/tofu apply or destroy changes real infrastructure",
     A + r"(?:terraform|tofu)\s+(?:apply|destroy)\b"),
    ("money", "pulumi up/destroy changes real infrastructure",
     A + r"pulumi\s+(?:up|destroy)\b"),
    ("money", "wrangler deploy/publish/delete",
     A + r"(?:npx\s+)?wrangler\s+(?:deploy|publish|delete|pages\s+deploy|versions\s+deploy)\b"),
    ("money", "fly.io deploy/scale/create",
     A + r"(?:fly|flyctl)\s+(?:deploy|launch|scale|machines?\s+(?:run|create)|"
         r"volumes?\s+create|apps?\s+create)\b"),
    ("money", "netlify deploy", A + r"(?:npx\s+)?netlify\s+deploy\b"),
    ("money", "vercel deploy",
     A + r"(?:npx\s+)?vercel(?=\s|$)(?!\s+(?:whoami|ls|list|inspect|logs|help|--version|-v)\b)"),
    ("money", "heroku create/scale/addons",
     A + r"heroku\s+(?:create|addons:create|ps:scale|ps:resize|pipelines:promote)\b"),
    ("money", "publishing a package or image",
     A + r"(?:(?:npm|pnpm|yarn|bun)\s+publish|twine\s+upload|cargo\s+publish|docker\s+push)\b"),
    ("money", "stripe CLI can touch real payments",
     A + r"stripe(?=\s|$)(?!\s+(?:listen|logs|--version|version|help|login)\b)"),
]

for kind, why, pat in RULES:
    if re.search(pat, cmd, re.I):
        block(kind, why)

# Cloud CLIs: allow only clearly read-only invocations
if re.search(A + r"(?:aws|gcloud|az|doctl)(?=\s|$)", cmd):
    read = re.search(r"\b(?:list|ls|describe|get|show|help|version|whoami)\b", cmd)
    mutate = re.search(
        r"\b(?:create|run|start|launch|delete|terminate|update|put|deploy|apply|publish|"
        r"invoke|scale|rm|remove|attach|enable|modify|purchase|allocate|destroy|import|"
        r"insert|copy|cp|mv|sync)", cmd)
    if not read or mutate:
        block("money", "cloud CLI command that may create or change billable resources")

# Bare `git push` while a protected branch is checked out
if re.search(r"\bgit\s+push\b", cmd):
    try:
        br = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        br = ""
    if br in PROTECTED:
        block("security", f"git push while on protected branch '{br}'")

sys.exit(0)
