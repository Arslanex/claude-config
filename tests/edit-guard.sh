#!/usr/bin/env bash
# edit-guard hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/edit-guard.py"
fail=0
P=/proj
run() { printf '%s' "$1" | python3 "$H"; }
ask()    { out=$(run "$2"); if grep -q '"permissionDecision": "ask"' <<<"$out"; then echo "ok   $1 (sorar)"; else echo "FAIL $1: [$out]"; fail=1; fi; }
silent() { out=$(run "$2"); if [ -z "$out" ]; then echo "ok   $1 (sessiz)"; else echo "FAIL $1: [$out]"; fail=1; fi; }
ask    "importlinter Edit"   '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/.importlinter","old_string":"a","new_string":"b"}}'
ask    "mimari test Write"   '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/backend/tests/unit/test_architecture_stateless.py","content":"x"}}'
ask    "layout test Edit"    '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/tests/unit/test_tests_layout.py","old_string":"a","new_string":"b"}}'
ask    "Makefile Write"      '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/Makefile","content":"all:"}}'
ask    "Makefile check Edit" '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/Makefile","old_string":"check: lint","new_string":"check:"}}'
silent "Makefile yeni hedef" '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/Makefile","old_string":"help:","new_string":"seed:\n\tpython seed.py\nhelp:"}}'
silent "src dosyasi"         '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/src/app/core/ids.py","old_string":"a","new_string":"b"}}'
silent "yeni test dosyasi"   '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/backend/tests/unit/test_new.py","content":"x"}}'
silent "baska projede ayni ad" '{"cwd":"/other","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/.importlinter","old_string":"a","new_string":"b"}}'
silent "bozuk girdi"         'xx'
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
