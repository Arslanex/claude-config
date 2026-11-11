"""
Full mode (`cfull`) is opt-in per session, and the default sandbox rules point to per-command hosts and /grant.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL = (ROOT / "src" / "shell" / "claude.zsh").read_text(encoding="utf-8")
RULES = (ROOT / "src" / "CLAUDE.md").read_text(encoding="utf-8")


class FullModeTest(unittest.TestCase):
    def test_cfull_disables_sandbox_and_prompts_for_one_session_only(self):
        self.assertIn("cfull() {", SHELL)
        self.assertIn("--permission-mode bypassPermissions", SHELL)
        self.assertIn('--settings \'{"sandbox":{"enabled":false,"failIfUnavailable":false}}\'', SHELL)

    def test_default_mode_uses_allowed_domains_and_grant(self):
        self.assertIn("with that host in `allowed_domains`", RULES)
        self.assertIn("`/grant domains <host>`", RULES)
        self.assertIn("Never turn the sandbox off yourself", RULES)
        self.assertIn("Hard blocks stay in every mode", RULES)


if __name__ == "__main__":
    unittest.main()
