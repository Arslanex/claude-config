BACKEND ?= backend
TEST_DATABASE_URL ?= postgresql+asyncpg://test:test@localhost:55463/test
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
API_CONTRACT ?= docs/api/openapi.json
.PHONY: help check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi openapi-check docs-lint stack-test-up stack-test-down hooks sast test-live test-ui
help:
	@echo 'Targets: check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi openapi-check docs-lint stack-test-up stack-test-down hooks sast verify-full test-live test-ui'
# Checks run through tools/quiet.sh: "<target>: ok" on success, only the failing lines otherwise
# (full output in .cache/logs/<target>.log). V=1 shows the full output. T=<test path> runs one test.
V ?= 0
ifeq ($(V),1)
AT :=
RUN :=
else
AT := @
RUN = $(CURDIR)/tools/quiet.sh $@
endif
PYTEST := uv run pytest -q --tb=short
check: lint typecheck arch test-unit openapi-check docs-lint
lint:
	$(AT)cd $(BACKEND) && $(RUN) sh -c 'uv run ruff check --output-format=concise . && uv run ruff format --check .'
typecheck:
	$(AT)cd $(BACKEND) && $(RUN) uv run mypy src
arch:
	$(AT)cd $(BACKEND) && $(RUN) uv run lint-imports
test-unit:
	$(AT)cd $(BACKEND) && $(RUN) $(PYTEST) $(if $(T),$(T),tests/unit --cov=src --cov-branch --cov-fail-under=100 --cov-report=term-missing:skip-covered)
test-integration:
	$(AT)cd $(BACKEND) && $(RUN) $(PYTEST) $(if $(T),$(T),tests/integration)
test-e2e:
	$(AT)cd $(BACKEND) && $(RUN) $(PYTEST) tests/e2e
test-smoke:
	$(AT)cd $(BACKEND) && $(RUN) $(PYTEST) tests/smoke
migrate:
	cd $(BACKEND) && uv run alembic upgrade head
migrate-check:
	$(AT)cd $(BACKEND) && $(RUN) env DATABASE_URL=$(TEST_DATABASE_URL) sh -c 'uv run alembic upgrade head && uv run alembic check'
# API sozlesmesi (ARCH-0007): kod tek kaynak, dosya commit edilir; frontend tipleri ve sozlesme testleri onu okur.
openapi:
	@mkdir -p $(dir $(API_CONTRACT))
	@cd $(BACKEND) && uv run python -m PKG_NAME.interface.cli.openapi > $(CURDIR)/$(API_CONTRACT)
	@echo 'openapi: $(API_CONTRACT) yazildi'
# Dosya yoksa ilk kez uretir; varsa koddan uretilenle bayt bayt karsilastirir.
openapi-check:
	@test -f $(API_CONTRACT) || $(MAKE) --no-print-directory openapi
	@mkdir -p .cache
	$(AT)$(RUN) sh -c '(cd $(BACKEND) && uv run python -m PKG_NAME.interface.cli.openapi > $(CURDIR)/.cache/openapi.json) || exit 1; cmp -s $(API_CONTRACT) .cache/openapi.json || { echo "openapi-check: $(API_CONTRACT) koddaki sozlesmeden farkli. Degisiklik bilincliyse: make openapi (ve mimara haber ver)"; exit 1; }'
docs-lint:
	$(AT)$(RUN) python3 tools/docs.py lint
stack-test-up:
	docker compose -f deploy/compose.yaml -f deploy/compose.test.yaml up -d --wait postgres redis
stack-test-down:
	docker compose -f deploy/compose.yaml -f deploy/compose.test.yaml down -v
# Gercek dis servis testleri (@pytest.mark.live): yalniz kullanici calistirir, para ve kota harcar.
# WORKER_MODE=live ve servis anahtarlari kok .env dosyasindan okunur; ajan .env okuyamaz.
test-live:
	set -a && . ./.env && set +a && cd $(BACKEND) && uv run pytest -m live
# Arayuz e2e testleri (Playwright, konteynerde). Ajanlar ayni adimlari .claude/team.md listesindeki bare dockerw ile calistirir.
test-ui:
	docker compose -f deploy/compose.yaml -f deploy/compose.test.yaml --profile e2e run --rm e2e

.PHONY: hooks
hooks:
	git config core.hooksPath tools/git-hooks
	@echo "pre-push gate active (core.hooksPath = tools/git-hooks)"

# Database-backed verification in one command. Projects extend it (e.g. with a local stack and smoke test).
# Statik guvenlik taramasi (semgrep). Kurallar semgrep.dev'den gelir ve zamanla degisir, bu yuzden
# `check` icinde degil; verify-full ve guvenlik isleri calistirir. Surum sabit, metrik ve surum denetimi kapali.
SEMGREP_VERSION := 1.182.1
sast:
	cd $(BACKEND) && SEMGREP_ENABLE_VERSION_CHECK=0 uvx --from semgrep==$(SEMGREP_VERSION) semgrep scan \
	  --metrics=off --error --quiet --config p/python --config p/secrets src

.PHONY: verify-full
verify-full:
	@set -e; trap '$(MAKE) stack-test-down > /dev/null 2>&1' EXIT; \
	$(MAKE) sast; $(MAKE) stack-test-down; $(MAKE) stack-test-up; $(MAKE) migrate-check; $(MAKE) test-integration; $(MAKE) stack-test-down
