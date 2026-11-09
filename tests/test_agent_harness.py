import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_run", ROOT / "tests" / "agents" / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

ALLOWED_TOOLS = ["Read", "Grep", "Glob"]


def agent(name):
    return run.parse_agent((run.AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8"))


def tool_event(*names):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": n} for n in names]}}


class CaseFilesTest(unittest.TestCase):
    def setUp(self):
        self.cases = run.load_cases()
        self.assertTrue(self.cases, "no cases found")

    def test_cases_are_valid(self):
        for c in self.cases:
            with self.subTest(case=c["name"]):
                self.assertTrue((run.AGENTS_DIR / f"{c['agent']}.md").is_file())
                self.assertIsInstance(c["expect"], list)
                self.assertIsInstance(c["forbid"], list)
                self.assertIsInstance(c["clean"], bool)
                self.assertTrue(c["patch"].startswith("diff --git"))
                if c["clean"]:
                    self.assertEqual(c["expect"], [])

    def test_each_agent_has_expect_and_clean_case(self):
        for name in {c["agent"] for c in self.cases}:
            mine = [c for c in self.cases if c["agent"] == name]
            with self.subTest(agent=name):
                self.assertTrue(any(c["expect"] for c in mine))
                self.assertTrue(any(c["clean"] for c in mine))
        for path in run.AGENTS_DIR.glob("*-reviewer.md"):
            self.assertIn(path.stem, {c["agent"] for c in self.cases})

    def test_ids_are_in_agent_dictionary(self):
        for c in self.cases:
            _, body = agent(c["agent"])
            for i in c["expect"] + c["forbid"]:
                with self.subTest(case=c["name"], id=i):
                    self.assertIn(f"- {i}:", body)

    def test_clean_cases_forbid_whole_dictionary(self):
        for c in self.cases:
            if c["clean"]:
                _, body = agent(c["agent"])
                declared = {line[2:].split(":")[0] for line in body.splitlines()
                            if line.startswith("- ") and line[2:].split(":")[0].isupper()}
                with self.subTest(case=c["name"]):
                    self.assertEqual(set(c["forbid"]), declared)

    def test_reviewer_tools_are_read_only(self):
        for path in run.AGENTS_DIR.glob("*-reviewer.md"):
            fields, _ = run.parse_agent(path.read_text(encoding="utf-8"))
            with self.subTest(agent=path.stem):
                self.assertEqual(fields["name"], path.stem)
                self.assertEqual(run.agent_tools(fields), ALLOWED_TOOLS)


class ParserTest(unittest.TestCase):
    FOUND = "FINDING SERVICE-COMMITS HIGH app/service.py:22 service commits the session\n"

    def test_found(self):
        case = {"expect": ["SERVICE-COMMITS"], "forbid": ["ORM-LEAK"], "clean": False}
        self.assertEqual(run.match_case(case, self.FOUND), [])
        findings, none = run.parse_findings(self.FOUND)
        self.assertEqual(findings[0]["loc"], "app/service.py:22")
        self.assertFalse(none)

    def test_missing(self):
        case = {"expect": ["ORM-LEAK"], "forbid": [], "clean": False}
        self.assertEqual(run.match_case(case, self.FOUND), ["missing expected ORM-LEAK"])

    def test_forbidden_found(self):
        case = {"expect": [], "forbid": ["SERVICE-COMMITS"], "clean": False}
        self.assertEqual(run.match_case(case, self.FOUND), ["forbidden SERVICE-COMMITS found"])

    def test_no_findings(self):
        case = {"expect": [], "forbid": ["RLS-MISSING"], "clean": True}
        self.assertEqual(run.match_case(case, "NO FINDINGS\n"), [])
        self.assertTrue(run.match_case(case, "all good"))
        self.assertTrue(run.match_case(case, self.FOUND))

    def test_prose_is_not_a_finding(self):
        findings, _ = run.parse_findings("I think FINDING X HIGH a:1 y is wrong")
        self.assertEqual(findings, [])


class AllowlistTest(unittest.TestCase):
    def test_clean_stream(self):
        events = [tool_event("Read", "Grep"), {"type": "result", "result": "NO FINDINGS"}]
        self.assertEqual(run.tool_violations(events, ALLOWED_TOOLS), [])

    def test_bash_is_caught(self):
        events = run.parse_events("\n".join(json.dumps(e) for e in [
            {"type": "system", "subtype": "init"}, tool_event("Read"), tool_event("Bash")]))
        self.assertEqual(run.tool_violations(events, ALLOWED_TOOLS), ["Bash"])

    def test_final_text_prefers_result(self):
        events = [{"type": "result", "result": "NO FINDINGS"}]
        self.assertEqual(run.final_text(events), "NO FINDINGS")


if __name__ == "__main__":
    unittest.main()
