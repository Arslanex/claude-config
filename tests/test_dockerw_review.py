import importlib.util
import shutil
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
        self.root = Path(tempfile.mkdtemp(prefix="dw-rev.")).resolve()
        self.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        self.name = self.mod.project_name(self.root)

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


class TestBuildParsing(Base):
    def test_context_is_the_only_positional_wherever_the_flags_are(self):
        self.allowed("build", ".", "-t", f"{self.name}-x")
        self.allowed("build", "-t", f"{self.name}-x", ".")
        self.refused("build", "/etc", "-t", f"{self.name}-x")
        self.refused("build", "-t", f"{self.name}-x", "/etc")
        self.refused("build", ".", "..")
        self.refused("build", "-t", f"{self.name}-x")

    def test_only_listed_flags_are_accepted(self):
        for extra in (["--output", "type=local,dest=/tmp/x"], ["-o", "/tmp/x"],
                      ["--cache-to", "type=local,dest=/x"], ["--cache-from", "type=local,src=/x"],
                      ["--secret", "id=k,src=/etc/passwd"], ["--ssh", "default"],
                      ["--build-context", "x=/etc"], ["--allow", "security.insecure"],
                      ["--config", "/proj/cfg"], ["--privileged"]):
            with self.subTest(extra=extra):
                self.refused("build", *extra, ".")

    def test_listed_flags_work(self):
        self.allowed("build", "--no-cache", "--pull", "-q", "--target", "dev", "--label", "a=b",
                     "--progress=plain", "--platform", "linux/amd64", "-t", f"{self.name}-x", ".")


class TestShortOptions(Base):
    def test_attached_and_clustered_short_options_refused(self):
        self.refused("compose", "-f/etc/evil.yml", "up")
        self.refused("compose", "run", "-dv", "/:/h", "web")
        self.refused("compose", "run", "-tv", "/:/h", "web")
        self.refused("compose", "down", "-vt", "1")
        self.refused("build", "-f/etc/Dockerfile", ".")
        self.refused("compose", "run", "-p8080:80", "web")

    def test_separate_short_options_still_work(self):
        self.allowed("compose", "run", "-T", "-e", "A=1", "web")


class TestNamedVolumes(Base):
    def test_only_this_projects_volumes(self):
        self.allowed("compose", "run", "-v", f"{self.name}_data:/d", "web")
        self.allowed("compose", "run", "--mount", f"type=volume,source={self.name}_data,target=/d", "web")
        self.refused("compose", "run", "-v", "victim_db:/d", "web")
        self.refused("compose", "run", "--mount", "type=volume,source=victim_db,target=/d", "web")


class TestOptionsAfterSubcommand(Base):
    def test_path_and_project_options_must_precede_the_subcommand(self):
        for argv in (["up", "--file", "/etc/x.yml"], ["up", "--file=/etc/x.yml"], ["up", "--env-file", "../.env"],
                     ["up", "--project-name", "victim"], ["up", "--project-directory", "/"],
                     ["ps", "-p", "victim"], ["up", "-f", "/etc/x.yml"]):
            with self.subTest(argv=argv):
                self.refused("compose", *argv)

    def test_follow_and_publish_flags_keep_working(self):
        self.allowed("compose", "logs", "-f", "web")
        self.allowed("compose", "run", "-p", "8080:80", "web")


class TestRemovedVerbs(Base):
    def test_logs_and_inspect_only_through_compose(self):
        self.refused("logs", "web")
        self.refused("inspect", "x")
        self.allowed("compose", "logs", "web")


class TestPortRange(Base):
    def test_range_does_not_crash(self):
        cfg = {"services": {"web": {"ports": [{"published": "8000-8002"}, {"published": "9000"}]}}}
        self.assertEqual(self.mod.published_ports(cfg), [("web", 9000)])


if __name__ == "__main__":
    unittest.main()
