BACKEND ?= backend
.PHONY: help check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi docs-lint
help:
	@echo 'Targets: check lint typecheck arch test-unit test-integration test-e2e test-smoke migrate migrate-check openapi docs-lint'
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
	cd $(BACKEND) && uv run alembic check
openapi:
	@echo 'openapi: uygulama yolu tanimli degil (profilde doldur)'; exit 1
docs-lint:
	@python3 tools/docs.py lint
