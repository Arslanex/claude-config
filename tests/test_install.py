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


if __name__ == "__main__":
    unittest.main()
