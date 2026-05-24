# Makefile — canonical entry points for governance + validation.
#
# Status: Canonical. See docs/REPO_HYGIENE.md, docs/GATES.md,
# docs/PR_HYGIENE.md for the underlying contracts.
#
# Why a Makefile when most contributors are on Windows?
# - Unix-like / WSL / CI environments get make for free; this is the
#   path of least friction there.
# - On Windows-only setups without make, copy the command body of the
#   target you want and run it directly. The canonical commands are
#   ALSO documented in docs/GATES.md and docs/PR_HYGIENE.md §7 so
#   nothing in this Makefile is a hidden requirement.
#
# Python invocation:
# - Set PY=path/to/python on the command line if you need a venv that
#   is not on PATH. Default is `python`.

PY ?= python

.PHONY: help project-state project-state-json repo-health repo-health-check repo-health-fix-dry gates pytest-gates pr-startup pr-exit ci-local

help: ## Show this help.
	@echo "Canonical governance targets:"
	@echo ""
	@echo "  make project-state          # G-PROJECT-STATE (canonical-paths gate)"
	@echo "  make project-state-json     # same, JSON output"
	@echo "  make repo-health            # G-REPO-HEALTH audit (read-only)"
	@echo "  make repo-health-check      # G-REPO-HEALTH check vs origin/develop"
	@echo "  make repo-health-fix-dry    # safe-fix preview (no writes)"
	@echo "  make gates                  # all cheap gates in order"
	@echo "  make pytest-gates           # pytest covering both gates"
	@echo "  make pr-startup             # docs/PR_HYGIENE.md §1 startup checklist"
	@echo "  make pr-exit                # docs/PR_HYGIENE.md §3 exit checklist"
	@echo "  make ci-local               # mirror the CI repo_health.yml job"
	@echo ""
	@echo "Override Python with PY=path/to/python (default: python)."

# --- Governance gates ----------------------------------------------------

project-state: ## Run scripts/project_state_check.py.
	$(PY) scripts/project_state_check.py

project-state-json: ## Run scripts/project_state_check.py with JSON output.
	$(PY) scripts/project_state_check.py --json

repo-health: ## Run tools/repo_health_gate.py --mode audit.
	$(PY) tools/repo_health_gate.py --mode audit

repo-health-check: ## Run tools/repo_health_gate.py --mode check --base origin/develop.
	$(PY) tools/repo_health_gate.py --mode check --base origin/develop

repo-health-fix-dry: ## Preview what --mode fix would do (no writes).
	$(PY) tools/repo_health_gate.py --mode fix --dry-run

gates: project-state repo-health-check ## Run both cheap governance gates.

pytest-gates: ## Run pytest over both gates' test files.
	$(PY) -m pytest tests/test_project_state_check.py tests/test_repo_health_gate.py -v

# --- PR hygiene checklists (read-only convenience targets) ---------------

pr-startup: ## Print the docs/PR_HYGIENE.md §1 startup checklist commands.
	@echo "Startup checklist (docs/PR_HYGIENE.md §1):"
	@echo "  git status"
	@echo "  git remote -v"
	@echo "  git fetch --all --prune"
	@echo "  git checkout develop"
	@echo "  git pull --ff-only origin develop"
	@echo "  git status"
	@echo "  gh pr list --state open --repo GFCDOTA/sketchup-mcp"

pr-exit: ## Print the docs/PR_HYGIENE.md §3 exit checklist commands.
	@echo "Exit checklist (docs/PR_HYGIENE.md §3):"
	@echo "  git status"
	@echo "  gh pr list --state open --repo GFCDOTA/sketchup-mcp"
	@echo "  $(PY) scripts/project_state_check.py"
	@echo "  $(PY) tools/repo_health_gate.py --mode check --base origin/develop"

# --- CI mirror -----------------------------------------------------------

ci-local: ## Mirror the .github/workflows/repo_health.yml job locally.
	$(PY) scripts/project_state_check.py
	$(PY) tools/repo_health_gate.py --mode check --base origin/develop
