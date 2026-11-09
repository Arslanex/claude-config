import importlib.util
import shutil
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


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)


class TestInstall(unittest.TestCase):
    def setUp(self):
        self.tool = load_tool()
        self.tmp = Path(tempfile.mkdtemp(prefix="inst-test."))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.repo = self.tmp / "src"
        (self.repo / "skills" / "alpha").mkdir(parents=True)
        (self.repo / "skills" / "alpha" / "SKILL.md").write_text("alpha\n")
        (self.repo / "skills" / "alpha" / "ref.md").write_text("ref\n")
        (self.repo / "skills" / "beta").mkdir(parents=True)
        (self.repo / "skills" / "beta" / "notes.md").write_text("no skill file\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "init")
        self.dest = self.tmp / "skills"
        self.dest.mkdir()
        self.data = {"skills": []}

    def add(self, name, status="approved"):
        self.data["skills"].append({"name": name, "kind": "skill", "source": str(self.repo),
                                    "subpath": f"skills/{name}", "status": "candidate"})
        self.tool.pin(self.data, name)
        e = self.tool.find(self.data, name)
        e["status"] = status
        return e

    def test_dry_run_changes_nothing(self):
        self.add("alpha")
        lines, problems = self.tool.install(self.data, self.dest, apply=False)
        self.assertEqual(problems, [])
        self.assertFalse((self.dest / "alpha").exists())
        self.assertTrue(any("would install" in l and "alpha" in l for l in lines))

    def test_apply_installs_and_hash_matches(self):
        e = self.add("alpha")
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertEqual(problems, [])
        self.assertTrue((self.dest / "alpha" / "SKILL.md").is_file())
        self.assertEqual(self.tool.tree_hash(self.dest / "alpha"), e["sha256"])

    def test_existing_directory_untouched(self):
        self.add("alpha")
        (self.dest / "alpha").mkdir()
        (self.dest / "alpha" / "mine.txt").write_text("keep\n")
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertEqual((self.dest / "alpha" / "mine.txt").read_text(), "keep\n")
        self.assertFalse((self.dest / "alpha" / "SKILL.md").exists())
        self.assertTrue(any("exists" in l for l in lines))

    def test_only_approved_skills(self):
        self.add("alpha", status="pinned")
        self.tool.install(self.data, self.dest, apply=True)
        self.assertFalse((self.dest / "alpha").exists())

    def test_hash_mismatch_blocks_install(self):
        e = self.add("alpha")
        e["sha256"] = "0" * 64
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertEqual(len(problems), 1)
        self.assertFalse((self.dest / "alpha").exists())

    def test_no_skill_md_is_skipped(self):
        self.add("beta")
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertEqual(problems, [])
        self.assertFalse((self.dest / "beta").exists())
        self.assertTrue(any("skipped" in l and "beta" in l for l in lines))

    def test_unsafe_name_rejected(self):
        e = self.add("alpha")
        e["name"] = "../evil"
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertTrue(problems)
        self.assertFalse((self.tmp / "evil").exists())

    def test_mcp_entries_ignored(self):
        self.data["skills"].append({"name": "pw", "kind": "mcp", "status": "approved", "version": "1"})
        lines, problems = self.tool.install(self.data, self.dest, apply=True)
        self.assertEqual(problems, [])
        self.assertEqual(list(self.dest.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
