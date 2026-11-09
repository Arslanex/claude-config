"""Second defensive review of tools/dockerw.py. Tests assert the DESIRED behaviour: an @expectedFailure test is an open finding;
when the fix lands the test reports an unexpected success: remove the decorator then.

Only a fake docker binary is used; nothing here starts a container.
"""
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

FAKE = """#!/bin/sh
echo "$@" >> "$DOCKERW_LOG"
env > "$FAKE/env.txt"
case "$*" in
  *--no-env-resolution*) cat "$FAKE/first.json"; exit 0;;
esac
for a in "$@"; do
  case "$a" in
    config)
      [ -x "$FAKE/on_config.sh" ] && "$FAKE/on_config.sh"
      if [ -f "$FAKE/fail" ]; then cat "$FAKE/fail" >&2; exit 1; fi
      cat "$FAKE/config.json"; exit 0;;
    -) cat > "$FAKE/stdin.json"; exit 0;;
  esac
done
exit 0
"""


def load():
    spec = importlib.util.spec_from_file_location("dockerw", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.root = Path(tempfile.mkdtemp(prefix="dw-rev2.")).resolve()
        self.outside = Path(tempfile.mkdtemp(prefix="dw-out.")).resolve()
        for d in (self.root, self.outside):
            self.addCleanup(lambda d=d: shutil.rmtree(d, ignore_errors=True))
        self.fake_dir = self.root / "fake"
        self.fake_dir.mkdir()
        self.log = self.root / "calls.log"
        self.fake = self.root / "fake-docker"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.name = self.mod.project_name(self.root)
        b = self.root / "bin"
        b.mkdir()
        shutil.copy(TOOL, b / "dockerw.py")
        (b / "dockerw.conf.json").write_text(json.dumps({"docker": str(self.fake), "root": str(self.root)}))
        self.tool = b / "dockerw.py"
        self.set_config({"services": {"app": {"image": "alpine"}}})

    def set_config(self, cfg, first=None):
        (self.fake_dir / "config.json").write_text(json.dumps(cfg))
        (self.fake_dir / "first.json").write_text(json.dumps(first if first is not None else cfg))

    def run_tool(self, *argv, **env):
        e = dict(os.environ, DOCKERW_LOG=str(self.log), FAKE=str(self.fake_dir), **env)
        return subprocess.run([sys.executable, str(self.tool), *argv], cwd=self.root, env=e,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def check(self, *argv):
        return self.mod.check(list(argv), self.root, self.root)


class TestUngatedComposeCommands(Base):
    """Only up/run/build/start/restart are validated; the other allowed subcommands run the raw config."""

    @unittest.expectedFailure
    def test_down_does_not_touch_networks_of_other_projects(self):
        cfg = {"services": {"app": {"image": "alpine"}}, "networks": {"n": {"name": "otherproj_default"}}}
        self.set_config(cfg)
        r = self.run_tool("compose", "down")
        self.assertEqual(r.returncode, 2, "compose down ran against an unvalidated config")

    def test_config_does_not_print_env_files_from_outside_the_project(self):
        cfg = {"services": {"app": {"env_file": [{"path": str(self.outside / "secret.env")}]}}}
        self.set_config(cfg)
        r = self.run_tool("compose", "config")
        self.assertEqual(r.returncode, 2, "compose config ran with an env_file outside the project")


class TestBuildFlags(Base):
    def test_build_does_not_forward_ssh_agent(self):
        reason, _ = self.check("compose", "build", "--ssh", "default")
        self.assertIsNotNone(reason, "--ssh was accepted")

    def test_build_does_not_push(self):
        reason, _ = self.check("compose", "build", "--push")
        self.assertIsNotNone(reason, "--push was accepted")


class TestMountParsing(Base):
    def test_mount_keys_are_case_insensitive_like_docker(self):
        with self.assertRaises(self.mod.Refused):
            self.mod.scan(["--mount", "Type=bind,Source=/etc,Target=/x"], self.root, self.root)

    def test_mount_last_duplicate_key_wins_like_docker(self):
        spec = f"type=bind,source={self.root},src=/etc,target=/x"
        with self.assertRaises(self.mod.Refused):
            self.mod.scan(["--mount", spec], self.root, self.root)


class TestPathBoundary(Base):
    def test_dockerfile_relative_to_context_cannot_leave_the_project(self):
        build = {"context": str(self.root), "dockerfile": "../../etc/hosts"}
        with self.assertRaises(self.mod.Refused):
            self.mod._validate_build("service app", build, self.root, self.root)

    def test_allowed_root_itself_is_too_broad(self):
        base = self.outside
        conf = self.root / "alt.conf.json"
        conf.write_text(json.dumps({"allowed_roots": [str(base)]}))
        self.mod.CONF = conf
        self.assertIsNone(self.mod.root_reason(base / "proj"))
        self.assertIsNotNone(self.mod.root_reason(base), "the allowed base directory itself was accepted as a project")

    def test_named_volume_must_be_exactly_project_key(self):
        root = Path("/x/foo")
        cfg = {"volumes": {"data": {"name": "foo_bar_data"}}}  # belongs to a project called foo_bar
        with self.assertRaises(self.mod.Refused):
            self.mod.validate_config(cfg, root, root)

    def test_project_name_differs_for_same_basename_in_different_places(self):
        self.assertNotEqual(self.mod.project_name("/a/app"), self.mod.project_name("/b/app"))


class TestEnvironment(Base):
    def test_ambient_credentials_are_not_passed_to_docker(self):
        self.run_tool("compose", "ps", SSH_AUTH_SOCK="/tmp/agent.sock", AWS_SECRET_ACCESS_KEY="x", GITHUB_TOKEN="y")
        seen = {line.split("=", 1)[0] for line in (self.fake_dir / "env.txt").read_text().splitlines()}
        for var in ("SSH_AUTH_SOCK", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"):
            self.assertNotIn(var, seen, f"{var} reaches docker; the env is a deny-list, not an allow-list")


class TestConfigIdentity(Base):
    def test_env_file_swapped_between_validation_and_use_is_not_run(self):
        link = self.root / "link"
        (self.root / "ok.env").write_text("A=1\n")
        (self.outside / "secret.env").write_text("SECRET=hunter2\n")
        link.symlink_to(self.root / "ok.env")
        first = {"services": {"app": {"env_file": [{"path": str(link)}]}}}
        self.set_config({"services": {"app": {"image": "alpine"}}}, first=first)
        hook = self.fake_dir / "on_config.sh"
        hook.write_text(
            f'#!/bin/sh\nln -sfn "{self.outside}/secret.env" "{link}"\n'
            f'printf \'{{"services":{{"app":{{"environment":{{"S":"%s"}}}}}}}}\' "$(cat "{link}")" > "$FAKE/config.json"\n')
        hook.chmod(0o755)
        self.run_tool("compose", "up")
        stdin = self.fake_dir / "stdin.json"
        sent = stdin.read_text() if stdin.exists() else ""
        self.assertNotIn("hunter2", sent, "content of a file validated as in-project, then swapped, reached docker")


class TestPortsOutput(Base):
    def test_ports_does_not_echo_raw_docker_stderr(self):
        (self.fake_dir / "fail").write_text("LEAK-FROM-FILE-CONTENT\n")
        r = self.run_tool("ports")
        self.assertNotIn("LEAK-FROM-FILE-CONTENT", r.stderr + r.stdout)


class TestParsingHolds(Base):
    """Green regressions for the parsing cases that were checked and are fine."""

    def test_attached_and_combined_short_options_refused(self):
        for tok in ("-f/etc/x.yml", "-v/etc:/x", "-p8080"):
            self.assertIsNotNone(self.check("compose", "run", "app", tok)[0], tok)

    def test_equals_forms_are_checked(self):
        self.assertIsNotNone(self.check("compose", "--file=/etc/x.yml", "ps")[0])
        self.assertIsNotNone(self.check("compose", "--project-name=other", "ps")[0])

    def test_repeated_project_name_must_always_match(self):
        self.assertIsNotNone(self.check("compose", "-p", "other", "-p", self.name, "ps")[0])
        self.assertIsNotNone(self.check("compose", "-p", self.name, "-p", "other", "ps")[0])

    def test_flags_after_double_dash_are_still_scanned(self):
        self.assertIsNotNone(self.check("compose", "run", "app", "--", "-v", "/etc:/x")[0])


if __name__ == "__main__":
    unittest.main()
