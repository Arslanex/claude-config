import contextlib
import importlib.util
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

DOCS_PY = (Path(__file__).resolve().parent.parent
           / "src" / "templates" / "project" / "tools" / "docs.py")
spec = importlib.util.spec_from_file_location("docs_engine", DOCS_PY)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(path, *args, date=None):
    env = dict(GIT_ENV)
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00+0000"
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, env=env)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = docs.main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def write_doc(root, rel, **fields):
    fm = {"id": "ADR-0001", "title": "T", "status": "draft", "area": "core", "updated": "2025-01-01"}
    fm.update(fields)
    body = "".join(f"{k}: {v}\n" for k, v in fm.items() if v is not None)
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{body}---\n\n# Body\n", encoding="utf-8")
    return path


class TempRoot(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.root = self.base / "docs"
        self.root.mkdir()


class ParserTests(unittest.TestCase):
    def parse(self, fm):
        return docs.parse_front_matter(f"---\n{fm}\n---\nbody\n")

    def test_valid_scalars_lists_comments(self):
        data, body = self.parse(
            "# header comment\n"
            "id: ADR-0001\n"
            'title: "Use: colons # and hashes"\n'
            "status: draft   # trailing comment\n"
            "owner:\n"
            "depends_on: [ARCH-0001, 'ARCH-0002' , \"T-0003\"]\n"
            "related: []\n"
            "area: a#b\n"
        )
        self.assertEqual(data["id"], "ADR-0001")
        self.assertEqual(data["title"], "Use: colons # and hashes")
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["owner"], "")
        self.assertEqual(data["depends_on"], ["ARCH-0001", "ARCH-0002", "T-0003"])
        self.assertEqual(data["related"], [])
        self.assertEqual(data["area"], "a#b")
        self.assertEqual(body.strip(), "body")

    def test_list_with_trailing_comment(self):
        data, _ = self.parse("depends_on: [A, B] # why")
        self.assertEqual(data["depends_on"], ["A", "B"])

    def test_rejected_formats(self):
        cases = {
            "nested": "parent:\n  child: 1",
            "block list": "depends_on:\n- A",
            "nested list": "depends_on: [[A], B]",
            "flow map": "x: {a: 1}",
            "block scalar": "x: |",
            "nested inline map": "x: a: b",
            "no colon": "just text",
            "duplicate": "id: A\nid: B",
            "unterminated list": "depends_on: [A, B",
            "empty item": "depends_on: [A,, B]",
            "trailing text": "title: \"x\" junk",
            "unterminated quote": 'title: "x',
        }
        for name, fm in cases.items():
            with self.subTest(name), self.assertRaises(docs.FrontMatterError) as cm:
                self.parse(fm)
            self.assertIn("line", str(cm.exception))

    def test_missing_or_unclosed_front_matter(self):
        with self.assertRaisesRegex(docs.FrontMatterError, "must start"):
            docs.parse_front_matter("# no front matter\n")
        with self.assertRaisesRegex(docs.FrontMatterError, "not closed"):
            docs.parse_front_matter("---\nid: A\n")


