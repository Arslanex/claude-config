#!/usr/bin/env bash
# compact-context hook'unu gecici bir proje uzerinde dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/compact-context.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
[ -n "$T" ] && [ -d "$T" ] || { echo "mktemp failed" >&2; exit 1; }
fail=0
chk() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
cd "$T" || exit 1; git init -q -b main . && mkdir -p docs/05-work/{handoffs,tasks,plans,log}
echo idx > docs/INDEX.md
echo "OLD-HANDOFF" > docs/05-work/handoffs/eski.md && touch -t 202001010000 docs/05-work/handoffs/eski.md
echo "HANDOFF-SENTINEL kaldigim yer" > docs/05-work/handoffs/yeni.md
echo t > docs/05-work/tasks/T-0001-ornek.md
git add -A && git -c user.name=t -c user.email=t@t commit -q -m ilk
echo kirli > kirli.txt
out=$(printf '{"cwd":"%s","source":"compact"}' "$T" | python3 "$H")
chk "gecerli JSON"            "python3 -c 'import json,sys; json.loads(sys.argv[1])' \"\$out\""
chk "olay adi SessionStart"   "grep -q '\"hookEventName\": \"SessionStart\"' <<<\"\$out\""
chk "son devir notu var"      "grep -q HANDOFF-SENTINEL <<<\"\$out\""
chk "eski devir notu yok"     "! grep -q OLD-HANDOFF <<<\"\$out\""
chk "gorev dosyasi listeli"   "grep -q T-0001-ornek <<<\"\$out\""
chk "git dali ve kirli sayi"  "grep -q 'dal main, 1 degisen' <<<\"\$out\""
python3 -c 'print("x"*9000)' > docs/05-work/handoffs/uzun.md
out2=$(printf '{"cwd":"%s"}' "$T" | python3 "$H")
chk "toplam sinir (<6000)"    "[ \${#out2} -lt 6000 ]"
rm docs/INDEX.md
out3=$(printf '{"cwd":"%s"}' "$T" | python3 "$H")
chk "INDEX yoksa sessiz"      "[ -z \"\$out3\" ]"
out4=$(printf 'xx' | python3 "$H")
chk "bozuk girdi sessiz"      "[ -z \"\$out4\" ]"
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
