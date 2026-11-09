.PHONY: test check help

PY_TESTS := $(notdir $(wildcard tests/test_*.py))
SH_TESTS := $(wildcard tests/*.sh)

help:
	@echo "Targets:"
	@echo "  test   run every tests/test_*.py (unittest) and tests/*.sh; run all, report failures at the end"
	@echo "  check  currently the same as test (lint will be added later)"
	@echo "  agent-eval  run the agent regression harness (calls claude, costs tokens)"
	@echo "  live-test   tests that need a live claude and network (not part of check)"
	@echo "  help   show this help"

# A failing test file never stops the others; failures are collected and listed at the end.
test:
	@guard_before="$$( (git rev-parse HEAD; git status --porcelain) 2>/dev/null )"; failed=""; \
	for f in $(PY_TESTS); do \
		echo "==> unittest: $$f"; \
		python3 -m unittest discover -s tests -p "$$f" -v || failed="$$failed tests/$$f"; \
	done; \
	for f in $(SH_TESTS); do \
		echo "==> script: $$f"; \
		bash "$$f" || failed="$$failed $$f"; \
	done; \
	guard_after="$$( (git rev-parse HEAD; git status --porcelain) 2>/dev/null )"; \
	if [ "$$guard_before" != "$$guard_after" ]; then \
		echo ""; echo "FAILED: tests changed the repository (HEAD or working tree)"; failed="$$failed <repo-mutation>"; \
	fi; \
	if [ -n "$$failed" ]; then \
		echo ""; \
		echo "FAILED:"; \
		for f in $$failed; do echo "  $$f"; done; \
		exit 1; \
	fi; \
	echo ""; \
	echo "All test files passed."

check: test

.PHONY: agent-eval
agent-eval:
	python3 tests/agents/run.py

.PHONY: live-test
live-test:
	bash tests/live/sandbox-secrets.sh
