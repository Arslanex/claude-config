import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "skills_lock.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("skills_lock", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SHA40 = "a" * 40
SHA64 = "b" * 64


def entry(**kw):
    base = {"name": "x", "kind": "skill", "source": "https://example.com/r", "status": "candidate"}
    base.update(kw)
    return base


class TestValidate(unittest.TestCase):
    def setUp(self):
        self.t = load_tool()

    def problems(self, *entries):
        return self.t.validate({"version": 1, "skills": list(entries)})

    def test_real_lock_is_valid(self):
        data = json.loads((ROOT / "skills.lock").read_text())
        self.assertEqual(self.t.validate(data), [])

    def test_candidate_is_valid(self):
        self.assertEqual(self.problems(entry()), [])

    def test_unknown_status_and_key_rejected(self):
        self.assertTrue(self.problems(entry(status="trusted")))
        self.assertTrue(self.problems(entry(token="x")))

    def test_duplicate_names_rejected(self):
        self.assertTrue(self.problems(entry(), entry()))

    def test_pinned_skill_needs_full_ref_and_hash(self):
        self.assertTrue(self.problems(entry(status="pinned")))
        self.assertTrue(self.problems(entry(status="pinned", ref="main", sha256=SHA64)))
        self.assertEqual(self.problems(entry(status="pinned", ref=SHA40, sha256=SHA64)), [])

    def test_pinned_mcp_needs_version(self):
        self.assertTrue(self.problems(entry(kind="mcp", status="pinned")))
        self.assertEqual(self.problems(entry(kind="mcp", status="pinned", version="1.2.3")), [])

    def test_approved_needs_review_record(self):
        pinned = dict(status="approved", ref=SHA40, sha256=SHA64)
        self.assertTrue(self.problems(entry(**pinned)))
        self.assertTrue(self.problems(entry(**pinned, reviewed="yesterday", reviewed_by="me")))
        self.assertEqual(self.problems(entry(**pinned, reviewed="2026-11-09", reviewed_by="me")), [])


class TestPinAndDrift(unittest.TestCase):
    def setUp(self):
        self.t = load_tool()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def make_repo(self):
        repo = self.root / "repo"
        (repo / "skills" / "demo").mkdir(parents=True)
        (repo / "skills" / "demo" / "SKILL.md").write_text("one")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["init", "-q"], cwd=repo, check=True)
        subprocess.run(git + ["add", "-A"], cwd=repo, check=True)
        subprocess.run(git + ["commit", "-q", "-m", "c"], cwd=repo, check=True)
        return repo

    def test_pin_records_commit_and_content_hash(self):
        repo = self.make_repo()
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        data = {"version": 1, "skills": [entry(name="demo", source=str(repo), subpath="skills/demo")]}
        self.t.pin(data, "demo")
        e = data["skills"][0]
        self.assertEqual((e["status"], e["ref"]), ("pinned", head))
        self.assertEqual(e["sha256"], self.t.tree_hash(repo / "skills" / "demo"))
        self.assertEqual(self.t.validate(data), [])

    def test_repin_drops_approval(self):
        repo = self.make_repo()
        e = entry(name="demo", source=str(repo), subpath="skills/demo", status="approved",
                  ref=SHA40, sha256=SHA64, reviewed="2026-11-09", reviewed_by="me")
        data = {"version": 1, "skills": [e]}
        self.t.pin(data, "demo")
        self.assertEqual(data["skills"][0]["status"], "pinned")
        self.assertNotIn("reviewed", data["skills"][0])

    def test_installed_drift_is_reported(self):
        skills = self.root / "skills"
        (skills / "demo").mkdir(parents=True)
        (skills / "demo" / "SKILL.md").write_text("one")
        h = self.t.tree_hash(skills / "demo")
        data = {"version": 1, "skills": [entry(name="demo", status="pinned", ref=SHA40, sha256=h)]}
        self.assertEqual(self.t.check_installed(data, skills), [])
        (skills / "demo" / "SKILL.md").write_text("tampered")
        self.assertEqual(len(self.t.check_installed(data, skills)), 1)

    def test_missing_installed_dir_is_not_drift(self):
        data = {"version": 1, "skills": [entry(name="gone", status="pinned", ref=SHA40, sha256=SHA64)]}
        self.assertEqual(self.t.check_installed(data, self.root / "nothing"), [])


if __name__ == "__main__":
    unittest.main()
