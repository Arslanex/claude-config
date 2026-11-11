import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

PROFILE = ROOT / "src" / "templates" / "profiles" / "fastapi-saas"
TEAM_SKILLS = PROFILE / "team" / "skills"
GLOBAL_SKILLS = ROOT / "src" / "skills"
LOCK = json.loads((ROOT / "skills.lock").read_text(encoding="utf-8"))
SERVERS = {s["name"] for s in json.loads((ROOT / "mcp" / "servers.json").read_text(encoding="utf-8"))["servers"]}
ROLES = ["architect", "backend", "frontend", "tester", "devops"]


def fields(name):
    return run.parse_agent(run.agent_file(name).read_text(encoding="utf-8"))[0]


ON_DEMAND = "## Skills (load only when the task needs them)"


def on_demand(name):
    body = run.parse_agent(run.agent_file(name).read_text(encoding="utf-8"))[1]
    if ON_DEMAND not in body:
        return []
    section = body.split(ON_DEMAND, 1)[1].split("\n## ", 1)[0]
    return [line[3:].split("`", 1)[0] for line in section.splitlines() if line.startswith("- `")]


def frontmatter_flag(path, flag):
    head = path.read_text(encoding="utf-8").split("\n---", 1)[0]
    return f"{flag}: true" in head


class AgentSkillsWiringTest(unittest.TestCase):
    """Every skill and MCP tool a role relies on must be reachable from its agent file."""

    def test_each_role_preloads_skills_that_exist_and_can_be_preloaded(self):
        approved = {s["name"] for s in LOCK["skills"] if s["status"] == "approved"}
        for role in ROLES:
            skills = fields(role).get("skills")
            with self.subTest(role=role):
                self.assertIsInstance(skills, list)
                self.assertTrue(skills)
                for skill in [*skills, *on_demand(role)]:
                    local = TEAM_SKILLS / skill / "SKILL.md"
                    if local.is_file():
                        self.assertFalse(frontmatter_flag(local, "disable-model-invocation"), skill)
                    else:
                        self.assertIn(skill, approved, f"{role}: {skill} is neither a profile skill nor approved in skills.lock")

    def test_mcp_tools_point_at_a_configured_server(self):
        for role in ROLES:
            for tool in run.agent_tools(fields(role)):
                if tool.startswith("mcp__"):
                    with self.subTest(role=role, tool=tool):
                        self.assertIn(tool.split("__")[1], SERVERS)

    def test_on_demand_skills_need_the_skill_tool_and_are_not_preloaded(self):
        for role in ROLES:
            with self.subTest(role=role):
                self.assertIn("Skill", run.agent_tools(fields(role)))
                self.assertFalse(set(on_demand(role)) & set(fields(role)["skills"]))

    def test_large_reference_skills_are_never_preloaded(self):
        for role in ROLES:
            for skill in fields(role)["skills"]:
                if (TEAM_SKILLS / skill).is_dir():
                    continue
                with self.subTest(role=role, skill=skill):
                    self.assertEqual(skill, "docker-destructive-guardrails", "only the docker safety rule is preloaded from outside the profile")

    def test_doc_lookup_roles_reach_context7_and_know_the_query_rule(self):
        team = (PROFILE / "team" / "team.md").read_text(encoding="utf-8")
        table = team.split("## Skills and MCP by role", 1)[1].split("\n## ", 1)[0]
        for role in ROLES:
            with self.subTest(role=role):
                self.assertIn("mcp__context7__*", run.agent_tools(fields(role)))
                body = run.agent_file(role).read_text(encoding="utf-8")
                self.assertIn("Never put project code, data, file contents or secrets in it", body)
                self.assertIn("look it up in the official docs through Context7", body)
                self.assertIn("at the version the repo pins. Never write an API from memory when unsure.", body)
                self.assertIn("- Docs checked: library, version, topic, in one line.", body)
                label = "DevOps" if role == "devops" else role.capitalize()
                row = next(l for l in table.splitlines() if l.startswith(f"| {label} |"))
                self.assertIn("Context7 (`mcp__context7__*`)", row)

    def test_mcp_servers_are_pinned_and_approved(self):
        manifest = json.loads((ROOT / "mcp" / "servers.json").read_text(encoding="utf-8"))["servers"]
        lock = {s["name"]: s for s in LOCK["skills"]}
        context7 = next(s for s in manifest if s["name"] == "context7")
        self.assertEqual(context7["command"][-1], f"@upstash/context7-mcp@{lock['context7']['version']}")
        self.assertEqual(lock["context7"]["status"], "approved")

    def test_context7_queries_pass_the_guard_hook(self):
        settings = json.loads((ROOT / "src" / "settings.json").read_text(encoding="utf-8"))
        entry = next(h for h in settings["hooks"]["PreToolUse"] if h["matcher"] == "mcp__context7__.*")
        self.assertIn("context7-guard.py", entry["hooks"][0]["command"])
        self.assertTrue((ROOT / "src" / "hooks" / "context7-guard.py").is_file())

    def test_sast_is_pinned_and_runs_in_verify_full_not_check(self):
        make = (PROFILE / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(make, r"SEMGREP_VERSION := \d+\.\d+\.\d+")
        self.assertIn("--metrics=off", make)
        check = next(line for line in make.splitlines() if line.startswith("check:"))
        self.assertNotIn("sast", check)
        self.assertIn("$(MAKE) sast;", make)

    def test_browser_roles_reach_playwright(self):
        for role in ("frontend", "tester"):
            self.assertIn("mcp__playwright__*", run.agent_tools(fields(role)))

    def test_team_table_lists_only_what_the_agents_load(self):
        team = (PROFILE / "team" / "team.md").read_text(encoding="utf-8")
        section = team.split("## Skills and MCP by role", 1)[1].split("\n## ", 1)[0]
        section = "\n".join(line for line in section.splitlines() if line.startswith("|"))
        for gone in ("FastAPI skill", "modern-python", "postgres-mcp", "semgrep"):
            self.assertNotIn(gone, section)
        for role in ROLES:
            row = next(line for line in section.splitlines() if line.startswith(f"| {role.capitalize()}") or line.startswith("| DevOps") and role == "devops")
            for skill in [*fields(role)["skills"], *on_demand(role)]:
                with self.subTest(role=role, skill=skill):
                    self.assertIn(skill, row)


if __name__ == "__main__":
    unittest.main()
