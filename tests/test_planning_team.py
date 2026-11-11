"""
Planning team: the /design-project skill registration, diagram classes and preview.py.

Role agent checks live in test_planning_roles.py.
"""

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "src" / "skills" / "design-project"
spec = importlib.util.spec_from_file_location("plan_preview", SKILL / "preview.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)

CLASSES = ["frontend", "backend", "database", "cloud", "security", "messagebus", "external"]


class DesignProjectSkillTest(unittest.TestCase):
    def test_supporting_files_exist(self):
        for name in ("SKILL.md", "diagrams.md", "preview.py"):
            with self.subTest(file=name):
                self.assertTrue((SKILL / name).is_file())

    def test_diagram_classes_are_defined_once_with_archify_colors(self):
        text = (SKILL / "diagrams.md").read_text(encoding="utf-8")
        for name, color in zip(CLASSES, ["#22D3EE", "#34D399", "#A78BFA", "#FBBF24", "#FB7185", "#FB923C", "#94A3B8"]):
            with self.subTest(cls=name):
                self.assertRegex(text, rf"classDef {name} fill:#[0-9A-F]{{6}},stroke:{color},color:#[0-9A-F]{{6}}")

    def test_the_skill_is_registered_globally(self):
        for path in (ROOT / "CLAUDE.md", ROOT / "src" / "agents" / "work-verifier.md"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertIn("design-project", text)


class PreviewTest(unittest.TestCase):
    def run_preview(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = preview.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_renders_every_block_with_its_heading_and_escapes_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "PLAN-0001-crm.md"
            doc.write_text(
                '---\ntitle: "CRM: product plan"\n---\n\n## Scope map\n\n```mermaid\nflowchart LR\n  a --> b\n```\n\n'
                "## Data model\n\n```mermaid\nerDiagram\n  a ||--o{ b : \"<has>\"\n```\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "out" / "preview.html"
            code, stdout, _ = self.run_preview(tmp, "-o", out)
            page = out.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("(2 diagrams)", stdout)
        # Two diagrams on the Diyagramlar page, plus the UML class diagram the Veri modeli page builds from the ERD.
        self.assertEqual(page.count('<pre class="mermaid">'), 3)
        self.assertIn("classDiagram", page)
        self.assertIn("<h3>Scope map</h3>", page)
        self.assertIn("<h3>Data model</h3>", page)
        self.assertIn("CRM: product plan", page)
        self.assertIn("&lt;has&gt;", page)
        self.assertIn("mermaid@11.4.1", page)
        self.assertIn('securityLevel: "strict"', page)

    def test_no_blocks_and_missing_paths_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "empty.md"
            doc.write_text("# Nothing\n", encoding="utf-8")
            self.assertEqual(self.run_preview(doc, "-o", Path(tmp) / "x.html")[0], 1)
            self.assertFalse((Path(tmp) / "x.html").exists())
            self.assertEqual(self.run_preview(Path(tmp) / "missing.md", "-o", Path(tmp) / "x.html")[0], 2)


if __name__ == "__main__":
    unittest.main()