class NewTests(TempRoot):
    def test_creates_file_with_valid_front_matter(self):
        code, out, _ = run("new", "adr", "Use SQLite", "--root", self.root)
        self.assertEqual(code, 0)
        path = self.root / "02-decisions" / "ADR-0001-use-sqlite.md"
        self.assertTrue(path.exists())
        data, _ = docs.parse_front_matter(path.read_text())
        self.assertEqual(data["id"], "ADR-0001")
        self.assertEqual(data["title"], "Use SQLite")
        self.assertEqual(run("lint", "--root", self.root)[0], 0)

    def test_slug_keeps_turkish_letters_readable(self):
        self.assertEqual(docs.slugify("Satış"), "satis")
        self.assertEqual(docs.slugify("Çağrı Ölçüm İşi"), "cagri-olcum-isi")

    def test_id_increments(self):
        run("new", "adr", "First", "--root", self.root)
        run("new", "adr", "Second", "--root", self.root)
        self.assertTrue((self.root / "02-decisions" / "ADR-0002-second.md").exists())

    def test_kinds_prefixes_and_folders(self):
        expected = {
            "adr": "02-decisions/ADR-0001-x.md",
            "task": "05-work/tasks/T-0001-x.md",
            "module": "01-architecture/modules/ARCH-0001-x.md",
            "domain": "03-domains/x/DOM-0001-x.md",
            "plan": "05-work/plans/PLAN-0001-x.md",
            "handoff": "05-work/handoffs/HO-0001-x.md",
            "log": "05-work/log/LOG-0001-x.md",
            "runbook": "04-operations/RUN-0001-x.md",
        }
        for kind, rel in expected.items():
            with self.subTest(kind):
                self.assertEqual(run("new", kind, "x", "--root", self.root)[0], 0)
                self.assertTrue((self.root / rel).exists(), rel)

    def test_planning_kinds_prefixes_and_folders(self):
        expected = {
            "brief": "05-work/plans/BRIEF-0001-x.md",
            "threat": "01-architecture/security/ARCH-0001-x.md",
            "perf": "01-architecture/performance/ARCH-0002-x.md",
            "quality": "05-work/plans/quality/PLAN-0001-x.md",
        }
        for kind, rel in expected.items():
            with self.subTest(kind):
                self.assertEqual(run("new", kind, "x", "--root", self.root)[0], 0)
                self.assertTrue((self.root / rel).exists(), rel)
        self.assertIn("## 5. Özellikler", (self.root / expected["brief"]).read_text())
        self.assertEqual(run("lint", "--root", self.root)[0], 0)

    def test_next_number(self):
        self.assertEqual(docs.next_number(self.root, "T"), 1)
        write_doc(self.root, "05-work/tasks/T-0004-x.md", id="T-0004")
        self.assertEqual(docs.next_number(self.root, "T"), 5)

    def test_plan_state_index_is_not_a_document(self):
        (self.root / "05-work" / "plans").mkdir(parents=True)
        (self.root / "05-work" / "plans" / "PLAN-0001.index.md").write_text("| ID |\n")
        self.assertEqual(run("lint", "--root", self.root)[0], 0)

    def test_id_is_global_per_prefix_not_per_folder(self):
        write_doc(self.root, "elsewhere/whatever.md", id="ADR-0007")
        run("new", "adr", "Next", "--root", self.root)
        self.assertTrue((self.root / "02-decisions" / "ADR-0008-next.md").exists())

    def test_collision_with_other_branches(self):
        git(self.base, "init", "-q", "-b", "main")
        git(self.base, "commit", "-q", "--allow-empty", "-m", "init")
        git(self.base, "checkout", "-q", "-b", "feature")
        write_doc(self.root, "02-decisions/ADR-0005-x.md", id="ADR-0005")
        git(self.base, "add", "-A")
        git(self.base, "commit", "-q", "-m", "add adr")
        git(self.base, "update-ref", "refs/remotes/origin/remote-only", "HEAD")
        git(self.base, "checkout", "-q", "main")
        # make a remote-only ID that exists on no local branch
        git(self.base, "checkout", "-q", "--detach", "feature")
        write_doc(self.root, "02-decisions/ADR-0009-y.md", id="ADR-0009")
        git(self.base, "add", "-A")
        git(self.base, "commit", "-q", "-m", "remote adr")
        git(self.base, "update-ref", "refs/remotes/origin/other", "HEAD")
        git(self.base, "checkout", "-q", "main")
        self.assertFalse(list(self.root.rglob("*.md")))
        run("new", "adr", "Fresh", "--root", self.root)
        self.assertTrue((self.root / "02-decisions" / "ADR-0010-fresh.md").exists())

    def test_works_without_git(self):
        self.assertIsNone(docs.repo_info(self.root))
        self.assertEqual(run("new", "task", "No git", "--root", self.root)[0], 0)


