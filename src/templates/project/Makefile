.PHONY: help check lint test docs-lint hooks
help:
	@echo 'Targets: check lint test docs-lint hooks'
check: lint test docs-lint
lint:
	@echo 'lint: not configured for this project (define it in the Makefile)'; exit 1
test:
	@echo 'test: not configured for this project (define it in the Makefile)'; exit 1
docs-lint:
	@python3 tools/docs.py lint

.PHONY: hooks
hooks:
	git config core.hooksPath tools/git-hooks
	@echo "pre-push gate active (core.hooksPath = tools/git-hooks)"
