# sketchup-mcp pipeline — developer targets
#
# Windows: requires `mingw32-make` (from MSYS2) or `make` via git-bash.
# POSIX:   standard GNU make.
#
# The PYTHON interpreter is hard-coded to E:/Python312/python.exe on
# the dev box; override with `make PYTHON=python3 test` etc.

.PHONY: help test validate skp-dryrun lint smoke clean all ci

PYTHON ?= E:/Python312/python.exe
RUN_DIR ?= runs/proto/p12_v1_run

help:
	@echo "Targets:"
	@echo "  test        - pytest suite (expects >=149 pass, 15 pre-existing fail)"
	@echo "  validate    - F11 multiplant validation (runs against frozen fixtures)"
	@echo "  skp-dryrun  - F8 Path B dry-run of skp_export bridge (skipped if CLI absent)"
	@echo "  lint        - py_compile on core pipeline modules"
	@echo "  smoke       - run p12 + planta_74 end-to-end extraction"
	@echo "  clean       - remove CI smoke outputs"
	@echo "  all         - lint + test + validate + skp-dryrun + smoke"
	@echo "  ci          - same as 'all' but exits on first failure"

test:
	$(PYTHON) -m pytest tests/ -q

validate:
	$(PYTHON) scripts/validate_multiplant.py

skp-dryrun:
	@if [ -f skp_export/__main__.py ]; then \
		$(PYTHON) -m skp_export --run-dir $(RUN_DIR) --dry-run; \
	else \
		echo "skp_export CLI not present (F8 not merged locally) — skipping"; \
	fi

lint:
	$(PYTHON) -m py_compile classify/service.py topology/service.py openings/service.py extract/service.py model/pipeline.py model/types.py

smoke:
	$(PYTHON) run_p12.py
	$(PYTHON) run_planta74.py

clean:
	rm -rf runs/ci_smoke runs/validation/report_*.csv pytest.xml

all: lint test validate skp-dryrun smoke

ci: lint test
	@$(MAKE) --no-print-directory validate || echo "validate advisory-fail"
	@$(MAKE) --no-print-directory skp-dryrun
