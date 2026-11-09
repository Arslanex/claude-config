#!/usr/bin/env bash
# stop-gate hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/stop-gate.py"
t=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$t"' EXIT
[ -d "$t" ] || { echo "mktemp failed" >&2; exit 1; }
fail=0
mk() { # ad, check tarifi, kirli(0/1)
  d="$t/$1"; mkdir -p "$d"
  (cd "$d" && git init -q && git config user.email t@t && git config user.name t \
    && printf 'check:\n\t%s\n' "$2" > Makefile && git add -A && git commit -qm init)
  if [ "$3" = 1 ]; then echo x > "$d/dirty.txt"; fi
}
run() { echo "{\"cwd\":\"$t/$1\"$2}" | python3 "$H"; }
silent() { out=$(run "$1" "$2"); if [ -z "$out" ]; then echo "ok   $1 $3"; else echo "FAIL $1: $out"; fail=1; fi; }
block() { out=$(run "$1" "$2"); if grep -q '"decision": "block"' <<<"$out" && grep -q BOOM <<<"$out"; then echo "ok   $1 (engelledi)"; else echo "FAIL $1: $out"; fail=1; fi; }
mk pass 'true' 1;                                                 silent pass "" "(gecen check)"
mk fail 'echo BOOM; exit 1' 1;                                    block fail ""
silent fail ',"stop_hook_active":true' "(stop_hook_active)"
mk unconf 'echo "lint: not configured for this project"; exit 1' 1; silent unconf "" "(yapilandirilmamis)"
mk clean 'echo BOOM; exit 1' 0;                                   silent clean "" "(temiz agac)"
mkdir -p "$t/nomake";                                             silent nomake "" "(Makefile yok)"
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
