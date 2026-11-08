#!/usr/bin/env python3
"""Stop hook: degisiklik varsa ve Makefile'da `check` hedefi varsa `make check` calistirir.
Kirik ise ajani durdurup cikti sonunu geri verir. Hata/zaman asimi/yapilandirilmamis proje
durumunda susar; oturumu asla kilitlemez."""
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
try:
    with open(os.path.join(cwd, "Makefile"), encoding="utf-8") as f:
        if not re.search(r"^check:", f.read(), re.M):
            sys.exit(0)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=10)
    if st.returncode != 0 or not st.stdout.strip():
        sys.exit(0)
    p = subprocess.run(["make", "check"], cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
except subprocess.TimeoutExpired:
    print(f"stop-gate: make check {TIMEOUT} sn'yi asti, dogrulanamadi", file=sys.stderr)
    sys.exit(0)
except Exception:
    sys.exit(0)

if p.returncode == 0:
    sys.exit(0)
out = (p.stdout or "") + (p.stderr or "")
if "not configured for this project" in out:
    sys.exit(0)

tail = "\n".join(out.strip().splitlines()[-TAIL:])
reason = "make check basarisiz. Bitirmeden once duzelt ve tekrar calistir.\n\n" + tail
print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
