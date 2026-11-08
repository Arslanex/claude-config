import os
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
