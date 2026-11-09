#!/bin/bash
# Install dockerw outside the project tree so a sandboxed agent cannot edit it.
# usage: install-dockerw.sh --root DIR [--root DIR ...] [--dest DIR] [--python PATH] [--docker PATH]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="$HOME/.local/bin"
py=""
docker=""
roots=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dest) dest="$2"; shift 2 ;;
    --python) py="$2"; shift 2 ;;
    --docker) docker="$2"; shift 2 ;;
    --root) roots+=("$2"); shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
if [ "${#roots[@]}" -eq 0 ]; then
  echo "give at least one --root DIR (the directory your projects live under)" >&2
  exit 2
fi
[ -n "$py" ] || py="$(python3 -c 'import sys; print(sys.executable)')"
[ -n "$docker" ] || docker="$(command -v docker || true)"
if [ ! -x "$py" ]; then echo "python is not executable: $py" >&2; exit 1; fi
if [ -z "$docker" ] || [ ! -x "$docker" ]; then echo "docker not found; pass --docker PATH" >&2; exit 1; fi
if [ -e "$dest/dockerw" ] && ! grep -q 'dockerw.py' "$dest/dockerw"; then
  echo "refusing to overwrite $dest/dockerw: it is not ours" >&2
  exit 1
fi
if [ -e "$dest/dockerw.py" ] && ! grep -q 'dockerw: project-scoped Docker wrapper' "$dest/dockerw.py"; then
  echo "refusing to overwrite $dest/dockerw.py: it is not ours" >&2
  exit 1
fi
# Roots must be absolute, existing and narrower than HOME; dest, docker and python must live outside every root
# (a path the agent can write is code that runs outside its sandbox).
python3 -c '
import os, sys
from pathlib import Path

dest, docker, py, *roots = sys.argv[1:]
home = Path.home().resolve()
bad = []
resolved = []
for r in roots:
    p = Path(os.path.expanduser(r))
    if not p.is_absolute() or not p.is_dir():
        bad.append(f"--root must be an existing absolute directory: {r}")
        continue
    p = p.resolve()
    if p == Path(p.anchor) or p == home or p in home.parents:
        bad.append(f"--root is too broad (use a directory below your home): {r}")
    resolved.append(p)
for label, path in (("--dest", dest), ("--docker", docker), ("--python", py)):
    p = Path(os.path.expanduser(path)).resolve()
    if any(p == r or r in p.parents for r in resolved):
        bad.append(f"{label} must be outside every --root (the agent could edit it): {path}")
if bad:
    print("\n".join(bad), file=sys.stderr)
    sys.exit(1)
' "$dest" "$docker" "$py" "${roots[@]}"
mkdir -p "$dest"
tmp="$(mktemp -d "$dest/.dockerw-install.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT
# The conf goes in first (atomically, private until final): a shim without its conf would run with no allowed_roots.
(umask 077; python3 - "$tmp/dockerw.conf.json" "$docker" "${roots[@]}" <<'PY'
import json
import sys

path, docker, *roots = sys.argv[1:]
with open(path, "w") as f:
    f.write(json.dumps({"docker": docker, "allowed_roots": roots}, indent=2) + "\n")
PY
)
chmod 644 "$tmp/dockerw.conf.json"
if [ -e "$dest/dockerw.conf.json" ]; then
  cp -p "$dest/dockerw.conf.json" "$dest/dockerw.conf.json.bak-$(date +%Y%m%d%H%M%S)"
fi
mv -f "$tmp/dockerw.conf.json" "$dest/dockerw.conf.json"
install -m 755 "$here/dockerw.py" "$tmp/dockerw.py"
mv -f "$tmp/dockerw.py" "$dest/dockerw.py"
printf '#!/bin/sh\nexec "%s" -I "${0%%/*}/dockerw.py" "$@"\n' "$py" > "$tmp/dockerw"
chmod 755 "$tmp/dockerw"
mv -f "$tmp/dockerw" "$dest/dockerw"
echo "installed dockerw to $dest (python: $py, docker: $docker)"
