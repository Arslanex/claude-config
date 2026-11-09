#!/usr/bin/env bash
# init.sh --kind: profildeki .cache dizinleri (ornegin uv onbellegi) projeye kopyalanmamali.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
h=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); d=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$h" "$d"' EXIT
[ -d "$h" ] && [ -d "$d" ] || { echo "mktemp failed" >&2; exit 1; }
mkdir -p "$h/.claude/templates"
cp -R "$R/src/templates/project" "$h/.claude/templates/project"
cp -R "$R/src/templates/profiles" "$h/.claude/templates/profiles"
c="$h/.claude/templates/profiles/fastapi-saas/.cache/uv"
mkdir -p "$c/sdists-v10"
echo x > "$c/.lock"
echo x > "$c/sdists-v10/.git"
cd "$d" && git init -q
HOME="$h" bash "$R/src/templates/project/init.sh" --kind fastapi-saas --pkg demo >/dev/null
[ -f Makefile ] || { echo "FAIL: profil dosyalari kopyalanmadi"; exit 1; }
[ -z "$(find . -path './.git' -prune -o -path '*/.cache*' -print | head -n 1)" ] || { echo "FAIL: .cache projeye kopyalandi"; find . -path './.git' -prune -o -path '*/.cache*' -print; exit 1; }
echo "PASS: profildeki .cache dizinleri projeye kopyalanmiyor"
