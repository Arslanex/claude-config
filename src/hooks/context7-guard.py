#!/usr/bin/env python3
"""
PreToolUse (Context7 MCP): sorgu metni context7.com'a gider; proje kodu, veri ya da sir tasiyan sorguyu durdurur.

Ne yapar: arac argumanlarindaki her metni denetler. Kisa ve tek satirlik bir kutuphane sorusu gecer; satir sonu,
kod blogu, dosya yolu, ortam degiskeni atamasi, anahtar ya da token biciminde metin ya da uzun metin reddedilir.
Nasil: reddederken nedeni ajana geri verir, ajan sorguyu kisaltip yeniden sorar. Bozuk girdide sessizce gecer.
"""
import json
import re
import sys

MAX_CHARS = 300
CHECKS = (
    (re.compile(r"\n"), "birden cok satir (kod ya da dosya icerigi)"),
    (re.compile(r"`{3}"), "kod blogu"),
    (re.compile(r"(?:^|\s)(?:~|/Users|/home|/private|/var|[A-Za-z]:\\)[/\\]?\S+"), "yerel dosya yolu"),
    (re.compile(r"\b[A-Z][A-Z0-9_]{2,}\s*=\s*\S+"), "ortam degiskeni atamasi"),
    (re.compile(r"(?i)\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S+"), "sir degeri"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{10,})"), "anahtar ya da token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "JWT"),
    (re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|redis|mongodb)(?:\+\w+)?://\S+"), "baglanti adresi"),
)


def problems(value):
    found = []
    if len(value) > MAX_CHARS:
        found.append(f"{MAX_CHARS} karakterden uzun")
    found += [reason for pattern, reason in CHECKS if pattern.search(value)]
    return found


try:
    d = json.load(sys.stdin)
    args = d.get("tool_input") or {}
except Exception:
    sys.exit(0)
if not isinstance(args, dict):
    sys.exit(0)

for key, value in args.items():
    if isinstance(value, str) and (found := problems(value)):
        print(
            f"context7-guard: `{key}` dis servise gidecekti ve {', '.join(found)} iceriyor. "
            "Sorguya yalniz kutuphane adini ve kisa API sorusunu yaz; proje kodu, veri, dosya yolu ya da sir koyma.",
            file=sys.stderr,
        )
        sys.exit(2)
sys.exit(0)
