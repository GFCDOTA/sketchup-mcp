#!/usr/bin/env python
"""Repository health gate.

Automated enforcement of docs/REPO_HYGIENE.md + CLAUDE.md §15 +
CLAUDE.md §17 twelve-question stop gate item #7 ("Safe cleanup
pending?"). Companion to scripts/project_state_check.py.

Three modes:

  audit   Default. Run every detector, print findings, always exit 0.
          Writes reports/current/repo_health_report.md.
  check   CI/PR mode. Exit 1 on any ERROR (any WARNING under --strict).
          With --base REF, only NEW violations vs REF count.
  fix     Apply ONLY the conservative safe-fix list and print what was
          done. Never deletes tracked files. Never rewrites .md
          content. Never touches *.py / *.rb.

Detectors:

  E001  tmp-file-tracked          .tmp_*/*.bak/*.swp/*.orig in index
  E002  generated-in-wrong-path   tracked generated artifact outside
                                  the allowed paths in REPO_HYGIENE.md §5
  E003  new-dir-not-canonical     PR mode: new top-level dir not in the
                                  canonical set
  E004  new-md-no-status          PR mode: new .md without Status: header
  E005  heavy-file-no-allowlist   tracked file > 5MB outside fixtures /
                                  vendor / docs/specs/_assets
  E006  project-state-stale       PR mode: structural diff but neither
                                  docs/PROJECT_STATE.md nor docs/HANDOFF.md
                                  is in the diff
  W001  loose-script-in-root      *.py at repo root other than main.py
  W002  existing-md-no-status     pre-existing docs/ .md without Status:
  W003  duplicate-fixture         identical SHA256 at two fixture paths
  W004  old-report-in-current     reports/current/ entry older than 30d
  W005  loose-data-in-root        *.pdf/*.png/*.svg at repo root not in
                                  the canonical allow-list
  I001  gitignore-missing         workdir file matching obvious ignore
                                  pattern that is not in .gitignore
  I002  archived-wrong-location   Status: Archived doc not under
                                  docs/_archive/
  I003  intentional-root-script   *.py at root that is in
                                  ROOT_PY_KEEP_AT_ROOT allowlist (with
                                  cited reason — never fires W001).
                                  Stale entries (allowlisted file no
                                  longer tracked) also surface as I003.

Safe fixes (mode=fix only):

  F-OLD-REPORT  move reports/current/<file> > 30d old to
                reports/archive/YYYY-MM/<file>
  F-GITIGNORE   append missing obvious patterns to .gitignore
  F-TMP-WORKDIR remove .tmp_*/*.bak/*.swp from working tree IF UNTRACKED

Exit codes:
  0  audit always; check with no errors; fix always
  1  check with any error (strict: any warning)
  2  argv error / IO error
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent

REPORT_PATH_DEFAULT = "reports/current/repo_health_report.md"

# ---- Canonical structure (kept in sync with docs/REPO_HYGIENE.md §1) -----

CANONICAL_TOP_LEVEL_DIRS = frozenset({
    # Source packages (pipeline)
    "agents", "api", "classify", "cockpit", "config", "debug",
    "extract", "ingest", "model", "openings", "patches", "renderers",
    "roi", "sketchup_mcp_server", "topology", "validator",
    # Docs & governance
    "docs", "scripts", "specs", "tools", "tests", "fixtures",
    "ground_truth", "references", "reports", "runs", "vendor",
    "out", "review",
    # Hidden / tooling
    ".github", ".claude", ".ai_bridge", ".venv", ".git", ".pytest_cache",
    ".ruff_cache", ".mypy_cache",
})

# Status: header policy (docs/REPO_HYGIENE.md §2)
STATUS_HEADER_RE = re.compile(r"^\s*>?\s*\*?\*?Status:\*?\*?\s*", re.MULTILINE)

# Root .md files exempt from Status: header policy (their role is obvious
# from path / they're top-level intentional docs that pre-date the policy).
ROOT_MD_EXEMPT = frozenset({
    "README.md", "CHANGELOG.md", "CLAUDE.md", "OVERVIEW.md", "AGENTS.md",
    "PROMPT-FELIPE.md", "PROMPT-RENAN.md",
})

# Tmp / backup file patterns banned from git index (E001).
TMP_FILE_GLOBS = ("*.tmp", ".tmp_*", "*.bak", "*~", "*.swp", "*.orig", "*.rej")

# Generated artifact patterns (E002). Allowed under the paths in
# GENERATED_ALLOWED_PREFIXES OR anywhere if they match GENERATED_ALLOWED_EXACT.
GENERATED_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".log", ".skp",
                      ".pkl", ".pth", ".pyc")

GENERATED_ALLOWED_PREFIXES = (
    "docs/",                        # docs/* may carry hand-curated images
    "fixtures/",
    "ground_truth/",
    "tests/baselines/",
    "tests/fixtures/",
    "vendor/",
    "patches/",                     # patches/archive/*.py contains legit code
    ".github/",
    ".claude/",
    "references/",
    "runs/",                        # gitignored anyway, but allowed if force-added
    "agents/",
    "tools/dashboard/",             # team-shared dashboard assets
    "tools/quadrado/",              # quadrado render assets
    "tools/fidelity/",              # fidelity gate assets
    "tools/synth/",                 # synthetic-corpus assets
    ".ai_bridge/",
    "sketchup_mcp_server/",         # ruby plugin assets
)

# Specific tracked files at unusual paths that have been explicitly
# justified and should not be flagged.
GENERATED_ALLOWED_EXACT = frozenset({
    "planta_74.pdf", "planta_74_clean.pdf", "planta_74_mask.png",
    "test_plan.pdf",
})

# Heavy-file threshold (E005), in bytes.
HEAVY_FILE_THRESHOLD = 5 * 1024 * 1024

# Old-report threshold (W004), in days.
OLD_REPORT_DAYS = 30

# Root .py files that are legitimately at the repo root.
ROOT_PY_ALLOWED = frozenset({"main.py", "setup.py"})

# Root .py files INTENTIONALLY kept at the repo root with a documented
# reason. These never fire W001; they fire I003 (informational) so the
# decision stays visible in every audit report.
#
# Each entry MUST cite an authoritative source (audit ledger / archive
# doc / deprecation-wrapper spec). Promote out (move/delete) only when
# the cited trigger fires.
#
# Source of these decisions: docs/ops/repo_hygiene_audit_2026-05-10.md
# §211 (per-file move-trigger matrix) + docs/architecture/
# target_repo_architecture.md step 5 (renderers/ migration wrapper
# policy) + .ai_bridge/HANDOFF.md:301 (3-audit "preserve-only"
# convergence under maintainer review).
ROOT_PY_KEEP_AT_ROOT: dict[str, str] = {
    # --- deprecation wrappers for renderers/ migration (step 5) ---
    "render_debug.py": (
        "deprecation wrapper for `renderers.debug` (2026-05-08 "
        "migration step 5); keeps `python render_debug.py` CLI alive "
        "for legacy callers until full client migration"
    ),
    "render_native.py": (
        "deprecation wrapper for `renderers.native` (2026-05-08 "
        "migration step 5); keeps `python render_native.py` CLI alive"
    ),
    "render_proto_overlays.py": (
        "deprecation wrapper for `renderers.proto_overlays` "
        "(2026-05-08 migration step 5)"
    ),
    "render_semantic.py": (
        "deprecation wrapper for `renderers.semantic` "
        "(2026-05-08 migration step 5)"
    ),
    "render_with_openings.py": (
        "deprecation wrapper for `renderers.with_openings` "
        "(2026-05-08 migration step 5)"
    ),
    # --- standalone diagnostic / fixture-builder scripts ---
    "analyze_overpoly.py": (
        "reproducible-script CLI cited at "
        "docs/_archive/2026-04-f1-cycle/OVER-POLYGONIZATION-ANALYSIS.md:220 "
        "(`python analyze_overpoly.py`); moving would break the "
        "archive's reproducibility instruction — archive is frozen "
        "per CLAUDE.md §1 hard rule"
    ),
    "crop_legend.py": (
        "historical baseline per docs/ops/repo_hygiene_audit_2026-05-10.md §60; "
        "deferred until raster-pipeline-retirement OR maintainer "
        "confirms 'not used manually'"
    ),
    "peek_pdf.py": (
        "debug aid per docs/ops/repo_hygiene_audit_2026-05-10.md §61; "
        "same trigger as crop_legend.py"
    ),
    "make_test_pdf.py": (
        "active fixture builder per "
        "docs/ops/repo_hygiene_audit_2026-05-10.md §211 ('mantém'); "
        "generates inviolable canonical test_plan.pdf — no removal "
        "trigger exists"
    ),
    "preprocess_walls.py": (
        "generates inviolable planta_74_mask.png per "
        "docs/ops/repo_hygiene_audit_2026-05-10.md §92; deferred until "
        "raster-pipeline-officially-retired trigger fires"
    ),
}

# Loose data extensions banned from repo root (W005).
LOOSE_DATA_AT_ROOT_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".svg",
                                ".skp", ".json", ".yaml", ".yml")

# Canonical root files exempt from W005 (pre-policy historical files).
ROOT_DATA_ALLOWED = frozenset({
    "planta_74.pdf", "planta_74_clean.pdf", "planta_74_mask.png",
    "test_plan.pdf",
})

# Structural diff trigger for E006 (PR mode).
STRUCTURAL_DIFF_PREFIXES = (
    "tools/", "tests/", "fixtures/", "ground_truth/",
    "docs/specs/", "docs/adr/",
    ".github/workflows/",
    "scripts/", "patches/",
)
STRUCTURAL_DIFF_EXEMPT_PATHS = frozenset({
    "docs/PROJECT_STATE.md",
    "docs/HANDOFF.md",
    "docs/REPO_HYGIENE.md",
    "docs/GATES.md",
    "docs/ANTI_FORGETTING.md",
})

# Obvious .gitignore patterns to ensure are present (I001 / F-GITIGNORE).
EXPECTED_GITIGNORE_PATTERNS = (
    "__pycache__/", "*.py[cod]", ".pytest_cache/", ".ruff_cache/",
    ".mypy_cache/", ".venv/", "*.log", ".DS_Store", "Thumbs.db",
    ".tmp_*", "*.bak", "*.swp", "*.orig",
)

# ---- Domain types ---------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """A single repository-hygiene finding produced by a detector."""

    code: str            # e.g. "E001"
    severity: str        # "error" | "warning" | "info"
    category: str        # short tag, e.g. "tracked-generated"
    path: str            # repo-relative path or "" if global
    message: str
    fix_action: str | None = None        # description of safe fix; None if not auto-fixable
    references: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FixOutcome:
    """One safe-fix application."""

    fix_id: str
    description: str
    succeeded: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---- git helpers (subprocess) --------------------------------------------


def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=check,
    )


def _tracked_files() -> list[str]:
    proc = _git("ls-files")
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _diff_added_files(base: str) -> list[str]:
    """Files added (status A or R or C) between base and HEAD."""
    proc = _git("diff", "--name-status", f"{base}...HEAD")
    if proc.returncode != 0:
        return []
    added: list[str] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        if status.startswith("A") or status.startswith("R") or status.startswith("C"):
            added.append(parts[-1])
    return added


def _diff_changed_files(base: str) -> list[str]:
    """Every file appearing in the diff (any status)."""
    proc = _git("diff", "--name-only", f"{base}...HEAD")
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _git_head() -> str:
    proc = _git("rev-parse", "--short", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _git_branch() -> str:
    proc = _git("rev-parse", "--abbrev-ref", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


# ---- Detectors ------------------------------------------------------------


def _matches_any_glob(name: str, globs: Iterable[str]) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(name, g) for g in globs)


def detect_tmp_file_tracked(tracked: list[str]) -> list[Finding]:
    """E001 — tmp / backup files tracked in git."""
    out: list[Finding] = []
    for rel in tracked:
        name = Path(rel).name
        if _matches_any_glob(name, TMP_FILE_GLOBS):
            out.append(Finding(
                code="E001",
                severity="error",
                category="tmp-file-tracked",
                path=rel,
                message=(
                    f"temporary/backup file is tracked: {rel}. "
                    "These should never be committed."
                ),
                fix_action=(
                    "untrack with `git rm --cached <file>` and add the "
                    "pattern to .gitignore"
                ),
            ))
    return out


def _generated_allowed(rel: str) -> bool:
    if rel in GENERATED_ALLOWED_EXACT:
        return True
    rel_posix = rel.replace("\\", "/")
    return any(rel_posix.startswith(pfx) for pfx in GENERATED_ALLOWED_PREFIXES)


def detect_generated_outside_allowed(tracked: list[str]) -> list[Finding]:
    """E002 — generated-looking artifacts tracked outside allowed paths."""
    out: list[Finding] = []
    for rel in tracked:
        rel_lower = rel.lower()
        if not rel_lower.endswith(GENERATED_SUFFIXES):
            continue
        if _generated_allowed(rel):
            continue
        out.append(Finding(
            code="E002",
            severity="error",
            category="tracked-generated",
            path=rel,
            message=(
                f"generated-looking artifact tracked outside the allowed "
                f"paths: {rel}. Allowed prefixes: "
                f"{', '.join(GENERATED_ALLOWED_PREFIXES[:5])}, ..."
            ),
            fix_action=None,
        ))
    return out


def detect_heavy_file(tracked: list[str]) -> list[Finding]:
    """E005 — file > 5MB tracked outside vendor/, fixtures/, docs/specs/_assets/."""
    out: list[Finding] = []
    allowed_prefixes = ("vendor/", "fixtures/", "docs/specs/_assets/",
                         "ground_truth/", "tests/baselines/")
    for rel in tracked:
        full = REPO_ROOT / rel
        try:
            size = full.stat().st_size
        except OSError:
            continue
        if size < HEAVY_FILE_THRESHOLD:
            continue
        rel_posix = rel.replace("\\", "/")
        if any(rel_posix.startswith(pfx) for pfx in allowed_prefixes):
            continue
        out.append(Finding(
            code="E005",
            severity="error",
            category="heavy-file",
            path=rel,
            message=(
                f"file is {size / 1024 / 1024:.1f} MB and tracked outside "
                f"the canonical heavy-file paths. If this is a fixture, "
                f"move under fixtures/; if vendor, under vendor/; "
                f"otherwise gitignore it."
            ),
            fix_action=None,
        ))
    return out


def _md_has_status_header(rel: str) -> bool:
    full = REPO_ROOT / rel
    if not full.is_file():
        return False
    try:
        with full.open(encoding="utf-8", errors="replace") as fh:
            head = "".join([next(fh, "") for _ in range(40)])
    except OSError:
        return False
    return bool(STATUS_HEADER_RE.search(head))


def detect_md_missing_status(tracked: list[str], *, only_paths: set[str] | None = None) -> list[Finding]:
    """W002 / E004 — .md files without Status: header.

    only_paths: when set (PR mode), restrict to that subset.
    Severity is "warning" for existing files; promote to "error" if
    the file is new in the PR (caller handles severity promotion).
    """
    out: list[Finding] = []
    candidates = (set(tracked) & only_paths) if only_paths is not None else set(tracked)
    for rel in sorted(candidates):
        if not rel.endswith(".md"):
            continue
        rel_posix = rel.replace("\\", "/")
        # W002 targets project policy docs: docs/ + root.
        # .ai_bridge/, .claude/, agents/, .github/ have their own
        # session/agent conventions and are NOT the REPO_HYGIENE.md §2
        # target.
        if not (rel_posix.startswith("docs/") or "/" not in rel):
            continue
        # Skip the _archive subtree — those are pre-policy historical
        # files; the don't-delete-blindly protocol covers them.
        if rel_posix.startswith("docs/_archive/"):
            continue
        # Root README/CHANGELOG and known root .md are exempt.
        if "/" not in rel and rel in ROOT_MD_EXEMPT:
            continue
        # README.md at any depth is exempt per REPO_HYGIENE.md §2.
        if Path(rel).name == "README.md":
            continue
        if _md_has_status_header(rel):
            continue
        out.append(Finding(
            code="W002",
            severity="warning",
            category="md-no-status",
            path=rel,
            message=(
                f"{rel} has no `Status:` header (docs/REPO_HYGIENE.md §2). "
                "Add Canonical / Active / Archived / Generated / Delete "
                "candidate when next touched."
            ),
            fix_action=None,
        ))
    return out


def detect_loose_script_root(tracked: list[str]) -> list[Finding]:
    """W001 — *.py files at repo root other than main.py.

    Skips files in ROOT_PY_KEEP_AT_ROOT (those get I003 via
    `detect_intentional_root_script` instead).
    """
    out: list[Finding] = []
    for rel in tracked:
        if "/" in rel or "\\" in rel:
            continue
        if not rel.endswith(".py"):
            continue
        if rel in ROOT_PY_ALLOWED:
            continue
        if rel in ROOT_PY_KEEP_AT_ROOT:
            # Intentional — covered by I003 below.
            continue
        out.append(Finding(
            code="W001",
            severity="warning",
            category="loose-script-root",
            path=rel,
            message=(
                f"script {rel} lives at repo root. Move under tools/ "
                f"(active) or tools/legacy/ (historical) when next "
                "touched. Don't auto-move — verify references first."
            ),
            fix_action=None,
        ))
    return out


def detect_intentional_root_script(tracked: list[str]) -> list[Finding]:
    """I003 — root-level *.py files explicitly kept at root with a
    documented reason (ROOT_PY_KEEP_AT_ROOT).

    Surfaces each keeper as an INFO finding so the decision stays
    visible in every audit report. Promote out only when the cited
    trigger fires.
    """
    out: list[Finding] = []
    tracked_set = set(tracked)
    for name, reason in sorted(ROOT_PY_KEEP_AT_ROOT.items()):
        if name not in tracked_set:
            # File is no longer in the index (already moved/deleted);
            # the allowlist entry is stale. Surface as INFO so we
            # remember to prune the entry.
            out.append(Finding(
                code="I003",
                severity="info",
                category="stale-keep-at-root-entry",
                path=name,
                message=(
                    f"`{name}` is in ROOT_PY_KEEP_AT_ROOT allowlist but "
                    "no longer tracked — remove the entry from "
                    "tools/repo_health_gate.py."
                ),
                fix_action=(
                    "remove the corresponding key from "
                    "ROOT_PY_KEEP_AT_ROOT in tools/repo_health_gate.py"
                ),
            ))
            continue
        out.append(Finding(
            code="I003",
            severity="info",
            category="intentional-root-script",
            path=name,
            message=f"kept at root: {reason}",
            fix_action=None,
        ))
    return out


def detect_loose_data_root(tracked: list[str]) -> list[Finding]:
    """W005 — data files at root not in the canonical allow-list."""
    out: list[Finding] = []
    for rel in tracked:
        if "/" in rel or "\\" in rel:
            continue
        if not rel.lower().endswith(LOOSE_DATA_AT_ROOT_SUFFIXES):
            continue
        if rel in ROOT_DATA_ALLOWED:
            continue
        # Whitelisted config files
        if rel in {"pyproject.toml", "requirements.txt", "Gemfile.lint",
                    ".mcp.json", ".env.example", ".rubocop.yml", ".gitignore"}:
            continue
        out.append(Finding(
            code="W005",
            severity="warning",
            category="loose-data-root",
            path=rel,
            message=(
                f"data file {rel} lives at repo root. Consider moving "
                "to fixtures/ (canonical) or docs/specs/_assets/ "
                "(promoted reference)."
            ),
            fix_action=None,
        ))
    return out


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_duplicate_fixture(tracked: list[str]) -> list[Finding]:
    """W003 — identical content at two fixture/ground_truth paths."""
    fixture_files = [rel for rel in tracked
                     if rel.startswith(("fixtures/", "ground_truth/"))
                     and (REPO_ROOT / rel).is_file()]
    sha_index: dict[str, list[str]] = {}
    for rel in fixture_files:
        try:
            digest = _sha256(REPO_ROOT / rel)
        except OSError:
            continue
        sha_index.setdefault(digest, []).append(rel)
    out: list[Finding] = []
    for digest, paths in sha_index.items():
        if len(paths) <= 1:
            continue
        for rel in paths[1:]:
            out.append(Finding(
                code="W003",
                severity="warning",
                category="duplicate-fixture",
                path=rel,
                message=(
                    f"fixture content sha256={digest[:12]} duplicated. "
                    f"Canonical copy: {paths[0]}. Keep one or justify "
                    "the duplication in a comment."
                ),
                references=[paths[0]],
            ))
    return out


def detect_old_report_in_current(tracked: list[str]) -> list[Finding]:
    """W004 — reports/current/*.md older than OLD_REPORT_DAYS."""
    out: list[Finding] = []
    cutoff = _dt.datetime.now() - _dt.timedelta(days=OLD_REPORT_DAYS)
    for rel in tracked:
        rel_posix = rel.replace("\\", "/")
        if not rel_posix.startswith("reports/current/"):
            continue
        full = REPO_ROOT / rel
        try:
            mtime = _dt.datetime.fromtimestamp(full.stat().st_mtime)
        except OSError:
            continue
        if mtime > cutoff:
            continue
        out.append(Finding(
            code="W004",
            severity="warning",
            category="old-report",
            path=rel,
            message=(
                f"{rel} is {(_dt.datetime.now() - mtime).days} days old. "
                "Move to reports/archive/YYYY-MM/."
            ),
            fix_action=(
                f"move to reports/archive/{mtime.strftime('%Y-%m')}/"
                f"{Path(rel).name}"
            ),
        ))
    return out


def detect_gitignore_missing() -> list[Finding]:
    """I001 — expected patterns missing from .gitignore."""
    gi = REPO_ROOT / ".gitignore"
    if not gi.is_file():
        return [Finding(
            code="I001",
            severity="info",
            category="gitignore-missing",
            path=".gitignore",
            message=".gitignore is missing entirely.",
            fix_action="create .gitignore with the expected pattern list",
        )]
    existing = gi.read_text(encoding="utf-8", errors="replace")
    missing = [pat for pat in EXPECTED_GITIGNORE_PATTERNS
               if pat not in existing]
    return [Finding(
        code="I001",
        severity="info",
        category="gitignore-missing",
        path=".gitignore",
        message=f".gitignore is missing expected pattern: {pat}",
        fix_action=f"append `{pat}` to .gitignore",
    ) for pat in missing]


def detect_new_dir_not_canonical(diff_added: list[str]) -> list[Finding]:
    """E003 — new top-level dir in PR diff that is not canonical."""
    out: list[Finding] = []
    new_top_level: set[str] = set()
    for rel in diff_added:
        parts = rel.replace("\\", "/").split("/")
        if len(parts) >= 2:
            new_top_level.add(parts[0])
    for top in sorted(new_top_level):
        if top in CANONICAL_TOP_LEVEL_DIRS:
            continue
        if top.startswith("."):
            # hidden dirs we may not have listed — info, not error
            out.append(Finding(
                code="E003",
                severity="warning",
                category="new-dir-not-canonical",
                path=top + "/",
                message=(
                    f"PR introduces hidden top-level dir `{top}/`. "
                    "Verify it belongs in CANONICAL_TOP_LEVEL_DIRS "
                    "(tools/repo_health_gate.py)."
                ),
            ))
        else:
            out.append(Finding(
                code="E003",
                severity="error",
                category="new-dir-not-canonical",
                path=top + "/",
                message=(
                    f"PR introduces new top-level dir `{top}/` not in "
                    "the canonical set. Either justify the new category "
                    "in docs/REPO_HYGIENE.md and add to "
                    "CANONICAL_TOP_LEVEL_DIRS, or move content under an "
                    "existing canonical dir."
                ),
            ))
    return out


def detect_project_state_stale(diff_files: list[str]) -> list[Finding]:
    """E006 — structural diff but state docs not in diff."""
    structural = [rel for rel in diff_files
                  if any(rel.replace("\\", "/").startswith(pfx)
                          for pfx in STRUCTURAL_DIFF_PREFIXES)]
    if not structural:
        return []
    diff_set = set(rel.replace("\\", "/") for rel in diff_files)
    if STRUCTURAL_DIFF_EXEMPT_PATHS & diff_set:
        return []
    return [Finding(
        code="E006",
        severity="error",
        category="project-state-stale",
        path="docs/PROJECT_STATE.md",
        message=(
            f"PR touches {len(structural)} structural file(s) under "
            f"{', '.join(sorted({p.split('/')[0] + '/' for p in structural}))} "
            "but neither docs/PROJECT_STATE.md nor docs/HANDOFF.md is "
            "in the diff. Update at least one (or one of the exempt "
            "canonical docs) to reflect the change."
        ),
        references=structural[:10],
    )]


def detect_archived_wrong_location(tracked: list[str]) -> list[Finding]:
    """I002 — Status: Archived doc not under docs/_archive/."""
    out: list[Finding] = []
    for rel in tracked:
        if not rel.endswith(".md"):
            continue
        rel_posix = rel.replace("\\", "/")
        if rel_posix.startswith("docs/_archive/"):
            continue
        full = REPO_ROOT / rel
        try:
            head = "".join(full.read_text(encoding="utf-8",
                                            errors="replace").splitlines(keepends=True)[:30])
        except OSError:
            continue
        if "Status:" not in head or "Archived" not in head:
            continue
        out.append(Finding(
            code="I002",
            severity="info",
            category="archived-wrong-location",
            path=rel,
            message=(
                f"{rel} declares Status: Archived but is not under "
                "docs/_archive/. Move it (with the explicit `git mv`) "
                "to a date-scoped archive subdir."
            ),
            fix_action=None,
        ))
    return out


# ---- Safe fixes (mode=fix only) -------------------------------------------


def apply_old_report_archive(findings: list[Finding], *, dry_run: bool) -> list[FixOutcome]:
    out: list[FixOutcome] = []
    for f in findings:
        if f.code != "W004" or not f.fix_action:
            continue
        src = REPO_ROOT / f.path
        if not src.is_file():
            continue
        try:
            mtime = _dt.datetime.fromtimestamp(src.stat().st_mtime)
        except OSError as exc:
            out.append(FixOutcome(
                fix_id="F-OLD-REPORT", description=f.fix_action,
                succeeded=False, detail=f"stat failed: {exc}",
            ))
            continue
        dest_dir = REPO_ROOT / "reports" / "archive" / mtime.strftime("%Y-%m")
        dest = dest_dir / src.name
        if dry_run:
            out.append(FixOutcome(
                fix_id="F-OLD-REPORT",
                description=f"would move {f.path} -> {dest.relative_to(REPO_ROOT)}",
                succeeded=True,
            ))
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            src.rename(dest)
        except OSError as exc:
            out.append(FixOutcome(
                fix_id="F-OLD-REPORT", description=f.fix_action,
                succeeded=False, detail=str(exc),
            ))
            continue
        out.append(FixOutcome(
            fix_id="F-OLD-REPORT",
            description=f"moved {f.path} -> {dest.relative_to(REPO_ROOT)}",
            succeeded=True,
        ))
    return out


def apply_gitignore_append(findings: list[Finding], *, dry_run: bool) -> list[FixOutcome]:
    missing = [f for f in findings if f.code == "I001"
               and f.fix_action and f.fix_action.startswith("append")]
    if not missing:
        return []
    gi = REPO_ROOT / ".gitignore"
    appended: list[str] = []
    for f in missing:
        # parse fix_action "append `pat` to .gitignore"
        m = re.search(r"`([^`]+)`", f.fix_action or "")
        if not m:
            continue
        appended.append(m.group(1))
    if not appended:
        return []
    if dry_run:
        return [FixOutcome(
            fix_id="F-GITIGNORE",
            description=f"would append {len(appended)} pattern(s) to .gitignore: {', '.join(appended)}",
            succeeded=True,
        )]
    try:
        existing = gi.read_text(encoding="utf-8") if gi.is_file() else ""
        sep = "\n" if existing and not existing.endswith("\n") else ""
        block = (
            f"{sep}# Added by tools/repo_health_gate.py --mode fix on "
            f"{_dt.date.today().isoformat()}\n"
            + "\n".join(appended) + "\n"
        )
        gi.write_text(existing + block, encoding="utf-8")
    except OSError as exc:
        return [FixOutcome(
            fix_id="F-GITIGNORE", description="append patterns",
            succeeded=False, detail=str(exc),
        )]
    return [FixOutcome(
        fix_id="F-GITIGNORE",
        description=f"appended to .gitignore: {', '.join(appended)}",
        succeeded=True,
    )]


def apply_tmp_workdir_cleanup(*, dry_run: bool) -> list[FixOutcome]:
    """F-TMP-WORKDIR — remove untracked tmp files in working tree only.

    NEVER touches tracked files. The tracked-tmp-file finding (E001) is
    handled by the human via `git rm --cached`.
    """
    out: list[FixOutcome] = []
    tracked = set(_tracked_files())
    candidates: list[Path] = []
    for root, dirs, files in os.walk(REPO_ROOT):
        # Skip vendored / virtualenv / .git
        rel_root = Path(root).relative_to(REPO_ROOT).as_posix()
        if (rel_root.startswith((".git", ".venv", "vendor", "node_modules",
                                  "__pycache__", ".pytest_cache",
                                  ".ruff_cache"))):
            dirs[:] = []
            continue
        for name in files:
            if not _matches_any_glob(name, TMP_FILE_GLOBS):
                continue
            full = Path(root) / name
            rel = full.relative_to(REPO_ROOT).as_posix()
            if rel in tracked:
                continue
            candidates.append(full)
    for c in candidates:
        rel = c.relative_to(REPO_ROOT).as_posix()
        if dry_run:
            out.append(FixOutcome(
                fix_id="F-TMP-WORKDIR",
                description=f"would remove untracked tmp file {rel}",
                succeeded=True,
            ))
            continue
        try:
            c.unlink()
            out.append(FixOutcome(
                fix_id="F-TMP-WORKDIR",
                description=f"removed untracked tmp file {rel}",
                succeeded=True,
            ))
        except OSError as exc:
            out.append(FixOutcome(
                fix_id="F-TMP-WORKDIR",
                description=f"remove untracked tmp file {rel}",
                succeeded=False, detail=str(exc),
            ))
    return out


# ---- Orchestration --------------------------------------------------------


def collect_findings(*, base: str | None) -> list[Finding]:
    """Run every detector. Return all findings, sorted by severity then code."""
    tracked = _tracked_files()
    findings: list[Finding] = []

    findings.extend(detect_tmp_file_tracked(tracked))
    findings.extend(detect_generated_outside_allowed(tracked))
    findings.extend(detect_heavy_file(tracked))
    findings.extend(detect_loose_script_root(tracked))
    findings.extend(detect_intentional_root_script(tracked))
    findings.extend(detect_loose_data_root(tracked))
    findings.extend(detect_md_missing_status(tracked))
    findings.extend(detect_duplicate_fixture(tracked))
    findings.extend(detect_old_report_in_current(tracked))
    findings.extend(detect_gitignore_missing())
    findings.extend(detect_archived_wrong_location(tracked))

    if base:
        diff_added = _diff_added_files(base)
        diff_changed = _diff_changed_files(base)
        findings.extend(detect_new_dir_not_canonical(diff_added))
        findings.extend(detect_project_state_stale(diff_changed))
        # Promote W002 -> E004 for .md files that are NEW in this PR.
        added_set = set(diff_added)
        promoted: list[Finding] = []
        for f in findings:
            if f.code == "W002" and f.path in added_set:
                promoted.append(Finding(
                    code="E004",
                    severity="error",
                    category=f.category,
                    path=f.path,
                    message=(f.message + " (new in PR — must be set "
                              "before merge)"),
                    fix_action=f.fix_action,
                    references=f.references,
                ))
            else:
                promoted.append(f)
        findings = promoted

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: (severity_rank.get(f.severity, 9), f.code, f.path))
    return findings


# ---- Output formatters ----------------------------------------------------


def format_text(findings: list[Finding], *, base: str | None) -> str:
    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")
    lines = [
        "repo_health_gate",
        "================",
        f"branch: {_git_branch()}  head: {_git_head()}  base: {base or '(none)'}",
        f"ERROR: {n_err}  WARNING: {n_warn}  INFO: {n_info}",
        "",
    ]
    for sev in ("error", "warning", "info"):
        bucket = [f for f in findings if f.severity == sev]
        if not bucket:
            continue
        lines.append(f"-- {sev.upper()} ({len(bucket)}) --")
        for f in bucket:
            lines.append(f"  [{f.code}] {f.path}")
            for line in f.message.splitlines():
                lines.append(f"        {line}")
            if f.fix_action:
                lines.append(f"        fix: {f.fix_action}")
            for ref in f.references[:3]:
                lines.append(f"        ref: {ref}")
        lines.append("")
    if not findings:
        lines.append("All detectors clean.")
    return "\n".join(lines)


def format_markdown_report(findings: list[Finding], *, base: str | None,
                            fixes: list[FixOutcome] | None = None) -> str:
    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_info = sum(1 for f in findings if f.severity == "info")
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# Repo Health Report",
        "",
        "> **Status:** Generated (do not edit). Produced by "
        "`tools/repo_health_gate.py`.",
        f"> **Generated:** {now}",
        f"> **Branch:** {_git_branch()}",
        f"> **Commit:** {_git_head()}",
        f"> **Base (--base):** {base or '(none)'}",
        "",
        "## Summary",
        "",
        "| Severity | Count |",
        "|---|---|",
        f"| error   | {n_err}  |",
        f"| warning | {n_warn} |",
        f"| info    | {n_info} |",
        "",
    ]

    for sev_label, sev_key in (("Errors", "error"),
                                 ("Warnings", "warning"),
                                 ("Info", "info")):
        bucket = [f for f in findings if f.severity == sev_key]
        if not bucket:
            continue
        lines.append(f"## {sev_label}")
        lines.append("")
        lines.append("| Code | Category | File | Message | Auto-fix? |")
        lines.append("|---|---|---|---|---|")
        for f in bucket:
            msg = f.message.replace("|", "\\|").replace("\n", " ")
            auto = "yes" if f.fix_action else "no"
            lines.append(f"| {f.code} | {f.category} | `{f.path}` | {msg} | {auto} |")
        lines.append("")

    auto_fixable = [f for f in findings if f.fix_action]
    if auto_fixable:
        lines.append("## What `--mode fix` would do (preview)")
        lines.append("")
        for f in auto_fixable:
            lines.append(f"- [{f.code}] {f.path}: {f.fix_action}")
        lines.append("")

    manual = [f for f in findings if not f.fix_action and f.severity in ("error", "warning")]
    if manual:
        lines.append("## Requires human decision")
        lines.append("")
        for f in manual:
            lines.append(f"- [{f.code}] `{f.path}` — {f.message.splitlines()[0]}")
        lines.append("")

    if fixes is not None:
        lines.append("## Fix actions applied this run")
        lines.append("")
        if not fixes:
            lines.append("_no safe fixes applied_")
        else:
            for fx in fixes:
                tag = "OK" if fx.succeeded else "FAIL"
                detail = f" — {fx.detail}" if fx.detail else ""
                lines.append(f"- [{fx.fix_id}] {tag}: {fx.description}{detail}")
        lines.append("")

    lines.append("## How to act")
    lines.append("")
    lines.append("- `python tools/repo_health_gate.py --mode audit` "
                  "(read-only, default).")
    lines.append("- `python tools/repo_health_gate.py --mode check "
                  "--base origin/develop` (CI / PR gate).")
    lines.append("- `python tools/repo_health_gate.py --mode fix` "
                  "(apply the conservative safe-fix list only).")
    lines.append("- Manual cleanup: follow `docs/REPO_HYGIENE.md` §3 "
                  "(don't-delete-blindly protocol).")
    lines.append("")
    lines.append("## References")
    lines.append("")
    lines.append("- [`../REPO_HYGIENE.md`](../../docs/REPO_HYGIENE.md) — policy")
    lines.append("- [`../GATES.md`](../../docs/GATES.md) — gate catalogue")
    lines.append("- [`../../CLAUDE.md`](../../CLAUDE.md) §15 — manual hygiene loop")
    lines.append("")
    return "\n".join(lines)


def write_report(content: str, report_path: str) -> str:
    p = Path(report_path)
    full = p if p.is_absolute() else REPO_ROOT / p
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    try:
        return str(full.relative_to(REPO_ROOT))
    except ValueError:
        return str(full)


# ---- CLI ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mode", choices=("audit", "check", "fix"),
                        default="audit",
                        help="audit (default): always exit 0. "
                              "check: exit 1 on errors. "
                              "fix: apply safe fixes only.")
    parser.add_argument("--base", default=None,
                        help="Reference for PR-diff mode (e.g. origin/develop). "
                              "Only NEW violations vs this base are counted as errors.")
    parser.add_argument("--strict", action="store_true",
                        help="check mode: also exit 1 on any warning.")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON to stdout.")
    parser.add_argument("--no-report", action="store_true",
                        help="skip writing the markdown report.")
    parser.add_argument("--report-path", default=REPORT_PATH_DEFAULT,
                        help=f"markdown report destination (default "
                              f"{REPORT_PATH_DEFAULT}).")
    parser.add_argument("--dry-run", action="store_true",
                        help="fix mode: show what would be done without "
                              "applying.")
    args = parser.parse_args(argv)

    findings = collect_findings(base=args.base)

    fixes: list[FixOutcome] | None = None
    if args.mode == "fix":
        fixes = []
        fixes.extend(apply_old_report_archive(findings, dry_run=args.dry_run))
        fixes.extend(apply_gitignore_append(findings, dry_run=args.dry_run))
        fixes.extend(apply_tmp_workdir_cleanup(dry_run=args.dry_run))

    if args.json:
        payload = {
            "branch": _git_branch(),
            "head": _git_head(),
            "base": args.base,
            "mode": args.mode,
            "summary": {
                "error": sum(1 for f in findings if f.severity == "error"),
                "warning": sum(1 for f in findings if f.severity == "warning"),
                "info": sum(1 for f in findings if f.severity == "info"),
            },
            "findings": [f.to_dict() for f in findings],
            "fixes": [fx.to_dict() for fx in (fixes or [])],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_text(findings, base=args.base))
        if fixes:
            print()
            print("-- FIX ACTIONS --")
            for fx in fixes:
                tag = "OK  " if fx.succeeded else "FAIL"
                detail = f" — {fx.detail}" if fx.detail else ""
                print(f"  [{fx.fix_id}] {tag} {fx.description}{detail}")

    if not args.no_report:
        report_md = format_markdown_report(findings, base=args.base, fixes=fixes)
        rel = write_report(report_md, args.report_path)
        if not args.json:
            print(f"\nreport: {rel}")

    if args.mode == "check":
        n_err = sum(1 for f in findings if f.severity == "error")
        n_warn = sum(1 for f in findings if f.severity == "warning")
        if n_err:
            return 1
        if args.strict and n_warn:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
