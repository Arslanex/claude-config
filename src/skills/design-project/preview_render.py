"""
Render the plan review page from the model that preview_model reads.

The page is one HTML file: the data is written into the markup when the page is built, so it opens from file://
without a server. The stylesheet and script come from preview_assets/ and are inlined. All doc text is escaped.
A pinned Mermaid loads from a CDN when the page opens; without it every diagram shows its Mermaid source.
"""
from __future__ import annotations

import datetime
import html
import os
import re
from pathlib import Path

from plan_state import checks, registry
from preview_model import (ANY_ID, CARD_KINDS, DEFAULT_CALL_LIMIT, DEFAULT_CALL_WARN, DEFAULT_CONTACT_LIMIT,
                           FINDING_KINDS, OPEN_STATES, UNVERIFIED_STATES, Model, clean, dig, eligibility, id_key,
                           norm, num, out_of_sync, traceability, track_of)

ASSETS = Path(__file__).resolve().parent / "preview_assets"
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
OWN_VIEW = CARD_KINDS + FINDING_KINDS + ("US", "D", "DEC", "E", "S")
PREFIX_LABEL = {"INV": "Değişmez kurallar (INV)", "BR": "İş kuralları (BR)", "API": "Uçlar ve olaylar (API)"}
CATEGORY = {"F": "Özellikler", "M": "Öneriler", "G": "Öneriler", "R": "Öneriler", "US": "Hikayeler",
            "D": "Diyagramlar", "E": "Veri modeli", "SEC": "Güvenlik", "PERF": "Güvenlik", "QA": "Güvenlik",
            "DA": "Güvenlik", "INV": "Kurallar", "BR": "Kurallar", "S": "Dilimler", "DEC": "Kararlar",
            "API": "Uçlar"}
STATUS_LABEL = dict(pair.split("=") for pair in (
    "accepted=kabul|accept=kabul|proposed=önerildi|rejected=reddedildi|reject=reddedildi|deferred=ertelendi|"
    "defer=ertelendi|modify=değişecek|add=eklenecek|draft=taslak|done=bitti|open=açık|fixed=çözüm önerildi|"
    "closed=kapandı|disputed=itirazlı|accepted_risk=risk kabul edildi|descoped=kapsamdan çıktı|pending=bekliyor|"
    "running=sürüyor|blocked=engellendi|stale=bayat|cancelled=iptal|approved=onaylandı|stopped=durduruldu|"
    "modify_requested=değişiklik istendi|active=sürüyor|waiting_user=senden karar bekliyor|handed_off=devredildi|"
    "reserved=rezerve|retired=emekli").split("|"))
# Tone per status. Done work stays neutral; only a close is green; a proposed solution stays amber until the dev team tests it.
TONES = {"done": "accepted accept done approved handed_off", "ok": "closed", "info": "active running",
         "unverified": "fixed",
         "warn": "proposed open waiting_user modify modify_requested add disputed stale accepted_risk",
         "mute": "rejected reject deferred defer descoped cancelled pending draft reserved retired",
         "bad": "blocked stopped"}
TONE = {status: tone for tone, names in TONES.items() for status in names.split()}
ICON = {"done": "✓", "ok": "✓", "info": "●", "unverified": "◐", "warn": "▲", "mute": "○", "bad": "■", "pri": "",
        "key": "", "sev-critical": "■", "sev-major": "▲", "sev-minor": "○"}
ACTION_LABEL = {"approve": "onay", "modify": "değiştir", "stop": "durdur", "extend": "uzat", "descope": "kapsamdan çıkar",
                "accept-current": "mevcut hâli kabul", "defaults": "varsayılanlar", "answers": "cevaplar"}
