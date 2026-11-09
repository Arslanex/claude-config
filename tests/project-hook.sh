#!/usr/bin/env bash
# Proje sablonu: pre-push kapisi init ile gelir, make hooks etkinlestirir, kirmizi check push'u engeller.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
t=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$t"' EXIT
[ -d "$t" ] || { echo "mktemp failed" >&2; exit 1; }
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
mkdir -p "$t/home/.claude"
cp -R "$R/src/templates" "$t/home/.claude/templates"
newproj() {
  rm -rf "$t/p" "$t/remote.git"
  git init -q --bare "$t/remote.git"
  mkdir "$t/p"
  ( cd "$t/p" && git init -q -b main && git config user.email t@t && git config user.name t \
    && git remote add origin "$t/remote.git" \
    && HOME="$t/home" bash "$R/src/templates/project/init.sh" "$@" > /dev/null )
}
H=src/templates/project/tools/git-hooks/pre-push
if cmp -s "$R/tools/git-hooks/pre-push" "$R/$H"; then ok "sync (sablon hook'u claude-config hook'uyla ayni)"; else bad "sablon hook'u claude-config hook'undan farkli"; fi

newproj
if [ -x "$t/p/tools/git-hooks/pre-push" ] && cmp -s "$R/$H" "$t/p/tools/git-hooks/pre-push"; then ok "init (hook kopyalandi, calistirilabilir)"; else bad "init hook'u getirmedi"; fi
if grep -q '^hooks:' "$t/p/Makefile"; then ok "target (proje Makefile'inda hooks var)"; else bad "proje Makefile'inda hooks yok"; fi
( cd "$t/p" && make hooks > /dev/null )
if [ "$(git -C "$t/p" config core.hooksPath)" = "tools/git-hooks" ]; then ok "hooks (core.hooksPath ayarlandi)"; else bad "core.hooksPath ayarlanmadi"; fi
( cd "$t/p" && git add -A && git commit -qm init )
if ( cd "$t/p" && git push -q origin main > /dev/null 2>&1 ); then bad "yapilandirilmamis proje push'u engellemedi"; else
  if git -C "$t/remote.git" rev-parse --verify -q main > /dev/null 2>&1; then bad "engellendi ama uzak depo degisti"; else ok "block (kirmizi check engeller, uzak depo bos)"; fi
fi
( cd "$t/p" && sed -i.bak 's/; exit 1//' Makefile && rm -f Makefile.bak && git add -A && git commit -qm green )
if ( cd "$t/p" && git push -q origin main > /dev/null 2>&1 ); then ok "pass (yesil check push'u gecirir)"; else bad "yesil check push'u engelledi"; fi

newproj --kind fastapi-saas --pkg app
if [ -x "$t/p/tools/git-hooks/pre-push" ] && grep -q '^hooks:' "$t/p/Makefile"; then ok "profile (fastapi-saas'ta hook ve hooks hedefi var)"; else bad "fastapi-saas'ta hook veya hedef eksik"; fi
if [ "$fail" = 0 ]; then echo PASS; else echo FAIL; exit 1; fi
