import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "dockerw.py"
SHIM = ROOT / "tools" / "dockerw"


def load():
    spec = importlib.util.spec_from_file_location("dockerw", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.root = Path(tempfile.mkdtemp(prefix="dw-test.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))

    def check(self, *argv):
        return self.mod.check(list(argv), self.root, self.root)

    def allowed(self, *argv):
        reason, final = self.check(*argv)
        self.assertIsNone(reason, f"{argv} was refused: {reason}")
        return final

    def refused(self, *argv):
        reason, final = self.check(*argv)
        self.assertIsNotNone(reason, f"{argv} was allowed")
        self.assertIsNone(final)


class TestVerbs(Base):
    def test_read_only_and_build_commands_allowed(self):
        for argv in (["ps"], ["images"], ["logs", "-f", "web"], ["inspect", "x"], ["version"],
                     ["info"], ["system", "df"], ["build", "."], ["build", "-f", "Dockerfile", "."],
                     ["build", "-t", "x", "--build-arg", "A=1", "."]):
            with self.subTest(argv=argv):
                self.allowed(*argv)

    def test_other_verbs_refused(self):
        for verb in ("run", "rm", "rmi", "kill", "stop", "exec", "cp", "login", "push", "save",
                     "volume", "network", "container", "image", "builder", "buildx"):
            with self.subTest(verb=verb):
                self.refused(verb, "x")

    def test_system_prune_refused(self):
        self.refused("system", "prune", "-a", "--volumes", "-f")

    def test_empty_and_global_options_refused(self):
        self.refused()
        self.refused("-H", "tcp://example:2375", "ps")
        self.refused("--context", "prod", "ps")


class TestFlags(Base):
    def test_dangerous_flags_refused(self):
        for extra in (["--privileged"], ["--cap-add=SYS_ADMIN"], ["--cap-add", "ALL"], ["--device=/dev/sda"],
                      ["--security-opt", "seccomp=unconfined"], ["--pid=host"], ["--ipc", "host"],
                      ["--network=host"], ["--network", "host"], ["--net=host"], ["--userns=host"]):
            with self.subTest(extra=extra):
                self.refused("compose", "run", *extra, "web")

    def test_other_networks_allowed(self):
        self.allowed("compose", "run", "--network", "appnet", "web")

    def test_docker_socket_refused(self):
        self.refused("compose", "run", "-v", "/var/run/docker.sock:/s", "web")
        self.refused("compose", "run", "--mount", "type=bind,source=/var/run/docker.sock,target=/s", "web")
        self.refused("compose", "run", "--volume=/var/run/docker.sock:/s", "web")


class TestPaths(Base):
    def test_mounts_inside_project_allowed(self):
        self.allowed("compose", "run", "-v", "./data:/d", "web")
        self.allowed("compose", "run", "-v", "named:/d", "web")
        self.allowed("compose", "run", "--mount", "type=bind,source=./data,target=/d", "web")
        self.allowed("compose", "run", "-v", f"{self.root}/data:/d", "web")

    def test_mounts_outside_project_refused(self):
        self.refused("compose", "run", "-v", "/etc:/e", "web")
        self.refused("compose", "run", "-v", "../x:/e", "web")
        self.refused("compose", "run", "-v", "~/.ssh:/e", "web")
        self.refused("compose", "run", "--mount", "type=bind,source=/etc,target=/e", "web")
        self.refused("compose", "run", "--mount", "type=bind,target=/e", "web")

    def test_symlink_escape_refused(self):
        (self.root / "escape").symlink_to("/etc")
        self.refused("compose", "run", "-v", "./escape:/e", "web")

    def test_compose_file_and_env_file_must_be_inside(self):
        self.allowed("compose", "-f", "compose.yaml", "up")
        self.allowed("compose", "--file=compose.yaml", "up")
        self.refused("compose", "-f", "/etc/x.yml", "up")
        self.refused("compose", "--env-file", "../.env", "up")
        self.refused("compose", "--project-directory", "/", "up")

    def test_follow_flag_is_not_a_path(self):
        self.allowed("compose", "logs", "-f", "web")


class TestCompose(Base):
    def test_project_name_is_pinned(self):
        name = self.mod.project_name(self.root)
        self.assertEqual(self.allowed("compose", "up", "-d"), ["compose", "-p", name, "up", "-d"])
        self.assertEqual(self.allowed("compose", "-p", name, "up"), ["compose", "-p", name, "up"])
        self.refused("compose", "-p", "other", "up")
        self.refused("compose", "--project-name=other", "up")

    def test_allowed_subcommands(self):
        for sub in ("up", "down", "build", "ps", "logs", "config", "pull", "restart", "stop", "start",
                    "exec", "run", "images", "top", "port"):
            with self.subTest(sub=sub):
                self.allowed("compose", sub)

    def test_other_subcommands_refused(self):
        for sub in ("rm", "kill", "cp", "create", "push", "publish"):
            with self.subTest(sub=sub):
                self.refused("compose", sub)
        self.refused("compose")

    def test_down_cannot_remove_data_or_images(self):
        self.allowed("compose", "down")
        for extra in (["-v"], ["--volumes"], ["--rmi", "all"], ["--rmi=all"]):
            with self.subTest(extra=extra):
                self.refused("compose", "down", *extra)


class TestBuild(Base):
    def test_context_must_be_inside(self):
        self.refused("build", "../")
        self.refused("build", "/")
        self.refused("build", "https://example.com/repo.git")
        self.refused("build")
        self.refused("build", "-")

    def test_dockerfile_must_be_inside(self):
        self.refused("build", "-f", "/etc/passwd", ".")
        self.refused("build", "--file=/etc/passwd", ".")


class TestEndToEnd(Base):
    def setUp(self):
        super().setUp()
        self.log = self.root / "calls.log"
        self.fake = self.root / "fake-docker"
        self.fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$DOCKERW_LOG"\n')
        self.fake.chmod(0o755)

    def run_tool(self, *argv):
        env = dict(os.environ, DOCKERW_DOCKER=str(self.fake), DOCKERW_ROOT=str(self.root),
                   DOCKERW_LOG=str(self.log))
        return subprocess.run([sys.executable, str(TOOL), *argv], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def test_allowed_command_reaches_docker(self):
        r = self.run_tool("compose", "up", "-d")
        self.assertEqual(r.returncode, 0, r.stderr)
        name = self.mod.project_name(self.root)
        self.assertEqual(self.log.read_text().split(), ["compose", "-p", name, "up", "-d"])

    def test_refused_command_never_reaches_docker(self):
        r = self.run_tool("run", "--privileged", "x")
        self.assertEqual(r.returncode, 2)
        self.assertIn("refused", r.stderr)
        self.assertFalse(self.log.exists())

    def test_no_command_exits_2(self):
        self.assertEqual(self.run_tool().returncode, 2)

    def test_shim_is_executable(self):
        self.assertTrue(os.access(SHIM, os.X_OK))


if __name__ == "__main__":
    unittest.main()
