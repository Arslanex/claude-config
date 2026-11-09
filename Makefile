.PHONY: test check help

PY_TESTS := $(notdir $(wildcard tests/test_*.py))
SH_TESTS := $(wildcard tests/*.sh)

help:
	@echo "Targets:"
	@echo "  test   run every tests/test_*.py (unittest) and tests/*.sh; run all, report failures at the end"
	@echo "  check  currently the same as test (lint will be added later)"
	@echo "  help   show this help"

# A failing test file never stops the others; failures are collected and listed at the end.
test:
	@failed=""; \
	for f in $(PY_TESTS); do \
		echo "==> unittest: $$f"; \
		python3 -m unittest discover -s tests -p "$$f" -v || failed="$$failed tests/$$f"; \
	done; \
	for f in $(SH_TESTS); do \
		echo "==> script: $$f"; \
		bash "$$f" || failed="$$failed $$f"; \
	done; \
	if [ -n "$$failed" ]; then \
		echo ""; \
		echo "FAILED:"; \
		for f in $$failed; do echo "  $$f"; done; \
		exit 1; \
	fi; \
	echo ""; \
	echo "All test files passed."

check: test
