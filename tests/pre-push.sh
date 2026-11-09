#!/usr/bin/env bash
# pre-push kapisi: kirmizi make check push'u engeller, yesil olan gecer (yerel bare uzak depoyla).
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
t=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$t"' EXIT
[ -d "$t" ] || { echo "mktemp failed" >&2; exit 1; }
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
setup() {
  rm -rf "$t/work" "$t/remote.git"
  git init -q --bare "$t/remote.git"
  mkdir -p "$t/work/tools/git-hooks"
  cp "$R/tools/git-hooks/pre-push" "$t/work/tools/git-hooks/pre-push"
  chmod +x "$t/work/tools/git-hooks/pre-push"
  ( cd "$t/work" && git init -q -b main && git config user.email t@t && git config user.name t \
    && git config core.hooksPath tools/git-hooks && git remote add origin "$t/remote.git" \
    && printf 'check:\n\t%s\n' "$1" > Makefile && git add -A && git commit -qm init )
}
setup true
if ( cd "$t/work" && git push -q origin main > /dev/null 2>&1 ); then ok "pass (yesil check push'u gecirir)"; else bad "yesil check push'u engelledi"; fi
setup false
if ( cd "$t/work" && git push -q origin main > /dev/null 2>&1 ); then bad "kirmizi check push'u engellemedi"; else
  if git -C "$t/remote.git" rev-parse --verify -q main > /dev/null 2>&1; then bad "engellendi ama uzak depo degisti"; else ok "block (kirmizi check engeller, uzak depo bos kalir)"; fi
fi
if [ "$fail" = 0 ]; then echo PASS; else echo FAIL; exit 1; fi