class LintTests(TempRoot):
    def lint(self, *extra):
        code, out, _ = run("lint", "--root", self.root, *extra)
        return code, out

    def test_clean_docs_pass(self):
        write_doc(self.root, "02-decisions/a.md")
        write_doc(self.root, "02-decisions/b.md", id="ADR-0002", depends_on="[ADR-0001]")
        self.assertEqual(self.lint(), (0, "0 error(s), 0 warning(s)\n"))

    def test_missing_required_field(self):
        for field in docs.REQUIRED:
            with self.subTest(field):
                write_doc(self.root, "a.md", **{field: None})
                code, out = self.lint()
                self.assertEqual(code, 1)
                self.assertIn(f"missing required field '{field}'", out)

    def test_invalid_status(self):
        write_doc(self.root, "a.md", status="wip")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("invalid status 'wip'", out)

    def test_duplicate_id(self):
        write_doc(self.root, "a.md")
        write_doc(self.root, "b.md")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("duplicate id ADR-0001", out)

    def test_unknown_references(self):
        for field in ("depends_on", "related", "superseded_by"):
            with self.subTest(field):
                value = "ADR-0099" if field == "superseded_by" else "[ADR-0099]"
                write_doc(self.root, "a.md", **{field: value})
                code, out = self.lint()
                self.assertEqual(code, 1)
                self.assertIn(f"{field} references unknown id ADR-0099", out)

    def test_parse_error_is_an_error(self):
        (self.root / "a.md").write_text("---\nparent:\n  child: 1\n---\n")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("nested structures", out)

    def test_invalid_date(self):
        write_doc(self.root, "a.md", updated="yesterday")
        code, out = self.lint()
        self.assertEqual(code, 1)
        self.assertIn("YYYY-MM-DD", out)

    def test_long_doc_warning_and_strict(self):
        path = write_doc(self.root, "a.md")
        path.write_text(path.read_text() + "line\n" * 300)
        code, out = self.lint()
        self.assertEqual(code, 0)
        self.assertIn("WARN  a.md: longer than 300 lines", out)
        self.assertEqual(self.lint("--strict")[0], 1)

    def test_long_index_warning(self):
        (self.root / "INDEX.md").write_text("x\n" * 101)
        code, out = self.lint()
        self.assertEqual(code, 0)
        self.assertIn("INDEX.md: longer than 100 lines", out)
        self.assertEqual(self.lint("--strict")[0], 1)

    def test_superseded_outside_archive_warning(self):
        write_doc(self.root, "02-decisions/a.md", status="superseded")
        write_doc(self.root, "99-archive/b.md", id="ADR-0002", status="superseded")
        code, out = self.lint()
        self.assertEqual(code, 0)
        self.assertIn("02-decisions/a.md: status is superseded", out)
        self.assertNotIn("99-archive/b.md", out)

    def _code_repo(self, updated):
        git(self.base, "init", "-q", "-b", "main")
        (self.base / "src").mkdir()
        (self.base / "src" / "app.py").write_text("x = 1\n")
        git(self.base, "add", "-A")
        git(self.base, "commit", "-q", "-m", "code", date="2025-01-10")
        write_doc(self.root, "a.md", updated=updated, code_paths="[src/app.py, src/untracked.py]")

    def test_code_touched_after_updated_warns(self):
        self._code_repo("2025-01-01")
        code, out = self.lint()
        self.assertEqual(code, 0)
        self.assertIn("code_paths 'src/app.py' changed on 2025-01-10", out)
        self.assertNotIn("untracked.py", out)
        self.assertEqual(self.lint("--strict")[0], 1)

    def test_code_older_than_updated_is_clean(self):
        self._code_repo("2025-02-01")
        self.assertEqual(self.lint(), (0, "0 error(s), 0 warning(s)\n"))

    def test_code_check_skipped_without_git(self):
        write_doc(self.root, "a.md", code_paths="[src/app.py]")
        self.assertEqual(self.lint(), (0, "0 error(s), 0 warning(s)\n"))


