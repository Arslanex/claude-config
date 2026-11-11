#!/usr/bin/env bash
# fastapi-saas profilini bos bir projede gercek araclarla dener (uv gerekir).
set -euo pipefail
R="$(cd "$(dirname "$0")/.." && pwd)"
h=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); d=$(mktemp -d "${TMPDIR:-/tmp}/cc.XXXXXX"); trap 'rm -rf "$h" "$d"' EXIT
[ -d "$h" ] && [ -d "$d" ] || { echo "mktemp failed" >&2; exit 1; }
mkdir -p "$h/.claude/templates"
cp -R "$R/src/templates/project" "$h/.claude/templates/project"
# Uretilmis dizinler (.venv, onbellekler) kopyalanmaz; install.sh de onlari atlar.
rsync -a --inplace --exclude .venv --exclude .cache --exclude .ruff_cache --exclude .mypy_cache --exclude .pytest_cache \
  "$R/src/templates/profiles" "$h/.claude/templates/"
cd "$d" && git init -q
HOME="$h" bash "$R/src/templates/project/init.sh" --kind fastapi-saas --pkg demo >/dev/null
HOME="$h" bash "$R/src/templates/project/init.sh" --kind fastapi-saas --pkg demo >/dev/null
[ -z "$(find . -name '*.proposed' -not -path './.git/*')" ] || { echo "FAIL: ikinci calistirma .proposed uretti"; exit 1; }
printf '"""Metin yardimcisi."""\n\n\ndef squash(value: str) -> str:\n    return " ".join(value.split())\n' > backend/src/demo/core/text.py
printf 'from demo.core.text import squash\n\n\ndef test_squash_joins_whitespace():\n    assert squash(" a  b ") == "a b"\n' > backend/tests/unit/test_text.py
for f in .claude/team.md .claude/agents/backend.md .claude/agents/architect.md .claude/skills/saas-fastapi/SKILL.md docs/01-architecture/ARCH-0006-dosya-duzeni.md; do
  [ -f "$f" ] || { echo "FAIL: profil dosyasi eksik: $f"; exit 1; }
done
[ ! -e team ] || { echo "FAIL: team/ proje kokune kopyalandi"; exit 1; }
make check
[ -x tools/quiet.sh ] || { echo "FAIL: tools/quiet.sh calistirilabilir degil"; exit 1; }
[ "$(make test-unit T=tests/unit/test_text.py::test_squash_joins_whitespace)" = "test-unit: ok" ] || { echo "FAIL: make test-unit T= tek testi calistirmadi"; exit 1; }
export UV_CACHE_DIR="$PWD/.cache/uv"
( cd backend && DATABASE_URL='postgresql+asyncpg://u:p%40ss@localhost/db' uv run alembic upgrade head --sql >/dev/null ) || { echo "FAIL: alembic ortami (cevrimdisi) calismadi"; exit 1; }
( cd backend && uv run pytest tests/integration --collect-only -q >/dev/null ) || { echo "FAIL: entegrasyon testleri toplanamadi"; exit 1; }
[ -f docs/api/openapi.json ] || { echo "FAIL: make check API sozlesmesini uretmedi"; exit 1; }
printf '\n' >> docs/api/openapi.json
if make openapi-check >/dev/null 2>&1; then echo "FAIL: degisen sozlesme openapi-check'ten gecti"; exit 1; fi
make openapi >/dev/null && make openapi-check >/dev/null || { echo "FAIL: make openapi sozlesmeyi onarmadi"; exit 1; }
printf 'def stray() -> int:\n    return 1\n' > backend/src/demo/core/stray.py
if make lint >/dev/null 2>&1; then echo "FAIL: docstring'siz modul lint'ten gecti (D100)"; exit 1; fi
echo "PASS: fastapi-saas profili make check'ten geciyor"
