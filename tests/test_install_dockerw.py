import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "tools" / "install-dockerw.sh"


class TestInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-inst.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.dest = self.tmp / "bin"
        self.projects = self.tmp / "projects"
        self.projects.mkdir()
        self.log = self.tmp / "calls.log"
        self.fake = self.tmp / "fake-docker"
        self.fake.write_text('#!/bin/sh\necho "$@" > "$DOCKERW_LOG"\n')
        self.fake.chmod(0o755)

    def install(self, *extra, roots=None):
        args = ["bash", str(INSTALLER), "--dest", str(self.dest), "--python", sys.executable,
                "--docker", str(self.fake)]
        for r in ([self.projects] if roots is None else roots):
            args += ["--root", str(r)]
        return subprocess.run(args + list(extra), capture_output=True, text=True)

    def run_shim(self, cwd, *argv, **env):
        e = dict(os.environ, DOCKERW_LOG=str(self.log))
        e.update(env)
        return subprocess.run([str(self.dest / "dockerw"), *argv], cwd=cwd, env=e,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def project(self, parent):
        proj = Path(parent) / "app"
        (proj / ".git").mkdir(parents=True)
        return proj

    def test_installs_shim_script_and_config(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        shim = (self.dest / "dockerw").read_text()
        self.assertIn(f'exec "{sys.executable}" -I "${{0%/*}}/dockerw.py"', shim)
        conf = json.loads((self.dest / "dockerw.conf.json").read_text())
        self.assertEqual(conf, {"docker": str(self.fake), "allowed_roots": [str(self.projects)]})
        for name in ("dockerw", "dockerw.py", "dockerw.conf.json"):
            with self.subTest(name=name):
                mode = (self.dest / name).stat().st_mode
                self.assertEqual(mode & 0o022, 0, "must not be group or world writable")
        self.assertTrue(os.access(self.dest / "dockerw", os.X_OK))

    def test_installed_tool_runs_inside_an_allowed_root(self):
        self.install()
        r = self.run_shim(self.project(self.projects), "ps")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.log.read_text().strip(), "ps")

    def test_installed_tool_refuses_projects_outside_the_allowed_roots(self):
        self.install()
        other = self.tmp / "other"
        other.mkdir()
        r = self.run_shim(self.project(other), "ps")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("allowed root", r.stderr)
        self.assertFalse(self.log.exists())

    def test_python_environment_cannot_hijack_the_tool(self):
        self.install()
        marker = self.tmp / "hijacked"
        evil = self.tmp / "evil"
        evil.mkdir()
        (evil / "json.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
        r = self.run_shim(self.project(self.projects), "ps", PYTHONPATH=str(evil))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(marker.exists())

    def test_running_twice_is_fine(self):
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual(self.install().returncode, 0)

    def test_a_root_is_required(self):
        r = self.install(roots=[])
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.dest / "dockerw").exists())

    def test_foreign_file_is_not_overwritten(self):
        self.dest.mkdir()
        (self.dest / "dockerw").write_text("#!/bin/sh\necho mine\n")
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertEqual((self.dest / "dockerw").read_text(), "#!/bin/sh\necho mine\n")

    def test_missing_python_is_an_error(self):
        r = self.install("--python", "/nonexistent/python3")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
