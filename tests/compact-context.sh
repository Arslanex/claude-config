#!/usr/bin/env bash
# compact-context hook'unu gecici bir proje uzerinde dener (claude gerekmez).
set -uo pipefail
H="$(cd "$(dirname "$0")/.." && pwd)/src/hooks/compact-context.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX")"; trap 'rm -rf "$T"' EXIT
[ -n "$T" ] && [ -d "$T" ] || { echo "mktemp failed" >&2; exit 1; }
fail=0
chk() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }
cd "$T" || exit 1; git init -q -b main . && mkdir -p docs/05-work/{handoffs,tasks,plans,log}
echo idx > docs/INDEX.md
echo "OLD-HANDOFF" > docs/05-work/handoffs/HO-0001-eski.md
printf -- '---\nupdated: 2026-11-09\n---\nHANDOFF-SENTINEL kaldigim yer\n' > docs/05-work/handoffs/HO-0002-yeni.md
# mtime tuzagi: yuksek numarali not dosya zamani olarak daha eski, yine de o secilmeli
touch -t 202001010000 docs/05-work/handoffs/HO-0002-yeni.md
echo t > docs/05-work/tasks/T-0001-ornek.md
echo t > docs/05-work/tasks/T-0002-ornek.md
git add -A && git -c user.name=t -c user.email=t@t commit -q -m ilk
echo kirli > kirli.txt
out=$(printf '{"cwd":"%s","source":"compact"}' "$T" | python3 "$H")
chk "gecerli JSON"            "python3 -c 'import json,sys; json.loads(sys.argv[1])' \"\$out\""
chk "olay adi SessionStart"   "grep -q '\"hookEventName\": \"SessionStart\"' <<<\"\$out\""
chk "son devir notu var"      "grep -q HANDOFF-SENTINEL <<<\"\$out\""
chk "eski devir notu yok (mtime tuzagi)" "! grep -q OLD-HANDOFF <<<\"\$out\""
chk "anlik goruntu uyarisi"   "grep -q 'ANLIK GORUNTU' <<<\"\$out\""
chk "updated tarihi basta"    "grep -q 'updated: 2026-11-09' <<<\"\$out\""
chk "gorev dosyasi listeli"   "grep -q T-0001-ornek <<<\"\$out\""
chk "gorevler ada gore (T-0002 once)" "python3 -c 'import sys; c=sys.argv[1]; sys.exit(0 if c.index(\"T-0002\") < c.index(\"T-0001\") else 1)' \"\$out\""
chk "git dali ve kirli sayi"  "grep -q 'dal main, 1 degisen' <<<\"\$out\""
for i in $(seq 1 40); do printf 'SATIR-%s-%s-SON\n' "$i" "$(printf 'x%.0s' $(seq 1 80))"; done > docs/05-work/handoffs/HO-0003-satirlar.md
out5=$(printf '{"cwd":"%s","source":"compact"}' "$T" | python3 "$H")
ctx5=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["hookSpecificOutput"]["additionalContext"])' "$out5")
chk "satir sinirinda kesim"   "grep -q 'SATIR-' <<<\"\$ctx5\" && ! grep 'SATIR-' <<<\"\$ctx5\" | grep -qv -- '-SON\$'"
python3 -c 'print("x"*9000)' > docs/05-work/handoffs/uzun.md
out2=$(printf '{"cwd":"%s"}' "$T" | python3 "$H")
chk "toplam sinir (<6000)"    "[ \${#out2} -lt 6000 ]"
rm docs/INDEX.md
out3=$(printf '{"cwd":"%s"}' "$T" | python3 "$H")
chk "INDEX yoksa sessiz"      "[ -z \"\$out3\" ]"
out4=$(printf 'xx' | python3 "$H")
chk "bozuk girdi sessiz"      "[ -z \"\$out4\" ]"
if [ $fail = 0 ]; then echo "PASS"; else echo "FAILED"; exit 1; fi
