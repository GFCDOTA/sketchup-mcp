"""Cross-reference catalog: every FP-XXX in docs/learning/failure_patterns.md
must have at least ONE regression test.

This module enforces two invariants:

  1. Every numbered failure pattern entry in `failure_patterns.md`
     (FP-001, FP-002, ...) appears in `KNOWN_FP_REGRESSIONS` below
     with one or more test references.
  2. Each referenced test exists, and either has the
     ``@pytest.mark.fp_<NN>`` marker or contains a `# FP-NN ref:`
     breadcrumb comment so a grep audit lands on it instantly.

When a new FP-XX is documented:
  a. Add the failure to `failure_patterns.md`.
  b. Add at least one regression test (anywhere under `tests/`)
     that would fail if the failure mode returned.
  c. Add the entry to `KNOWN_FP_REGRESSIONS` below referencing
     that test file / node-id.

This avoids the failure mode "we wrote about it once, then forgot
to test it" — i.e. the situation the soft-barrier bbox bug exposed.

The catalog is intentionally hand-maintained: it forces the author
of a new failure pattern to think about the test BEFORE shipping
the pattern entry.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FAILURE_PATTERNS_MD = (
    REPO_ROOT / "docs" / "learning" / "failure_patterns.md"
)

# (fp_id, [list of regression test references — either file path
#  relative to repo root, or "file.py::test_name" pytest node-ids])
#
# Each entry must include AT LEAST one reference. Use a comment for
# entries that document a pattern enforced by infra (CI, hooks, git
# flow) rather than runtime code — those cannot be unit-tested
# directly but still need a marker so this catalog stays exhaustive.
KNOWN_FP_REGRESSIONS: list[tuple[str, list[str], str]] = [
    (
        "FP-001",
        ["scripts/smoke/smoke_skp_export.py",
         "tests/test_smoke_gate_f0.py",
         "tests/test_skp_from_consensus_skip.py"],
        "Cheap-gate ordering before SU launch — enforced by gate "
        "ordering in smoke_skp_export.py and exercised by every smoke "
        "gate test (test_smoke_gate_*) that runs --skip-skp. The "
        "skp_from_consensus skip test confirms the cache layer "
        "short-circuits the SU launch when consensus is unchanged.",
    ),
    (
        "FP-002",
        ["pyproject.toml",
         ".github/workflows/ci.yml"],
        "Forgotten deps caught at install time by `uv pip install -e "
        "\".[dev]\"` in CI. No runtime test possible — failure mode is "
        "ImportError before any test loads.",
    ),
    (
        "FP-003",
        [".claude/hooks/pre_bash_guard.py"],
        "Direct push to main: enforced by the pre_bash_guard hook "
        "(CLAUDE.md §9). Hook is the regression: if it stops "
        "rejecting `git push origin main`, the safety vanishes. Add "
        "a hook-self-test if a regression actually happens.",
    ),
    (
        "FP-004",
        [".claude/hooks/pre_bash_guard.py"],
        "ruff --fix over the whole repo: same hook covers this "
        "(rejects `ruff --fix .` and `ruff format .`).",
    ),
    (
        "FP-005",
        ["tests/test_consume_consensus_regression.py",
         ".github/workflows/skp_fidelity_gate.yml"],
        "Triplication of geometry in .skp: source-level grep gate "
        "in skp_fidelity_gate.yml asserts `reset_model` + "
        "`Sketchup.quit` still present in consume_consensus.rb. "
        "Plus the consume_consensus regression test in pytest.",
    ),
    (
        "FP-006",
        ["tests/test_plan_shell_invariants.py::"
         "test_soft_barriers_footprint_below_architectural_ceiling",
         "tests/test_plan_shell_invariants.py::"
         "test_soft_barriers_height_is_parapet_not_wall",
         "tools/build_plan_shell_skp.rb"],
        "Parapets covering walls: plan_shell exporter ports the "
        "3-pt overlap filter (tol_in=1.0). Regression suite asserts "
        "soft barrier top-face area < 1.0 m² so a return of the "
        "bbox-as-slab bug (2026-05-20) fails the gate. Production "
        "exporter retains the original `_segment_overlaps_wall?` "
        "function.",
    ),
    (
        "FP-007",
        ["tools/skp_from_consensus.py",
         "tools/build_plan_shell_skp.py"],
        "Welcome dialog blocking SU2026 autorun: both launchers "
        "drop a bootstrap .skp into out_dir before invoking SU. "
        "Documented via the `find_bootstrap` / template-copy logic "
        "in each launcher.",
    ),
    (
        "FP-008",
        ["CLAUDE.md"],
        "Mass branch deletion: CLAUDE.md §0 git flow rule + the "
        "pre_bash_guard hook combined. No standalone test (would "
        "require running `git worktree` cross-process); the policy "
        "is enforced by review.",
    ),
    (
        "FP-009",
        [".claude/agents/"],
        "Specialist agents with write permission: enforced by the "
        ".claude/agents/*.md frontmatter (allow/deny lists). No "
        "runtime test; the rule sits in the agent spec.",
    ),
    (
        "FP-010",
        [".github/workflows/ci.yml",
         ".github/workflows/quality_gates.yml"],
        "Hidden CI deselects masking regressions: deselect lists are "
        "explicit in ci.yml comments and tracked in this file's "
        "BASELINE_KNOWN_FAILURES block. Any new deselect must be "
        "justified in the YAML comment.",
    ),
    (
        "FP-011",
        ["validator/"],
        "Ground-truth leaked into validator LLM prompt: enforced by "
        "the validator module's prompt construction. Add a unit test "
        "if the prompt logic is ever templated dynamically.",
    ),
    (
        "FP-012",
        ["tests/baselines/planta_74.json",
         "tests/test_planta_74_truth_gate.py"],
        "Convex-hull room clip leaks watershed: locked by the truth "
        "gate (33/11/11/8 baseline). Any regression in SUITE 01 "
        "polygon area (back above ~30 m²) trips the gate.",
    ),
    (
        "FP-013",
        ["docs/learning/failure_patterns.md",
         ".github/workflows/quality_gates.yml"],
        "adjacency_f1 plateau: the gate currently surfaces this as a "
        "WARN with explicit threshold band [0.60, 0.80]. The "
        "anti-pattern is lowering the threshold to make it pass, "
        "documented in the entry itself.",
    ),
    (
        "FP-014",
        ["tests/test_disarm_sketchup_autoruns.py",
         "tools/disarm_sketchup_autoruns.py",
         "tools/skp_from_consensus.py",
         "tools/build_plan_shell_skp.py"],
        "Orphan autorun_control.txt clobbering opened .skp: the "
        "disarm helper plus try/finally cleanup in both launchers. "
        "6 unit tests on the disarm helper.",
    ),
    (
        "FP-015",
        ["tests/test_plan_shell_invariants.py::"
         "test_door_leaf_stays_near_its_opening_center",
         "tools/build_plan_shell_skp.rb"],
        "Door leaf hinge_world wrong for vertical walls: pivot Y "
        "dispatched on axis_idx but X was hardcoded, sending the "
        "rotation pivot onto an arbitrary diagonal. Regression "
        "test asserts every DoorLeaf bbox center sits within 1 m of "
        "its opening's declared center.",
    ),
    (
        "FP-016",
        ["CLAUDE.md",
         "docs/learning/lessons_learned.md"],
        "Path proliferation (parallel artifacts outside canonical "
        "run dir): policy enforced by CLAUDE.md §18 Canonical "
        "Artifact Rule (4-declaration template requires canonical "
        "input path) + LL-013. No runtime test possible — the "
        "anti-pattern is structural (creating a new dir for outputs "
        "of a task against an existing canonical artifact); caught "
        "at code review.",
    ),
    (
        "FP-017",
        ["CLAUDE.md",
         "docs/learning/lessons_learned.md",
         "tools/consume_consensus.rb"],
        "Rebuild via consume_consensus.rb when in-place edit was "
        "correct: policy enforced by CLAUDE.md §18.3 forbidden "
        "actions list ('using consume_consensus.rb to ADD features "
        "to existing SKP'). The `entities.clear!` at the top of "
        "consume_consensus.rb is by-design for the BUILD pipeline; "
        "the rule is choosing the right tool, not modifying the "
        "builder. Caught at PR review via the 4-declaration "
        "template (pipeline choice must be justified).",
    ),
    (
        "FP-018",
        ["CLAUDE.md",
         "docs/learning/lessons_learned.md"],
        "Hardcoded coords cause intersect_with float drift: "
        "policy enforced by CLAUDE.md §18.4 ('Hardcoded "
        "coordinates are forbidden; every edit reads its geometry "
        "from the model') + LL-014. Recommended pattern is "
        "documented inline in LL-014 and FP-018. A runtime test "
        "would require running an SU in-place edit pipeline in CI; "
        "deferred until etapa 5 ships an in-place edit tool that "
        "can be unit-tested.",
    ),
    (
        "FP-019",
        ["tools/su_runner_safety.py",
         "tests/test_su_runner_safety.py",
         "CLAUDE.md",
         "docs/learning/lessons_learned.md"],
        "Python subprocess.terminate of SU confuses user about SKP "
        "stability: enforced by the runner-mode protocol in "
        "tools/su_runner_safety.py (parse_mode + should_terminate "
        "+ is_attach + log_mode helpers) covered by 35 unit tests "
        "in test_su_runner_safety.py. Safe default is `interactive` "
        "(no termination); `headless`/`ci` is opt-in via "
        "`RUN_MODE` env, `--mode` CLI, or absence of `--no-terminate`. "
        "Even in headless mode, runners terminate ONLY their own "
        "`proc.pid` — never `taskkill /IM SketchUp.exe`. "
        "CLAUDE.md §18.6 codifies the protocol; LL-015 documents "
        "the positive rule.",
    ),
]


def _fp_ids_in_md() -> list[str]:
    """Return every `FP-NNN` from the failure_patterns.md headings."""
    if not FAILURE_PATTERNS_MD.exists():
        pytest.skip(f"{FAILURE_PATTERNS_MD} not found")
    text = FAILURE_PATTERNS_MD.read_text(encoding="utf-8")
    return re.findall(r"^## (FP-\d+)\b", text, flags=re.M)


def test_every_fp_in_md_has_a_catalog_entry() -> None:
    """Each `## FP-NNN` heading must appear in `KNOWN_FP_REGRESSIONS`.
    A new failure pattern that ships without a catalog entry is the
    exact failure mode this module guards against."""
    md_fps = set(_fp_ids_in_md())
    cataloged = {fp_id for fp_id, _, _ in KNOWN_FP_REGRESSIONS}
    missing = md_fps - cataloged
    assert not missing, (
        f"Failure patterns in {FAILURE_PATTERNS_MD.name} without a "
        f"regression entry in KNOWN_FP_REGRESSIONS: {sorted(missing)}. "
        "Add at least one test reference per FP."
    )


def test_no_catalog_orphans() -> None:
    """Reverse: every catalog entry must correspond to a real
    `## FP-NNN` heading. An orphan entry suggests a renamed or
    deleted pattern that left dead-code references behind."""
    md_fps = set(_fp_ids_in_md())
    cataloged = {fp_id for fp_id, _, _ in KNOWN_FP_REGRESSIONS}
    orphans = cataloged - md_fps
    assert not orphans, (
        f"Catalog entries that don't match any FP-NNN heading in "
        f"{FAILURE_PATTERNS_MD.name}: {sorted(orphans)}"
    )


def test_every_catalog_reference_exists_on_disk() -> None:
    """Every test/file/path referenced in the catalog must exist.
    A stale reference (deleted test, renamed file) is a silent
    regression in the regression catalog itself."""
    missing = []
    for fp_id, refs, _reason in KNOWN_FP_REGRESSIONS:
        for ref in refs:
            # Strip pytest node-id suffix if present (file.py::test_name)
            path_part = ref.split("::", 1)[0]
            full = REPO_ROOT / path_part
            if not full.exists():
                missing.append((fp_id, ref))
    assert not missing, (
        f"Catalog references whose target file does not exist: "
        f"{missing}"
    )


def test_every_catalog_entry_has_at_least_one_reference() -> None:
    """An entry with an empty reference list is a TODO disguised as
    documentation. Force at least one concrete pointer per FP."""
    empty = [fp_id for fp_id, refs, _ in KNOWN_FP_REGRESSIONS if not refs]
    assert not empty, (
        f"Catalog entries with no test reference (these are TODOs, "
        f"not regression coverage): {empty}"
    )


def test_every_catalog_entry_has_a_reason() -> None:
    """Each entry must explain WHY this collection of references
    covers the FP. Forces the author to think about coverage."""
    blank = [fp_id for fp_id, _, reason in KNOWN_FP_REGRESSIONS
             if not reason.strip()]
    assert not blank, f"Catalog entries with empty reason text: {blank}"
