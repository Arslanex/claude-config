"""/grant skill: user-only, fixed presets, writes only the gitignored local settings."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = (ROOT / "src" / "skills" / "grant" / "SKILL.md").read_text()


class GrantSkill(unittest.TestCase):
    def test_only_the_user_invokes_it(self):
        self.assertIn("disable-model-invocation: true", BODY)
        self.assertIn("Only the user grants", BODY)

    def test_local_binding_preset_is_defined_with_its_risk(self):
        self.assertIn("| local-binding | `sandbox.network.allowLocalBinding: true` |", BODY)
        self.assertIn("Every localhost port is reachable", BODY)
        self.assertIn("Never add a key that is not in this table", BODY)

    def test_domains_preset_takes_only_user_named_hosts(self):
        self.assertIn("| domains `<host>...` | the hosts appended to `sandbox.network.allowedDomains` |", BODY)
        self.assertIn("never a bare `*`, an IP address, `localhost`", BODY)
        self.assertIn("a live call stays the user's", BODY)

    def test_writes_only_settings_local_and_never_with_bash(self):
        self.assertIn("Write the file with the Write or Edit tool, never with Bash", BODY)
        self.assertIn("Never edit `.claude/settings.json`", BODY)
        self.assertIn("`.claude/settings.local.json` is listed in `<root>/.gitignore`", BODY)

    def test_dev_command_and_global_rules_point_to_it(self):
        skill = ROOT / "src" / "templates" / "profiles" / "fastapi-saas" / "team" / "skills" / "saas-fastapi" / "SKILL.md"
        self.assertIn("/grant local-binding", skill.read_text())
        self.assertIn("/grant local-binding", (ROOT / "src" / "CLAUDE.md").read_text())


if __name__ == "__main__":
    unittest.main()
