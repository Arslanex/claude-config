import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUP = ROOT / "setup-mcp.sh"
MANIFEST = ROOT / "mcp" / "servers.json"

# Fake claude: logs every call; `mcp get <name>` succeeds only for names in $FAKE_EXISTING.
FAKE_CLAUDE = """#!/bin/bash
echo "$*" >> "$FAKE_LOG"
if [ "$1 $2" = "mcp get" ]; then
  for n in $FAKE_EXISTING; do [ "$n" = "$3" ] && exit 0; done
  exit 1
fi
exit 0
"""


def run_setup(args, existing="", with_claude=True, extra_env=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bindir = tmp / "bin"
        bindir.mkdir()
        log = tmp / "calls.log"
        log.touch()
        if with_claude:
            fake = bindir / "claude"
            fake.write_text(FAKE_CLAUDE)
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        else:
            (bindir / "python3").symlink_to(shutil.which("python3"))
        base = "/usr/bin:/bin"
        env = {
            "HOME": str(tmp),
            "PATH": f"{bindir}:{os.environ['PATH']}" if with_claude else f"{bindir}:{base}",
            "FAKE_LOG": str(log),
            "FAKE_EXISTING": existing,
        }
        env.update(extra_env or {})
        r = subprocess.run(["bash", str(SETUP), *args], capture_output=True, text=True, env=env, timeout=30)
        return r, log.read_text().splitlines()


class TestSetupMcp(unittest.TestCase):
    def test_adds_missing_servers(self):
        r, calls = run_setup([])
        self.assertEqual(r.returncode, 0, r.stderr)
        adds = [c for c in calls if c.startswith("mcp add")]
        self.assertIn(
            "mcp add --scope user --transport stdio playwright -- npx -y @playwright/mcp@0.0.84 --browser chromium",
            adds,
        )
        self.assertIn("mcp add --scope user --transport http cloudflare-api https://mcp.cloudflare.com/mcp", adds)
        self.assertIn("run /mcp and authenticate with Cloudflare", r.stdout)

    def test_skips_existing_servers(self):
        r, calls = run_setup([], existing="playwright")
        self.assertEqual(r.returncode, 0, r.stderr)
        adds = [c for c in calls if c.startswith("mcp add")]
        self.assertEqual(len(adds), 2)
        self.assertIn("cloudflare-api", adds[0])
        self.assertIn("context7", adds[1])
        self.assertIn("skip   playwright", r.stdout)

    def test_all_existing_adds_nothing(self):
        r, calls = run_setup([], existing="playwright cloudflare-api context7")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c for c in calls if c.startswith("mcp add")], [])

    def test_dry_run_never_adds(self):
        r, calls = run_setup(["--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([c for c in calls if c.startswith("mcp add")], [])
        self.assertIn("[dry-run] add", r.stdout)
        self.assertIn("nothing was changed", r.stdout)

    def test_missing_claude_fails_clearly(self):
        if any(Path(d, "claude").exists() for d in ("/usr/bin", "/bin")):
            self.skipTest("a real claude is in the base PATH")
        r, _ = run_setup([], with_claude=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("'claude' not found", r.stderr)

    def test_unknown_flag_fails(self):
        r, _ = run_setup(["--bogus"])
        self.assertEqual(r.returncode, 1)


class TestEnvRequired(unittest.TestCase):
    def test_warns_by_name_and_never_prints_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mcp").mkdir()
            shutil.copy(SETUP, root / "setup-mcp.sh")
            (root / "mcp" / "servers.json").write_text(
                json.dumps(
                    {
                        "servers": [
                            {
                                "name": "x",
                                "scope": "user",
                                "transport": "http",
                                "url": "https://example.com/mcp",
                                "env_required": ["SET_VAR", "UNSET_VAR"],
                            }
                        ]
                    }
                )
            )
            bindir = root / "bin"
            bindir.mkdir()
            fake = bindir / "claude"
            fake.write_text(FAKE_CLAUDE)
            fake.chmod(0o755)
            env = {
                "HOME": tmp,
                "PATH": f"{bindir}:{os.environ['PATH']}",
                "FAKE_LOG": str(root / "log"),
                "FAKE_EXISTING": "",
                "SET_VAR": "super-secret-value",
            }
            r = subprocess.run(
                ["bash", str(root / "setup-mcp.sh"), "--dry-run"], capture_output=True, text=True, env=env, timeout=30
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("UNSET_VAR", r.stderr)
            self.assertNotIn("variable SET_VAR,", r.stderr)
            self.assertNotIn("super-secret-value", r.stdout + r.stderr)


class TestManifest(unittest.TestCase):
    ALLOWED = {"name", "scope", "transport", "command", "url", "env_required", "notes", "post_install"}
    SECRET = re.compile(r"ghp_|github_pat_|sk-|Bearer|[A-Za-z0-9+/_=-]{40,}")

    def setUp(self):
        self.data = json.loads(MANIFEST.read_text())

    def test_only_allowed_keys(self):
        self.assertEqual(set(self.data), {"servers"})
        for s in self.data["servers"]:
            self.assertLessEqual(set(s), self.ALLOWED, s["name"])
            self.assertTrue({"name", "scope", "transport"} <= set(s))
            if s["transport"] == "stdio":
                self.assertIsInstance(s["command"], list)
            else:
                self.assertTrue(s["url"].startswith("https://"))

    def test_env_required_holds_only_names(self):
        for s in self.data["servers"]:
            for var in s.get("env_required", []):
                self.assertRegex(var, r"^[A-Z_][A-Z0-9_]*$")

    def test_no_secret_like_values(self):
        def strings(o):
            if isinstance(o, str):
                yield o
            elif isinstance(o, list):
                for i in o:
                    yield from strings(i)
            elif isinstance(o, dict):
                for i in o.values():
                    yield from strings(i)

        for value in strings(self.data):
            self.assertIsNone(self.SECRET.search(value), value)


class TestClaudeZsh(unittest.TestCase):
    @unittest.skipUnless(shutil.which("zsh"), "zsh not installed")
    def test_syntax(self):
        r = subprocess.run(
            ["zsh", "-n", str(ROOT / "src" / "shell" / "claude.zsh")], capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
