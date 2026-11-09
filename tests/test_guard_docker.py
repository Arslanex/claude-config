import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "src" / "hooks" / "guard.py"


def run_guard(cmd):
    payload = json.dumps({"tool_input": {"command": cmd}, "cwd": str(ROOT)})
    return subprocess.run([sys.executable, str(GUARD)], input=payload, capture_output=True, text=True)


class TestRawDocker(unittest.TestCase):
    def test_raw_docker_is_blocked_and_points_to_dockerw(self):
        for cmd in ("docker ps", "docker compose up -d", "docker-compose up", "docker run --privileged x",
                    "docker system prune -a --volumes -f", "/usr/local/bin/docker ps", "env FOO=1 docker ps",
                    'bash -c "docker ps"', "echo hi && docker ps", "X=$(docker ps -q)",
                    "echo x | xargs docker rm", "timeout 5 docker logs web", "podman ps", "nerdctl run x",
                    "colima status", "orbctl list"):
            with self.subTest(cmd=cmd):
                r = run_guard(cmd)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("dockerw", r.stderr)

    def test_docker_push_keeps_its_money_rule(self):
        r = run_guard("docker push example/app")
        self.assertEqual(r.returncode, 2)
        self.assertIn("[money]", r.stderr)

    def test_dockerw_and_plain_mentions_are_allowed(self):
        for cmd in ("tools/dockerw ps", "./tools/dockerw compose up -d", "python3 tools/dockerw.py ps",
                    "echo docker ps", 'git commit -m "docker fix"', "cat docker-compose.yml",
                    "grep -r docker README.md", "ls tools"):
            with self.subTest(cmd=cmd):
                r = run_guard(cmd)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_blocks_keep_their_message(self):
        r = run_guard("sudo ls")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Stop and ask the user", r.stderr)


if __name__ == "__main__":
    unittest.main()
