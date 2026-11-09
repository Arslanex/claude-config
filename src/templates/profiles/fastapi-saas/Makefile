BACKEND ?= backend
TEST_DATABASE_URL ?= postgresql+asyncpg://test:test@localhost:55463/test
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
.PHONY: help check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi docs-lint stack-test-up stack-test-down hooks
help:
	@echo 'Targets: check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi docs-lint stack-test-up stack-test-down hooks verify-full'
check: lint typecheck arch test-unit docs-lint
lint:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
typecheck:
	cd $(BACKEND) && uv run mypy src
arch:
	cd $(BACKEND) && uv run lint-imports
test-unit:
	cd $(BACKEND) && uv run pytest tests/unit --cov=src --cov-branch --cov-fail-under=100
test-integration:
	cd $(BACKEND) && uv run pytest tests/integration
test-e2e:
	cd $(BACKEND) && uv run pytest tests/e2e
test-smoke:
	cd $(BACKEND) && uv run pytest tests/smoke
migrate:
	cd $(BACKEND) && uv run alembic upgrade head
migrate-check:
	cd $(BACKEND) && DATABASE_URL=$(TEST_DATABASE_URL) uv run alembic upgrade head && DATABASE_URL=$(TEST_DATABASE_URL) uv run alembic check
openapi:
	@echo 'openapi: uygulama yolu tanimli degil (profilde doldur)'; exit 1
docs-lint:
	@python3 tools/docs.py lint
stack-test-up:
	docker compose -f deploy/compose.yaml -f deploy/compose.test.yaml up -d --wait postgres redis
stack-test-down:
	docker compose -f deploy/compose.yaml -f deploy/compose.test.yaml down -v

.PHONY: hooks
hooks:
	git config core.hooksPath tools/git-hooks
	@echo "pre-push gate active (core.hooksPath = tools/git-hooks)"

# Database-backed verification in one command. Projects extend it (e.g. with a local stack and smoke test).
.PHONY: verify-full
verify-full:
	@set -e; trap '$(MAKE) stack-test-down > /dev/null 2>&1' EXIT; \
	$(MAKE) stack-test-down; $(MAKE) stack-test-up; $(MAKE) test-integration; $(MAKE) migrate-check; $(MAKE) stack-test-down
