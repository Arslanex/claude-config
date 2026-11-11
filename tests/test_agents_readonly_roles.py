import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
# name -> (exact tools, model); None means the caller passes the model on each call
ROLES = {
    "file-explorer": (["Read", "Grep", "Glob"], "haiku"),
    "structure-explorer": (["Read", "Grep", "Glob"], "haiku"),
    "work-verifier": (["Read", "Grep", "Glob", "Bash"], "sonnet"),
    "plan-critic": (["Read", "Grep", "Glob"], None),
}


def load(name):
    return run.parse_agent(run.agent_file(name).read_text(encoding="utf-8"))


class ReadOnlyRolesTest(unittest.TestCase):
    """Static checks only: the model is never called here."""

    def test_frontmatter(self):
        for name, (_, model) in ROLES.items():
            fields, _ = load(name)
            expected = {"name", "description", "tools"} | ({"model"} if model else set())
            with self.subTest(agent=name):
                self.assertEqual(set(fields), expected)
                self.assertEqual(fields["name"], name)
                self.assertGreater(len(fields["description"]), 40)

    def test_tools_and_model(self):
        for name, (tools, model) in ROLES.items():
            fields, _ = load(name)
            with self.subTest(agent=name):
                self.assertEqual(run.agent_tools(fields), tools)
                self.assertEqual(fields.get("model"), model)

    def test_no_write_tool(self):
        for name in ROLES:
            fields, _ = load(name)
            with self.subTest(agent=name):
                self.assertFalse(WRITE_TOOLS & set(run.agent_tools(fields)))

    def test_say_they_are_read_only(self):
        for name in ROLES:
            _, body = load(name)
            with self.subTest(agent=name):
                self.assertRegex(body, r"(?i)never (modify|edit, write)")

    def test_explorers_skip_dot_env_and_never_quote_secrets(self):
        for name in ("file-explorer", "structure-explorer"):
            _, body = load(name)
            with self.subTest(agent=name):
                self.assertIn("Skip `.env*` files and never quote a secret value", body)

    def test_structure_explorer_reads_the_target_repo_rules_first(self):
        _, body = load("structure-explorer")
        self.assertIn("CLAUDE.md, `.claude/rules/`", body)
        self.assertLess(body.index("CLAUDE.md"), body.index("manifest and config files"))

    def test_work_verifier_docker_only_through_bare_dockerw(self):
        _, body = load("work-verifier")
        self.assertIn("`dockerw` (ps, images, system df, info only; by its bare name, called alone, never raw docker)", body)
        self.assertNotRegex(body, r"docker \((ps|images)")
        self.assertIn("`dockerw info`", body)
        self.assertIn("`dockerw system df`", body)
        self.assertNotRegex(body, r"`docker (info|system df)`")

    def test_work_verifier_has_no_hardcoded_lock_counts(self):
        _, body = load("work-verifier")
        self.assertNotRegex(body, r"approved \d+")
        self.assertRegex(body, r"(?i)counts that verify prints")

    def test_work_verifier_knows_the_dev_command_and_a_tracked_file(self):
        _, body = load("work-verifier")
        self.assertRegex(body, r"design-project, grant, kickoff, maintain, promote and remember")
        self.assertRegex(body, r"saas-fastapi is NOT global")
        self.assertNotRegex(body, r"expected: untracked")
        self.assertIn("is expected to be tracked", body)


class ChangedReviewerTextTest(unittest.TestCase):
    """The reviewers' own checks live in test_agent_harness.py; these lock only the added wording."""

    def test_security_reviewer_never_opens_dot_env(self):
        _, body = load("security-reviewer")
        self.assertIn("Never open `.env*` files (`.env.example` is fine)", body)
        self.assertRegex(body, r"never quote its value")

    def test_security_reviewer_vite_values_reuse_secret_literal(self):
        _, body = load("security-reviewer")
        line = next(l for l in body.splitlines() if l.startswith("- SECRET-LITERAL:"))
        self.assertIn("`VITE_` variable is shipped to the browser", line)
        self.assertIn("is SECRET-LITERAL even in `.env.example`", line)
        ids = {l[2:].split(":")[0] for l in body.splitlines() if l.startswith("- ") and l[2:].split(":")[0].isupper()}
        self.assertEqual(ids, {"RLS-MISSING", "DEFINER-SEARCH-PATH", "SECRET-LITERAL", "GRANT-TO-PUBLIC", "PORT-EXPOSED"})

    def test_arch_reviewer_rule_location_is_overridable_and_scope_unchanged(self):
        _, body = load("arch-reviewer")
        self.assertIn("(or wherever the repo's CLAUDE.md says they live)", body)
        self.assertIn("docs/01-architecture/ARCH-0005-katmanlar.md", body)
        self.assertNotIn("docs/decisions/", body)


if __name__ == "__main__":
    unittest.main()