class IndexTests(TempRoot):
    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_text()
                for p in sorted(self.root.rglob("INDEX.md"))}

    def setUp(self):
        super().setUp()
        write_doc(self.root, "02-decisions/ADR-0001-a.md", title="Pipe | title")
        write_doc(self.root, "03-domains/billing/DOM-0001-b.md", id="DOM-0001", title="Billing")
        write_doc(self.root, "05-work/tasks/T-0002-c.md", id="T-0002", title="Two")
        write_doc(self.root, "05-work/tasks/T-0010-d.md", id="T-0010", title="Ten")

    def test_generates_root_section_and_domain_indexes(self):
        self.assertEqual(run("index", "--root", self.root)[0], 0)
        snap = self.snapshot()
        self.assertEqual(set(snap), {"INDEX.md", "02-decisions/INDEX.md", "03-domains/INDEX.md",
                                     "03-domains/billing/INDEX.md", "05-work/INDEX.md"})
        self.assertIn("[02-decisions](02-decisions/INDEX.md) | 1", snap["INDEX.md"])
        self.assertIn("[ADR-0001](ADR-0001-a.md) | Pipe \\| title", snap["02-decisions/INDEX.md"])
        self.assertIn("[DOM-0001](DOM-0001-b.md)", snap["03-domains/billing/INDEX.md"])
        work = snap["05-work/INDEX.md"]
        self.assertLess(work.index("T-0002"), work.index("T-0010"))  # numeric order

    def test_second_run_is_identical(self):
        run("index", "--root", self.root)
        first = self.snapshot()
        code, out, _ = run("index", "--root", self.root)
        self.assertEqual(code, 0)
        self.assertIn("already up to date", out)
        self.assertEqual(self.snapshot(), first)

    def test_hand_written_text_is_preserved(self):
        run("index", "--root", self.root)
        path = self.root / "INDEX.md"
        text = path.read_text()
        path.write_text("# My title\n\nIntro by hand.\n\n" + text.split("\n", 2)[2].lstrip("\n")
                        + "\nFooter by hand.\n")
        write_doc(self.root, "00-project/ADR-0003-new.md", id="ADR-0003", title="New")
        run("index", "--root", self.root)
        after = path.read_text()
        self.assertTrue(after.startswith("# My title\n\nIntro by hand.\n"))
        self.assertTrue(after.endswith("Footer by hand.\n"))
        self.assertIn("00-project", after)
        run("index", "--root", self.root)
        self.assertEqual(path.read_text(), after)

    def test_existing_file_without_markers_gets_block_appended(self):
        (self.root / "INDEX.md").write_text("# Hand written\n\nKeep me.\n")
        run("index", "--root", self.root)
        text = (self.root / "INDEX.md").read_text()
        self.assertTrue(text.startswith("# Hand written\n\nKeep me.\n"))
        self.assertIn(docs.INDEX_START, text)

    def test_unbalanced_markers_fail(self):
        (self.root / "INDEX.md").write_text(f"{docs.INDEX_START}\nno end\n")
        code, _, err = run("index", "--root", self.root)
        self.assertEqual(code, 2)
        self.assertIn("unbalanced", err)


class GraphTests(TempRoot):
    def test_mermaid_graph_from_depends_on(self):
        write_doc(self.root, "01-architecture/modules/a.md", id="ARCH-0001", title="Api")
        write_doc(self.root, "01-architecture/modules/b.md", id="ARCH-0002", title='Db "core"',
                  depends_on="[ARCH-0001, ARCH-0099]")
        write_doc(self.root, "02-decisions/c.md", id="ADR-0001", title="Lonely")
        self.assertEqual(run("graph", "--root", self.root)[0], 0)
        text = (self.root / "01-architecture" / "graph.md").read_text()
        self.assertIn("```mermaid\ngraph LR", text)
        self.assertIn("ARCH_0002 --> ARCH_0001", text)
        self.assertIn('ARCH_0002["ARCH-0002 - Db \'core\'"]', text)
        self.assertNotIn("0099", text)      # dangling reference skipped
        self.assertNotIn("Lonely", text)    # nodes without edges omitted

    def test_graph_is_idempotent_and_keeps_hand_text(self):
        write_doc(self.root, "a.md", id="ARCH-0001")
        write_doc(self.root, "b.md", id="ARCH-0002", depends_on="[ARCH-0001]")
        run("graph", "--root", self.root)
        path = self.root / "01-architecture" / "graph.md"
        path.write_text("Intro.\n\n" + path.read_text())
        run("graph", "--root", self.root)
        first = path.read_text()
        run("graph", "--root", self.root)
        self.assertEqual(path.read_text(), first)
        self.assertTrue(first.startswith("Intro."))

    def test_graph_md_and_index_are_not_linted_as_docs(self):
        write_doc(self.root, "a.md", id="ARCH-0001")
        write_doc(self.root, "b.md", id="ARCH-0002", depends_on="[ARCH-0001]")
        run("graph", "--root", self.root)
        run("index", "--root", self.root)
        self.assertEqual(run("lint", "--root", self.root)[0], 0)


