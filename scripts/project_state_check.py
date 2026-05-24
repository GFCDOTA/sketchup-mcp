#!/usr/bin/env python
"""Project state hygiene gate.

Verifies that the repo contains the canonical documents, fixtures, and
gate scripts that PROJECT_STATE.md, HANDOFF.md, GATES.md, and
ANTI_FORGETTING.md depend on. Exit 0 when all hard requirements pass.
Exit 1 with a human-readable report otherwise.

This gate is intentionally cheap (< 2 s, no imports beyond stdlib +
filesystem). Run on every cycle (locally + CI) per
docs/HANDOFF.md §6 and docs/GATES.md G-PROJECT-STATE.

Usage:
    python scripts/project_state_check.py
    python scripts/project_state_check.py --json       # machine output
    python scripts/project_state_check.py --strict     # warnings become errors

Schema of the JSON output (--json):
    {
      "ok": bool,
      "summary": {"hard_pass": int, "hard_fail": int, "warn": int},
      "checks": [
        {"id": str, "kind": "doc"|"fixture"|"gate"|"script"|"header",
         "path": str, "status": "PASS"|"FAIL"|"WARN", "reason": str}
      ]
    }
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List

# Repository root is the parent of this script's parent (scripts/ -> repo).
REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Check:
    """A single state-check item."""

    id: str
    kind: str  # "doc" | "fixture" | "gate" | "script" | "header"
    path: str
    status: str  # "PASS" | "FAIL" | "WARN"
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


# --- HARD REQUIREMENTS (FAIL exits non-zero) -------------------------------
# Canonical docs that PROJECT_STATE / HANDOFF / GATES / ANTI_FORGETTING
# reference. If any of these is missing, the project state is incoherent.
CANONICAL_DOCS = [
    "CLAUDE.md",
    "README.md",
    "OVERVIEW.md",
    "AGENTS.md",
    "docs/PROJECT_STATE.md",
    "docs/HANDOFF.md",
    "docs/REPO_HYGIENE.md",
    "docs/GATES.md",
    "docs/ANTI_FORGETTING.md",
    "docs/git_workflow.md",
    "docs/adr/README.md",
]

# Canonical fixtures the docs depend on.
# Listed here are fixtures known to live on `develop` (or any clone of it).
# Quadrado fixtures live on `feature/window-aperture-semantics` and are
# tracked as SOFT_FIXTURES below until the feature merges.
CANONICAL_FIXTURES = [
    "fixtures/planta_74/human_openings_truth.json",
    "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
    "ground_truth/planta_74/expected_model.json",
    "ground_truth/planta_74_micro.json",
    "planta_74.pdf",
    "docs/specs/quadrado_demo_spec.md",
]

# Scripts / CI workflows the gates depend on.
CANONICAL_SCRIPTS = [
    "scripts/smoke/smoke_skp_export.py",
    "scripts/project_state_check.py",
    "tools/build_plan_shell_skp.py",
    "tools/coherence_audit.py",
    "tools/micro_truth_gate.py",
    "tools/fidelity/compare_generated_to_expected.py",
    ".github/workflows/ci.yml",
    ".github/workflows/quality_gates.yml",
]

# --- SOFT REQUIREMENTS (WARN, only fail under --strict) --------------------
# Tests + fixtures + reference outputs that live on
# `feature/window-aperture-semantics` as of 2026-05-24. Flagged WARN
# until the feature merges into develop, at which point they should be
# promoted to CANONICAL_FIXTURES / SOFT removed.
SOFT_TESTS = [
    "tests/test_quadrado_canonical_smoke.py",
    "tests/test_wall_shell_canonical.py",
    "tests/test_window_aperture_contract.py",
    "tests/test_window_aperture_geometry.py",
]

SOFT_FIXTURES = [
    "fixtures/quadrado/consensus_with_window.json",
    "fixtures/quadrado/consensus_empty.json",
]

# Canonical reference outputs (promoted artefacts).
SOFT_ASSETS = [
    "docs/specs/_assets/quadrado_canonical_shell_polygon.json",
    "docs/specs/_assets/quadrado_canonical_geometry_report.json",
    "docs/specs/_assets/quadrado_canonical_success_render.png",
]

# Docs that MUST carry a Status: header per docs/REPO_HYGIENE.md §2.
STATUS_REQUIRED_DOCS = [
    "docs/PROJECT_STATE.md",
    "docs/HANDOFF.md",
    "docs/REPO_HYGIENE.md",
    "docs/GATES.md",
    "docs/ANTI_FORGETTING.md",
]


def _exists_nonempty(rel_path: str) -> bool:
    """File exists and is non-empty."""
    p = REPO_ROOT / rel_path
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def _has_status_header(rel_path: str) -> bool:
    """File's first ~30 lines contain a `Status:` marker per the policy."""
    p = REPO_ROOT / rel_path
    if not p.is_file():
        return False
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            head = "".join([next(fh, "") for _ in range(30)])
    except OSError:
        return False
    return "Status:" in head


