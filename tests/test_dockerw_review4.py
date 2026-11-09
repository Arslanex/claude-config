"""Fourth defensive review of tools/dockerw.py, tools/install-dockerw.sh and the installed conf.

Every finding (F1-F18) is closed and its test asserts the fixed behaviour; a failing test here is a regression.
test_udp_port_in_use_is_not_reported_free is skipped where local ports cannot be bound (the Claude sandbox): run it
outside the sandbox. Only fake docker binaries are used.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_dockerw_review2 import Base as RevBase, TOOL, load
from test_install_dockerw import INSTALLER


class TestComposeFlagEscapes(RevBase):
    def refused(self, *argv):
        reason, _ = self.check(*argv)
        self.assertIsNotNone(reason, f"allowed: {argv}")

    def test_config_output_flag_writes_a_host_file_outside_the_project(self):
        # docker compose config -o/--output FILE; dockerw runs outside the sandbox, so this is a host file write.
        for flag in (["-o", str(self.outside / "x")], ["--output", str(self.outside / "x")],
                     [f"--output={self.outside}/x"], [f"-o{self.outside}/x"]):
            self.refused("compose", "config", *flag)

    def test_output_flag_is_refused_for_every_subcommand_even_inside_the_project(self):
        for sub in ("config", "ps", "logs", "images", "up"):
            for flag in (["-o", "out.yml"], ["--output", "out.yml"], ["--output=out.yml"], ["-oout.yml"]):
                self.refused("compose", sub, *flag)

    def test_run_env_from_file_reads_a_host_file_outside_the_project(self):
        out = str(self.outside / "secret.env")
        self.refused("compose", "run", "--env-from-file", out, "app", "env")
        self.refused("compose", "run", f"--env-from-file={out}", "app", "env")
        self.refused("compose", "run", "--env-from-file", "../secret.env", "app", "env")
        self.refused("compose", "run", "--env-from-file", "~/.aws/credentials", "app", "env")
        self.refused("compose", "run", "--env-from-file")  # missing value

    def test_run_env_from_file_inside_the_project_is_allowed(self):
        (self.root / "ok.env").write_text("A=1\n")
        for argv in (["--env-from-file", "ok.env"], [f"--env-from-file={self.root}/ok.env"]):
            reason, _ = self.check("compose", "run", *argv, "app", "env")
            self.assertIsNone(reason, reason)

    def test_env_from_file_symlink_to_outside_is_refused(self):
        (self.outside / "secret.env").write_text("S=1\n")
        (self.root / "link.env").symlink_to(self.outside / "secret.env")
        self.refused("compose", "run", "--env-from-file", "link.env", "app", "env")

    def test_unknown_global_flags_are_refused_not_silently_dropped(self):
        # --dry-run used to be dropped from the rebuilt argv, so `down` really ran. Flags before the subcommand that
        # dockerw does not know are refused (no pass-through) and nothing reaches docker.
        for flag in (["--dry-run"], ["--compatibility"], ["--all-resources"], ["--whatever"], ["-x"]):
            for sub in ("down", "ps", "config"):
                self.refused("compose", *flag, sub)
        r = self.run_tool("compose", "--dry-run", "down")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("--dry-run", r.stderr)
        self.assertFalse(self.log.exists() and self.log.read_text().strip(), "docker was called")

    def test_known_global_flags_still_work(self):
        for argv in (["-p", self.name, "ps"], [f"--project-name={self.name}", "ps"], ["--profile", "dev", "ps"],
                     ["--profile=dev", "ps"], ["--ansi", "never", "ps"], ["--progress=plain", "ps"],
                     ["--parallel", "2", "ps"], ["-f", "compose.yaml", "ps"], ["--env-file", ".env", "ps"],
                     ["--project-directory", ".", "ps"]):
            reason, _ = self.check("compose", *argv)
            self.assertIsNone(reason, f"{argv}: {reason}")

    def test_stdin_compose_file_is_refused(self):
        # `-f -` passes inside(); dockerw's own config calls inherit the caller's stdin.
        for sub in ("up", "ps", "config", "pull"):
            self.refused("compose", "-f", "-", sub)
            self.refused("compose", "--file=-", sub)
            self.refused("compose", "-f=-", sub)
            self.refused("compose", "-f", "compose.yaml", "-f", "-", sub)

    def test_remote_compose_file_urls_are_refused(self):
        # inside() reads "oci://host/x:1" as a relative path, so remote compose files pass as in-project.
        for f in ("oci://evil.example/stack:1", "https://evil.example/c.git", "git@evil.example:a/b.git",
                  "http://evil.example/c.yml", "git://evil.example/r.git", "docker://x/y"):
            for argv in (["-f", f], [f"--file={f}"], ["-f", "compose.yaml", "-f", f]):
                self.refused("compose", *argv, "ps")

    def test_local_compose_files_are_still_allowed(self):
        for argv in (["-f", "compose.yaml"], ["--file=compose.yaml"], ["-f", "a.yml", "-f", "b.yml"],
                     ["-f", "sub/compose-1.yml"], ["-f", f"{self.root}/compose.yaml"]):
            reason, _ = self.check("compose", *argv, "ps")
            self.assertIsNone(reason, f"{argv}: {reason}")

    def test_logs_follow_flag_is_not_a_compose_file(self):
        self.assertIsNone(self.check("compose", "logs", "-f", "app")[0])


class TestValidateConfigGaps(RevBase):
    def refused(self, cfg):
        with self.assertRaises(self.mod.Refused, msg=json.dumps(cfg)):
            self.mod.validate_config(cfg, self.root, self.root)

    def test_watch_sync_path_outside_the_project(self):
        # `up --watch` copies service.develop.watch[].path from the host into the container.
        self.refused({"services": {"app": {"develop": {"watch": [
            {"path": str(self.outside), "action": "sync", "target": "/x"}]}}}})

    def test_lifecycle_hook_privileged(self):
        # post_start/pre_stop hooks accept privileged: true (an exec --privileged) that only the top-level key blocks.
        for hook in ("post_start", "pre_stop"):
            self.refused({"services": {"app": {hook: [{"command": "id", "privileged": True}]}}})

    def test_nfs_or_cifs_volume_driver_opts(self):
        # device ":/export" is a relative path to inside(); type/o turn the local volume into a network mount.
        self.refused({"volumes": {"data": {"name": self.name + "_data", "driver": "local",
                                          "driver_opts": {"type": "nfs", "o": "addr=203.0.113.9,rw",
                                                          "device": ":/export"}}}})

    def test_built_image_cannot_take_over_another_projects_tag(self):
        # build.tag/image: postgres:16 re-tags a shared image that other projects pull or run.
        for image in ("postgres:16", "postgres", "x", "docker.io/library/postgres", f"{self.name}x", "other-" + self.name):
            self.refused({"services": {"db": {"image": image, "build": {"context": str(self.root)}}}})
        self.refused({"services": {"db": {"build": {"context": str(self.root), "tags": ["postgres:16"]}}}})

    def test_built_service_tags_with_the_project_prefix_are_allowed(self):
        for image in (f"{self.name}-db", f"{self.name}-db:dev", f"{self.name}/db", f"{self.name}/db:1"):
            self.mod.validate_config({"services": {"db": {"image": image, "build": {"context": str(self.root)}}}},
                                     self.root, self.root)
        self.mod.validate_config({"services": {"db": {"build": {"context": str(self.root)}}}}, self.root, self.root)

    def test_pulled_images_are_not_restricted(self):
        self.mod.validate_config({"services": {"db": {"image": "postgres:16"}}}, self.root, self.root)

    def test_build_tag_flag_cannot_take_over_a_shared_tag(self):
        for tag in ("postgres:16", "postgres", "x", "myapp", "docker.io/library/postgres", f"{self.name}x",
                    "other-" + self.name):
            for flag in (["-t", tag], [f"--tag={tag}"], ["--tag", tag]):
                reason, _ = self.check("build", *flag, ".")
                self.assertIsNotNone(reason, f"{flag} was allowed")

    def test_build_tags_with_the_project_prefix_are_allowed(self):
        for tag in (f"{self.name}-app", f"{self.name}-app:dev", f"{self.name}/app", f"{self.name}/app:1"):
            reason, _ = self.check("build", "-t", tag, ".")
            self.assertIsNone(reason, reason)

    def test_compose_build_builder_flag(self):
        # varsayım: any buildx builder already configured on the host (e.g. a remote driver) can be selected.
        reason, _ = self.check("compose", "build", "--builder", "remote")
        self.assertIsNotNone(reason)


class TestProtectedPathsInsideProject(RevBase):
    """The sandbox denies the agent .env, .claude/{hooks,skills,settings*} and .git/hooks|config; a bind mount of the same
    paths is 'inside the project' for dockerw and runs unsandboxed, so a container can read or rewrite them.
    Policy: a read-write bind mount may not be, lie inside, or contain .git/.claude (the project root included), and
    .env*/secrets may not be mounted read-write. Read-only mounts are fine."""

    PROTECTED = (".git/hooks", ".git", ".claude/hooks", ".claude", ".env", "secrets")

    def setUp(self):
        super().setUp()
        for p in self.PROTECTED:
            path = self.root / p
            path.parent.mkdir(parents=True, exist_ok=True)
            path.mkdir(exist_ok=True) if p != ".env" else path.write_text("K=v\n")

    def cli(self, src, ro=False):
        suffix = ":ro" if ro else ""
        return [["-v", f"{src}:/x{suffix}"], [f"--volume={src}:/x{suffix}"],
                ["--mount", f"type=bind,source={src},target=/x" + (",readonly" if ro else "")]]

    def cfg(self, src, **extra):
        return {"services": {"app": {"volumes": [{"type": "bind", "source": str(src), "target": "/x", **extra}]}}}

    def test_cli_mounts_of_protected_paths(self):
        for p in self.PROTECTED:
            for argv in self.cli(self.root / p):
                with self.assertRaises(self.mod.Refused, msg=f"{p}: {argv}"):
                    self.mod.scan(argv, self.root, self.root)

    def test_config_mounts_of_protected_paths(self):
        for p in self.PROTECTED:
            with self.assertRaises(self.mod.Refused, msg=p):
                self.mod.validate_config(self.cfg(self.root / p), self.root, self.root)

    def test_project_root_mount_that_contains_protected_paths(self):
        # rw root is refused (it contains .git/.claude), ro root is fine.
        for argv in self.cli(self.root):
            with self.assertRaises(self.mod.Refused, msg=str(argv)):
                self.mod.scan(argv, self.root, self.root)
        for argv in self.cli(".") + self.cli(self.root / "."):
            with self.assertRaises(self.mod.Refused, msg=str(argv)):
                self.mod.scan(argv, self.root, self.root)
        with self.assertRaises(self.mod.Refused):
            self.mod.validate_config(self.cfg(self.root), self.root, self.root)
        for argv in self.cli(self.root, ro=True):
            self.mod.scan(argv, self.root, self.root)
        self.mod.validate_config(self.cfg(self.root, read_only=True), self.root, self.root)

    def test_read_only_mounts_of_protected_paths_are_allowed(self):
        for p in self.PROTECTED:
            for argv in self.cli(self.root / p, ro=True) + [["-v", f"{self.root}/{p}:/x:ro,z"],
                                                           ["--mount", f"type=bind,source={self.root}/{p},target=/x,readonly=true"],
                                                           ["--mount", f"type=bind,src={self.root}/{p},dst=/x,ro"]]:
                self.mod.scan(argv, self.root, self.root)
            self.mod.validate_config(self.cfg(self.root / p, read_only=True), self.root, self.root)

    def test_readonly_false_or_rw_is_still_read_write(self):
        src = self.root / ".git"
        for argv in (["-v", f"{src}:/x:rw"], ["--mount", f"type=bind,source={src},target=/x,readonly=false"],
                     ["--mount", f"type=bind,source={src},target=/x,readonly=true,readonly=false"]):
            with self.assertRaises(self.mod.Refused, msg=str(argv)):
                self.mod.scan(argv, self.root, self.root)
        with self.assertRaises(self.mod.Refused):
            self.mod.validate_config(self.cfg(src, read_only=False), self.root, self.root)

    def test_subdirectories_and_files_next_to_protected_paths_stay_allowed(self):
        (self.root / "data").mkdir()
        (self.root / "src").mkdir()
        for argv in self.cli(self.root / "data") + self.cli("./src"):
            self.mod.scan(argv, self.root, self.root)
        self.mod.validate_config(self.cfg(self.root / "data"), self.root, self.root)

    def test_nested_protected_paths_and_dirs_that_contain_them(self):
        (self.root / "vendor" / "lib" / ".git").mkdir(parents=True)
        (self.root / "app" / ".env.local").parent.mkdir()
        (self.root / "app" / ".env.local").write_text("K=v\n")
        for src in (self.root / "vendor" / "lib" / ".git", self.root / "vendor" / "lib",
                    self.root / "app" / ".env.local", self.root / ".claude" / "x" / "y"):
            for argv in self.cli(src):
                with self.assertRaises(self.mod.Refused, msg=f"{src}: {argv}"):
                    self.mod.scan(argv, self.root, self.root)

    def test_scan_finds_protected_dirs_up_to_four_levels_below_the_source(self):
        (self.root / "src" / "a" / "b" / "c" / ".git").mkdir(parents=True)      # 4 levels below src
        (self.root / "src" / "a" / "b" / "c" / "d" / ".claude").mkdir(parents=True)  # 5 levels: beyond the scan
        (self.root / "deep" / "a" / "b" / "c" / "d" / ".claude").mkdir(parents=True)
        (self.root / "wt" / "x").mkdir(parents=True)
        (self.root / "wt" / "x" / ".git").write_text("gitdir: ../../.git/worktrees/x\n")  # worktree: .git is a file
        for src in ("src", "wt"):
            for argv in self.cli(self.root / src):
                with self.assertRaises(self.mod.Refused, msg=f"{src}: {argv}"):
                    self.mod.scan(argv, self.root, self.root)
        for argv in self.cli(self.root / "deep"):
            self.mod.scan(argv, self.root, self.root)  # only found beyond the limit; documented limit
        for argv in self.cli(self.root / "src", ro=True) + self.cli(self.root / "wt", ro=True):
            self.mod.scan(argv, self.root, self.root)

    def test_scan_refuses_when_the_entry_limit_is_exceeded(self):
        big = self.root / "big"
        big.mkdir()
        for i in range(5001):
            (big / f"f{i}").touch()
        for argv in self.cli(big):
            with self.assertRaises(self.mod.Refused, msg=str(argv)) as cm:
                self.mod.scan(argv, self.root, self.root)
            self.assertIn(":ro", str(cm.exception))
        for argv in self.cli(big, ro=True):
            self.mod.scan(argv, self.root, self.root)
        ok = self.root / "ok"
        ok.mkdir()
        for i in range(100):
            (ok / f"f{i}").touch()
        for argv in self.cli(ok):
            self.mod.scan(argv, self.root, self.root)

    def test_scan_refuses_what_it_cannot_read(self):
        locked = self.root / "locked"
        (locked / "inner").mkdir(parents=True)
        locked.chmod(0)
        self.addCleanup(lambda: locked.chmod(0o755))
        if os.access(locked, os.R_OK):
            self.skipTest("directory permissions are not enforced here (running as root?)")
        for argv in self.cli(locked):
            with self.assertRaises(self.mod.Refused, msg=str(argv)):
                self.mod.scan(argv, self.root, self.root)

    def test_message_points_to_ro_or_a_subdirectory(self):
        with self.assertRaises(self.mod.Refused) as cm:
            self.mod.scan(["-v", f"{self.root}:/x"], self.root, self.root)
        self.assertIn(":ro", str(cm.exception))
        self.assertIn("subdirectory", str(cm.exception))

    def test_named_volumes_and_compose_run_end_to_end(self):
        self.assertIsNotNone(self.check("compose", "run", "-v", f"{self.root}/.git:/x", "app")[0])
        self.assertIsNone(self.check("compose", "run", "-v", f"{self.root}/.git:/x:ro", "app")[0])
        self.assertIsNone(self.check("compose", "run", "-v", f"{self.name}_data:/x", "app")[0])


class TestPathUsedIsPathValidated(RevBase):
    def test_bind_source_symlink_is_resolved_in_the_config_that_runs(self):
        real = self.root / "real"
        real.mkdir()
        (self.root / "link").symlink_to(real)
        cfg = {"services": {"app": {"image": "alpine", "volumes": [
            {"type": "bind", "source": str(self.root / "link"), "target": "/x"}]}}}
        self.set_config(cfg)
        self.run_tool("compose", "up")
        sent = json.loads((self.fake_dir / "stdin.json").read_text())
        src = sent["services"]["app"]["volumes"][0]["source"]
        self.assertEqual(src, str(real), "docker re-resolves the symlink after validation (swap race), not the checked path")


class TestEnvFileRecheck(RevBase):
    def test_second_resolution_env_files_are_validated_not_the_first_again(self):
        # varsayım: the compose version used keeps env_file in the fully resolved output; gate_compose re-validates
        # `unresolved` (line 545) instead of `cfg`, so a compose file swapped between the two calls is not re-checked.
        first = {"services": {"app": {"env_file": [{"path": str(self.root / "ok.env")}]}}}
        second = {"services": {"app": {"env_file": [{"path": str(self.outside / "secret.env")}],
                                       "environment": {"S": "x"}}}}
        (self.root / "ok.env").write_text("A=1\n")
        self.set_config(second, first=first)
        r = self.run_tool("compose", "up")
        self.assertEqual(r.returncode, 2, r.stderr)


class TestPortsReliability(RevBase):
    def test_udp_port_in_use_is_not_reported_free(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(u.close)
        try:
            u.bind(("0.0.0.0", 0))
        except OSError:
            self.skipTest("local port binding is not permitted here (sandbox)")
        port = u.getsockname()[1]
        self.set_config({"services": {"dns": {"ports": [{"published": str(port), "target": 53, "protocol": "udp"}]}}})
        line = self.run_tool("ports").stdout.strip()
        self.assertNotEqual(line, f"PORT {port} dns free", "is_free only probes TCP; the protocol is dropped")

    def test_failing_docker_ps_is_not_reported_as_foreign_process(self):
        class R:
            returncode, stdout, stderr = 1, "", "Cannot connect to the Docker daemon"

        self.mod._run = lambda args, cwd=None: R
        self.mod.is_free = lambda port: False
        self.assertEqual(self.mod.port_status(8080, "p"), "unknown")


class TestCleanScope(unittest.TestCase):
    def test_dangling_image_prune_is_gone(self):
        # clean only prunes this project's labelled containers; unlabelled images are never pruned (see test_dockerw_cmds).
        import test_dockerw_cmds as c
        t = c.TestClean("test_dry_run_runs_nothing")
        t.setUp()
        try:
            r = t.run_tool("clean", "--apply", "--include-dangling")
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("image prune", t.log.read_text() if t.log.exists() else "")
        finally:
            shutil.rmtree(t.root, ignore_errors=True)


class TestConfFailOpen(RevBase):
    def test_unparseable_conf_does_not_disable_allowed_roots(self):
        # _conf() returns {} on any parse/read error, so a truncated or corrupt file silently drops allowed_roots.
        conf = self.tool.parent / "dockerw.conf.json"
        for text in ("", "{", '{"allowed_roots": ["/nowhere"]} trailing', "[]"):
            conf.write_text(text)
            mod = load()
            mod.CONF = conf
            with self.assertRaises(SystemExit, msg=f"conf {text!r} treated as empty (no allowed_roots, no pinned docker)"):
                mod._conf()


class TestInstallerRaces(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-inst4.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.dest = self.tmp / "bin"
        self.projects = self.tmp / "projects"
        self.projects.mkdir()
        self.fake = self.tmp / "fake-docker"
        self.fake.write_text("#!/bin/sh\nexit 0\n")
        self.fake.chmod(0o755)

    def install(self, *extra, roots=None, docker=None, python=None, env=None, dest=None):
        args = ["bash", str(INSTALLER), "--dest", str(dest or self.dest), "--python", python or sys.executable,
                "--docker", str(docker or self.fake)]
        for r in ([self.projects] if roots is None else roots):
            args += ["--root", str(r)]
        return subprocess.run(args + list(extra), capture_output=True, text=True, env=env or os.environ)

    def test_failed_install_leaves_no_runnable_shim_without_conf(self):
        # dockerw.py and the shim are written before the conf; if the conf step fails, dockerw starts with _conf() == {}.
        bindir = self.tmp / "fakepath"
        bindir.mkdir()
        real = shutil.which("python3")
        wrapper = bindir / "python3"
        wrapper.write_text(f'#!/bin/sh\n[ "$1" = "-" ] && exit 1\nexec "{real}" "$@"\n')
        wrapper.chmod(0o755)
        r = self.install(env=dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}"))
        self.assertNotEqual(r.returncode, 0)
        shim, conf = self.dest / "dockerw", self.dest / "dockerw.conf.json"
        self.assertFalse(shim.exists() and not conf.exists(), "shim installed without a conf: runs with no allowed_roots")

    def test_conf_is_not_world_writable_while_it_is_being_written(self):
        # open(path, "w") creates with the umask; chmod 644 only happens afterwards. Record the mode in between.
        bindir = self.tmp / "fakepath"
        bindir.mkdir()
        real, rec = shutil.which("python3"), self.tmp / "mode.txt"
        wrapper = bindir / "python3"
        wrapper.write_text(f'#!/bin/sh\n"{real}" "$@"; rc=$?\n[ "$1" = "-" ] && stat -f %Lp "$2" > "{rec}"\nexit $rc\n')
        wrapper.chmod(0o755)
        r = subprocess.run(["bash", "-c", f'umask 000; exec bash "{INSTALLER}" --dest "{self.dest}" --python "{sys.executable}" '
                            f'--docker "{self.fake}" --root "{self.projects}"'],
                           capture_output=True, text=True, env=dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}"))
        self.assertEqual(r.returncode, 0, r.stderr)
        mode = int(rec.read_text().strip(), 8)
        self.assertEqual(mode & 0o022, 0, f"conf mode {mode:o} before chmod")

    def test_dest_inside_a_root_is_refused(self):
        # The point of the installer is a copy the sandboxed agent cannot edit; a dest under a --root defeats it.
        r = self.install(dest=self.projects / "app" / "bin")
        self.assertNotEqual(r.returncode, 0)

    def test_docker_or_python_inside_a_root_is_refused(self):
        # The configured docker binary is executed outside the sandbox; a path the agent can write is code execution.
        planted = self.projects / "app" / "docker"
        planted.parent.mkdir(parents=True)
        planted.write_text("#!/bin/sh\nexit 0\n")
        planted.chmod(0o755)
        self.assertNotEqual(self.install(docker=planted).returncode, 0, "docker inside a root accepted")
        self.assertNotEqual(self.install(python=planted).returncode, 0, "python inside a root accepted")

    def test_too_broad_or_relative_roots_are_refused(self):
        for root in ("/", str(Path.home()), "."):
            self.assertNotEqual(self.install(roots=[root]).returncode, 0, f"--root {root} accepted")

    def test_reinstall_keeps_a_backup_of_the_conf_and_does_not_clobber_foreign_files(self):
        self.assertEqual(self.install().returncode, 0)
        conf = self.dest / "dockerw.conf.json"
        conf.write_text(json.dumps({"docker": str(self.fake), "allowed_roots": ["/a", "/b"], "root": "/pinned"}))
        (self.dest / "dockerw.py").write_text("# somebody else's tool\n")
        r = self.install()
        backed_up = [p for p in self.dest.iterdir() if p.name.startswith("dockerw.conf.json.") or p.name.endswith(".bak")]
        self.assertTrue(backed_up or r.returncode != 0, "previous conf (two roots, pinned root) replaced silently")
        self.assertTrue(r.returncode != 0 or (self.dest / "dockerw.py").read_text().startswith("#!"),
                        "foreign dockerw.py replaced without the 'is it ours' check that dockerw has")


class TestProjectRootBehaviour(RevBase):
    """Item 5: pinned current behaviour, no open finding (passing tests)."""

    def mod_root(self, cwd):
        mod = load()
        mod.CONF = self.outside / "none.json"  # no pinned root
        old = os.getcwd()
        os.chdir(cwd)
        try:
            return mod.project_root()
        finally:
            os.chdir(old)

    def test_symlinked_git_still_marks_the_root_at_the_link_location(self):
        proj = self.outside / "p"
        (proj / "sub").mkdir(parents=True)
        (proj / ".git").symlink_to(self.root)
        self.assertEqual(self.mod_root(proj / "sub"), proj)

    def test_dangling_git_symlink_is_skipped(self):
        proj = self.outside / "p"
        (proj / "sub").mkdir(parents=True)
        (proj / ".git").symlink_to(self.outside / "missing")
        self.assertNotEqual(self.mod_root(proj / "sub"), proj)

    def test_nested_repo_becomes_its_own_project_with_its_own_compose_name(self):
        proj = self.outside / "p"
        (proj / ".git").mkdir(parents=True)
        (proj / "vendor" / "lib").mkdir(parents=True)
        (proj / "vendor" / "lib" / ".git").write_text("gitdir: ../../.git/modules/lib\n")  # any file, e.g. a submodule
        nested = self.mod_root(proj / "vendor" / "lib")
        self.assertEqual(nested, proj / "vendor" / "lib")
        self.assertNotEqual(self.mod.project_name(nested), self.mod.project_name(proj))


if __name__ == "__main__":
    unittest.main()
