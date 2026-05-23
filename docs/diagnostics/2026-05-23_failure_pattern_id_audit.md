# Failure-pattern ID audit — 2026-05-23

> Generated alongside `2026-05-23_stack_integrity_report.md` after
> discovering an FP-016 collision between PR #144 (open, targets
> develop) and PR #150 (squash-merged into the SDD stack).
>
> **No renumbering applied** until Felipe approves a strategy.
> This audit only inventories the conflict and proposes a safe
> resolution.

---

## TL;DR

- **`develop` has FP-001 through FP-015**, no gaps, no collisions.
- **PR #144** (targets develop, open since 2026-05-21) introduces
  **FP-016 = "Soft barrier near-miss causing merged floor cell"**.
- **PR #150** (squash-merged into `chore/workflow-and-deps-hardening`
  on 2026-05-23) introduces:
  - **FP-016 = "Path proliferation"** ← **COLLIDES with #144**
  - **FP-017 = "Rebuild via consume_consensus.rb when in-place edit was correct"**
  - **FP-018 = "Hardcoded coords cause intersect_with float drift"**
  - **FP-019 = "Python subprocess.terminate of SU confuses user about SKP stability"**
- The collision must be resolved BEFORE either of these PRs lands
  on develop. Otherwise the second arrival breaks the failure
  pattern regression catalog gate
  (`tests/test_failure_patterns_regression_catalog.py::test_every_fp_in_md_has_a_catalog_entry`).

---

## 1. FP IDs on `develop` (ground truth)

Source: `git show origin/develop:docs/learning/failure_patterns.md`

```
FP-001  Opening SketchUp inside a tight dev loop
FP-002  Forgetting Pillow / matplotlib / scipy in pyproject deps
FP-003  Direct push to main
FP-004  `ruff --fix` over the whole repo
FP-005  Triplication of geometry in .skp
FP-006  Parapets covering walls ("rodapé branco")
FP-007  Welcome dialog blocking SU2026 plugin firing
FP-008  Mass branch deletion losing uncommitted work
FP-009  Specialist agents granted write permission
FP-010  Hidden CI deselects masking real regressions
FP-011  Ground-truth leaked into validator LLM prompt (2026-05-XX)
FP-012  Convex-hull room clip leaks watershed into exterior
FP-013  adjacency_f1 plateau lives upstream in room polygon quality
FP-014  Orphan autorun_control.txt clobbering opened .skp (2026-05-20)
FP-015  Door leaf hinge_world wrong for vertical walls in plan_shell (2026-05-20)
```

**Next free FP ID on develop:** FP-016.

---

## 2. FP IDs in open PRs (per branch HEAD)

### PR #144 (targets develop) — `fix/floor-r001-soft-barrier-buffered-split`

Adds **1 new FP**:

```
FP-016  Soft barrier near-miss does not cross polygon interior,
        causing merged floor cell (2026-05-21)
```

Date in heading: 2026-05-21 (PR opened same day).

### PRs #145 / #146 / #147 / #148 — SDD stack lower half

`docs/learning/failure_patterns.md` on each of these branch HEADs
still ends at **FP-015**. None of these PRs introduce new FPs.

### PR #149 — `chore/workflow-and-deps-hardening` (BEFORE #150 squash)

