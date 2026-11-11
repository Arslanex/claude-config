#!/usr/bin/env python3
"""Agent regression harness: runs each case through `claude -p` and checks the findings.

Costs tokens (one model call per case); run it via `make agent-eval`, not from `make check`.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = ROOT / "src" / "agents"
# Team roles ship with a profile (installed into the project's .claude/agents), not globally.
PROFILE_AGENTS_DIR = ROOT / "src" / "templates" / "profiles" / "fastapi-saas" / "team" / "agents"
AGENT_DIRS = (AGENTS_DIR, PROFILE_AGENTS_DIR)
CASES_DIR = Path(__file__).resolve().parent / "cases"
# Agents read the ARCH docs at docs/01-architecture/, so run from the profile that ships them.
RUN_CWD = ROOT / "src" / "templates" / "profiles" / "fastapi-saas"

# Flags verified against `claude --help`: both --agents (JSON) and --agent are supported.
# --agents defines the agent from its source file; --agent selects it. The "eval-" prefix keeps
# it from colliding with an installed copy of the same agent.
CLAUDE_BIN = "claude"
AGENT_PREFIX = "eval-"
# User settings are left out so the run does not depend on the local hooks (a Stop hook would run make check).
BASE_FLAGS = ["-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--setting-sources", "project,local"]
TIMEOUT_SECONDS = 300

FINDING_RE = re.compile(r"^FINDING (?P<id>[A-Z][A-Z0-9-]*) (?P<level>\S+) (?P<loc>\S+:\d+) (?P<desc>.+)$")
NO_FINDINGS = "NO FINDINGS"


def agent_file(name):
    """Path of the agent's source file, global or profile-shipped."""
    for d in AGENT_DIRS:
        if (d / f"{name}.md").is_file():
            return d / f"{name}.md"
    raise FileNotFoundError(f"no agent file for {name!r}")


def reviewer_files():
    return sorted(p for d in AGENT_DIRS for p in d.glob("*-reviewer.md"))


def parse_agent(text):
    """Split an agent file into (frontmatter dict, body)."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise ValueError("frontmatter must start on line 1")
    end = lines.index("---", 1)
    fields = {}
    key = None
    for line in lines[1:end]:
        if line.startswith("  - ") and isinstance(fields.get(key), list):
            fields[key].append(line[4:].strip())
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"bad frontmatter line: {line!r}")
        key = key.strip()
        fields[key] = value.strip() or []
    return fields, "\n".join(lines[end + 1:]).strip()


def agent_tools(fields):
    return [t.strip() for t in fields.get("tools", "").split(",") if t.strip()]


def parse_findings(text):
    """Return (list of finding dicts, whether a NO FINDINGS line is present)."""
    findings, none = [], False
    for raw in text.splitlines():
        line = raw.strip()
        m = FINDING_RE.match(line)
        if m:
            findings.append(m.groupdict())
        elif line == NO_FINDINGS:
            none = True
    return findings, none


def match_case(case, text):
    """Return a list of failure reasons (empty means the case passed)."""
    findings, none = parse_findings(text)
    ids = {f["id"] for f in findings}
    problems = [f"missing expected {i}" for i in case.get("expect", []) if i not in ids]
    problems += [f"forbidden {i} found" for i in case.get("forbid", []) if i in ids]
    if case.get("clean"):
        if not none:
            problems.append("clean case: NO FINDINGS line missing")
        if findings:
            problems.append("clean case: FINDING lines present")
    return problems


def iter_tool_uses(events):
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        content = (ev.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name", "")


def tool_violations(events, allowed):
    """Sorted tool names used that are not in the agent's allowed list."""
    return sorted({name for name in iter_tool_uses(events) if name not in allowed})


def parse_events(stdout):
    events = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def final_text(events):
    """Text of the final result event, else all assistant text blocks joined."""
    for ev in reversed(events):
        if ev.get("type") == "result" and isinstance(ev.get("result"), str):
            return ev["result"]
    parts = []
    for ev in events:
        if ev.get("type") == "assistant":
            for block in (ev.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts)


def load_cases(cases_dir=CASES_DIR):
    cases = []
    for d in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        case = json.loads((d / "case.json").read_text(encoding="utf-8"))
        case["name"] = d.name
        case["patch"] = (d / "input.patch").read_text(encoding="utf-8")
        cases.append(case)
    return cases


def build_command(agent_name, fields, body):
    name = AGENT_PREFIX + agent_name
    spec = {name: {"description": fields.get("description", ""), "prompt": body, "tools": agent_tools(fields)}}
    if fields.get("model"):
        spec[name]["model"] = fields["model"]
    if fields.get("skills"):
        spec[name]["skills"] = fields["skills"]
    return [CLAUDE_BIN, *BASE_FLAGS, "--agents", json.dumps(spec), "--agent", name]


def run_case(case):
    fields, body = parse_agent(agent_file(case["agent"]).read_text(encoding="utf-8"))
    prompt = f"Review this diff:\n\n{case['patch']}"
    proc = subprocess.run(
        build_command(case["agent"], fields, body), input=prompt, capture_output=True,
        text=True, cwd=RUN_CWD, timeout=TIMEOUT_SECONDS,
    )
    events = parse_events(proc.stdout)
    problems = match_case(case, final_text(events))
    bad = tool_violations(events, agent_tools(fields))
    if bad:
        problems.append("tool allowlist violation: " + ", ".join(bad))
    if proc.returncode != 0 and not events:
        problems.append(f"claude exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    return problems


def main():
    failed = 0
    only = set(os.environ.get("CASES", "").split())
    cases = [c for c in load_cases() if not only or c["name"] in only]
    for case in cases:
        try:
            problems = run_case(case)
        except Exception as exc:  # a crashed case counts as a failure, the rest still run
            problems = [f"harness error: {exc}"]
        if problems:
            failed += 1
            print(f"FAIL {case['name']}: " + "; ".join(problems))
        else:
            print(f"OK   {case['name']}")
    print(f"\n{len(cases) - failed}/{len(cases)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