# Sidebar items with a 24 px stroke icon each (SVG path data).
NAV = [("ozet", "Özet", "M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z"),
       ("ozellikler", "Özellikler", "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"),
       ("diyagramlar", "Diyagramlar", "M4 4h6v5H4zM14 15h6v5h-6zM7 9v3a2 2 0 0 0 2 2h6a2 2 0 0 1 2 2"),
       ("veri", "Veri modeli", "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"
        "M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"),
       ("guvenlik", "Güvenlik ve performans", "M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"),
       ("kalite", "Kalite", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6"),
       ("surec", "Süreç", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2")]
# The answers the user types at each gate, in the words the Lead records (SKILL.md, user contacts).
GATE_ANSWERS = {"Q1": ("cevaplar", "varsayılanlar", "durdur"), "Q2": ("cevaplar", "varsayılanlar", "durdur"),
                "G1": ("onayla", "değiştir: <ne>", "durdur"),
                "G2": ("karar sütununu doldurup tamam", "varsayılanlar"),
                "G3": ("onayla", "değiştir <ID>", "kapsamdan çıkar <ID>", "durdur")}
GATE_NAME = {"Q1": "ilk kısa sorular", "Q2": "ikinci kısa sorular", "G1": "strateji onayı",
             "G2": "özellik kataloğu kararı", "G3": "final onayı", "A": "strateji ve katalog kararı"}
# What each answer does, keyed by its first word.
ANSWER_HINT = {"onayla": "planı kabul eder, akış sonraki adıma geçer", "değiştir": "o madde için düzeltme turu açılır",
               "değiştir:": "yazdığın değişiklikle düzeltme turu açılır", "kapsamdan": "maddeyi plandan çıkarır",
               "durdur": "çalışmayı kalıcı olarak kapatır", "cevaplar": "soruların cevabını yazarsın",
               "varsayılanlar": "önerilen varsayılanlar kabul edilir",
               "karar": "katalogda her satırın karar hücresini doldurursun", "bir": "sınırı bir kez yükseltir",
               "mevcut": "açık işler risk listesine geçer, akış sürer",
               "yeniden": "devir hazırlığı bir kez daha denenir", "/design-project": "durdurulan çalışmayı açar",
               "tamamla": "kapanış çağrısını çalıştırır, sonra Kapı G3 onayını sorar"}
CLOSING_NOTE = "Kapanış: son çağrı eksikleri kapatıyor."
# Meaning of the codes a reader meets on the page.
KIND_NAME = {"F": "özellik", "M": "eksik özellik önerisi", "G": "ara özellik önerisi", "R": "sektör önerisi",
             "US": "kullanıcı hikayesi", "INV": "değişmez kural", "BR": "iş kuralı", "SEC": "güvenlik bulgusu",
             "PERF": "performans bulgusu", "QA": "kalite bulgusu", "DA": "itiraz bulgusu", "S": "teslim dilimi",
             "D": "diyagram", "E": "veri tablosu", "DEC": "karar", "API": "uç veya olay"}
HCODE_NAME = {"H1": "kapanmamış kritik bulgu", "H2": "değişmez kural ihlali", "H3": "kiracı yalıtımı açığı",
              "H4": "kimlik veya bağlantı hatası", "H5": "veri bütünlüğü riski", "H6": "izlenebilirlik boşluğu"}
TASK_NAME = {"strategy": "strateji", "catalog": "özellik kataloğu", "design": "veri tasarımı", "ux": "arayüz tasarımı",
             "security": "güvenlik", "performance": "performans", "slices": "teslim dilimleri", "quality": "kalite planı",
             "critic_review": "eleştirmen incelemesi", "fix1": "düzeltme turu", "fix2": "düzeltme turu", "handoff": "devir",
             "closing": "kapanış"}
UML_MULT = {"||": "1", "|o": "0..1", "o|": "0..1", "}|": "1..*", "|{": "1..*", "}o": "0..*", "o{": "0..*"}


# Components

def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


class Page:
    """HTML helpers that know which IDs have an anchor on the page and where the page file lives."""

    def __init__(self, anchors: set[str], out_dir: Path | None = None):
        self.anchors, self.out_dir = anchors, out_dir

    def text(self, value) -> str:
        """Escaped text with code spans and every anchored ID as a link."""
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(value))
        return ANY_ID.sub(lambda m: self.ref(m.group(1)) if m.group(1) in self.anchors else m.group(1), escaped)

    def ref(self, item_id: str) -> str:
        if item_id in self.anchors:
            return f'<a class="ref" href="#{esc(item_id)}">{esc(item_id)}</a>'
        return f'<span class="ref ref-plain">{esc(item_id)}</span>'

    def refs(self, ids) -> str:
        return " ".join(self.ref(i) for i in ids)

    def src(self, doc, label: str = "") -> str:
        """The source path of a doc as a link to the Markdown file, relative to the page."""
        if doc is None:
            return f'<span class="src">{esc(label)}</span>' if label else ""
        label = label or doc.rel
        # A doc with an ID shows it instead of its long path; the full path stays in the tooltip.
        if doc.meta.get("id") and label.startswith(doc.rel):
            label = doc.meta["id"] + label[len(doc.rel):]
        if self.out_dir is None:
            return f'<span class="src" title="{esc(doc.rel)}">{esc(label)}</span>'
        href = Path(os.path.relpath(doc.path, self.out_dir)).as_posix()
        return f'<a class="src" href="{esc(href)}" title="Kaynak belgeyi aç: {esc(doc.rel)}">{esc(label)}</a>'


def chip(label, tone: str = "mute", title: str = "") -> str:
    if not label:
        return ""
    hint = f' title="{esc(title)}"' if title else ""
    icon = ICON.get(tone, "")
    mark = f'<span class="ic" aria-hidden="true">{icon}</span>' if icon else ""
    return f'<span class="chip tone-{tone}"{hint}>{mark}{esc(label)}</span>'


def status_chip(value: str) -> str:
    key = norm(value)
    return chip(STATUS_LABEL.get(key, value), TONE.get(key, "mute"), value if key in STATUS_LABEL else "")


def severity_chip(value: str) -> str:
    return chip(value, {"CRITICAL": "sev-critical", "MAJOR": "sev-major", "MINOR": "sev-minor"}.get(value, "mute"))


def hclass_chip(value: str) -> str:
    return chip(value, "hcls", ", ".join(HCODE_NAME.get(h, h) for h in value.split())) if value else ""


def named(item_id: str) -> str:
    """The plain name of an ID's kind, for example "güvenlik bulgusu" for SEC-15."""
    return KIND_NAME.get(registry.prefix_of(item_id), "")


def is_open(finding: dict) -> bool:
    return (finding.get("state") or "open") in OPEN_STATES


def is_unverified(finding: dict) -> bool:
    return finding.get("state") in UNVERIFIED_STATES


def empty(text: str) -> str:
    return f'<p class="empty">{esc(text)}</p>'


def notice(tone: str, title: str, body: str) -> str:
    return (f'<div class="notice tone-{tone}" role="note"><span class="ic" aria-hidden="true">{ICON.get(tone, "")}'
            f'</span><div><p class="notice-title">{esc(title)}</p>{body}</div></div>')


def attrs(anchor: str, label: str, title: str, category: str = "") -> str:
    """Anchor and search attributes of an element that a deep link or the search box can reach."""
    category = category or (CATEGORY.get(registry.prefix_of(label), "Diğer") if label else "Diğer")
    return f'id="{esc(anchor)}" data-sid="{esc(label)}" data-stitle="{esc(title)}" data-scat="{esc(category)}"'


def ul(values: list, page: Page, cls: str = "ears") -> str:
    return f'<ul class="{cls}">{"".join(f"<li>{page.text(v)}</li>" for v in values)}</ul>' if values else ""


def table(heads, rows: list[list[str]], cls: str, row_attrs=None) -> str:
    """A table whose cells carry their column name, so a phone shows each row as a labeled stack."""
    body = "".join(f"<tr{(' ' + row_attrs[n]) if row_attrs else ''}>"
                   + "".join(f'<td data-label="{esc(h)}">{c}</td>' for h, c in zip(heads, row)) + "</tr>"
                   for n, row in enumerate(rows))
    return (f'<div class="table-wrap"><table class="{cls}"><thead><tr>{"".join(f"<th scope=col>{esc(h)}</th>" for h in heads)}'
            f"</tr></thead><tbody>{body}</tbody></table></div>")


def xtable(heads, rows: list[tuple[str, list[str], str]], cls: str, key: str = "") -> str:
    """
    A table whose rows open a detail row below them. Each row is (attributes, cells, detail); the first cell gets
    the toggle button, and a deep link to the row's ID opens its detail. `key` keeps detail IDs unique when several
    tables share a class.
    """
    key = key or cls
    body = []
    for n, (row_attrs, cells, detail) in enumerate(rows):
        toggle = (f'<button type="button" class="xtoggle" aria-expanded="false" aria-controls="xd-{key}-{n}">'
                  f'<span class="chev" aria-hidden="true"></span>{cells[0]}</button>')
        tds = "".join(f'<td data-label="{esc(h)}">{c}</td>' for h, c in zip(heads[1:], cells[1:]))
        body.append(f'<tbody class="xrow" {row_attrs}><tr class="xmain"><td data-label="{esc(heads[0])}">{toggle}</td>'
                    f'{tds}</tr><tr class="xdetail" id="xd-{key}-{n}" hidden><td colspan="{len(heads)}">'
                    f'<div class="xbody">{detail}</div></td></tr></tbody>')
    head = "".join(f"<th scope=col>{esc(h)}</th>" for h in heads)
    return f'<div class="table-wrap"><table class="xt {cls}"><thead><tr>{head}</tr></thead>{"".join(body)}</table></div>'


def accordion(title: str, count, body: str, anchor: str = "", is_open: bool = False) -> str:
    badge = f' <span class="count">{esc(count)}</span>' if count != "" else ""
    ident = f' id="{esc(anchor)}"' if anchor else ""
    return (f'<details class="acc"{ident}{" open" if is_open else ""}><summary><span class="chev" aria-hidden="true">'
            f'</span><span class="acc-title">{esc(title)}{badge}</span></summary><div class="acc-body">{body}</div>'
            "</details>")


def facts(pairs: list[tuple[str, str]], cls: str = "facts") -> str:
    rows = "".join(f"<div><dt>{esc(k)}</dt><dd>{v}</dd></div>" for k, v in pairs if v)
    return f'<dl class="{cls}">{rows}</dl>' if rows else ""


def details_list(details: list, page: Page) -> str:
    """The key and value lines of a block as a definition list; a line without a key keeps an empty term."""
    rows = "".join(f'<div>{f"<dt>{esc(k)}</dt>" if k else ""}<dd>'
                   f'{page.text(v[0]) if len(v) == 1 else ul(v, page, "plain-list")}</dd></div>'
                   for k, v in details if v)
    return f'<dl class="details">{rows}</dl>' if rows else ""


def filters(target: str, controls: list[tuple[str, str, list[tuple[str, str]]]], text: str = "",
            label: str = "Filtreler") -> str:
    """
    A filter bar over the rows that match `target`: one select per (key, label, options) and an optional text box.
    A row matches a select when the value is one of the space separated tokens in its data-<key> attribute.
    """
    parts = []
    for key, name, options in controls:
        if options:
            opts = "".join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in options)
            parts.append(f'<label class="filter"><span>{esc(name)}</span><select data-key="{esc(key)}">'
                         f'<option value="">Tümü</option>{opts}</select></label>')
    if text:
        parts.append(f'<label class="filter filter-text"><span>{esc(text)}</span>'
                     '<input type="search" data-key="q" placeholder="F-12, kanal" autocomplete="off"></label>')
    if not parts:
        return ""
    return (f'<div class="toolbar" role="group" aria-label="{esc(label)}" data-filters="{esc(target)}">{"".join(parts)}'
            '<button type="button" class="link-button" data-reset>Temizle</button>'
            '<p class="shown" aria-live="polite" data-count></p></div>')


def panel_head(title: str, lede: str, meta: str = "", tools: str = "") -> str:
    """The header band of a page: title and a one line helper on the left, totals and page tools on the right."""
    side = (f'<p class="pmeta">{esc(meta)}</p>' if meta else "") + tools
    return (f'<header class="phead"><div class="phead-text"><h2>{esc(title)}</h2><p class="lede">{lede}</p></div>'
            + (f'<div class="pside">{side}</div>' if side else "") + "</header>")


def stat(label: str, value, tone: str = "", hint: str = "") -> str:
    cls = f" tone-{tone}" if tone else ""
    icon = f'<span class="ic" aria-hidden="true">{ICON.get(tone, "")}</span>' if tone and ICON.get(tone) else ""
    return (f'<div class="stat{cls}"><dt>{esc(label)}</dt><dd>{icon}{esc(str(value))}'
            + (f'<span class="hint">{esc(hint)}</span>' if hint else "") + "</dd></div>")


def meter(label: str, value: float, total: float, text: str, tone: str = "ok", hint: str = "") -> str:
    percent = max(0.0, min(100.0, value / total * 100 if total else 0.0))
    return (f'<div class="meter tone-{tone}"><div class="meter-head"><span>{esc(label)}</span><strong>{esc(text)}</strong>'
            f'</div><div class="meter-track" role="progressbar" aria-label="{esc(label)}" aria-valuemin="0" '
            f'aria-valuemax="{total:g}" aria-valuenow="{value:g}"><span style="width:{percent:.1f}%"></span></div>'
            + (f'<span class="hint">{esc(hint)}</span>' if hint else "") + "</div>")


def amount(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return esc(f"{value:,.0f}".replace(",", ".") if float(value).is_integer() else f"{value:.2f}")
    return '<span class="dim">bilinmiyor (<code>unknown</code>)</span>' if value in (None, "", "unknown") else esc(value)


# Shared 16 px stroke icons of the page controls (SVG path data).
ICONS = {"menu": "M4 6h16M4 12h16M4 18h16", "theme": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 3v18",
         "copy": "M9 9h10v10H9zM5 15V5h10", "reload": "M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4"}
RELOAD_TIP = "Planlama her adımda bu sayfayı yeniden üretir; Yenile son hâli gösterir"
# Run states in which the run is over; any other run state makes the page reload itself while it is visible.
FINISHED_RUNS = ("handed_off", "stopped")


def icon(path: str) -> str:
    """One control icon; every icon on the page uses the shared ico class, so size and stroke match."""
    return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="{path}"/></svg>'


def copy_button(item_id: str) -> str:
    return (f'<button type="button" class="copy" data-copy="{esc(item_id)}" aria-label="{esc(item_id)} kimliğini kopyala"'
            f' title="Kimliği kopyala">{icon(ICONS["copy"])}</button>')


def title_of(item: dict, page: Page) -> str:
    if item.get("missing_title") or not item.get("title"):
        return chip("başlık kaynakta yok", "warn", "Kaynak belgede bu kimliğin başlığı bulunamadı")
    return page.text(item["title"])


# Step track

def gate_label(status: str, stopped: bool) -> str:
    if status == "open":
        return "açık kaldı, artık onaylanamaz" if stopped else "onay bekliyor"
    return STATUS_LABEL.get(status, status) or "bekliyor"


def render_track(track: list[dict], stopped: bool = False, closing: bool = False) -> str:
    """
    The flow on one line: a mark per step and gate, with its name and state in the tooltip. Only the current node
    is described, in one short line under the marks.
    """
    nodes, now = [], ""
    for node in track:
        status = norm(node["status"])
        state_text = gate_label(status, stopped) if node["kind"] == "gate" else STATUS_LABEL.get(status, node["status"]) or "bekliyor"
        tone = "warn" if node["kind"] == "gate" and status == "open" else TONE.get(status, "none")
        if node["current"]:
            name = (f"{node['name']}, {GATE_NAME.get(node['id'], '')}".rstrip(", ") if node["kind"] == "gate"
                    else f"Adım {node['id']}, {node['name']}")
            now = f"{name} ({state_text})"
        skipped = "".join(f"; {name} atlandı (küçük mod)" for name in node.get("skipped", []))
        label = esc(f"{node['name']}: {state_text}{skipped}")
        current = ' is-current" aria-current="step"' if node["current"] else '"'
        nodes.append(f'<li class="node {node["kind"]} is-{tone}{current} title="{label}"><span class="nmark" aria-hidden="true">'
                     f'{esc(node["id"])}</span><span class="sr">{label}</span></li>')
    lead = "Plan durduruldu. " if stopped else f"{CLOSING_NOTE} " if closing else ""
    now = f'<p class="track-now">{lead}Şu an: <strong>{esc(now)}</strong></p>' if now else (
        f'<p class="track-now">{lead}</p>' if lead else "")
    return (f'<div class="track"><ol class="steps" aria-label="Planlama adımları (0 ile 8) ve kapılar">{"".join(nodes)}</ol>'
            f"{now}</div>")


# Decision panel

def blocked_questions(state: dict) -> list[tuple[str, list[str]]]:
    """The blocked questions the run waits on (a limit, a task, a failed handoff), each with its answers."""
    out = []
    limits = dig(state, "limits", default={})
    for b in dig(state, "run", "blocked", default=[]) or []:
        target = b.get("target", "") if isinstance(b, dict) else ""
        extend = [] if dig(limits, target, "extended") else ["bir kez uzat"]
        if target != "calls":
            out.append((f"Sınır doldu: {b.get('reason', target)}", extend + ["mevcut hâli kabul et", "durdur"]))
        elif dig(state, "run", "closing") == "done":
            # The call cap itself never asks; only the calls a G3 change brought can run out (SKILL.md).
            out.append(("Kapı G3 değişikliği için verilen çağrılar bitti", extend + ["durdur"]))
    for name, task in sorted(dig(state, "tasks", default={}).items()):
        if isinstance(task, dict) and task.get("status") == "blocked":
            reason = (task.get("history") or [[""] * 5])[-1][-1]
            extend = [] if task.get("extended") else ["bir kez uzat"]
            out.append((f"Görev engellendi: {name} ({reason})", extend + ["mevcut hâli kabul et", "durdur"]))
    if dig(state, "handoff", "state") == "failed":
        retry = [] if dig(state, "run", "handoff_retried") else ["yeniden dene"]
        out.append(("Devir hazırlığı başarısız", ["değiştir <ID>", "kapsamdan çıkar <ID>"] + retry + ["durdur"]))
    return out


def answer_block(title: str, answers, extra: str = "", lead: str = "Claude oturumuna şunlardan birini yaz:") -> str:
    """A question the user answers in the Claude session: each answer with what it does."""
    rows = "".join(f'<li><code>{esc(a)}</code><span>{esc(ANSWER_HINT.get(a.split()[0], ""))}</span></li>' for a in answers)
    return (f'<div class="decide-gate"><p class="gate-title">{esc(title)}</p>{extra}'
            f'<p class="hint">{esc(lead)}</p><ul class="answers">{rows}</ul></div>')


def quality_drift(model: Model, page: Page) -> str:
    drift = out_of_sync(model.state, "quality")
    if not drift:
        return ""
    left, last = drift["left"], drift["last"]
    reason = f"{left[1]} → {left[2]}" + (f" ({left[4]})" if len(left) > 4 and left[4] else "")
    if last is not left:
        reason += f", sonra {last[2]}" + (f" ({last[4]})" if len(last) > 4 and last[4] else "")
    scope = dig(model.state, "tasks", "quality", "scope", default=[]) or []
    doc = next((d for d in model.docs if d.rel in scope), None) or next(
        (d for d in model.docs if (d.meta.get("title") or "").lower().endswith("quality plan")), None)
    return notice("warn", "Kalite planı son düzeltmelerle eşitlenmedi.",
                  f'<p>Kaynak: run.json, <code>tasks.quality</code>: {esc(reason)}.'
                  + (f" Belge: {page.src(doc)}" if doc else "") + "</p>")


def h_reasons(state: dict) -> list[str]:
    """What would block the handoff (plan_state.checks.h_items), also for a stopped run."""
    try:
        return checks.h_items(state)
    except (KeyError, TypeError, AttributeError, ValueError, IndexError):
        return []


def stop_reason(state: dict, page: Page) -> str:
    stops = [(d, r) for d, r in dig(state, "decisions", default={}).items() if isinstance(r, dict) and r.get("action") == "stop"]
    if not stops:
        return "Çalışma durdurma kararıyla kapandı."
    dec, record = max(stops, key=lambda p: id_key(p[0]))
    target = record.get("gate") or record.get("target") or ""
    where = ("Rol çağrısı sınırı dolunca" if target == "calls" else f"Kapı {target} açıkken" if target in GATE_NAME
             else f"{target} için" if target else "")
    return f"{esc(where)} durdurma kararı verildi ({page.ref(dec)}, {esc(str(record.get('at') or '')[:10])})."


def hero(tone: str, title: str, body: str) -> str:
    return (f'<section class="hero tone-{tone}" id="durum" aria-labelledby="hero-title"><h3 id="hero-title">'
            f'<span class="ic" aria-hidden="true">{ICON.get(tone, "")}</span>{esc(title)}</h3>{body}</section>')


def can_finish(state: dict) -> bool:
    """A stopped run after sitting A can be finished with "tamamla" (plan_state status can_finish)."""
    return dig(state, "run", "status") == "stopped" and dig(state, "gates", "G2", "status") == "approved"


def render_hero(model: Model, page: Page, now: str, waiting: bool) -> str:
    """The main message of the page: the state of the run in plain words, what it means and the next step."""
    state = model.state
    status = str(dig(state, "run", "status", default=""))
    gates = [g for g, r in dig(state, "gates", default={}).items() if dig(r, "status") == "open"]
    if status == "stopped":
        brief = dig(state, "run", "brief", default="") or "<brief yolu>"
        still = f" Kapı {', '.join(gates)} açık görünse de şu an onaylanamaz." if gates else ""
        meaning = (f'<p><b>Ne oldu:</b> {stop_reason(state, page)}</p><p><b>Ne anlama gelir:</b> çalışma durdu ve motor '
                   f'kapı cevabı kabul etmez.{esc(still)} Yazılan belgeler yerinde kalır; geliştirme görevleri yazılmadı.</p>')
        if can_finish(state):
            return hero("bad", "Planlama durduruldu", meaning + (
                '<p><b>Sonraki adım:</b> projede Claude oturumunu aç, <code>/design-project</code> yaz, sonra '
                '<code>tamamla</code> cevabını ver.</p><p class="hint">Tamamla: tek bir kapanış çağrısı eksik teslim '
                'dilimlerini yazar, kritik olmayan açık maddeler geliştirme ekibine not olur, sonra Kapı G3 onayını '
                'sorar.</p>'))
        return hero("bad", "Planlama durduruldu", meaning + (
            '<p><b>Sonraki adım:</b> bu çalışma A oturumundan önce durduğu için tamamlanamaz. Devam etmek istersen '
            'Claude oturumunda yeni bir çalışma başlat; yeni çalışma yeni bir PLAN kimliği alır.</p>'
            f'<p class="cmd"><code>/design-project {esc(brief)}</code></p>'))
    if status == "handed_off" or dig(state, "handoff", "state") == "committed":
        return hero("ok", "Plan devredildi", '<p>Geliştirme görevleri <code>docs/05-work/tasks/</code> altına yazıldı; '
                    'geliştirme ekibi ilk teslim diliminden başlar. Bu planda senden beklenen bir karar kalmadı.</p>')
    if dig(state, "run", "closing") == "active":
        return hero("info", CLOSING_NOTE, "<p>Ekip son çağrıyla eksik teslim dilimlerini yazıyor; kritik olmayan açık "
                    "maddeler geliştirme ekibine not olur. Bitince Kapı G3 açılır ve Claude onayını sorar.</p>")
    if waiting:
        title = (f"Senden karar bekleniyor: Kapı {gates[0]}, {GATE_NAME.get(gates[0], '')}".rstrip(", ") if gates
                 else "Çalışma bir sınıra takıldı ve senden cevap bekliyor")
        return hero("warn", title, '<p>Aşağıdaki "Senin işin" bölümünden bir cevabı Claude oturumuna yaz. '
                    'Sen cevap verene kadar ekip bekler.</p>')
    return hero("info", f"Ekip çalışıyor: {now}" if now else "Ekip çalışıyor",
                "<p>Senden şu an bir şey beklenmiyor. Ekip bir sonraki kapıya gelince Claude sana sorar.</p>")


def blocker_rows(reasons: list[str], model: Model, page: Page) -> list[list[str]]:
    """One row per blocked item: what it is, why it blocks, how it gets closed and who closes it."""
    grouped = {}
    for reason in reasons:
        head, _, text = reason.partition(":")
        ids = ANY_ID.findall(head)
        entry = grouped.setdefault(ids[0] if ids else reason, {"codes": [], "texts": []})
        entry["codes"] += [c for c in re.findall(r"H[1-6]", head) if c not in entry["codes"]]
        entry["texts"].append(text.strip() or head)
    rows = []
    for key, entry in grouped.items():
        is_id = bool(ANY_ID.fullmatch(key))
        finding = model.findings.get(key, {})
        what = finding.get("title") or model.items.get(key, {}).get("title") or "; ".join(entry["texts"])
        how = (f"Claude oturumunda <code>değiştir {esc(key)}</code> yaz: sahibi bir çözüm önerir ve belgeye yazar. "
               f"Ya da <code>kapsamdan çıkar {esc(key)}</code> yaz." if is_id else "Claude'a sor; ilgili rol belgeyi düzeltir.")
        who = finding.get("owner") or model.items.get(key, {}).get("owner") or "ekip"
        rows.append([(page.ref(key) + f'<span class="dim"> {esc(named(key))}</span>') if is_id else "genel",
                     page.text(what), esc("; ".join(HCODE_NAME.get(c, c) for c in entry["codes"])
                                          + ". Bu tür madde açıkken devir yapılamaz."), how, esc(who)])
    return rows


def render_dashboard(model: Model, page: Page, handoff: tuple, track: list[dict]) -> str:
    """The summary dashboard: status, place in the flow, the user's job, the team's job, blockers and risks."""
    state = model.state
    status = str(dig(state, "run", "status", default=""))
    stopped, closed = status == "stopped", status in ("stopped", "handed_off")
    eligible, reasons = handoff
    # Blockers count once G3 has opened; a run stopped at G3 still shows what would have blocked it.
    g3_open = dig(state, "gates", "G3", "status") == "open"
    reasons = reasons if eligible is not None else h_reasons(state) if stopped and g3_open else []
    counted, blockers = eligible is not None or (stopped and g3_open), blocker_rows(reasons, model, page)
    findings = sorted(model.findings.values(), key=lambda f: id_key(f["id"]))
    current = next((n for n in track if n["current"]), None)
    now = (current["name"] if current["kind"] == "gate" else f"Adım {current['id']}, {current['name']}") if current else ""
    mine = [] if closed else [answer_block(title, answers) for title, answers in blocked_questions(state)]
    for gate, record in ({} if closed else dig(state, "gates", default={})).items():
        if dig(record, "status") != "open":
            continue
        actions = list(GATE_ANSWERS.get(gate, ("onayla", "durdur")))
        questions = "".join("<li>" + page.text(f"{i.get('id', '')} {i.get('text', '')}")
                            + (f' <span class="where">varsayılan: {esc(i["default"])}</span>' if i.get("default") else "")
                            + "</li>" for i in record.get("items") or [] if isinstance(i, dict))
        note = ""
        if gate == "G3" and eligible is False:
            actions.remove("onayla")
            note = (f'<p class="gate-note">Onay seçeneği yok: {len(blockers)} madde devri '
                    'engelliyor (aşağıda). Önce onları kapat veya kapsamdan çıkar.</p>')
        title = f"Kapı {gate} açık: {GATE_NAME.get(gate, '')}" + (f", tur {record['round']}" if record.get("round") else "")
        mine.append(answer_block(title, actions, note + (f"<ul class=plain-list>{questions}</ul>" if questions else "")))
    rows, seen = [], set()
    for entry in [] if closed else model.pending:
        if (entry["id"] or entry["anchor"]) not in seen:
            seen.add(entry["id"] or entry["anchor"])
            label = page.ref(entry["id"]) if entry["id"] else f'<a href="#{esc(entry["anchor"])}">{esc(entry["label"])}</a>'
            title = model.items.get(entry["id"], {}).get("title") or entry.get("title", "")
            rows.append(f'<li>{label}<span class="decide-text">{page.text(title)}</span>'
                        f'<span class="where">{esc(entry["where"])}</span></li>')
    if rows:
        mine.append(f'<div class="decide-gate"><p class="gate-title">Karar hücresi boş satırlar ({len(rows)})</p>'
                    '<p class="hint">Belgede bu satırların karar sütununu doldur, sonra Claude oturumuna tamam yaz.</p>'
                    f'<ul class="decide-list">{"".join(rows)}</ul></div>')
    asks = bool(mine)
    if stopped and can_finish(state):
        mine.append(answer_block("Çalışmayı tamamla", ("/design-project", "tamamla"), lead="Claude oturumunda sırayla yaz:"))
    elif stopped:
        mine.append('<p class="decide-empty">Bu çalışmada karar vermen gereken bir şey kalmadı. Devam etmek '
                    'istersen yukarıdaki komutla yeni bir çalışma başlat.</p>')
    elif not mine:
        mine.append('<p class="decide-empty">Şu an senden beklenen bir karar yok. Plan bir sonraki kapıya kadar kendi '
                    'ilerler.</p>')
    tasks = {n: t for n, t in dig(state, "tasks", default={}).items() if isinstance(t, dict) and not t.get("is_group")}
    unverified = sum(map(is_unverified, findings))
    team = []
    if closed:
        team.append("Ekip çalışmıyor; çalışma durdu." if stopped else "Ekip çalışmıyor; bu çalışma kapandı.")
        # Verification calls of older runs are not planning work any more; the dev team verifies.
        left = sorted({TASK_NAME.get(n.split(".")[0], n.split(".")[0]) for n, t in tasks.items()
                       if t.get("status") in ("cancelled", "blocked", "pending", "stale") and "verdict" not in n})
        if left and stopped:
            team.append("Yarım kalan işler: " + ", ".join(left) + ".")
    else:
        if dig(state, "run", "closing") == "active":
            team.append("Kapanış çağrısı eksik teslim dilimlerini yazıyor; kritik olmayan açık maddeler not olur.")
        running = [TASK_NAME.get(n, n) for n, t in tasks.items() if t.get("status") == "running"]
        if running:
            team.append("Şu an çalışan: " + ", ".join(running) + ".")
        if blockers:
            team.append(f"Devri engelleyen {len(blockers)} maddeyi sahipleri düzeltir; "
                        "düzeltme turu senin değiştir cevabınla başlar.")
    if unverified:
        team.append(f"{unverified} bulgu için çözüm önerildi; geliştirme ekibi ilgili dilimde dener ve testle doğrular.")
    team = "".join(f"<li>{esc(t)}</li>" for t in team) or "<li>Ekibin bekleyen işi yok.</li>"
    limit = num(dig(state, "limits", "calls", "cap")) or DEFAULT_CALL_LIMIT
    opened = sum(map(is_open, findings))
    out = [render_hero(model, page, now, asks),
           '<dl class="stats">'
           + stat("Durum", STATUS_LABEL.get(status, status) or "bilinmiyor", TONE.get(status, ""), "çalışmanın genel hâli")
           + stat("Akıştaki yer", now or "başlamadı", "", "0 ile 8 arası akışta şu anki durak")
           + (stat("Devri engelleyen madde", len(blockers), "bad" if blockers else "", "sıfır olmadan final onayı verilmez")
              if counted else stat("Devri engelleyen madde", "henüz yok", "", "Kapı G3 açılınca hesaplanır"))
           + stat("Açık bulgu", f"{opened} / {len(findings)}", "warn" if opened else "",
                  f"{unverified} çözüm önerildi")
           + stat("Rol çağrısı", f"{num(dig(state, 'budget', 'calls', 'total')):g} / {limit:g}", "",
                  "ekibin harcadığı çağrı ve sınırı") + "</dl>",
           '<section class="duties" id="karar" aria-label="İş bölümü"><div class="duty"><h3>Senin işin</h3>'
           '<p class="hint">Senin Claude oturumunda yazman gerekenler.</p>' + "".join(mine) + '</div>'
           '<div class="duty"><h3>Ekibin işi</h3><p class="hint">Planlama rollerinin kendi yaptığı işler.</p>'
           f'<ul class="team">{team}</ul></div></section>']
    if blockers:
        out.append('<section class="block" id="engel"><h3 class="sub">Devri engelleyen maddeler</h3><p class="hint">'
                   'Bunlar açıkken final onayı (Kapı G3) verilemez; risk kabulüyle de geçilmez.</p>'
                   + table(("Madde", "Ne", "Neden engeller", "Nasıl kapanır", "Kim"), blockers, "blockers") + "</section>")
    listed = set(ANY_ID.findall(" ".join(reasons)))
    risks = [[page.ref(f["id"]) + f'<span class="dim"> {esc(named(f["id"]))}</span>', page.text(f["title"]),
              severity_chip(f["severity"]) + hclass_chip(f["hclass"]),
              "Tamamlanırsa geliştirme ekibine not olur." if stopped and can_finish(state) else
              "Bu çalışmada kapanmadı; yeni çalışmada ele alınmalı." if stopped else
              "Sahibi çözüm önerir; Kapı G3'te risk kabul edebilir veya kapsamdan çıkarabilirsin.", esc(f["owner"] or "ekip")]
             for f in findings if is_open(f) and f["id"] not in listed and (f["hclass"] or f["severity"] in ("MAJOR", "CRITICAL"))]
    if risks:
        out.append('<section class="block" id="riskler"><h3 class="sub">Açık riskler</h3><p class="hint">Devri '
                   'engellemeyen ama hâlâ açık olan önemli bulgular.</p>'
                   + table(("Madde", "Ne", "Önem", "Nasıl kapanır", "Kim"), risks, "risks") + "</section>")
    return "".join(out) + quality_drift(model, page)


# Summary

def id_items(items: list[dict], page: Page, cls: str = "", seen: set | None = None) -> str:
    """
    List rows for IDs (stories, rules, any new prefix) with their sub bullets and status. With `seen`, an ID that
    already has its anchor elsewhere is listed without one, so every anchor stays unique.
    """
    out = []
    for i in items:
        anchor = seen is None or i["id"] not in seen
        if seen is not None:
            seen.add(i["id"])
        ident = attrs(i["id"], i["id"], i.get("title", "")) if anchor else ""
        out.append(f'<li class="{cls}" {ident}><span class="fid">{esc(i["id"])}</span> '
                   f'<span class="li-body">{title_of(i, page)}{ul(i["sub"], page)}</span>'
                   f'{status_chip(i.get("status", ""))}</li>')
    return "".join(out)


def render_slices(model: Model, page: Page) -> str:
    slices = model.of_kind("S")
    if not slices:
        return ""
    rows = []
    for s in slices:
        by_prefix = {}
        for r in s["refs"]:
            by_prefix.setdefault(registry.prefix_of(r), []).append(r)
        counts = "".join(f'<span class="tally"><b>{len(v)}</b> {esc(KIND_NAME.get(k, k))}</span>' for k, v in by_prefix.items())
        links = "".join(f'<div><dt>{esc(KIND_NAME.get(k, k))} ({esc(k)})</dt><dd>{page.refs(sorted(v, key=id_key))}</dd></div>'
                        for k, v in by_prefix.items())
        rest = details_list([d for d in s["details"] if norm(d[0]) not in (
            "stories", "features", "entities", "endpoints_and_events", "security", "performance")], page)
        rows.append(f'<li class="slice" {attrs(s["id"], s["id"], s.get("title", ""))}><span class="sdot" aria-hidden="true">'
                    f'</span><div class="sbody"><p class="shead"><span class="fid">{esc(s["id"])}</span>'
                    f'<span class="stitle">{title_of(s, page)}</span></p><p class="tallies">{counts}</p>'
                    f'<details class="sdetail"><summary>Kapsam ve doğrulama</summary><dl class="facts">{links}</dl>'
                    f'{rest}<p class="where">{page.src(s.get("doc"), s.get("where", ""))}</p></details></div></li>')
    return (f'<section class="block"><h3 class="sub">Teslim dilimleri <span class="count">{len(slices)}</span></h3>'
            '<p class="hint">Kaynaktaki sırayla. Kaynakta dilimler arası bağımlılık alanı yok.</p>'
            f'<ol class="timeline">{"".join(rows)}</ol></section>')


def render_summary(model: Model, page: Page, handoff: tuple, seen: set) -> str:
    state, parts = model.state, []
    if state:
        track = track_of(state)
        parts.append(render_track(track, dig(state, "run", "status") == "stopped",
                                  dig(state, "run", "closing") == "active"))
        parts.append(render_dashboard(model, page, handoff, track))
    else:
        parts.append('<section class="duties" id="karar" aria-label="İş bölümü"><div class="duty"><h3>Senin işin</h3>'
                     '<p class="decide-empty">Şu an senden beklenen bir karar yok. Plan bir sonraki kapıya kadar kendi '
                     'ilerler.</p></div></section>')
    structure = []
    decisions = dig(state, "decisions", default={})
    if decisions:
        rows = [[f'<span class="fid" {attrs(d, d, str(r.get("note") or r.get("action") or ""))}>{esc(d)}</span>',
                 esc(r.get("gate") or r.get("target") or ""), esc(ACTION_LABEL.get(r.get("action"), r.get("action") or "")),
                 page.text(r.get("note") or r.get("item") or ""), esc(str(r.get("at") or "")[:10])]
                for d, r in sorted(decisions.items(), key=lambda p: id_key(p[0])) if isinstance(r, dict)]
        seen.update(decisions)
        structure.append(accordion("Kararlar (DEC)", len(rows), table(("Kimlik", "Kapı veya hedef", "Eylem", "Not", "Tarih"),
                                                                      rows, "dec")))
    for t in model.decision_tables:
        heads = [clean(h) for h in t["headers"]]
        rows = [[chip("karar bekliyor", "warn") if t["keys"][n] == "karar" and not clean(c) else page.text(clean(c))
                 for n, c in enumerate(cells[: len(heads)])] for _, cells in t["rows"]]
        marks = [f'id="karar-{esc(Path(t["doc"].rel).stem)}-{line}"' for line, _ in t["rows"]]
        where = page.src(t["doc"], t["doc"].rel + ":" + str(t["start"]))
        structure.append(accordion(t["heading"], len(rows), f'<p class="where">{where}</p>' + table(heads, rows, "stack", marks)))
    order = [p for p in ("INV", "BR", "API") if model.of_kind(p)]
    order += sorted({registry.prefix_of(i) for i in model.items} - set(OWN_VIEW) - set(order))
    for p in order:
        items = model.of_kind(p)
        structure.append(accordion(PREFIX_LABEL.get(p, f"{p} kimlikleri"), len(items),
                                   f'<ul class="idlist">{id_items(items, page, seen=seen)}</ul>'))
    if model.docs:
        rows = [[f'<span class="doc-title" {attrs("doc-" + re.sub(r"[^A-Za-z0-9]+", "-", d.rel), d.meta.get("id") or "", d.title, "Belgeler")}>'
                 f'{esc(d.title)}</span>', status_chip(d.meta.get("status", "")), page.src(d)] for d in model.docs]
        structure.append(accordion("Belgeler", len(rows), table(("Belge", "Durum", "Kaynak"), rows, "docs")))
    if structure:
        parts.append('<section class="block"><h3 class="sub">Planın yapısı</h3><p class="hint">Verilen kararlar, kurallar '
                     've belgeler. Bir başlığa tıkla, liste açılır.</p>' + "".join(structure) + "</section>")
    parts.append(render_slices(model, page))
    return "".join(parts) or empty("Özet için belge bulunamadı.")


# Features

def feature_detail(item: dict, model: Model, page: Page, seen: set) -> str:
    meta = facts([("Köken", page.text(item.get("origin", ""))), ("Sahip", esc(item.get("owner", ""))),
                  ("Kaynak", page.src(item.get("doc"), item.get("where", "")))])
    stories = model.stories_of(item)
    story_list = (f'<h4 class="mini-head">Hikayeler ve ölçütler <span class="count">{len(stories)} hikaye, '
                  f'{sum(len(s["sub"]) for s in stories)} ölçüt</span></h4>'
                  f'<ul class="stories">{id_items(stories, page, "story", seen)}</ul>') if stories else ""
    diagrams = sorted({r for r in item["refs"] if r.startswith("D-")} |
                      {d["id"] for d in model.diagrams if item["id"] in d["features"]}, key=id_key)
    links = facts([("Diyagramlar", page.refs(diagrams)),
                   ("Bağlantılar", page.refs(sorted({r for r in item["refs"] if not r.startswith(("D-", "US-"))
                                                     and r != item["id"]}, key=id_key)))])
    return meta + details_list(item["details"], page) + story_list + links


def feature_rows(items: list[dict], model: Model, page: Page, seen: set, born: dict) -> list:
    rows = []
    for item in items:
        status, karar = item.get("status", ""), item.get("karar", "")
        decision = status_chip(status or karar)
        if item.get("has_karar") and not karar and not status:
            decision = chip("karar bekliyor", "warn")
        stories = model.stories_of(item)
        slices = " ".join(re.findall(r"S\d+", item.get("slice") or ""))
        seen.add(item["id"])
        kind = registry.prefix_of(item["id"])
        data = (f'{attrs(item["id"], item["id"], item.get("title", ""))} data-priority="{esc(item.get("priority"))}" '
                f'data-slice="{esc(slices)}" data-decision="{esc(norm(status or karar))}" '
                f'data-q="{esc((item["id"] + " " + (item.get("title") or "")).lower())}"')
        first = f'<span class="fid">{esc(item["id"])}</span>'
        cells = [first, title_of(item, page), chip(item.get("priority"), "pri"), esc(item.get("slice")), decision]
        if kind == "F":
            cells += [str(len(stories)), str(sum(len(s["sub"]) for s in stories))]
        else:
            cells += [page.ref(born[item["id"]]) if item["id"] in born else '<span class="dim">yok</span>']
        rows.append((data, cells, feature_detail(item, model, page, seen)))
    return rows


def options(values, labels=None) -> list[tuple[str, str]]:
    return [(v, (labels or {}).get(v, v)) for v in sorted(set(values) - {""}, key=lambda v: id_key(v) if ANY_ID.fullmatch(v) else ("", 0, v))]


def render_features(model: Model, page: Page, seen: set) -> str:
    features, proposals = model.of_kind("F"), model.of_kind("M", "G", "R")
    head = panel_head("Özellikler", "Katalogdaki özellikler ve öneriler. Satıra tıkla: hikayeler, kabul ölçütleri ve "
                      "kaynak açılır.", f"{len(features)} özellik, {len(proposals)} öneri")
    if not features and not proposals:
        return head + empty("Özellik satırı bulunamadı. Katalog veya plan belgesi F satırlarını taşıdığında burada görünür.")
    for item in features + proposals:
        stories = {s["id"] for s in model.stories_of(item)}
        item["slice"] = item.get("slice") or ", ".join(s["id"] for s in model.of_kind("S") if stories & set(s["refs"]))
    born = {f["origin"]: f["id"] for f in features if f.get("origin")}
    out = [head]
    if features:
        decisions = {norm(f.get("status") or f.get("karar") or ""): STATUS_LABEL.get(norm(f.get("status") or f.get("karar") or ""), "")
                     for f in features}
        out.append(filters(".ft-features .xrow", [
            ("priority", "Öncelik", options([f.get("priority") or "" for f in features])),
            ("slice", "Dilim", options([s for f in features for s in re.findall(r"S\d+", f.get("slice") or "")])),
            ("decision", "Karar", options(decisions, decisions))], "Kimlik veya ad", "Özellik filtreleri"))
        out.append(xtable(("Kimlik", "Özellik", "Öncelik", "Dilim", "Karar", "Hikaye", "Ölçüt"),
                          feature_rows(features, model, page, seen, born), "ft-features"))
    if proposals:
        out.append('<section class="block proposals"><h3 class="sub">Katalog önerileri <span class="count">'
                   f'{len(proposals)}</span></h3><p class="hint">Eksik özellik (M), ara özellik (G) ve sektör önerisi (R) satırları. '
                   'Kabul edilen öneri bir özellik (F) kimliği alır; "Özellik" sütunu onu gösterir.</p>'
                   + xtable(("Kimlik", "Öneri", "Öncelik", "Dilim", "Karar", "Özellik"),
                            feature_rows(proposals, model, page, seen, born), "ft-proposals") + "</section>")
    loose = [s for s in model.of_kind("US") if s["id"] not in seen]
    if loose:
        out.append(f'<section class="block"><h3 class="sub">Özelliğe bağlanmamış hikayeler</h3><ul class="stories">'
                   f'{id_items(loose, page, "story", seen)}</ul></section>')
    return "".join(out)


# Diagrams

def diagram_figure(diagram: dict, page: Page) -> str:
    features = page.refs(diagram["features"])
    info = (f'<figcaption class="dinfo"><p class="dhead">' + (f'<span class="fid">{esc(diagram["id"])}</span>'
            + copy_button(diagram["id"]) if diagram["id"] else "") + f'{chip(diagram["kind"], "mute")}</p>'
            f'<h3>{page.text(diagram["title"])}</h3>'
            + facts([("Kaynak", page.src(diagram["doc"], diagram["where"])),
                     ("Belge", esc(diagram["doc"].title)),
                     ("Özellikler", features)])
            + "".join(f'<p class="caption">{page.text((k + ": " if k else "") + "; ".join(v))}</p>'
                      for k, v in diagram["details"]) + "</figcaption>")
    stage = diagram_stage(diagram["code"]) if diagram["code"] else (
        '<div class="dstage"><p class="caption empty">Bu D bloğunda Mermaid yok.</p></div>')
    return (f'<figure class="diagram" {attrs(diagram["anchor"], diagram["id"] or diagram["anchor"], diagram["title"])} '
            f'data-f="{esc(" ".join(diagram["features"]))}">{stage}{info}</figure>')


def diagram_stage(code: str) -> str:
    """A pan and zoom canvas for one Mermaid source, with the source as the offline fallback."""
    return ('<div class="dstage"><div class="dtools" role="toolbar" aria-label="Diyagram araçları">'
                 '<button type="button" data-act="out" aria-label="Uzaklaştır" title="Uzaklaştır">−</button>'
                 '<span class="zoom" aria-live="polite">100%</span>'
                 '<button type="button" data-act="in" aria-label="Yakınlaştır" title="Yakınlaştır">+</button>'
                 '<button type="button" data-act="fit">Sığdır</button><button type="button" data-act="reset">Sıfırla</button>'
                 '<button type="button" data-act="full" aria-pressed="false">Tam ekran</button></div>'
                 '<div class="canvas" tabindex="0" aria-label="Diyagram tuvali: sürükleyerek gez, Ctrl veya Cmd ile '
                 'tekerlek yakınlaştırır, ok tuşları kaydırır, artı ve eksi yakınlaştırır">'
                 '<div class="viewport diagram-render" hidden></div><p class="dstatus" role="status">Diyagram hazırlanıyor.</p>'
                 '</div><p class="diagram-offline">Diyagram çizilemedi. Mermaid kaynağı aşağıda.</p>'
                 '<details class="diagram-src" open><summary>Mermaid kaynağı</summary>'
                 f'<pre class="mermaid">{esc(code)}</pre></details></div>')


def render_diagrams(model: Model, page: Page) -> str:
    head = panel_head("Diyagramlar", "Belgelerdeki şemalar. Soldan seç; tuvalde sürükleyerek gez, araç çubuğuyla "
                      "yakınlaştır.", f"{len(model.diagrams)} diyagram")
    if not model.diagrams:
        return head + empty("Mermaid diyagramı bulunamadı.")
    features = sorted({f for d in model.diagrams for f in d["features"]}, key=id_key)
    select = filters(".dindex li", [("f", "Özellik", [(f, f + " " + (model.items.get(f, {}).get("title") or ""))
                                                       for f in features])], label="Diyagram filtresi")
    index = "".join(f'<li data-f="{esc(" ".join(d["features"]))}"><a href="#{esc(d["anchor"])}" data-diagram="{esc(d["anchor"])}">'
                    f'<span class="fid">{esc(d["id"] or "D")}</span><span class="dtitle">{page.text(d["title"])}</span>'
                    f'<span class="dkind">{esc(d["kind"] or "metin")} · {esc(d["doc"].meta.get("id") or d["doc"].path.stem)}</span></a></li>'
                    for d in model.diagrams)
    return (head + '<div class="dws"><nav class="dindex" aria-label="Diyagram listesi">' + select
            + f'<ol>{index}</ol></nav><div class="dfigures">{"".join(diagram_figure(d, page) for d in model.diagrams)}'
            "</div></div>")


# Data model

def class_diagram(groups: list[dict]) -> str:
    """
    All entities as one Mermaid classDiagram from the same ERD data: a class per entity with its typed attributes
    and key marks, and a line per relation with both multiplicities and the relation name.
    """
    def safe(text: str) -> str:
        return re.sub(r"[^\w.,\[\] -]", "", str(text).replace("(", "[").replace(")", "]")).strip()

    lines, relations = ["classDiagram", "  direction TB"], []
    for row in (r for g in groups for r in g["rows"]):
        members = [f"    {safe(kind)} {safe(attr)}" + (" " + safe(keys).replace(",", " ") if keys else "")
                   for kind, attr, keys, _ in row["attrs"]]
        lines += [f"  class {safe(row['name'])} {{"] + members + ["  }"] if members else [f"  class {safe(row['name'])}"]
        relations += [r for r in row["relations"] if r not in relations]
    for a, sym, b, label in relations:
        lines.append(f'  {safe(a)} "{UML_MULT.get(sym[:2], "*")}" -- "{UML_MULT.get(sym[-2:], "*")}" {safe(b)}'
                     + (f" : {safe(label)}" if safe(label) else ""))
    return "\n".join(lines)


def entity_detail(row: dict, page: Page) -> str:
    anchor = row["id"] or f'entity-{row["name"]}'
    item = row["item"] or {}
    fields = [[f'<code>{esc(attr)}</code>', f'<span class="type">{esc(kind)}</span>',
               "".join(chip(k.strip(), "key") for k in keys.split(",") if k.strip()) or '<span class="dim">yok</span>',
               page.text(note)] for kind, attr, keys, note in row["attrs"]]
    rels = "".join(f'<li><code>{esc(a)}</code> <span class="card-sym">{esc(sym)}</span> <code>{esc(b)}</code>'
                   f'{" " + esc(label) if label else ""}</li>' for a, sym, b, label in row["relations"])
    diagram = row["diagram"]
    head = (f'<header class="ehead"><p class="dhead">' + (f'<span class="fid">{esc(row["id"])}</span>{copy_button(row["id"])}'
            if row["id"] else chip("E kimliği yok", "mute")) + f'</p><h3><code>{esc(row["name"])}</code></h3>'
            + facts([("Kaynak", page.src(item.get("doc"), item.get("where", "")) if item else ""),
                     ("ERD", (page.ref(diagram["id"]) if diagram and diagram["id"] else "") +
                      (" " + page.src(diagram["doc"], diagram["where"]) if diagram else ""))]) + "</header>")
    return (f'<article class="entity" {attrs(anchor, row["id"] or row["name"], row["name"])}>{head}<div class="etable">'
            + (f'<h4 class="mini-head">Alanlar <span class="count">{len(fields)}</span></h4>'
               + table(("Alan", "Tip", "Anahtar", "Not"), fields, "fields") if fields else
               '<p class="empty">Bu tablonun alanları ERD\'de yazılı değil.</p>')
            + (f'<h4 class="mini-head">İlişkiler</h4><ul class="relations">{rels}</ul>' if rels else "") + "</div>"
            + (f'<h4 class="mini-head">Tanım</h4>{details_list(item["details"], page)}' if item.get("details") else "")
            + "</article>")


def render_data_model(model: Model, page: Page) -> str:
    groups = model.entity_groups()
    total = sum(len(g["rows"]) for g in groups)
    toggle = ('<div class="seg" role="group" aria-label="Görünüm: tablo veya UML"><button type="button" data-view="table" '
              'aria-pressed="true" title="Tablolar tek tek, alan listesiyle">Tablo</button><button type="button" '
              'data-view="uml" aria-pressed="false" title="Tüm tablolar tek UML sınıf diyagramında">UML</button></div>'
              if groups else "")
    head = panel_head("Veri modeli", "Tablolar, alanları ve ilişkileri. Soldan seç; sağ üstten tablo veya UML görünümüne "
                      "geç.", f"{total} tablo, {len(groups)} belge" if groups else "", toggle)
    if not groups:
        return head + empty("ERD veya E bloğu bulunamadı. DOM belgeleri erDiagram ve E kimlikleri taşıdığında veri modeli "
                            "burada görünür.")
    links = {r["name"]: r["id"] or "entity-" + r["name"] for g in groups for r in g["rows"]}
    index = "".join(f'<li class="egroup"><p class="egroup-title">{esc(g["doc"].title if g["doc"] else "Belgesiz")}</p><ul>'
                    + "".join(f'<li><a href="#{esc(links[r["name"]])}" data-entity="{esc(links[r["name"]])}">'
                              f'<span class="fid">{esc(r["id"] or "·")}</span><code>{esc(r["name"])}</code></a></li>'
                              for r in g["rows"]) + "</ul></li>" for g in groups)
    details = "".join(entity_detail(r, page) for g in groups for r in g["rows"])
    uml = ('<figure class="diagram uml-figure" aria-label="UML sınıf diyagramı"><p class="hint">Her kutu bir tablo: '
           'alanlar tipleriyle, PK ve FK işaretiyle. Çizgiler ilişkiler; uçlardaki sayılar çokluk.</p>'
           f'{diagram_stage(class_diagram(groups))}</figure>')
    return (head + f'<div class="ews"><nav class="eindex" aria-label="Veri tabloları"><ul>{index}</ul></nav>'
            f'<div class="edetails">{details}</div></div>{uml}')


# Findings

# One line per finding status: what it means and who acts next. Kept in one dict so engine renames stay small.
STATUS_NOTE = {
    "fixed": "Planlama çözümü belgeye yazdı; geliştirme ekibi ilgili dilimde bunu dener ve testle doğrular.",
    "open": "{owner} bir çözüm önerip belgeye yazar. Kritik bir bulgu çözümsüz kalırsa Kapı G3'ü engeller.",
    "disputed": "{owner} bulguya itiraz etti; itiraz final paketinde kalır ve geliştirme ekibi ilgili dilimde değerlendirir.",
    "accepted_risk": "Risk kabul edildi: madde final paketinde geliştirme ekibine not olarak kalır, ilgili dilimde testle "
                     "kapsanır.",
    "closed": "Kapandı; yapılacak iş yok.",
    "descoped": "Kapsamdan çıkarıldı; bu planda ele alınmaz.",
}


def status_note(f: dict) -> str:
    note = STATUS_NOTE.get(f["state"], "").format(owner=f["owner"] or "Sahibi")
    must = f["state"] == "fixed" and f["severity"] == "CRITICAL"
    return (chip("doğrulanması zorunlu", "bad", "Kritik bulgu: geliştirme ekibi çözümü testle doğrulamadan dilim bitmez")
            if must else "") + esc(note)


def finding_detail(f: dict, page: Page) -> str:
    history = " → ".join(f"{h[1]} (rev {h[0]})" for h in f["history"])
    note = status_note(f)
    return facts([("Durum", status_chip(f["state"]) + (f'<span class="status-note">{note}</span>' if note else "")),
                  ("İddia", page.text(f["title"])), ("Kanıt", page.text(f["evidence"])),
                  ("Önerilen çözüm", page.text(f["reply"]) if f["reply"] else '<span class="dim">yok</span>'),
                  ("Açan rol", esc(f["raised_by"])), ("Sahip", esc(f["owner"])), ("Görev", esc(f["task"])),
                  ("Geçmiş", esc(history))], "facts wide")


FINDING_GROUPS = (("open", "Açık"), ("fixed", "Çözüm önerildi"), ("other", "Kapandı veya kabul edildi"))


def render_findings(model: Model, page: Page, seen: set) -> str:
    order = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    findings = sorted(model.findings.values(), key=lambda f: (not is_open(f), not is_unverified(f),
                                                              order.get(f["severity"], 3), id_key(f["id"])))
    controls = [i for i in model.of_kind(*FINDING_KINDS) if i["id"] not in model.findings]
    opened, unverified = sum(map(is_open, findings)), sum(map(is_unverified, findings))
    closed = sum(1 for f in findings if f["state"] == "closed")
    head = panel_head("Güvenlik ve performans", "Rollerin açtığı bulgular; açık olanlar önce gelir. Satıra tıkla: "
                      "kanıt, cevap ve geçmiş açılır.", f"{len(findings)} bulgu, {opened} açık" if findings else "")
    if not findings and not controls:
        return head + empty("Güvenlik veya performans bulgusu yok.")
    out = [head]
    if findings:
        out.append('<dl class="stats">' + stat("Toplam bulgu", len(findings))
                   + stat("Açık", opened, "warn" if opened else "")
                   + stat("Çözüm önerildi", unverified, "unverified" if unverified else "")
                   + stat("Kapandı", closed, "ok" if closed else "") + "</dl>")
        states = {f["state"]: STATUS_LABEL.get(f["state"], f["state"]) for f in findings}
        out.append(filters(".ft-findings .xrow", [
            ("state", "Durum", options(states, states)),
            ("severity", "Önem", options([f["severity"] for f in findings])),
            ("hclass", "Sınıf", options([h for f in findings for h in f["hclass"].split()])),
            ("owner", "Sahip", options([f["owner"] for f in findings])),
            ("kind", "Kaynak", options([registry.prefix_of(f["id"]) for f in findings]))],
            "Kimlik veya metin", "Bulgu filtreleri"))
        groups = {"open": [], "fixed": [], "other": []}
        for f in findings:
            seen.add(f["id"])
            data = (f'{attrs(f["id"], f["id"], f["title"])} data-state="{esc(f["state"])}" data-severity="{esc(f["severity"])}" '
                    f'data-hclass="{esc(f["hclass"])}" data-owner="{esc(f["owner"])}" '
                    f'data-kind="{esc(registry.prefix_of(f["id"]))}" data-q="{esc((f["id"] + " " + f["title"]).lower())}"'
                    + ("" if is_open(f) else ' data-closed="1"'))
            group = "open" if is_open(f) else "fixed" if is_unverified(f) else "other"
            groups[group].append((data, [f'<span class="fid">{esc(f["id"])}</span>', page.text(f["title"]),
                                         severity_chip(f["severity"]), hclass_chip(f["hclass"]) or '<span class="dim">yok</span>',
                                         esc(f["owner"]), status_chip(f["state"])], finding_detail(f, page)))
        heads = ("Kimlik", "Bulgu", "Önem", "Sınıf", "Sahip", "Durum")

        def group_table(key):
            # Side by side tables are narrow: the owner moves to the detail (and the filter), and the status column
            # stays only in the mixed table, because every row of the open and the proposed table has the same one.
            keep = [0, 1, 2, 3] + ([5] if key == "other" else [])
            rows = [(data, [cells[i] for i in keep], detail) for data, cells, detail in groups[key]]
            return xtable([heads[i] for i in keep], rows, "ft-findings", f"ft-{key}")
        tables = "".join(f'<div class="ftable"><h3 class="sub">{title} <span class="count">{len(groups[key])}</span></h3>'
                         + group_table(key) + "</div>" for key, title in FINDING_GROUPS if groups[key])
        out.append(f'<div class="ftables">{tables}</div>')
    if controls:
        out.append(accordion("Belgelerde tanımlı güvenlik, performans ve kalite maddeleri", len(controls),
                             f'<ul class="idlist">{id_items(controls, page, seen=seen)}</ul>'))
    return "".join(out)


# Quality and process

def render_quality(model: Model, page: Page) -> str:
    head = panel_head("Kalite", "Her özelliğin hikayeye, ölçüte ve dilime bağlanma oranı ile bulgu kapanışı.")
    value, errors = traceability(model) if model.state else (None, [])
    parts = [quality_drift(model, page)]
    if value is not None:
        parts.append(meter("Tasarım izlenebilirliği", round(value), 100, f"%{value:.0f}", "ok" if value >= 100 else "warn",
                           "" if value >= 100 else "G3 için %100 gerekir"))
    closed = sum(1 for f in model.findings.values() if f["state"] == "closed")
    if model.findings:
        parts.append(meter("Bulgu kapanışı", closed, len(model.findings), f"{closed} / {len(model.findings)}",
                           "info", "Çözüm önerilen bulgular geliştirme ekibi testle doğrulayana kadar kapanmış sayılmaz."))
    if errors:
        parts.append(f'<h3 class="sub">İzlenebilirlik eksikleri</h3>{ul(errors, page, "plain")}')
    body = "".join(parts)
    return head + (f'<div class="meters">{body}</div>' if body else empty(
        "İzlenebilirlik oranı henüz yok. run.json ve özellik satırları olduğunda burada görünür."))


def render_process(model: Model) -> str:
    head = panel_head("Süreç", "Rol çağrıları, sana sorulan oturumlar ve görevler. Bütçe planın kalitesini göstermez.")
    state = model.state
    if not state:
        return head + empty(model.state_note or "Durum dosyası (run.json) bulunamadı. Süreç sayaçları çalıştırma "
                            "başladığında görünür.")
    budget, tokens = dig(state, "budget", default={}), dig(state, "budget", "tokens", default={})
    limit = num(dig(state, "limits", "calls", "cap")) or DEFAULT_CALL_LIMIT
    warn = num(dig(state, "limits", "calls", "warn")) or DEFAULT_CALL_WARN
    used = num(dig(budget, "calls", "total"))
    tone = "bad" if used >= limit else "warn" if used >= warn else "ok"
    hint = {"bad": "Bütçe doldu; son çağrılar kapanışa ayrıldı.", "warn": f"Uyarı eşiği {warn:g} çağrı geçildi."}.get(
        tone, f"Uyarı eşiği {warn:g} çağrı.")
    contacts, cap = num(dig(state, "contacts", "count")), DEFAULT_CONTACT_LIMIT
    meters = (meter("Rol çağrısı bütçesi", used, limit, f"{used:g} / {limit:g}", tone, hint)
              + meter("Kullanıcı temasları", contacts, cap, f"{contacts:g} / {cap}",
                      "bad" if contacts > cap else "warn" if contacts >= cap else "ok"))
    by_model = {m: num(n) for m, n in dig(budget, "calls", "by_model", default={}).items()}
    models = sorted(set(by_model) | set(tokens))
    top = max([by_model.get(m, 0) for m in models] + [1])
    rows = [[f"<strong>{esc(m)}</strong>", f'<span class="mini"><span style="width:{by_model.get(m, 0) / top * 100:.0f}%">'
             f"</span></span>{by_model.get(m, 0):g}", amount(tokens.get(m))] for m in models]
    costs = "".join(f"<div><dt>{label}</dt><dd>{amount(budget.get(key))}</dd></div>"
                    for key, label in (("cost_estimated", "Tahmini maliyet"), ("cost_actual", "Gerçek maliyet")))
    tasks = sorted(((n, t) for n, t in dig(state, "tasks", default={}).items() if isinstance(t, dict)),
                   key=lambda p: (num(p[1].get("step"), 99), p[0]))
    task_rows = []
    for name, t in tasks:
        attempts = t.get("attempts")
        last = (t.get("history") or [[]])[-1]
        task_rows.append([f"<code>{esc(name)}</code>", esc(t.get("step", "")), esc(t.get("role") or ""),
                          esc(t.get("model") or ""), esc(len(attempts) if isinstance(attempts, (list, dict)) else attempts or 0),
                          status_chip(t.get("status", "")), esc(last[-1] if len(last) > 4 else "")])
    return (head + f'<div class="meters">{meters}</div>'
            + (f'<h3 class="sub">Model başına</h3>{table(("Model", "Çağrı", "Token"), rows, "models")}' if models else "")
            + f'<dl class="facts">{costs}</dl>'
            + (accordion("Görevler ve geçmiş", len(task_rows), table(("Görev", "Adım", "Rol", "Model", "Deneme", "Durum",
                                                                      "Son not"), task_rows, "tasks"))
               if task_rows else ""))


# Page

def asset(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


HEAD_JS = ("(function(){var r=document.documentElement;r.classList.add('js');try{var t=localStorage.getItem("
           "'plan-preview-theme');if(t==='light'||t==='dark')r.setAttribute('data-theme',t);}catch(e){}})();")


def render(model: Model, plan_id: str = "", out_dir: Path | None = None) -> str:
    anchors = (set(model.items) | set(model.findings) | {d["anchor"] for d in model.diagrams}
               | set(dig(model.state, "decisions", default={})))
    page = Page(anchors, out_dir)
    handoff = eligibility(model.state) if model.state else (None, [])
    pid = plan_id or str(dig(model.state, "plan_id", default=""))
    brief = dig(model.state, "run", "brief", default="")
    doc = next((d for d in model.docs if d.rel == brief), None) or next(
        (d for d in model.docs if pid and Path(d.rel).name.startswith(pid)), None)
    name = re.sub(r"^Brief:\s*", "", doc.title) if doc else pid or (model.docs[0].title if model.docs else "Plan")
    run_status = str(dig(model.state, "run", "status", default=""))
    seen = set()
    panels = {"ozet": render_summary(model, page, handoff, seen), "ozellikler": render_features(model, page, seen),
              "diyagramlar": render_diagrams(model, page), "veri": render_data_model(model, page),
              "guvenlik": render_findings(model, page, seen), "kalite": render_quality(model, page),
              "surec": render_process(model)}
    nav = "".join(f'<li><a role="tab" class="tab" id="tab-{k}" href="#panel-{k}" aria-controls="panel-{k}" data-tab="{k}" '
                  f'title="{label}">{icon(path)}<span class="tab-label">{label}</span></a></li>' for k, label, path in NAV)
    panels["ozet"] = panel_head("Özet", "Planın durumu, senden beklenen iş ve devri engelleyen maddeler tek bakışta.") + panels["ozet"]
    sections = "".join(f'<section class="panel" role="tabpanel" id="panel-{k}" aria-labelledby="tab-{k}" data-tab="{k}">'
                       f"{panels[k]}</section>" for k, _, _ in NAV)
    live = bool(model.state) and run_status not in FINISHED_RUNS
    live_chip = ('<span class="live" title="Çalışma sürüyor; sayfa görünürken 30 saniyede bir kendini yeniler">canlı</span>'
                 if live else "")
    built = datetime.datetime.now()
    live_attr = ' data-live="1"' if live else ""
    meta = (f'<span class="pid">{esc(pid)}</span>' if pid and pid != name else "") + status_chip(run_status)
    body = (
        '<a class="skip" href="#main">İçeriğe geç</a><header class="bar"><button type="button" class="btn icon-btn nav-toggle" '
        f'aria-controls="nav" aria-expanded="false" aria-label="Menüyü aç">{icon(ICONS["menu"])}</button><div class="plan">'
        f'<h1>{esc(name)}</h1><p class="plan-meta">{meta}</p></div><div class="tools"><div class="search" role="search">'
        '<label class="sr" for="q">Kimlik veya başlık ara</label><input id="q" type="search" placeholder="Ara: F-12, SEC-15, kanal" '
        'autocomplete="off" role="combobox" aria-expanded="false" aria-controls="q-results" aria-autocomplete="list">'
        '<kbd aria-hidden="true">/</kbd><ul id="q-results" role="listbox" aria-label="Arama sonuçları" hidden></ul></div>'
        f'<span class="stamp" title="{RELOAD_TIP}">{live_chip}<span class="stamp-time">güncellendi: '
        f'<time datetime="{built.isoformat(timespec="minutes")}">{built:%H:%M}</time></span></span>'
        f'<button type="button" class="btn" id="reload" title="{RELOAD_TIP}" aria-label="Sayfayı yenile">'
        f'{icon(ICONS["reload"])}<span class="btn-text">Yenile</span></button>'
        f'<button type="button" class="btn theme" id="theme" aria-label="Temayı değiştir">{icon(ICONS["theme"])}'
        '<span class="theme-text">Tema</span></button></div></header>'
        f'<div class="shell"><nav class="nav" id="nav" aria-label="Plan bölümleri"><ul role="tablist" aria-orientation="vertical">'
        f'{nav}</ul></nav><div class="scrim" data-close-nav hidden></div><main id="main" tabindex="-1">'
        '<p class="mermaid-note" role="status" hidden>Mermaid betiği yüklenemedi (çevrimdışı olabilirsin). Diyagramlar '
        f'kaynak kodu olarak gösteriliyor.</p>{sections}<footer class="foot">Doğruluğun kaynağı Markdown belgeleri ve '
        'run.json dosyasıdır. Bu sayfa yalnız okur; kararlar sohbette verilir.</footer></main></div>')
    return (f'<!doctype html>\n<html lang="tr"{live_attr}>\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{esc(name)}: plan incelemesi</title>\n<script>{HEAD_JS}</script>\n<style>{asset('page.css')}</style>\n"
            f"</head>\n<body>\n{body}\n<script>{asset('page.js')}</script>\n"
            f'<script src="{MERMAID_URL}" async onload="planDraw()" onerror="planOffline()"></script>\n</body>\n</html>\n')
