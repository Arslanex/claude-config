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
for a in "$@"; do
  case "$a" in
    config) cat "$FAKE/config.json"; exit 0;;
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
        self.root = Path(tempfile.mkdtemp(prefix="dw-gate.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.fake_dir = self.root / "fake"
        self.fake_dir.mkdir()
        self.log = self.root / "calls.log"
        self.fake = self.root / "fake-docker"
        self.fake.write_text(FAKE)
        self.fake.chmod(0o755)
        self.name = self.mod.project_name(self.root)
        self.tool = self.stage(docker=str(self.fake), root=str(self.root))

    def stage(self, **conf):
        b = self.root / "bin"
        b.mkdir(exist_ok=True)
        shutil.copy(TOOL, b / "dockerw.py")
        (b / "dockerw.conf.json").write_text(json.dumps(conf))
        return b / "dockerw.py"

    def run_with(self, tool, *argv):
        env = dict(os.environ, DOCKERW_LOG=str(self.log), FAKE=str(self.fake_dir))
        return subprocess.run([sys.executable, str(tool), *argv], cwd=self.root, env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True)

    def run_tool(self, *argv):
        return self.run_with(self.tool, *argv)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def write_config(self, **parts):
        cfg = {"name": self.name, "services": {"web": {"image": "app"}}}
        cfg.update(parts)
        (self.fake_dir / "config.json").write_text(json.dumps(cfg))
        return cfg

    def bad(self, services=None, **top):
        cfg = {"services": services or {"web": {"image": "app"}}}
        cfg.update(top)
        with self.assertRaises(self.mod.Refused, msg=json.dumps(cfg)[:160]):
            self.mod.validate_config(cfg, self.root, self.root)

    def good(self, services=None, **top):
        cfg = {"services": services or {"web": {"image": "app"}}}
        cfg.update(top)
        self.mod.validate_config(cfg, self.root, self.root)


class TestValidateConfig(Base):
    def test_dangerous_service_settings_refused(self):
        for key, value in (("privileged", True), ("cap_add", ["SYS_ADMIN"]), ("devices", ["/dev/sda:/dev/sda"]),
                           ("security_opt", ["seccomp=unconfined"]), ("pid", "host"), ("ipc", "host"),
                           ("uts", "host"), ("userns_mode", "host"), ("cgroup_parent", "/x"),
                           ("network_mode", "host"), ("network_mode", "container:other"),
                           ("volumes_from", ["container:other"]), ("provider", {"type": "x"}),
                           ("device_cgroup_rules", ["c 1:3 mr"])):
            with self.subTest(key=key, value=value):
                self.bad({"web": {"image": "app", key: value}})

    def test_ordinary_services_pass(self):
        self.good({"web": {"image": "app", "network_mode": "service:db", "volumes_from": ["db"],
                           "ports": [{"published": "8000", "target": 8000}]},
                   "db": {"image": "postgres"}})

    def test_bind_mounts_must_be_inside_the_project(self):
        for src in ("/", "/etc", "/var/run/docker.sock", str(self.root.parent), ""):
            with self.subTest(src=src):
                self.bad({"web": {"image": "a", "volumes": [{"type": "bind", "source": src, "target": "/x"}]}})
        self.good({"web": {"image": "a", "volumes": [{"type": "bind", "source": str(self.root / "data"),
                                                      "target": "/x"}]}})

    def test_build_settings(self):
        base = {"context": str(self.root)}
        self.good({"web": {"build": dict(base, dockerfile="Dockerfile")}})
        self.good({"web": {"build": dict(base, additional_contexts={"x": "docker-image://alpine"})}})
        for extra in ({"context": "/etc"}, {"context": "https://example.com/r.git"}, {"ssh": ["default"]},
                      {"privileged": True}, {"entitlements": ["security.insecure"]},
                      {"cache_to": ["type=local,dest=/x"]}, {"cache_from": ["type=local,src=/x"]},
                      {"network": "host"}, {"additional_contexts": {"x": "/etc"}}, {"dockerfile": "/etc/passwd"}):
            with self.subTest(extra=extra):
                self.bad({"web": {"build": dict(base, **extra)}})

    def test_top_level_volumes_networks_secrets_configs(self):
        n = self.name
        self.good(volumes={"data": {"name": f"{n}_data"}}, networks={"default": {"name": f"{n}_default"}})
        self.bad(volumes={"data": {"name": "victim_data"}})
        self.bad(volumes={"data": {"name": f"{n}_data", "driver": "nfs"}})
        self.bad(volumes={"data": {"name": f"{n}_data",
                                   "driver_opts": {"type": "none", "o": "bind", "device": "/"}}})
        self.good(volumes={"data": {"name": f"{n}_data", "driver_opts": {"device": str(self.root / "d")}}})
        self.bad(networks={"net": {"name": "victim_default"}})
        self.bad(secrets={"k": {"file": "/etc/passwd"}})
        self.bad(configs={"c": {"file": "/etc/passwd"}})
        self.bad(secrets={"k": {"environment": "HOME"}})
        self.good(secrets={"k": {"file": str(self.root / "k.txt")}})

    def test_env_files_are_checked_before_they_are_read(self):
        v = self.mod.validate_env_files
        inside = str(self.root / ".env")
        v({"services": {"web": {"env_file": [inside]}}}, self.root, self.root)
        v({"services": {"web": {"env_file": [{"path": inside, "required": False}]}}}, self.root, self.root)
        v({"services": {"web": {"env_file": inside}}}, self.root, self.root)
        for bad in ("/etc/passwd", "~/.ssh/id_rsa", "../.env"):
            for entry in (bad, {"path": bad}):
                with self.subTest(entry=entry):
                    with self.assertRaises(self.mod.Refused):
                        v({"services": {"web": {"env_file": [entry]}}}, self.root, self.root)


class TestGateEndToEnd(Base):
    def test_gated_command_runs_the_validated_config_from_stdin(self):
        cfg = self.write_config()
        r = self.run_tool("compose", "up", "-d")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 3, calls)
        self.assertIn("config --no-env-resolution --format json", calls[0])
        self.assertTrue(calls[1].endswith("config --format json"), calls[1])
        self.assertEqual(calls[2], f"compose -p {self.name} -f - up -d")
        self.assertEqual(json.loads((self.fake_dir / "stdin.json").read_text()), cfg)

    def test_profiles_are_kept(self):
        self.write_config()
        self.run_tool("compose", "--profile", "dev", "up", "-d")
        self.assertEqual(self.calls()[2], f"compose -p {self.name} --profile dev -f - up -d")

    def test_file_options_are_consumed_by_validation(self):
        self.write_config()
        (self.root / "compose.yaml").write_text("services: {}\n")
        self.run_tool("compose", "-f", "compose.yaml", "up", "-d")
        calls = self.calls()
        self.assertIn("-f compose.yaml", calls[0])
        self.assertEqual(calls[2], f"compose -p {self.name} -f - up -d")

    def test_non_gated_commands_do_not_resolve_the_config(self):
        for argv in (("compose", "ps"), ("compose", "logs", "web"), ("compose", "stop")):
            with self.subTest(argv=argv):
                if self.log.exists():
                    self.log.unlink()
                r = self.run_tool(*argv)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(len(self.calls()), 1)
        self.assertFalse((self.fake_dir / "stdin.json").exists())

    def test_down_validates_the_config(self):
        cfg = self.write_config()
        r = self.run_tool("compose", "down")
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 3, calls)
        self.assertEqual(calls[2], f"compose -p {self.name} -f - down")
        self.assertEqual(json.loads((self.fake_dir / "stdin.json").read_text()), cfg)
        self.write_config(networks={"n": {"name": "victim_default"}})
        self.log.unlink()
        r = self.run_tool("compose", "down")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(any(c.endswith(" down") for c in self.calls()))

    def test_bad_config_is_refused_and_nothing_runs(self):
        self.write_config(services={"web": {"image": "a", "privileged": True}})
        r = self.run_tool("compose", "up", "-d")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("privileged", r.stderr)
        self.assertFalse((self.fake_dir / "stdin.json").exists())
        self.assertFalse(any(c.endswith("up -d") for c in self.calls()))

    def test_bad_env_file_is_refused_before_full_resolution(self):
        self.write_config(services={"web": {"image": "a", "env_file": ["/etc/passwd"]}})
        r = self.run_tool("compose", "up", "-d")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(self.calls()), 1)

    def test_unreadable_config_is_refused(self):
        r = self.run_tool("compose", "up", "-d")
        self.assertEqual(r.returncode, 2)
        self.assertIn("could not resolve", r.stderr)


class TestAllowedRoots(Base):
    def test_root_must_be_under_an_allowed_root(self):
        elsewhere = self.stage(docker=str(self.fake), root=str(self.root),
                               allowed_roots=[str(self.root.parent / "elsewhere")])
        r = self.run_with(elsewhere, "ps")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("allowed root", r.stderr)
        parent = self.stage(docker=str(self.fake), root=str(self.root), allowed_roots=[str(self.root.parent)])
        self.assertEqual(self.run_with(parent, "ps").returncode, 0)


if __name__ == "__main__":
    unittest.main()
