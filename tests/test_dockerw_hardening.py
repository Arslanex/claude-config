import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "dockerw.py"


def load():
    spec = importlib.util.spec_from_file_location("dockerw", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.root = Path(tempfile.mkdtemp(prefix="dw-hard.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.log = self.root / "calls.log"
        self.fake = self.root / "fake-docker"
        self.fake.write_text('#!/bin/sh\n/usr/bin/env > "$DOCKERW_LOG"\n')
        self.fake.chmod(0o755)

    def stage(self, **conf):
        b = self.root / "bin"
        b.mkdir(exist_ok=True)
        shutil.copy(TOOL, b / "dockerw.py")
        (b / "dockerw.conf.json").write_text(json.dumps(conf))
        return b / "dockerw.py"

    def run_tool(self, tool, *argv, cwd=None, **env):
        e = dict(os.environ, DOCKERW_LOG=str(self.log))
        e.update(env)
        return subprocess.run([sys.executable, str(tool), *argv], cwd=cwd or self.root, env=e,
                              capture_output=True, text=True)


class TestEnvironment(Base):
    def test_docker_and_compose_env_is_scrubbed_and_path_is_fixed(self):
        tool = self.stage(docker=str(self.fake), root=str(self.root))
        r = self.run_tool(tool, "ps", DOCKER_HOST="tcp://evil:2375", DOCKER_CONFIG="/tmp/c",
                          COMPOSE_FILE="/etc/x.yml", BUILDX_BUILDER="evil", PATH="/tmp/evil:/usr/bin:/bin")
        self.assertEqual(r.returncode, 0, r.stderr)
        seen = self.log.read_text()
        for bad in ("DOCKER_HOST=", "DOCKER_CONFIG=", "COMPOSE_FILE=", "BUILDX_BUILDER="):
            self.assertNotIn(bad, seen)
        self.assertNotIn("/tmp/evil", seen)

    def test_env_cannot_override_docker_binary_or_root(self):
        tool = self.stage(docker=str(self.fake), root=str(self.root))
        r = self.run_tool(tool, "ps", DOCKERW_DOCKER="/nonexistent/docker")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.log.exists())
        r = self.run_tool(tool, "build", "../", DOCKERW_ROOT=str(self.root.parent))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class TestRoot(Base):
    def test_too_broad_roots_refused_everywhere(self):
        for broad in ("/", str(Path.home())):
            tool = self.stage(docker=str(self.fake), root=broad)
            for argv in (("ps",), ("ports",), ("clean",)):
                with self.subTest(root=broad, argv=argv):
                    r = self.run_tool(tool, *argv)
                    self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                    self.assertIn("too broad", r.stderr)
        self.assertFalse(self.log.exists())

    def test_check_refuses_broad_root(self):
        for broad in (Path("/"), Path.home()):
            with self.subTest(root=str(broad)):
                reason, final = self.mod.check(["ps"], broad, broad)
                self.assertIsNotNone(reason)
                self.assertIsNone(final)

    def test_root_is_found_by_walking_up_to_git(self):
        proj = self.root / "proj"
        (proj / ".git").mkdir(parents=True)
        (proj / "sub").mkdir()
        tool = self.stage(docker=str(self.fake))
        self.assertEqual(self.run_tool(tool, "build", "..", cwd=proj / "sub").returncode, 0)
        self.assertEqual(self.run_tool(tool, "build", "../..", cwd=proj / "sub").returncode, 2)


if __name__ == "__main__":
    unittest.main()