def _check_hard(paths: Iterable[str], kind: str) -> List[Check]:
    out: List[Check] = []
    for rel in paths:
        if _exists_nonempty(rel):
            out.append(
                Check(
                    id=f"{kind}:{rel}",
                    kind=kind,
                    path=rel,
                    status="PASS",
                    reason="present",
                )
            )
        else:
            out.append(
                Check(
                    id=f"{kind}:{rel}",
                    kind=kind,
                    path=rel,
                    status="FAIL",
                    reason="missing or empty (hard requirement)",
                )
            )
    return out


def _check_soft(paths: Iterable[str], kind: str, strict: bool) -> List[Check]:
    out: List[Check] = []
    for rel in paths:
        if _exists_nonempty(rel):
            out.append(
                Check(
                    id=f"{kind}:{rel}",
                    kind=kind,
                    path=rel,
                    status="PASS",
                    reason="present",
                )
            )
        else:
            status = "FAIL" if strict else "WARN"
            note = (
                "missing or empty (soft requirement - may live on a feature branch)"
            )
            out.append(
                Check(
                    id=f"{kind}:{rel}",
                    kind=kind,
                    path=rel,
                    status=status,
                    reason=note,
                )
            )
    return out


def _check_status_headers(paths: Iterable[str]) -> List[Check]:
    out: List[Check] = []
    for rel in paths:
        if not _exists_nonempty(rel):
            # Missing file is already a hard FAIL via _check_hard.
            continue
        if _has_status_header(rel):
            out.append(
                Check(
                    id=f"header:{rel}",
                    kind="header",
                    path=rel,
                    status="PASS",
                    reason="Status: header present",
                )
            )
        else:
            out.append(
                Check(
                    id=f"header:{rel}",
                    kind="header",
                    path=rel,
                    status="FAIL",
                    reason="missing Status: header (docs/REPO_HYGIENE.md §2)",
                )
            )
    return out


def run(strict: bool = False) -> List[Check]:
    """Collect all checks. No side effects."""
    checks: List[Check] = []
    checks.extend(_check_hard(CANONICAL_DOCS, "doc"))
    checks.extend(_check_hard(CANONICAL_FIXTURES, "fixture"))
    checks.extend(_check_hard(CANONICAL_SCRIPTS, "script"))
    checks.extend(_check_soft(SOFT_TESTS, "gate", strict))
    checks.extend(_check_soft(SOFT_FIXTURES, "fixture", strict))
    checks.extend(_check_soft(SOFT_ASSETS, "asset", strict))
    checks.extend(_check_status_headers(STATUS_REQUIRED_DOCS))
    return checks


def _format_text(checks: List[Check]) -> str:
    hard_pass = sum(1 for c in checks if c.status == "PASS")
    hard_fail = sum(1 for c in checks if c.status == "FAIL")
    warn = sum(1 for c in checks if c.status == "WARN")

    lines: List[str] = []
    lines.append("project_state_check")
    lines.append("===================")
    lines.append(
        f"PASS: {hard_pass}  FAIL: {hard_fail}  WARN: {warn}"
    )
    lines.append("")
    if hard_fail:
        lines.append("Hard failures (FAIL):")
        for c in checks:
            if c.status == "FAIL":
                lines.append(f"  [{c.kind:7s}] {c.path}  -- {c.reason}")
        lines.append("")
    if warn:
        lines.append("Warnings (WARN, soft requirements):")
        for c in checks:
            if c.status == "WARN":
                lines.append(f"  [{c.kind:7s}] {c.path}  -- {c.reason}")
        lines.append("")
    if not hard_fail and not warn:
        lines.append("All canonical docs / fixtures / scripts / gates present.")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that the repo contains the canonical docs, fixtures, "
            "and gate scripts that PROJECT_STATE.md depends on."
        )
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON output"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat soft warnings as hard failures",
    )
    args = parser.parse_args(argv)

    checks = run(strict=args.strict)
    hard_fail = any(c.status == "FAIL" for c in checks)

    if args.json:
        summary = {
            "hard_pass": sum(1 for c in checks if c.status == "PASS"),
            "hard_fail": sum(1 for c in checks if c.status == "FAIL"),
            "warn": sum(1 for c in checks if c.status == "WARN"),
        }
        payload = {
            "ok": not hard_fail,
            "summary": summary,
            "checks": [c.to_dict() for c in checks],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_format_text(checks))

    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
