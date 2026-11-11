"""
Live check that every role agent of a profile gets its preloaded skills and its MCP tools.

Ne yapar: copies the profile's team into a scratch project, runs each role as a real subagent
through `claude -p` and asks it for its tool names and one verbatim sentence from each skill.
Nasil: preloaded skills are quoted from context, on-demand skills are first loaded with the Skill
tool; a skill counts as loaded only when five to eight words in a row of the quote are found in its file; an
`mcp__<server>__*` entry counts only when the agent reports at least one tool of that server.
MCP servers come from the repo's mcp/servers.json, not from the user's registered servers.
Calls the model, so it costs tokens and is not part of `make check`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402

PROFILE = os.environ.get("PROFILE", "fastapi-saas")
TEAM = ROOT / "src" / "templates" / "profiles" / PROFILE / "team"
USER_SKILLS = Path.home() / ".claude" / "skills"
TIMEOUT = 600
ON_DEMAND = "## Skills (load only when the task needs them)"


def norm(text):
    return re.sub(r"\W+", " ", text).strip().lower()


def quoted(quote, body):
    """True when up to eight words in a row of the quote (at least five) appear in the skill."""
    words, text = norm(quote).split(), f" {norm(body)} "
    run_length = min(8, len(words))
    return run_length >= 5 and any(f" {' '.join(words[i:i + run_length])} " in text for i in range(len(words) - run_length + 1))


def skill_body(project, name):
    for base in (project / ".claude" / "skills", USER_SKILLS):
        path = base / name / "SKILL.md"
        if path.is_file():
            return path.read_text(encoding="utf-8").split("\n---", 1)[-1]
    return ""


def on_demand(body):
    if ON_DEMAND not in body:
        return []
    section = body.split(ON_DEMAND, 1)[1].split("\n## ", 1)[0]
    return [line[3:].split("`", 1)[0] for line in section.splitlines() if line.startswith("- `")]


def probe_prompt(skills, loadable):
    wanted = ", ".join(f'"{s}": "<one full line of at least twelve words copied exactly from the body of this skill, not its name, description or a heading, or MISSING>"' for s in [*skills, *loadable])
    load = f"First load each of these skills with the Skill tool: {', '.join(loadable)}. " if loadable else ""
    return (
        f"{load}Use no other tool. Answer from your context. Reply with one JSON object and nothing else: "
        '{"tools": [every tool name you can call, exactly], "skills": {' + wanted + "}}"
    )


def mcp_config(project, servers):
    """The repo's own MCP manifest for the servers the agents name, so the check does not depend on `claude mcp add`."""
    manifest = json.loads((ROOT / "mcp" / "servers.json").read_text(encoding="utf-8"))["servers"]
    config = {s["name"]: {"type": "stdio", "command": s["command"][0], "args": s["command"][1:]}
              for s in manifest if s["name"] in servers and s["transport"] == "stdio"}
    path = project / "mcp.json"
    path.write_text(json.dumps({"mcpServers": config}), encoding="utf-8")
    return path


def ask(project, role, skills, loadable):
    prompt = (
        f"Use the Agent tool to run the `{role}` subagent with exactly this task, "
        f"then print its final reply verbatim and nothing else:\n\n{probe_prompt(skills, loadable)}"
    )
    proc = subprocess.run(
        [run.CLAUDE_BIN, "-p", "--model", "sonnet", "--output-format", "json", "--no-session-persistence",
         "--permission-mode", "dontAsk", "--allowedTools", "Agent",
         "--mcp-config", str(project / "mcp.json"), "--strict-mcp-config"],
        input=prompt, cwd=project, capture_output=True, text=True, timeout=TIMEOUT,
    )
    result = json.loads(proc.stdout)["result"]
    return json.loads(result[result.index("{"): result.rindex("}") + 1])


def check_role(project, path):
    fields, body = run.parse_agent(path.read_text(encoding="utf-8"))
    skills = fields.get("skills") or []
    loadable = on_demand(body)
    servers = [t.split("__")[1] for t in run.agent_tools(fields) if t.startswith("mcp__")]
    if not skills and not servers:
        return []
    problems = []
    # One retry: a model sometimes quotes a heading or the description instead of the body.
    for _ in range(2):
        try:
            data = ask(project, path.stem, skills, loadable)
        except Exception as exc:
            problems = [f"no answer ({exc})"]
            continue
        problems = probe_problems(project, data, skills, loadable, servers)
        if not problems:
            break
    return problems


def probe_problems(project, data, skills, loadable, servers):
    problems = []
    for skill in [*skills, *loadable]:
        quote = str(data.get("skills", {}).get(skill, "MISSING"))
        if not quoted(quote, skill_body(project, skill)):
            how = "loaded with the Skill tool" if skill in loadable else "preloaded"
            problems.append(f"skill {skill} not {how}: {quote[:120]!r}")
    tools = data.get("tools", [])
    for server in servers:
        if not any(t.startswith(f"mcp__{server}__") for t in tools):
            problems.append(f"no {server} MCP tools (is the server connected? `claude mcp list`)")
    return problems


def main():
    project = Path(tempfile.mkdtemp(prefix="agent-wiring-"))
    try:
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        shutil.copytree(TEAM / "agents", project / ".claude" / "agents")
        shutil.copytree(TEAM / "skills", project / ".claude" / "skills")
        failed = 0
        agents = [run.parse_agent(p.read_text(encoding="utf-8"))[0] for p in (project / ".claude" / "agents").glob("*.md")]
        mcp_config(project, {t.split("__")[1] for f in agents for t in run.agent_tools(f) if t.startswith("mcp__")})
        only = set(os.environ.get("ROLES", "").split())
        for path in sorted((project / ".claude" / "agents").glob("*.md")):
            if only and path.stem not in only:
                continue
            problems = check_role(project, path)
            print(f"{'FAIL' if problems else 'ok  '} {path.stem}" + "".join(f"\n     {p}" for p in problems))
            failed += bool(problems)
        print("PASS" if not failed else f"FAILED ({failed} role(s))")
        return 1 if failed else 0
    finally:
        shutil.rmtree(project, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
