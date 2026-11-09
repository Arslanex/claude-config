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
mkdir -p "$dest"
install -m 755 "$here/dockerw.py" "$dest/dockerw.py"
printf '#!/bin/sh\nexec "%s" -I "${0%%/*}/dockerw.py" "$@"\n' "$py" > "$dest/dockerw"
chmod 755 "$dest/dockerw"
python3 - "$dest/dockerw.conf.json" "$docker" "${roots[@]}" <<'PY'
import json
import sys

path, docker, *roots = sys.argv[1:]
with open(path, "w") as f:
    f.write(json.dumps({"docker": docker, "allowed_roots": roots}, indent=2) + "\n")
PY
chmod 644 "$dest/dockerw.conf.json"
echo "installed dockerw to $dest (python: $py, docker: $docker)"
