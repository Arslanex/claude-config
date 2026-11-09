#!/usr/bin/env bash
# commit-msg hook: Co-Authored-By and Claude-Session lines never reach a commit message.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
d=$(mktemp -d "${TMPDIR:-/tmp}/cm.XXXXXX"); trap 'rm -rf "$d"' EXIT
[ -d "$d" ] || { echo "mktemp failed" >&2; exit 1; }
cd "$d" && git init -q
mkdir -p hooks
cp "$R/tools/git-hooks/commit-msg" hooks/commit-msg 2>/dev/null || true
git config core.hooksPath "$d/hooks"
git config user.name t; git config user.email t@t
echo x > f; git add f
git commit -q -F - <<'MSG'
subject line

Body stays.

Co-Authored-By: Someone <a@b.c>
co-authored-by: lower <a@b.c>
Claude-Session: https://example.com/s
MSG
msg="$(git log -1 --format=%B)"
echo "$msg" | grep -qi -E '^(co-authored-by|claude-session):' && { echo "FAIL: trailer kaldı"; exit 1; }
echo "$msg" | grep -q '^subject line$' || { echo "FAIL: konu satırı kayboldu"; exit 1; }
echo "$msg" | grep -q '^Body stays\.$' || { echo "FAIL: gövde kayboldu"; exit 1; }
echo "PASS: commit-msg hook trailer satırlarını siliyor, gerisini koruyor"
