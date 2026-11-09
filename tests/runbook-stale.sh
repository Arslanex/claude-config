#!/usr/bin/env bash
# docs engine v5: runbook kind (RUN, 04-operations) is a living kind for `stale`; handoffs are not.
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_COMMON_DIR
t=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$t"' EXIT
[ -d "$t" ] || { echo "mktemp failed" >&2; exit 1; }
E="$R/src/templates/project/tools/docs.py"
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1"; fail=1; }
mkdir -p "$t/docs"
python3 "$E" new runbook "Rotate keys" --root "$t/docs" > /dev/null
python3 "$E" new handoff "Some handoff" --root "$t/docs" > /dev/null
if [ -f "$t/docs/04-operations/RUN-0001-rotate-keys.md" ]; then ok "runbook (RUN-0001 04-operations altinda)"; else bad "runbook dosyasi beklenen yerde degil"; fi
if python3 "$E" lint --root "$t/docs" > /dev/null 2>&1; then ok "lint (runbook ve handoff temiz)"; else bad "lint hata verdi"; fi
out="$(python3 "$E" stale --days 90 --today 2099-01-01 --root "$t/docs" 2>&1 || true)"
if printf '%s\n' "$out" | grep -q 'RUN-0001'; then ok "stale (runbook yasayan tur, listelendi)"; else bad "stale runbook'u listelemedi: $out"; fi
if printf '%s\n' "$out" | grep -q 'HO-0001'; then bad "stale handoff'u listeledi"; else ok "stale (handoff taranmaz)"; fi
if [ "$fail" = 0 ]; then echo PASS; else echo FAIL; exit 1; fi
