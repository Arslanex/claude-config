import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "dockerw.py"

FAKE = """#!/bin/sh
echo "$@" >> "$DOCKERW_LOG"
for a in "$@"; do
  case "$a" in
    config) cat "$FAKE/config.json"; exit 0;;
    publish=*) f="$FAKE/ps-${a#publish=}.txt"; [ -f "$f" ] && cat "$f"; exit 0;;
  esac
done
exit 0
"""


def load():
    spec = importlib.util.spec_from_file_location("dockerw", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def free_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def staged_tool(root, fake):
    """Copy the tool next to a config file, the way it is installed; env vars cannot configure it."""
    b = Path(root) / "bin"
    b.mkdir(exist_ok=True)
    shutil.copy(TOOL, b / "dockerw.py")
    (b / "dockerw.conf.json").write_text(json.dumps({"docker": str(fake), "root": str(root)}))
    return b / "dockerw.py"


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.root = Path(tempfile.mkdtemp(prefix="dw-cmd.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.fake_dir = self.root / "fake"
        self.fake_dir.mkdir()
        self.log = self.root / "calls.log"
        self.fake = self.root / "fake-docker"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.name = self.mod.project_name(self.root)

    def run_tool(self, *argv):
        env = dict(os.environ, DOCKERW_LOG=str(self.log), FAKE=str(self.fake_dir))
        return subprocess.run([sys.executable, str(staged_tool(self.root, self.fake)), *argv], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def occupy(self, port):
        s = socket.socket()
        s.bind(("0.0.0.0", port))
        s.listen(1)
        self.addCleanup(s.close)

    def config(self, services):
        spec = {svc: {"ports": [{"mode": "ingress", "target": 8000, "published": str(p), "protocol": "tcp"}]}
                for svc, p in services.items()}
        (self.fake_dir / "config.json").write_text(json.dumps({"services": spec}))

    def holder(self, port, line):
        (self.fake_dir / f"ps-{port}.txt").write_text(line + "\n")


class TestPorts(Base):
    def setUp(self):
        super().setUp()
        try:
            free_port()
        except OSError:
            self.skipTest("local port binding is not permitted here (sandbox)")

    def test_free_port(self):
        p = free_port()
        self.config({"web": p})
        r = self.run_tool("ports")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"PORT {p} web free")

    def test_foreign_process_gets_a_suggestion(self):
        p = free_port()
        self.occupy(p)
        self.config({"web": p})
        line = self.run_tool("ports").stdout.strip()
        self.assertTrue(line.startswith(f"PORT {p} web foreign-process suggest="), line)
        self.assertGreater(int(line.rsplit("=", 1)[1]), p)

    def test_own_project_container_is_reported_without_suggestion(self):
        p = free_port()
        self.occupy(p)
        self.holder(p, f"web-1|{self.name}")
        self.config({"web": p})
        self.assertEqual(self.run_tool("ports").stdout.strip(), f"PORT {p} web own")

    def test_other_project_container(self):
        p = free_port()
        self.occupy(p)
        self.holder(p, "db-1|someotherproject")
        self.config({"web": p})
        line = self.run_tool("ports").stdout.strip()
        self.assertTrue(line.startswith(f"PORT {p} web other-container suggest="), line)

    def test_unreadable_config_exits_1(self):
        r = self.run_tool("ports")
        self.assertEqual(r.returncode, 1)

    def test_no_published_ports(self):
        (self.fake_dir / "config.json").write_text(json.dumps({"services": {"web": {}}}))
        self.assertEqual(self.run_tool("ports").stdout.strip(), "PORTS none")


class TestClean(Base):
    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_dry_run_runs_nothing(self):
        r = self.run_tool("clean")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry run", r.stdout)
        self.assertEqual(self.calls(), "")

    def test_apply_prunes_only_this_projects_containers(self):
        r = self.run_tool("clean", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls().strip(),
                         f"container prune -f --filter label=com.docker.compose.project={self.name}")

    def test_include_dangling_is_not_supported(self):
        r = self.run_tool("clean", "--apply", "--include-dangling")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("not supported: unlabelled images are never pruned", r.stderr)
        self.assertEqual(self.calls().strip(), "", "docker was called")

    def test_clean_never_prunes_images_or_anything_unlabelled(self):
        for argv in (["clean"], ["clean", "--apply"], ["clean", "--include-dangling"],
                     ["clean", "--apply", "--include-dangling"]):
            self.run_tool(*argv)
        lines = self.calls().strip().splitlines()
        for line in lines:
            self.assertIn(f"label=com.docker.compose.project={self.name}", line)
        for bad in ("image", "-a", "--all", "volume", "system", "builder", "network"):
            self.assertFalse(any(bad in l.split() for l in lines), bad)

    def test_unknown_flag_refused(self):
        for flag in ("--all", "--volumes", "-a"):
            with self.subTest(flag=flag):
                r = self.run_tool("clean", flag)
                self.assertEqual(r.returncode, 2)
        self.assertEqual(self.calls(), "")


if __name__ == "__main__":
    unittest.main()