Same as develop — ends at FP-015 (since #149 itself didn't add
FPs; the additions came from the squashed #150 content).

### PR #150 (MERGED into chore/workflow-and-deps-hardening) — adds 4 new FPs

```
FP-016  Path proliferation: creating parallel artifacts outside
        canonical run dir (2026-05-23)
FP-017  Rebuild via consume_consensus.rb when in-place edit was
        correct (2026-05-23)
FP-018  Hardcoded coordinates cause intersect_with float drift
        (2026-05-23)
FP-019  Python subprocess.terminate of SU confuses user about SKP
        stability (2026-05-23)
```

Note: now lives at the tip of `chore/workflow-and-deps-hardening`
(via squash commit `87c2f4f`).

---

## 3. Collision table

| FP ID | Title (PR #144, develop-direct) | Title (PR #150 squash, stack) | Date #144 | Date #150 |
|---|---|---|---|---|
| **FP-016** | Soft barrier near-miss does not cross polygon interior, causing merged floor cell | Path proliferation: parallel artifacts outside canonical run dir | 2026-05-21 | 2026-05-23 |
| FP-017 | (none) | Rebuild via consume_consensus.rb when in-place edit was correct | — | 2026-05-23 |
| FP-018 | (none) | Hardcoded coords cause intersect_with float drift | — | 2026-05-23 |
| FP-019 | (none) | Python subprocess.terminate of SU confuses user about SKP stability | — | 2026-05-23 |

Only **FP-016** is contested. FP-017/018/019 are unclaimed by
PR #144 but are in the squashed #150 content.

---

## 4. Cross-references in the catalog gate

`tests/test_failure_patterns_regression_catalog.py` is the gate
that enforces "every FP-NNN in failure_patterns.md must have a
catalog entry in `KNOWN_FP_REGRESSIONS`".

### On develop

`KNOWN_FP_REGRESSIONS` ends at FP-015 entry (matching the FP-015
in `failure_patterns.md`).

### On PR #144 head

PR #144 adds the FP-016 entry to `KNOWN_FP_REGRESSIONS` per its
diff (the gate passes on its branch).

### On chore/workflow-and-deps-hardening (post #150 squash)

`KNOWN_FP_REGRESSIONS` has entries for FP-016/017/018/019 pointing
at:
- FP-016 → CLAUDE.md + LL doc
- FP-017 → CLAUDE.md + LL doc + consume_consensus.rb
- FP-018 → CLAUDE.md + LL doc
- FP-019 → tools/su_runner_safety.py + tests/test_su_runner_safety.py + CLAUDE.md + LL doc

The gate passes on this branch too — but the FP-016 title here
contradicts PR #144's title.

### When BOTH eventually merge to develop

The second-arriver gets a 3-way merge conflict on:
- `docs/learning/failure_patterns.md` (two different "## FP-016 — …" headings)
- `tests/test_failure_patterns_regression_catalog.py` (two different FP-016 entries in the catalog list)

Resolution at conflict time is possible but UGLY — better to
pre-empt by renumbering one side now.

---

## 5. Priority claim analysis

Two factors weigh on who keeps FP-016:

1. **First-opened wins** — PR #144 opened **2026-05-21**, PR #150
   opened **2026-05-21** (same day for the PR itself) but its
   FP-016 entry was added in the 2026-05-23 consolidation commit
   `dac78a5`. PR #144 has prior claim on the FP-016 NUMBER for its
   "Soft barrier near-miss" content.

2. **Targets develop directly** — PR #144 → develop direct. PR
   #150 → stack (5 PRs deep). PR #144 will reach develop first
   in any realistic scenario (it's MERGEABLE, all 7 CI checks
   green, no upstream PR blocking it).

**Conclusion:** PR #144 keeps FP-016. PR #150 content must
renumber.

---

## 6. Proposed safe renumbering scheme

Renumber the 4 FPs from the #150 squash, shifting up by 1 to
avoid the collision:

| Current (in #150 squash) | Proposed (after renumber) | Title (unchanged) |
|---|---|---|
| FP-016 | **FP-017** | Path proliferation |
| FP-017 | **FP-018** | Rebuild via consume_consensus.rb when in-place edit was correct |
| FP-018 | **FP-019** | Hardcoded coords cause intersect_with float drift |
| FP-019 | **FP-020** | Python subprocess.terminate of SU confuses user |

This maintains the relative order of the 4 entries (they were
discovered in this order during the 2026-05-23 cycle) and only
shifts to avoid the contested FP-016 slot.

### Files needing the renumber

All in the `chore/workflow-and-deps-hardening` branch (post #150
squash):

| File | Change | Notes |
|---|---|---|
| `docs/learning/failure_patterns.md` | 4 heading renames (FP-016→017, 017→018, 018→019, 019→020) + their inter-doc "See also" backlinks | Largest diff |
| `docs/learning/lessons_learned.md` | LL-013/LL-014/LL-015 cross-refs to FP-016/017/018/019 → FP-017/018/019/020 | Several "See also: FP-NNN" lines |
| `tests/test_failure_patterns_regression_catalog.py` | 4 entries in `KNOWN_FP_REGRESSIONS` renumber | Order of entries stays the same |
| `CLAUDE.md` §18 (Canonical Artifact Rule, §18.5/§18.6/§18.7) | Cross-refs to FP-016/017/018/019 → FP-017/018/019/020 | Several refs |
| `.ai_bridge/CURRENT_STATE.md` | "Recently added rules/lessons" section + cross-refs | Quick find/replace |
| `.ai_bridge/HANDOFF.md` | Session 2026-05-23 entry — "mistake taxonomy" lists the 4 FPs by old ID | Update list |
| `tools/su_runner_safety.py` | Docstring refs to "FP-019" → "FP-020" | 2–3 occurrences |
| `tests/test_su_runner_safety.py` | Docstring ref to "FP-019" → "FP-020" | 1 occurrence |
| `docs/diagnostics/2026-05-23_consolidation_hygiene_audit.md` | Cross-refs to FP-016..019 → FP-017..020 | A few references |

**Total surface:** ~9 files, mechanical edits. No semantic
changes, no test rewrites — just numeric ID shifts + their
backlinks.

---

## 7. When NOT to renumber

If Felipe decides PR #144 should renumber instead (e.g. because
the #150 content was discovered "morally first" even though
PR #144's PR-creation date is earlier), the cost is similar in
PR #144's branch:

| File | Change |
|---|---|
| `docs/learning/failure_patterns.md` | FP-016 → FP-020 (or any free ID) |
| `tests/test_failure_patterns_regression_catalog.py` | FP-016 catalog entry → FP-020 |
| `docs/adr/ADR-003-plan-shell-exporter.md` | "FP-016" mentions in PR #144 diff |
| PR #144 title | "(FP-016)" → "(FP-020)" |

This would require coordinating with the PR #144 author (or
operating on PR #144's branch). Higher friction.

**Default recommendation: renumber the #150 squash content** per
§6, since:
- PR #144 has earlier PR creation date.
- PR #144 targets develop directly and is mergeable green NOW.
- The #150 content is still 5 PRs away from develop — easier to
  fix in-flight.

---

## 8. New safety rule (proposed; not yet documented)

To prevent future FP/LL/ADR ID collisions:

1. Before reserving a new FP ID, run a quick scan across:
   - `git show origin/develop:docs/learning/failure_patterns.md`
   - `gh pr list --state open` then `gh pr diff` for each open PR
     touching `failure_patterns.md`
   - Local feature branches (`git branch -a --contains <last-known-FP-commit>`)
2. The "next free ID" is `max(develop_ids ∪ open_pr_ids) + 1`.
3. Same protocol for LL-NNN in `lessons_learned.md` and ADR-NNN in
   `docs/adr/`.

Proposed home (post-decision):
- `CLAUDE.md` — new subsection under §6 (Operational memory) or
  §15 (Repository Hygiene Protocol).
- A new LL entry (number TBD) — "Reserve IDs against ALL open
  PRs, not just develop".

---

## 9. Decision required from Felipe

Before any file is touched:

- **Pick a renumbering side** (default: #150 squash content
  renumbers; PR #144 keeps FP-016).
- **Pick a renumbering target window** (default: FP-017..020,
  contiguous; alternative: leave gap, FP-020..023).
- **Pick when to apply** (default: ASAP as a small follow-up PR on
  `chore/workflow-and-deps-hardening`; alternative: defer until
  stack-merge strategy is chosen per stack integrity report §8).

Once the renumbering target window is approved, the agent will:
1. Open a small follow-up PR (one mechanical commit) on the
   chosen branch.
2. Verify catalog gate still passes (`pytest tests/test_failure_patterns_regression_catalog.py`).
3. Report deltas + push for review.

---

## Appendix — commands used

```bash
# FP IDs per branch
git show "origin/<branch>:docs/learning/failure_patterns.md" \
  | grep -E "^## FP-"

# Catalog content
git show "origin/<branch>:tests/test_failure_patterns_regression_catalog.py" \
  | grep -E '^        "FP-'

# Search across open PRs (heuristic)
gh pr list --repo GFCDOTA/sketchup-mcp --state open --search "FP-016 OR FP-017 OR FP-018 OR FP-019"

# Per-PR file diff
gh pr diff <N> --repo GFCDOTA/sketchup-mcp | grep -E "^\\+## FP-"
```
