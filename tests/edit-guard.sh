#!/usr/bin/env bash
# edit-guard hook'unu sentetik girdiyle dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/edit-guard.py"
fail=0
P=/proj
run() { printf '%s' "$1" | python3 "$H"; }
ask()    { out=$(run "$2"); if grep -q '"permissionDecision": "ask"' <<<"$out"; then echo "ok   $1 (sorar)"; else echo "FAIL $1: [$out]"; fail=1; fi; }
allow()  { out=$(run "$2"); if grep -q '"permissionDecision": "allow"' <<<"$out"; then echo "ok   $1 (onaylar)"; else echo "FAIL $1: [$out]"; fail=1; fi; }
silent() { out=$(run "$2"); if [ -z "$out" ]; then echo "ok   $1 (sessiz)"; else echo "FAIL $1: [$out]"; fail=1; fi; }
ask    "importlinter Edit"   '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/.importlinter","old_string":"a","new_string":"b"}}'
ask    "mimari test Write"   '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/backend/tests/unit/test_architecture_stateless.py","content":"x"}}'
ask    "layout test Edit"    '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/tests/unit/test_tests_layout.py","old_string":"a","new_string":"b"}}'
ask    "Makefile Write"      '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/Makefile","content":"all:"}}'
ask    "Makefile check Edit" '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/Makefile","old_string":"check: lint","new_string":"check:"}}'
ask    "rol tanimi Edit"     '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/agents/backend.md","old_string":"a","new_string":"b"}}'
allow  "ekip skill Write"    '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/.claude/skills/saas-fastapi/SKILL.md","content":"x"}}'
ask    "ekip tanimi Edit"    '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/team.md","old_string":"a","new_string":"b"}}'
ask    "proje kurali"        '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/.claude/rules/backend-tests.md","old_string":"a","new_string":"b"}}'
silent "sablon kaynagi"      '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/src/templates/profiles/x/team/agents/backend.md","old_string":"a","new_string":"b"}}'
ask    "pre-push kapisi"     '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/tools/git-hooks/pre-push","old_string":"make check","new_string":"true"}}'
ask    "ruff kurali silme"   '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/pyproject.toml","old_string":"extend-select = [\"D100\", \"D104\"]","new_string":""}}'
ask    "pyproject Write"     '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/backend/pyproject.toml","content":"[project]"}}'
ask    "mypy gevsetme"       '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/pyproject.toml","old_string":"x","new_string":"[tool.mypy]\nignore_missing_imports = true"}}'
silent "bagimlilik ekleme"   '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/pyproject.toml","old_string":"dependencies = [\"fastapi\"]","new_string":"dependencies = [\"fastapi\", \"httpx\"]"}}'
silent "Makefile yeni hedef" '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/Makefile","old_string":"help:","new_string":"seed:\n\tpython seed.py\nhelp:"}}'
silent "src dosyasi"         '{"cwd":"/proj","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/src/app/core/ids.py","old_string":"a","new_string":"b"}}'
silent "yeni test dosyasi"   '{"cwd":"/proj","tool_name":"Write","tool_input":{"file_path":"/proj/backend/tests/unit/test_new.py","content":"x"}}'
silent "baska projede ayni ad" '{"cwd":"/other","tool_name":"Edit","tool_input":{"file_path":"/proj/backend/.importlinter","old_string":"a","new_string":"b"}}'
silent "bozuk girdi"         'xx'
T="$(mktemp -d "${TMPDIR:-/tmp}/edit-guard.XXXXXX")"; [ -d "$T" ] || exit 1
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/.claude/agents" "$T/.claude/skills/x"
printf -- '---\nname: backend\ntools: Read, Edit\nmodel: sonnet\n---\nBody line.\n' > "$T/.claude/agents/backend.md"
printf -- '---\nname: x\n---\nStep one.\n' > "$T/.claude/skills/x/SKILL.md"
printf 'Team rules.\n' > "$T/.claude/team.md"
allow  "rol govdesi Edit"    '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/agents/backend.md","old_string":"Body line.","new_string":"Body line. More."}}'
allow  "rol modeli Edit"     '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/agents/backend.md","old_string":"model: sonnet","new_string":"model: opus"}}'
ask    "rol tools genisler"  '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/agents/backend.md","old_string":"tools: Read, Edit","new_string":"tools: Read, Edit, Bash"}}'
ask    "rol Write tools"     '{"cwd":"'"$T"'","tool_name":"Write","tool_input":{"file_path":"'"$T"'/.claude/agents/backend.md","content":"---\nname: backend\ntools: Read, Edit, Bash\n---\nx\n"}}'
ask    "permissionMode ekler" '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/agents/backend.md","old_string":"model: sonnet","new_string":"model: sonnet\npermissionMode: bypassPermissions"}}'
allow  "skill govdesi Edit"  '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/skills/x/SKILL.md","old_string":"Step one.","new_string":"Step one. Step two."}}'
ask    "skill allowed-tools" '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/skills/x/SKILL.md","old_string":"name: x","new_string":"name: x\nallowed-tools: Bash"}}'
allow  "yeni skill dosyasi"  '{"cwd":"'"$T"'","tool_name":"Write","tool_input":{"file_path":"'"$T"'/.claude/skills/y/SKILL.md","content":"---\nname: y\n---\nx\n"}}'
allow  "team.md Edit"        '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/team.md","old_string":"Team rules.","new_string":"Team rules, better."}}'
ask    "eslesmeyen Edit"     '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/team.md","old_string":"missing","new_string":"x"}}'
silent "settings dosyasi"    '{"cwd":"'"$T"'","tool_name":"Edit","tool_input":{"file_path":"'"$T"'/.claude/settings.json","old_string":"a","new_string":"b"}}'
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
