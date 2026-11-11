"""
Plan review page (src/skills/design-project/preview.py): fixture project, escaping, Mermaid fallback, old usage,
and a page built from a real plan_state end-to-end run.

Set PREVIEW_SAMPLE to a file path to also write the end-to-end page there for a visual review.
"""

import html
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
SKILL = ROOT / "src" / "skills" / "design-project"
SCRIPT = SKILL / "preview.py"
spec = importlib.util.spec_from_file_location("plan_review_preview", SCRIPT)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
from plan_state import engine, registry  # noqa: E402  (preview put the skill folder on sys.path)
preview_render = sys.modules["preview_render"]

CATALOG = """---
id: PLAN-0001
title: "CRM: özellik kataloğu"
status: draft
---
# CRM: özellik kataloğu

## Özellikler
| ID | Başlık | Öncelik | Dilim | Durum | Origin | D | karar |
|---|---|---|---|---|---|---|---|
| F-01 | Hesap listesi <script>alert(1)</script> | P1 | S1 | accepted | | D-01 | accept |
| F-02 | Fırsat panosu | P1 | S2 | proposed | | | |
| F-03 | Raporlar | P2 | S3 | deferred | R-01 | | defer |

## Öneriler
| ID | Başlık | Gerekçe | Büyüklük | karar |
|---|---|---|---|---|
| R-01 | Satış hunisi raporu | Sektörde yaygın | M | |

## Hikayeler
### P1
- US-01 Satış temsilcisi olarak hesapları görmek istiyorum (F-01).
  - When the user opens the list, the system shall show accounts of the own tenant only.
  - If the list is empty, then the system shall show an invite action.

## Dilimler
### S1 İlk dilim
- Covers US-01.
- Doğrulama: kiracı yalıtımı testi.

## Mimari strateji
| Karar | Şimdi | İdeal | Tetikleyici | karar |
|---|---|---|---|---|
| Topoloji | modüler monolith | çok servisli | 50 kiracı | |

## Değişmez kurallar
- INV-01 Başka kiracının verisi hiçbir yoldan görünmez.

## Kapsam
### D-02 Kapsam haritası
Covers: F-02

```mermaid
flowchart LR
  user([Sales user]) --> web[Web app]
```
"""

DOM = """---
id: DOM-0001
title: "Hesap alanı"
status: draft
---
# Hesap alanı

## D-01 Veri modeli
Covers: F-01

```mermaid
erDiagram
  account {
    uuid id PK
    uuid tenant_id FK
    text name "unique per tenant"
  }
  account ||--o{ contact : "employs"
```
"""

OWNERS = {"PLAN": "product-manager", "DOM": "solution-architect"}
FINDINGS = {
    "SEC-01": ("CRITICAL", "H3", "security-architect", "open", "Kiracı filtresi bir uçta eksik"),
    "PERF-01": ("MAJOR", None, "performance-architect", "open", "Liste ucunda sayfa sınırı yok"),
    "QA-01": ("MINOR", None, "quality-engineer", "closed", "Belirsiz ölçüt"),
}


def run_state(base: Path) -> dict:
    """
    A run.json in the shape plan_state writes: artifacts from registry.scan_doc, G3 open, three findings.
    """
    state = engine.new_state("PLAN-0001")
    for path in sorted(base.rglob("*.md")):
        rel = path.relative_to(base).as_posix()
        role = OWNERS[path.name.split("-")[0]]
        state["artifacts"][rel] = {"owner_task": "catalog", "role": role, **registry.scan_doc(path.read_text())}
        for item_id in state["artifacts"][rel]["blocks"]:
            state["ids"][item_id] = {"prefix": registry.prefix_of(item_id), "owner": role, "doc": rel, "first_rev": 1,
                                     "status": "active", "origin": None, "decision": None}
    state["ids"]["F-01"]["decision"], state["ids"]["F-03"]["decision"] = "accepted", "deferred"
    for item_id, (severity, cls, owner, status, claim) in FINDINGS.items():
        state["findings"][item_id] = {"severity": severity, "owner": owner, "claim": claim, "evidence": "", "cls": cls,
                                      "raised_by": owner, "task": "security", "status": status, "fix_count": 0,
                                      "history": []}
        state["ids"][item_id] = {"prefix": registry.prefix_of(item_id), "owner": owner, "doc": None, "first_rev": 2,
                                 "status": "active", "origin": None, "decision": None}
    for task in state["tasks"].values():
        task["status"] = "done"
    for gate in ("Q1", "G1", "G2"):
        state["gates"][gate]["status"] = "approved"
    state["gates"]["G3"]["status"] = "open"
    state["run"]["status"] = "waiting_user"
    state["budget"]["calls"].update(total=38, by_model={"opus": 14, "sonnet": 22, "fable": 2})
    state["limits"]["calls"].update(cap=45, warn=35)
    state["contacts"]["count"] = 3
    return state


