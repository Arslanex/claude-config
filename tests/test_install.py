import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"


class TestInstallDryRun(unittest.TestCase):
    def test_dry_run_prints_plan_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as home:
            claude = Path(home) / ".claude"
            claude.mkdir()
            existing = claude / "CLAUDE.md"
            existing.write_text("original")
            before = sorted(p.name for p in Path(home).rglob("*"))

            r = subprocess.run(
                ["bash", str(INSTALL), "--dry-run"],
                capture_output=True,
                text=True,
                env={"HOME": home, "PATH": os.environ["PATH"]},
                timeout=30,
            )

            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("[dry-run] backup  ", r.stdout)
            self.assertIn("hooks/guard.py", r.stdout)
            self.assertIn("nothing was changed", r.stdout)
            self.assertEqual(existing.read_text(), "original")
            self.assertEqual(sorted(p.name for p in Path(home).rglob("*")), before)
            self.assertEqual([p for p in Path(home).glob(".claude.bak-*")], [])
            self.assertFalse((claude / "hooks").exists())

    def test_unknown_flag_fails(self):
        r = subprocess.run(["bash", str(INSTALL), "--bogus"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


class TestInstallExcludes(unittest.TestCase):
    def test_cache_directories_are_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            cache = root / "src" / "templates" / "profiles" / "p" / ".cache" / "uv"
            cache.mkdir(parents=True)
            (cache / ".lock").write_text("x")
            (cache / "sdists-v10").mkdir()
            (cache / "sdists-v10" / ".git").write_text("x")
            (root / "src" / "keep.txt").write_text("keep")
            shutil.copy(INSTALL, root / "install.sh")
            home = Path(tmp) / "home"
            home.mkdir()

            r = subprocess.run(["bash", str(root / "install.sh")], capture_output=True, text=True,
                               env={"HOME": str(home), "PATH": os.environ["PATH"]}, timeout=30)

            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((home / ".claude" / "keep.txt").exists())
            self.assertFalse((home / ".claude" / "templates" / "profiles" / "p" / ".cache").exists())


def run_install(home, *args):
    return subprocess.run(
        ["bash", str(INSTALL), *args],
        capture_output=True,
        text=True,
        env={"HOME": home, "PATH": os.environ["PATH"]},
        timeout=30,
    )


class TestInstallPermissions(unittest.TestCase):
    def test_overwrites_read_only_files(self):
        with tempfile.TemporaryDirectory() as home:
            hooks = Path(home) / ".claude" / "hooks"
            hooks.mkdir(parents=True)
            target = hooks / "guard.py"
            target.write_text("old")
            target.chmod(0o555)

            r = run_install(home)

            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(target.read_text(), (ROOT / "src/hooks/guard.py").read_text())

    def test_hooks_are_read_only_after_install(self):
        with tempfile.TemporaryDirectory() as home:
            r = run_install(home)

            self.assertEqual(r.returncode, 0, r.stderr)
            files = [p for p in (Path(home) / ".claude" / "hooks").rglob("*") if p.is_file()]
            self.assertTrue(files)
            for p in files:
                self.assertEqual(p.stat().st_mode & 0o777, 0o555, p)

    def test_dry_run_does_not_change_hook_modes(self):
        with tempfile.TemporaryDirectory() as home:
            hooks = Path(home) / ".claude" / "hooks"
            hooks.mkdir(parents=True)
            target = hooks / "guard.py"
            target.write_text("old")
            target.chmod(0o644)

            r = run_install(home, "--dry-run")

            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            self.assertEqual(target.read_text(), "old")


if __name__ == "__main__":
    unittest.main()


class TestInstallConfigSource(unittest.TestCase):
    def test_install_records_the_repo_path_and_dry_run_only_prints_it(self):
        with tempfile.TemporaryDirectory() as home:
            r = run_install(home, "--dry-run")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"[dry-run] write   {home}/.claude/config-source <- {ROOT}", r.stdout)
            self.assertFalse((Path(home) / ".claude" / "config-source").exists())
            r = run_install(home)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((Path(home) / ".claude" / "config-source").read_text(), f"{ROOT}\n")