class StaleTests(TempRoot):
    TODAY = "2025-06-01"

    def stale(self, *extra):
        code, out, _ = run("stale", "--root", self.root, "--today", self.TODAY, *extra)
        return code, out

    def test_old_listed_new_not(self):
        write_doc(self.root, "a.md", id="ADR-0001", updated="2025-01-01")
        write_doc(self.root, "b.md", id="ADR-0002", status="accepted", updated="2025-05-20")
        code, out = self.stale()
        self.assertEqual(code, 0)
        self.assertIn("STALE ADR-0001 draft 2025-01-01 151d a.md\n", out)
        self.assertNotIn("ADR-0002", out)
        self.assertEqual(out.splitlines()[-1], "1 stale of 2 checked")

    def test_threshold_is_strictly_greater(self):
        write_doc(self.root, "a.md", updated="2025-03-03")  # exactly 90 days
        self.assertEqual(self.stale()[1], "0 stale of 1 checked\n")
        self.assertIn("STALE", self.stale("--days", "89")[1])

    def test_superseded_and_archived_excluded(self):
        write_doc(self.root, "a.md", id="ADR-0001", status="superseded")
        write_doc(self.root, "b.md", id="ADR-0002", status="archived")
        write_doc(self.root, "c.md", id="ADR-0003", status="accepted")
        code, out = self.stale()
        self.assertEqual(code, 0)
        self.assertNotIn("ADR-0001", out)
        self.assertNotIn("ADR-0002", out)
        self.assertEqual(out.splitlines()[-1], "1 stale of 1 checked")

    def test_bad_or_missing_date_warns_and_exits_zero(self):
        write_doc(self.root, "a.md", id="ADR-0001", updated="yesterday")
        write_doc(self.root, "b.md", id="ADR-0002", updated=None)
        code, out = self.stale()
        self.assertEqual(code, 0)
        self.assertIn("WARN  a.md:", out)
        self.assertIn("WARN  b.md:", out)
        self.assertNotIn("STALE", out)
        self.assertEqual(out.splitlines()[-1], "0 stale of 2 checked")

    def test_empty_docs(self):
        self.assertEqual(self.stale(), (0, "0 stale of 0 checked\n"))

    def _historical_and_living(self):
        write_doc(self.root, "t.md", id="T-0001")
        write_doc(self.root, "h.md", id="HO-0001")
        write_doc(self.root, "l.md", id="LOG-0001")
        write_doc(self.root, "a.md", id="ADR-0001")
        write_doc(self.root, "r.md", id="ARCH-0001")

    def test_default_skips_historical_kinds(self):
        self._historical_and_living()
        code, out = self.stale()
        self.assertEqual(code, 0)
        for hid in ("T-0001", "HO-0001", "LOG-0001"):
            self.assertNotIn(hid, out)
        self.assertIn("STALE ADR-0001", out)
        self.assertIn("STALE ARCH-0001", out)
        self.assertEqual(out.splitlines()[-1], "2 stale of 2 checked")

    def test_all_flag_scans_every_kind(self):
        self._historical_and_living()
        code, out = self.stale("--all")
        self.assertEqual(code, 0)
        for did in ("T-0001", "HO-0001", "LOG-0001", "ADR-0001", "ARCH-0001"):
            self.assertIn(f"STALE {did}", out)
        self.assertEqual(out.splitlines()[-1], "5 stale of 5 checked")


if __name__ == "__main__":
    unittest.main()