def build_project(base: Path) -> Path:
    plans = base / "docs" / "05-work" / "plans"
    domains = base / "docs" / "02-domain"
    plans.mkdir(parents=True)
    domains.mkdir(parents=True)
    (plans / "PLAN-0001-crm.md").write_text(CATALOG, encoding="utf-8")
    (domains / "DOM-0001-account.md").write_text(DOM, encoding="utf-8")
    (plans / "PLAN-0001.run.json").write_text(json.dumps(run_state(base)), encoding="utf-8")
    return base


def panel_of(page: str, name: str) -> str:
    """The HTML of one sidebar page (tab panel)."""
    return page.split(f'id="panel-{name}"', 1)[1].split('role="tabpanel"', 1)[0]


def run_preview(*args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = preview.main([str(a) for a in args])
    return code, out.getvalue(), err.getvalue()


class FullProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = build_project(Path(cls.tmp.name) / "crm")
        out = Path(cls.tmp.name) / "out" / "review.html"
        cls.code, cls.stdout, cls.stderr = run_preview(root, "-o", out, "--plan", "PLAN-0001")
        cls.page = out.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_exit_code_and_summary(self):
        self.assertEqual(self.code, 0, self.stderr)
        self.assertIn("(2 diagrams)", self.stdout)
        self.assertIn("3 features, 3 findings", self.stdout)

    def test_page_is_turkish_and_self_contained(self):
        self.assertIn('<html lang="tr"', self.page)
        self.assertIn("mermaid@11.4.1", self.page)
        self.assertIn('securityLevel: "strict"', self.page)
        self.assertNotIn("<link", self.page)
        self.assertEqual(self.page.count("<script src="), 1)

    def test_summary_dashboard_splits_the_user_job_blockers_and_risks(self):
        panel = self.page.split('id="karar"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Senin işin", panel)
        self.assertIn("Ekibin işi", panel)
        self.assertIn("Kapı G3 açık: final onayı", panel)
        self.assertIn("Onay seçeneği yok", panel)
        self.assertIn('href="#F-02"', panel)
        self.assertIn('href="#R-01"', panel)
        self.assertIn("Topoloji", panel)
        self.assertNotIn('href="#F-01"', panel)
        summary = panel_of(self.page, "ozet")
        self.assertIn("Senden karar bekleniyor: Kapı G3, final onayı", summary)
        blockers = summary.split('id="engel"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Devri engelleyen maddeler", blockers)
        self.assertIn('href="#SEC-01"', blockers)
        self.assertIn("kiracı yalıtımı açığı", blockers)
        self.assertIn("<code>değiştir SEC-01</code>", blockers)
        self.assertIn("security-architect", blockers)
        risks = summary.split('id="riskler"', 1)[1].split("</section>", 1)[0]
        self.assertIn('href="#PERF-01"', risks)
        self.assertIn("performans bulgusu", risks)
        self.assertNotIn("H maddesi", self.page)

    def test_feature_rows_with_filters_stories_and_links(self):
        for item_id in ("F-01", "F-02", "F-03", "R-01"):
            self.assertIn(f'<tbody class="xrow" id="{item_id}"', self.page)
        self.assertIn('data-priority="P1"', self.page)
        self.assertIn('data-key="slice"', self.page)
        self.assertIn('<h3 class="sub">Katalog önerileri', self.page)
        self.assertIn("Hikayeler ve ölçütler", self.page)
        self.assertIn('id="US-01"', self.page)
        self.assertIn("the system shall show accounts", self.page)
        self.assertIn('<a class="ref" href="#D-01">D-01</a>', self.page)

    def test_deep_link_anchors_and_id_mentions_are_links(self):
        for anchor in ("D-01", "D-02", "INV-01", "SEC-01", "panel-ozellikler", "panel-diyagramlar"):
            self.assertIn(f'id="{anchor}"', self.page)
        self.assertIn('<a class="ref" href="#F-01">F-01</a>', self.page)
        self.assertIn('data-f="F-02"', self.page)

    def test_every_anchor_is_unique_and_every_link_has_a_target(self):
        ids = re.findall(r'\sid="([^"]+)"', self.page)
        self.assertEqual([i for i in set(ids) if ids.count(i) > 1], [])
        self.assertEqual({h for h in re.findall(r'href="#([^"]+)"', self.page)} - set(ids), set())

    def test_sidebar_items_are_one_line_icon_buttons_without_counts(self):
        nav = self.page.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(nav.count('role="tab"'), 7)
        self.assertEqual(nav.count("<svg"), 7)
        self.assertNotIn('class="count"', nav)
        self.assertIsNone(re.search(r'tab-label">[^<]*\d', nav))
        self.assertNotIn("h-alert", self.page)

    def test_page_headers_carry_the_totals(self):
        self.assertIn('<p class="pmeta">3 özellik, 1 öneri</p>', panel_of(self.page, "ozellikler"))
        self.assertIn('<p class="pmeta">3 bulgu, 2 açık</p>', panel_of(self.page, "guvenlik"))
        self.assertIn('<p class="pmeta">2 diyagram</p>', panel_of(self.page, "diyagramlar"))

    def test_no_one_sided_accent_border(self):
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertNotIn("border-left", css)
        one_side = re.findall(r"border-(?:left|right|top|bottom)(?:-color)?\s*:([^;}]*)", css)
        self.assertEqual([v for v in one_side if re.search(r"accent|warn|bad|ok|info|#", v)], [])
        self.assertIsNone(re.search(r"inset\s+-?\d+px\s+0\s+0", css))

    def test_step_bar_is_only_on_the_summary(self):
        self.assertEqual(self.page.count('<div class="track">'), 1)
        self.assertIn('<div class="track">', panel_of(self.page, "ozet"))
        self.assertNotIn('class="track"', panel_of(self.page, "ozellikler"))
        track = self.page.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertEqual(track.count('class="track-now"'), 1)
        self.assertNotIn('class="nname"', track)

    def test_data_model_uml_view_is_one_class_diagram(self):
        panel = panel_of(self.page, "veri")
        self.assertIn('data-view="uml"', panel)
        self.assertIn('data-view="table" aria-pressed="true"', panel)
        figure = panel.split('class="diagram uml-figure"', 1)[1].split("</figure>", 1)[0]
        self.assertEqual(figure.count('<pre class="mermaid">'), 1)
        source = html.unescape(figure.split('<pre class="mermaid">', 1)[1].split("</pre>", 1)[0])
        self.assertTrue(source.startswith("classDiagram\n"))
        self.assertIn("  class account {\n    uuid id PK\n    uuid tenant_id FK\n    text name\n  }", source)
        self.assertIn('  account "1" -- "0..*" contact : employs', source)
        self.assertIn("  class contact\n", source + "\n")
        self.assertIn('data-act="fit"', figure)
        self.assertIn("#panel-veri.is-uml .uml-figure", self.page)

    def test_motion_is_short_ease_out_and_respects_reduced_motion(self):
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        js = self.page.split("<script>")[-1].split("</script>", 1)[0]
        reduced = css.split("@media (prefers-reduced-motion: reduce) {\n  *", 1)[1]
        self.assertIn("transition: none !important", reduced)
        self.assertIn("animation: none !important", reduced)
        self.assertIn("select::picker(select)", css)
        self.assertIn("@starting-style", css)
        self.assertIn("if (reduced || !el.animate)", js)
        self.assertIn('duration: 180, easing: "ease-out"', js)
        self.assertIn('if (!summary || reduced) return;', js)

    def test_source_paths_link_to_the_markdown_files(self):
        self.assertIn('href="../crm/docs/02-domain/DOM-0001-account.md"', self.page)

    def test_every_finding_status_says_who_acts_next(self):
        findings = panel_of(self.page, "guvenlik")
        self.assertIn("security-architect bir çözüm önerip belgeye yazar.", findings)
        self.assertIn("Kapandı; yapılacak iş yok.", findings)
        notes = sys.modules["preview_render"].status_note
        base = {"owner": "ux-designer", "severity": "MAJOR"}
        self.assertIn("ux-designer bulguya itiraz etti", notes({**base, "state": "disputed"}))
        self.assertIn("Risk kabul edildi", notes({**base, "state": "accepted_risk"}))
        fixed = notes({**base, "state": "fixed"})
        self.assertIn("geliştirme ekibi ilgili dilimde bunu dener ve testle doğrular", fixed)
        self.assertNotIn("doğrulanması zorunlu", fixed)
        self.assertIn("doğrulanması zorunlu", notes({**base, "state": "fixed", "severity": "CRITICAL"}))
        self.assertNotIn("verdict", self.page.lower().split("<style>", 1)[0] + panel_of(self.page, "ozet"))
        self.assertNotIn("düzeltildi, doğrulanmadı", self.page)

    def test_controls_share_one_icon_size_and_keep_their_box_in_every_state(self):
        svgs = re.findall(r"<svg[^>]*>", self.page.split("<body>", 1)[1])
        self.assertTrue(svgs)
        self.assertEqual([t for t in svgs if 'class="ico"' not in t], [])
        for button in ('class="btn icon-btn nav-toggle"', 'class="btn theme"'):
            self.assertIn('<svg class="ico"', self.page.split(button, 1)[1].split("</button>", 1)[0])
        nav = self.page.split('<nav class="nav"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(nav.count('<svg class="ico"'), nav.count('role="tab"'))
        self.assertIn('<svg class="ico"', self.page.split('class="copy"', 1)[1].split("</button>", 1)[0])
        css = self.page.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn(".ico { flex: 0 0 16px; width: 16px; height: 16px;", css)
        for state in ('.tab[aria-selected="true"]', '.seg button[aria-pressed="true"]', ".btn:hover"):
            rule = css.split(state + " {", 1)[1].split("}", 1)[0]
            self.assertNotIn("font-weight", rule)
            self.assertNotIn("border:", rule)
        self.assertIn("position: absolute", css.split(".copy.is-done::after {", 1)[1].split("}", 1)[0])

    def test_doc_text_is_escaped(self):
        self.assertNotIn("<script>alert(1)</script>", self.page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", self.page)

    def test_mermaid_source_is_the_offline_fallback(self):
        self.assertEqual(panel_of(self.page, "diyagramlar").count('<pre class="mermaid">'), 2)
        self.assertIn('<details class="diagram-src" open>', self.page)
        self.assertIn("Mermaid betiği yüklenemedi", self.page)
        self.assertIn("account ||--o{ contact : &quot;employs&quot;", self.page)

    def test_data_model_findings_quality_and_process(self):
        self.assertIn('<article class="entity" id="entity-account"', self.page)
        self.assertIn("<h3><code>account</code></h3>", self.page)
        self.assertIn("tenant_id", self.page)
        self.assertIn('class="chip tone-hcls" title="kiracı yalıtımı açığı">H3</span>', self.page)
        self.assertIn("CRITICAL", self.page)
        self.assertIn("Tasarım izlenebilirliği", self.page)
        self.assertIn('aria-valuenow="50"', self.page)
        self.assertIn('H6 <a class="ref" href="#F-02">F-02</a>: no user story references it', self.page)
        self.assertIn("38 / 45", self.page)
        self.assertIn('class="meter tone-warn"', self.page)
        self.assertIn("3 / 4", self.page)
        self.assertIn("<code>unknown</code>", self.page)
        self.assertIn("security-architect", self.page)

    def test_stepper_marks_the_open_gate(self):
        self.assertIn('aria-current="step"', self.page)
        self.assertIn("Kapı G3", self.page)
        self.assertIn("Şu an:", self.page)

    def test_theme_and_print_support(self):
        self.assertIn("prefers-color-scheme: dark", self.page)
        self.assertIn(':root[data-theme="dark"]', self.page)
        self.assertIn("@media print", self.page)
        self.assertIn('id="theme"', self.page)


class OldUsageTest(unittest.TestCase):
    def test_folder_of_mermaid_docs_still_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "PLAN-0001-crm.md"
            doc.write_text(
                '---\ntitle: "CRM: product plan"\n---\n\n## Scope map\n\n```mermaid\nflowchart LR\n  a --> b\n```\n\n'
                "## Data model\n\n```mermaid\nerDiagram\n  a ||--o{ b : \"<has>\"\n```\n",
                encoding="utf-8",
            )
            out = Path(tmp) / "out" / "preview.html"
            code, stdout, _ = run_preview(tmp, "-o", out)
            page = out.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn("(2 diagrams", stdout)
        self.assertEqual(panel_of(page, "diyagramlar").count('<pre class="mermaid">'), 2)
        self.assertIn("Scope map", page)
        self.assertIn("CRM: product plan", page)
        self.assertIn("&lt;has&gt;", page)
        self.assertIn("Şu an senden beklenen bir karar yok", page)

    def test_several_files_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            one, two = Path(tmp) / "a.md", Path(tmp) / "b.md"
            one.write_text("## A\n\n```mermaid\nflowchart LR\n  a --> b\n```\n", encoding="utf-8")
            two.write_text("## B\n\n```mermaid\nflowchart LR\n  c --> d\n```\n", encoding="utf-8")
            code, stdout, _ = run_preview(one, two, "-o", Path(tmp) / "x.html")
        self.assertEqual(code, 0)
        self.assertIn("(2 diagrams", stdout)

    def test_nothing_to_show_and_missing_paths_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "empty.md"
            doc.write_text("# Nothing\n", encoding="utf-8")
            self.assertEqual(run_preview(doc, "-o", Path(tmp) / "x.html")[0], 1)
            self.assertFalse((Path(tmp) / "x.html").exists())
            self.assertEqual(run_preview(Path(tmp) / "missing.md", "-o", Path(tmp) / "x.html")[0], 2)

    def test_broken_run_state_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            plans = Path(tmp) / "docs" / "05-work" / "plans"
            plans.mkdir(parents=True)
            (plans / "PLAN-0002.run.json").write_text("{not json", encoding="utf-8")
            (plans / "PLAN-0002-x.md").write_text("| ID | Başlık |\n|---|---|\n| F-01 | Giriş |\n", encoding="utf-8")
            code, _, _ = run_preview(tmp, "-o", Path(tmp) / "x.html")
            page = (Path(tmp) / "x.html").read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertIn('id="F-01"', page)
        self.assertIn("run.json", page)


def render_track_of(state):
    return preview.render_track(preview.track_of(state))


def engine_state():
    """A run.json as plan_state writes it, at gate A with the strategy and catalog done."""
    state = engine.new_state("PLAN-0003")
    for name in ("strategy", "catalog"):
        state["tasks"][name]["status"] = "done"
    state["gates"]["Q1"]["status"] = "approved"
    state["gates"]["G1"]["status"] = "open"
    state["gates"]["G2"]["status"] = "open"
    state["budget"]["calls"]["total"] = 19
    state["run"]["status"] = "waiting_user"
    return state


class EngineStateTest(unittest.TestCase):
    def render_state(self, state):
        with tempfile.TemporaryDirectory() as tmp:
            plans = Path(tmp) / "docs" / "05-work" / "plans"
            plans.mkdir(parents=True)
            (plans / "PLAN-0003.run.json").write_text(json.dumps(state), encoding="utf-8")
            code, _, _ = run_preview(tmp, "-o", Path(tmp) / "x.html", "--plan", "PLAN-0003")
            return code, (Path(tmp) / "x.html").read_text(encoding="utf-8")

    def test_default_budget_is_24_calls_with_a_warning_at_18(self):
        self.assertEqual((preview.DEFAULT_CALL_LIMIT, preview.DEFAULT_CALL_WARN), (24, 18))
        state = engine_state()
        state.pop("limits")
        code, page = self.render_state(state)
        self.assertEqual(code, 0)
        self.assertIn("19 / 24", page)
        self.assertIn('class="meter tone-warn"', page)
        self.assertIn("Uyarı eşiği 18 çağrı geçildi.", page)

    def test_budget_reads_the_limits_plan_state_writes(self):
        state = engine_state()
        state["limits"]["calls"].update(cap=30, warn=18)
        _, page = self.render_state(state)
        self.assertIn("19 / 30", page)

    def panel(self, state):
        _, page = self.render_state(state)
        return page.split('id="karar"', 1)[1].split("</section>", 1)[0]

    def test_gate_answers_are_the_turkish_words_per_gate(self):
        panel = self.panel(engine_state())
        g1, g2 = panel.split("Kapı G2", 1)
        for word in ("<code>onayla</code>", "<code>değiştir: &lt;ne&gt;</code>", "<code>durdur</code>"):
            self.assertIn(word, g1)
        self.assertIn("<code>karar sütununu doldurup tamam</code>", g2)
        self.assertIn("<code>varsayılanlar</code>", g2)
        self.assertNotIn("approve", panel)
        state = engine_state()
        state["gates"]["G1"]["status"] = state["gates"]["G2"]["status"] = "approved"
        state["gates"]["G3"]["status"] = "open"
        self.assertIn("<code>onayla</code>", self.panel(state))
        state["findings"]["SEC-01"] = {"severity": "CRITICAL", "status": "open", "claim": "x", "evidence": "y",
                                       "owner": "solution-architect", "cls": None}
        panel = self.panel(state)
        self.assertIn("<code>kapsamdan çıkar &lt;ID&gt;</code>", panel)
        self.assertNotIn("<code>onayla</code>", panel)  # an open CRITICAL makes the handoff ineligible

    def test_a_blocked_question_replaces_the_calm_message(self):
        state = engine_state()
        state["gates"]["G1"]["status"] = state["gates"]["G2"]["status"] = "approved"
        state["run"]["blocked"] = [{"target": "calls", "reason": "role-call cap 24 reached"}]
        state["run"]["status"] = "blocked"
        _, page = self.render_state(state)
        self.assertNotIn("bir kez uzat", page)
        self.assertNotIn("role-call cap", page)
        state["run"]["closing"] = "done"
        panel = self.panel(state)
        self.assertIn("Kapı G3 değişikliği için verilen çağrılar bitti", panel)
        self.assertNotIn("mevcut hâli kabul et", panel)
        state["run"]["closing"] = None
        state["run"]["blocked"] = []
        state["tasks"]["design"]["status"] = "blocked"
        state["tasks"]["design"]["history"] = [[3, "running", "blocked", "T4", "retry limit reached"]]
        panel = self.panel(state)
        self.assertIn("Görev engellendi: design (retry limit reached)", panel)
        self.assertIn("<code>mevcut hâli kabul et</code>", panel)

    def test_the_call_cap_never_offers_an_extension(self):
        state = engine_state()
        state["limits"]["calls"]["extended"] = True
        state["budget"]["calls"]["total"] = 24
        _, page = self.render_state(state)
        self.assertNotIn("uzat", page)
        self.assertIn("son çağrılar kapanışa ayrıldı", page)

    def test_a_closing_run_says_so_in_the_hero_and_the_step_bar(self):
        state = engine_state()
        state["gates"]["G1"]["status"] = state["gates"]["G2"]["status"] = "approved"
        state["run"].update(status="active", closing="active")
        state["tasks"]["slices"]["status"] = "running"
        _, page = self.render_state(state)
        summary = panel_of(page, "ozet")
        hero = summary.split('id="durum"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Kapanış: son çağrı eksikleri kapatıyor.", hero)
        track = summary.split('<div class="track">', 1)[1].split("</div>", 1)[0]
        self.assertIn('<p class="track-now">Kapanış: son çağrı eksikleri kapatıyor. Şu an:', track)
        self.assertNotIn("Kapanış:", render_track_of(engine_state()))

    def test_a_stopped_run_after_sitting_a_offers_tamamla(self):
        state = engine_state()
        state["gates"]["G1"]["status"] = state["gates"]["G2"]["status"] = "approved"
        state["gates"]["G3"]["status"] = "open"
        state["run"]["status"] = "stopped"
        _, page = self.render_state(state)
        summary = panel_of(page, "ozet")
        hero = summary.split('id="durum"', 1)[1].split("</section>", 1)[0]
        self.assertIn("<code>/design-project</code> yaz, sonra <code>tamamla</code> cevabını ver", hero)
        self.assertIn("tek bir kapanış çağrısı eksik teslim dilimlerini yazar", hero)
        self.assertNotIn('class="cmd"', hero)
        duty = summary.split('id="karar"', 1)[1].split("</section>", 1)[0]
        self.assertIn("<code>tamamla</code>", duty)
        self.assertIn("Claude oturumunda sırayla yaz:", duty)

    def test_track_marks_the_steps_small_mode_skipped(self):
        state = engine_state()
        for name in engine.SMALL_SKIP:
            state["tasks"][name].update(status="done", skipped=True)
        html = preview.render_track(preview.track_of(state))
        self.assertIn("Güvenlik ve performans: bekliyor; performans atlandı (küçük mod)", html)
        self.assertIn("kalite planı atlandı (küçük mod)", html)
        self.assertNotIn("atlandı", preview.render_track(preview.track_of(engine_state())))

    def test_a_stopped_run_shows_no_gate_and_no_fixed_finding_as_open(self):
        state = engine_state()
        state["gates"]["G3"]["status"] = "open"
        state["run"]["status"] = "stopped"
        base = {"claim": "x", "evidence": "y", "owner": "solution-architect", "severity": "MINOR"}
        state["findings"]["SEC-01"] = {**base, "status": "fixed", "cls": "H3"}
        state["findings"]["SEC-02"] = {**base, "status": "open", "cls": "H5"}
        state["run"]["brief"] = "docs/05-work/plans/BRIEF-0003-crm.md"
        state["decisions"]["DEC-01"] = {"action": "stop", "target": "calls", "at": "2026-11-10T21:36:40+00:00"}
        _, page = self.render_state(state)
        summary = panel_of(page, "ozet")
        hero = summary.split('id="durum"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Planlama durduruldu", hero)
        self.assertIn("Rol çağrısı sınırı dolunca durdurma kararı verildi", hero)
        self.assertIn("motor kapı cevabı kabul etmez", hero)
        self.assertIn("<code>/design-project docs/05-work/plans/BRIEF-0003-crm.md</code>", hero)
        self.assertIn("A oturumundan önce durduğu için tamamlanamaz", hero)
        self.assertNotIn("tamamla</code>", page)
        self.assertNotIn("hiçbir kapı kararı uygulanmaz", page)
        self.assertNotIn("Onay seçeneği yok", summary)
        for word in ("onayla", "değiştir &lt;ID&gt;", "durdur"):
            self.assertNotIn(f"<code>{word}</code>", summary)
        self.assertIn("SEC-02", summary)
        self.assertNotIn("SEC-01", summary)
        self.assertEqual(preview.eligibility(state), (None, []))

    def test_default_track_follows_the_plan_state_flow(self):
        track = preview.track_of(engine_state())
        extra = [g for g in engine.GATES if g not in ("Q1", "G1", "G2", "G3")]
        self.assertEqual([n["id"] for n in track], ["0", "1", "2", "A", "3", "4", "5", *extra, "6", "7", "G3", "8"])
        self.assertEqual({t[1] for t in engine.FLOW}, set(range(1, 8)))
        by_id = {node["id"]: node for node in track}
        self.assertEqual(by_id["1"]["status"], "done")
        self.assertEqual(by_id["0"]["status"], "approved")
        self.assertEqual(by_id["A"]["status"], "open")
        self.assertTrue(by_id["A"]["current"])
        self.assertEqual(by_id["3"]["status"], "pending")
        self.assertEqual(by_id["G3"]["status"], "")
        self.assertEqual(by_id["8"]["status"], "")


BORN_CATALOG = """---
id: PLAN-0002
title: "CRM: özellik kataloğu"
---
# CRM: özellik kataloğu

| ID | Tür | Başlık | Öncelik | Büyüklük | karar |
|---|---|---|---|---|---|
| G-01 | G | Oturum düşerse taslak korunur | P1 | S | kabul |
"""

BORN_SLICES = """---
id: PLAN-0003
title: "CRM: dilimler"
---
# CRM: dilimler

## Notlar
- F-05 ile F-06 için hikayeler katalogda eklendi; riskler sonra ele alınır.
"""


class BornFeatureTest(unittest.TestCase):
    """
    Features that plan_state created at G2 from a G row, and the run-state views that change how a page reads.
    """

    def render(self, state):
        with tempfile.TemporaryDirectory() as tmp:
            plans = Path(tmp) / "docs" / "05-work" / "plans"
            plans.mkdir(parents=True)
            (plans / "PLAN-0002-catalog.md").write_text(BORN_CATALOG, encoding="utf-8")
            (plans / "PLAN-0003-slices.md").write_text(BORN_SLICES, encoding="utf-8")
            (plans / "PLAN-0001.run.json").write_text(json.dumps(state), encoding="utf-8")
            code, _, err = run_preview(tmp, "-o", Path(tmp) / "out" / "x.html", "--plan", "PLAN-0001")
            self.assertEqual(code, 0, err)
            return (Path(tmp) / "out" / "x.html").read_text(encoding="utf-8")

    def state(self):
        state = engine.new_state("PLAN-0001")
        slices = "docs/05-work/plans/PLAN-0003-slices.md"
        state["ids"]["G-01"] = {"prefix": "G", "owner": "product-manager", "doc": "docs/05-work/plans/PLAN-0002-catalog.md",
                                "status": "active", "origin": None, "decision": "accepted"}
        state["ids"]["F-05"] = {"prefix": "F", "owner": "plan_state", "doc": slices, "status": "active",
                                "origin": "G-01", "decision": "accepted"}
        state["ids"]["F-06"] = {"prefix": "F", "owner": "plan_state", "doc": slices, "status": "active",
                                "origin": "G-09", "decision": "accepted"}
        return state

    def row(self, page, item_id):
        return page.split(f'<tbody class="xrow" id="{item_id}"', 1)[1].split("</tr>", 1)[0]

    def test_a_born_feature_takes_its_title_from_the_origin_row_not_from_a_mention(self):
        page = self.render(self.state())
        self.assertIn("Oturum düşerse taslak korunur", self.row(page, "F-05"))
        self.assertNotIn("riskler sonra", self.row(page, "F-05"))
        self.assertIn('<a class="ref" href="#F-05">F-05</a>', self.row(page, "G-01"))

    def test_a_born_feature_without_an_origin_title_says_so(self):
        row = self.row(self.render(self.state()), "F-06")
        self.assertIn("başlık kaynakta yok", row)
        self.assertNotIn("riskler sonra", row)

    def test_a_fixed_finding_is_never_shown_as_a_success(self):
        state = self.state()
        state["findings"]["SEC-01"] = {"severity": "MAJOR", "status": "fixed", "claim": "x", "evidence": "y",
                                       "owner": "security-architect", "cls": "H3", "history": [[3, "open"], [5, "fixed"]]}
        page = self.render(state)
        row = page.split('<tbody class="xrow" id="SEC-01"', 1)[1].split("</tbody>", 1)[0]
        self.assertIn('class="chip tone-unverified"', row)
        self.assertNotIn("tone-ok", row)
        self.assertIn("open (rev 3) → fixed (rev 5)", row)
        self.assertIn("çözüm önerildi", row)
        self.assertIn("Planlama çözümü belgeye yazdı", row)
        self.assertIn('<p class="pmeta">1 bulgu, 0 açık</p>', page)
        self.assertIn("Kapı G3 açılınca hesaplanır", page)

    def test_a_quality_plan_left_behind_by_later_fixes_is_named(self):
        state = self.state()
        state["tasks"]["quality"].update(status="cancelled", history=[[4, "running", "done", "T1", ""],
                                                                       [7, "done", "stale", "T2", "contract change by ux"],
                                                                       [9, "stale", "cancelled", "T3", "stop (DEC-02)"]])
        page = self.render(state)
        self.assertIn("Kalite planı son düzeltmelerle eşitlenmedi.", page)
        self.assertIn("done → stale (contract change by ux), sonra cancelled (stop (DEC-02))", page)
        state["tasks"]["quality"].update(status="done")
        self.assertNotIn("eşitlenmedi", self.render(state))


class EndToEndTest(unittest.TestCase):
    """
    A page built from a real plan_state run that the fixture team drives to gate G3.
    """

    @classmethod
    def setUpClass(cls):
        import plan_state_fixtures as fx
        cls.root = fx.tmp_project()
        fx.run(cls.root, "init", "BRIEF.md", "--op", "init")
        fx.FakeTeam(cls.root).run_until("ASK G3")
        # A Mermaid ERD inside the D-01 block, as the solution architect writes it; the run state stays as it is.
        dom = next(cls.root.rglob("DOM-0001-*.md"))
        dom.write_text(dom.read_text(encoding="utf-8") + "\n```mermaid\nerDiagram\n  deal {\n    uuid id PK\n"
                       "    uuid tenant_id FK\n    text stage\n  }\n  deal ||--o{ audit : \"records\"\n```\n",
                       encoding="utf-8")
        out = cls.root / ".cache" / "plan" / "review-G3.html"
        cls.code, cls.stdout, cls.stderr = run_preview(cls.root, "-o", out, "--plan", "PLAN-0001")
        cls.page = out.read_text(encoding="utf-8")
        sample = os.environ.get("PREVIEW_SAMPLE")
        if sample:
            Path(sample).write_text(cls.page, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_page_shows_the_run(self):
        self.assertEqual(self.code, 0, self.stderr)
        self.assertIn("1 features, 4 findings", self.stdout)
        panel = self.page.split('id="karar"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Kapı G3 açık", panel)
        self.assertIn("<title>Deal board: plan incelemesi</title>", self.page)
        self.assertIn('aria-current="step"', self.page)
        for anchor in ("F-01", "R-01", "US-01", "BR-01", "INV-01", "S0", "D-01", "D-02", "SEC-01", "SEC-02", "DA-01"):
            self.assertIn(f'id="{anchor}"', self.page)
        self.assertIn("Pipeline board", self.page)
        self.assertIn("When a card moves, the system shall record the stage.", self.page)
        self.assertIn("no audit trail", self.page)
        self.assertIn("<h3><code>deal</code></h3>", self.page)
        self.assertEqual(panel_of(self.page, "diyagramlar").count('<pre class="mermaid">'), 1)
        self.assertIn("  class deal {\n    uuid id PK", panel_of(self.page, "veri"))
        self.assertIn("Bu D bloğunda Mermaid yok.", self.page)
        self.assertIn("solution-architect", self.page)
        self.assertIn('href="../../docs/03-domains/deals/DOM-0001-deals.md"', self.page)
        self.assertIn('<a class="ref" href="#D-01">D-01</a>', self.page)

    def test_findings_are_split_into_tables_by_status(self):
        panel = panel_of(self.page, "guvenlik")
        self.assertIn('<div class="ftables">', panel)
        self.assertIn('<h3 class="sub">Çözüm önerildi <span class="count">2</span></h3>', panel)
        self.assertEqual(panel.count('class="xrow"'), 2)
        ids = re.findall(r'id="(xd-[^"]+)"', panel)
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_run_keeps_the_live_review_page_up_to_date(self):
        live = (self.root / ".cache" / "plan" / "review.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="tr" data-live="1">', live)
        self.assertIn('id="reload"', live)
        self.assertIn(preview_render.RELOAD_TIP, live)
        self.assertIn('class="live"', live)
        self.assertRegex(live, r"güncellendi: <time datetime=\S+>\d\d:\d\d</time>")


class LiveReviewTest(unittest.TestCase):
    """
    plan_state rebuilds .cache/plan/review.html after each accepted command, and never fails because of it.
    """

    def setUp(self):
        import plan_state_fixtures as fx
        self.fx = fx
        self.root = fx.tmp_project()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.page = self.root / ".cache" / "plan" / "review.html"

    def test_a_mutating_command_rebuilds_the_page(self):
        code, _ = self.fx.run(self.root, "init", "BRIEF.md", "--op", "init")
        self.assertEqual(code, 0)
        self.assertIn('id="reload"', self.page.read_text(encoding="utf-8"))
        self.page.unlink()
        self.fx.run(self.root, "status")
        self.assertFalse(self.page.exists(), "a read only command must not rebuild the page")

    def test_a_broken_preview_does_not_fail_the_command(self):
        saved = sys.modules.get("preview_render")
        sys.modules["preview_render"] = None
        try:
            code, out = self.fx.run(self.root, "init", "BRIEF.md", "--op", "init")
        finally:
            sys.modules["preview_render"] = saved
        self.assertEqual(code, 0, out)
        self.assertFalse(self.page.exists())

    def test_a_finished_run_does_not_reload_itself(self):
        for status in ("handed_off", "stopped"):
            state = engine_state()
            state["run"]["status"] = status
            _, page = EngineStateTest.render_state(self, state)
            self.assertNotIn("data-live", page.split("<head>", 1)[0])
            self.assertNotIn('class="live"', page)
            self.assertIn('id="reload"', page)
        _, page = EngineStateTest.render_state(self, engine_state())
        self.assertIn('data-live="1"', page.split("<head>", 1)[0])

    def test_reload_keeps_the_view_and_auto_reload_needs_a_visible_live_page(self):
        js = (SKILL / "preview_assets" / "page.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem(RELOAD_KEY", js)
        self.assertIn('root.dataset.live === "1"', js)
        self.assertIn('document.visibilityState === "visible"', js)
        self.assertIn("30000", js)

    def test_process_blocks_share_one_width(self):
        css = (SKILL / "preview_assets" / "page.css").read_text(encoding="utf-8")
        self.assertIn("#panel-surec > :not(.phead) { max-width: var(--wide); }", css)


if __name__ == "__main__":
    unittest.main()
