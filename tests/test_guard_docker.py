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
                self.assertNotIn("tools/dockerw", r.stderr)

    def test_docker_push_keeps_its_money_rule(self):
        r = run_guard("docker push example/app")
        self.assertEqual(r.returncode, 2)
        self.assertIn("[money]", r.stderr)

    def test_dockerw_and_plain_mentions_are_allowed(self):
        for cmd in ("dockerw ps", "dockerw compose up -d", "dockerw compose --env-file .env.example -f compose.yaml config",
                    "dockerw ps 2>&1", "python3 tools/dockerw.py ps",
                    "echo docker ps", 'git commit -m "docker fix"', "cat docker-compose.yml",
                    "grep -r docker README.md", "ls tools"):
            with self.subTest(cmd=cmd):
                r = run_guard(cmd)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_dockerw_must_be_called_alone_by_its_bare_name(self):
        msg = ("BLOCKED [dockerw]: call dockerw alone from the project directory by its bare name "
               "(no pipe, chain, env prefix, cd or path). Other forms run inside the sandbox and fail.")
        for cmd in ("tools/dockerw ps", "./tools/dockerw compose up -d", "~/.local/bin/dockerw ps",
                    "/Users/x/.local/bin/dockerw ps", "../tools/dockerw ps", "FOO=1 dockerw ps",
                    "env FOO=1 dockerw ps", "dockerw ps | head", "dockerw ps | grep web", "dockerw ps && echo ok",
                    "dockerw ps || true", "dockerw ps; ls", "cd sub && dockerw ps", "echo $(dockerw ps)",
                    "echo `dockerw ps`", 'bash -c "dockerw ps"', "ls\ndockerw ps", "echo x | xargs dockerw ps",
                    "(dockerw ps)", "dockerw ps &"):
            with self.subTest(cmd=cmd):
                r = run_guard(cmd)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertEqual(r.stderr.strip(), msg)

    def test_dockerw_text_mentions_stay_allowed(self):
        for cmd in ('git commit -m "dockerw: fix"', "cat tools/dockerw", "grep -n dockerw src/hooks/guard.py",
                    "echo dockerw ps | cat"):
            with self.subTest(cmd=cmd):
                self.assertEqual(run_guard(cmd).returncode, 0)

    def test_other_blocks_keep_their_message(self):
        r = run_guard("sudo ls")
        self.assertEqual(r.returncode, 2)
        self.assertIn("Stop and ask the user", r.stderr)


if __name__ == "__main__":
    unittest.main()
