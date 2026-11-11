#!/usr/bin/env python3
"""
Stop hook: degisiklik varsa ve Makefile'da `check` hedefi varsa `make check` calistirir.

Kirik ise ajani durdurup cikti sonunu geri verir. Hata, zaman asimi ya da yapilandirilmamis
proje durumunda susar; oturumu asla kilitlemez. Calisma agaci son gecen kontrolden beri
degismediyse `make check` yeniden calismaz: parmak izi git dizininde tutulur. Yalniz reponun
kok dizininde calisir; alt klasordeki bir Makefile (ornegin bir sablon) tetiklemez.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

TIMEOUT = 300
TAIL = 40

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
if not isinstance(d, dict) or d.get("stop_hook_active"):
    sys.exit(0)

cwd = d.get("cwd") or os.getcwd()


def git(*args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=10).stdout


def fingerprint(root):
    """Izlenen dosyalardaki fark ile izlenmeyen dosyalarin ad, boyut ve zamani."""
    h = hashlib.sha256(git("rev-parse", "HEAD") + git("diff", "HEAD", "--no-ext-diff", "--binary"))
    for name in sorted(git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        if not name:
            continue
        try:
            s = os.stat(os.path.join(root, os.fsdecode(name)))
        except OSError:
            continue
        h.update(b"%s\0%d\0%d\0" % (name, s.st_size, s.st_mtime_ns))
    return h.hexdigest()


def stamp_path(root):
    gitdir = git("rev-parse", "--absolute-git-dir").decode().strip()
    return os.path.join(gitdir, "claude-stop-gate") if gitdir else ""


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""
try:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True, timeout=10)
    if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(cwd):
        sys.exit(0)
    with open(os.path.join(cwd, "Makefile"), encoding="utf-8") as f:
        if not re.search(r"^check:", f.read(), re.M):
            sys.exit(0)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=10)
    if st.returncode != 0 or not st.stdout.strip():
        sys.exit(0)
    stamp, current = stamp_path(cwd), fingerprint(cwd)
    if current and read(stamp) == current:
        sys.exit(0)
    p = subprocess.run(["make", "check"], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
except subprocess.TimeoutExpired:
    print(f"stop-gate: make check {TIMEOUT} sn'yi asti, dogrulanamadi", file=sys.stderr)
    sys.exit(0)
except Exception:
    sys.exit(0)

if p.returncode == 0:
    if stamp and current:
        try:
            with open(stamp, "w", encoding="utf-8") as f:
                f.write(current)
        except OSError:
            pass
    sys.exit(0)
out = (p.stdout or "") + (p.stderr or "")
if "not configured for this project" in out:
    sys.exit(0)

tail = "\n".join(out.strip().splitlines()[-TAIL:])
reason = "make check basarisiz. Bitirmeden once duzelt ve tekrar calistir.\n\n" + tail
print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
