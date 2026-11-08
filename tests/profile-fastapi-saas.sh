#!/usr/bin/env bash
# fastapi-saas profilini bos bir projede gercek araclarla dener (uv gerekir).
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
h=$(mktemp -d); d=$(mktemp -d); trap 'rm -rf "$h" "$d"' EXIT
mkdir -p "$h/.claude/templates"
cp -R "$R/src/templates/project" "$h/.claude/templates/project"
cp -R "$R/src/templates/profiles" "$h/.claude/templates/profiles"
cd "$d" && git init -q
HOME="$h" bash "$R/src/templates/project/init.sh" --kind fastapi-saas --pkg demo >/dev/null
HOME="$h" bash "$R/src/templates/project/init.sh" --kind fastapi-saas --pkg demo >/dev/null
[ -z "$(find . -name '*.proposed' -not -path './.git/*')" ] || { echo "FAIL: ikinci calistirma .proposed uretti"; exit 1; }
printf 'import uuid\n\n\ndef new_id() -> str:\n    return str(uuid.uuid4())\n' > backend/src/demo/core/ids.py
printf 'from demo.core.ids import new_id\n\n\ndef test_new_id_is_uuid_string():\n    assert len(new_id()) == 36\n' > backend/tests/unit/test_ids.py
make check
echo "PASS: fastapi-saas profili make check'ten geciyor"
