#!/usr/bin/env python3
"""
SessionStart hook: profil durumuna göre tek satırlık ipucu ekler.
- .claude/profile yok, pyproject.toml'da fastapi var: 'cinit --kind fastapi-saas' önerilir.
- .claude/profile var ama profilin ekip dosyaları projede yok (.claude/team.md): roller global
  değil, profille gelir; 'cinit --kind <profil> --team-only' önerilir.
- Ekip dosyaları var ama şablon kurulumdan sonra değişmiş (.claude/profile içindeki team=<hash>
  damgası güncel değil): 'cinit --kind <profil> --team-only --apply' önerilir.
Hata olursa sessizce çıkar, oturumu asla bloklamaz."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def team_hash(root):
    """templates/project/init.sh içindeki team_hash ile aynı algoritma."""
    h = hashlib.sha256()
    for rel in sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"):
        h.update(rel.encode() + b"\0" + (root / rel).read_bytes() + b"\0")
    return h.hexdigest()


hint = None
try:
    d = json.load(sys.stdin)
    cwd = (d.get("cwd") if isinstance(d, dict) else None) or os.getcwd()
    profile_file = os.path.join(cwd, ".claude", "profile")
    if os.path.exists(profile_file):
        with open(profile_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
        kind = lines[0].strip() if lines else ""
        # Dosya içeriği bağlama girer: yalnızca profil adı biçimine izin ver.
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", kind):
            sys.exit(0)
        stamp = next((m.group(1) for m in (re.fullmatch(r"team=([0-9a-f]{64})", x.strip()) for x in lines[1:]) if m), None)
        team_src = Path(os.path.expanduser("~")) / ".claude" / "templates" / "profiles" / kind / "team"
        if not team_src.is_dir():
            sys.exit(0)
        if not os.path.exists(os.path.join(cwd, ".claude", "team.md")):
            hint = (f"Bu projede '{kind}' profili kurulu ama ekip dosyaları (.claude/agents, .claude/team.md) yok; "
                    "ekip rolleri global değil, profille gelir. "
                    f"Kullanıcıya şunu öner: 'cinit --kind {kind} --team-only'. Kendiliğinden uygulama.")
        elif stamp != team_hash(team_src):
            hint = (f"'{kind}' profilinin ekip şablonu bu projeye kurulduktan sonra değişmiş; .claude/ altındaki "
                    "rol dosyaları eski olabilir. Kullanıcıya şunu öner: "
                    f"'cinit --kind {kind} --team-only --apply' (önceki kopyalar .bak olarak kalır) "
                    "ya da --apply olmadan .proposed dosyalarını incelemek. Kendiliğinden uygulama.")
    else:
        for rel in ("pyproject.toml", os.path.join("backend", "pyproject.toml")):
            try:
                with open(os.path.join(cwd, rel), encoding="utf-8") as f:
                    if "fastapi" in f.read().lower():
                        hint = ("Bu dizin bir FastAPI projesi gibi görünüyor ve .claude/profile yok. "
                                "Kullanıcıya şunu öner: yeni proje için 'cinit --kind fastapi-saas', kendi düzeni olan "
                                "mevcut repo için 'cinit --kind fastapi-saas --team-only'. Kendiliğinden uygulama.")
                        break
            except OSError:
                pass
except Exception:
    sys.exit(0)

if hint:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": hint}}, ensure_ascii=False))
