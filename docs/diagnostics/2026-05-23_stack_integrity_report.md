# Stack integrity report — 2026-05-23

> Generated after discovering that PR #150 was squash-merged into
> the **wrong target** for the user's intent (`chore/workflow-and-deps-hardening`,
> not `develop`). This report establishes ground truth for the
> SDD-stack state before any cascade decision.
>
> **No merges, no renumbering, no cherry-picks** until the user
> picks Option A / B / C at the end of this doc.

---

## TL;DR

- Squash commit `87c2f4f` (PR #150's body: ADR-005 + Canonical
  Artifact Rule + SU runner mode protocol) lives ONLY on
  `chore/workflow-and-deps-hardening`. **NOT reachable from
  `develop`.**
- Reaching develop requires merging PRs #149 → #148 → #147 → #146 → #145
  in order. Each is a stacked PR whose base is the previous one's
  head.
- 3 PRs in the chain (#146, #148, #149) have `spec-harness` CI
  check **FAILED**. Test + quality-gates + ruby-syntax all SUCCESS.
- FP-016 collision: PR #144 (open, targets develop) and the
  squashed #150 both use FP-016 for different bugs. Detailed
  audit in companion doc
  `2026-05-23_failure_pattern_id_audit.md`.

---

## 1. Cadeia completa de PRs

PRs in the SDD stack, oldest base → newest head:

| PR | Title | Head branch | Base branch | State | Mergeable | CI status | Files touched (highlights) | Risk | Required for #150? |
|---|---|---|---|---|---|---|---|---|---|
| #145 | feat(sdd): spec-driven development framework + harness (Phase 1) | `feat/spec-driven-harness-engineering` | `develop` | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ | SDD framework foundation; specs/, harness, lint | LOW | YES — base of stack |
| #146 | feat(sdd): Phase 2 — CI gate + coverage report + baseline failures audit | `feat/sdd-phase-2-ci-and-test-debt-audit` | `feat/spec-driven-harness-engineering` (#145 head) | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ · **spec-harness ❌** | CI gate wiring + coverage report + audit | MEDIUM | YES |
| #147 | docs: CONTRIBUTING.md + pipeline_overview.md (mermaid) | `chore/docs-foundations` | `feat/sdd-phase-2-ci-and-test-debt-audit` (#146 head) | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ | Pure docs additions | LOW | YES |
| #148 | feat(sdd): spec YAML linter + contract scaffolding | `feat/spec-linter-and-scaffolding` | `chore/docs-foundations` (#147 head) | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ · **spec-harness ❌** | SDD linter + contract scaffolding tools | MEDIUM | YES |
| #149 | chore: workflow concurrency + PyYAML pin + README doc map | `chore/workflow-and-deps-hardening` | `feat/spec-linter-and-scaffolding` (#148 head) | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ · **spec-harness ❌** | Workflow concurrency + dep pin + README doc map | MEDIUM | YES (this PR's HEAD is where #150 merged into) |
| **#150** | docs(adr): ADR-005 — Spec-Driven Development formalisation | `docs/adr-005-spec-driven-development` | `chore/workflow-and-deps-hardening` (#149 head) | **MERGED** at `87c2f4f` (2026-05-23T05:23:02Z) | — | test ✅ · quality-gates ✅ · ruby-syntax ✅ | ADR-005 + (added 2026-05-23) Canonical Artifact Rule + LL-013/14/15 + FP-016/17/18/19 + tools/su_runner_safety.py + tests | LOW (docs + new helper module) | — already merged into the stack |

### Side-by-side PR (NOT in stack)

| PR | Title | Head | Base | State | Mergeable | CI | Risk |
|---|---|---|---|---|---|---|---|
| #144 | fix(rooms): Floor_r001 split via near-miss SB extension + Voronoi (FP-016) | `fix/floor-r001-soft-barrier-buffered-split` | `develop` | OPEN | MERGEABLE | test ✅ · quality-gates ✅ · ruby-syntax ✅ · rubocop ✅ · skp-fidelity-gate ✅ · smoke ✅ · ruby-syntax-tools ✅ (7/7 green) | LOW |

PR #144 is independent: targets develop directly, fully green, claims
FP-016 = "Soft barrier near-miss". Opened 2026-05-21 (2 days
before the squashed #150 entered chore/workflow-and-deps-hardening).

---

## 2. Where commit `87c2f4f` lives now

- **Current branch:** `chore/workflow-and-deps-hardening` (remote +
  via PR #150 squash-merge)
- **Reachable from `develop`?** **NO.** Verified via:
  ```
  $ git merge-base --is-ancestor 87c2f4f origin/develop
  → NOT REACHABLE from develop
  ```
- **Reachable from other open PR heads?** Only the head of #149
  (the same branch). Not on #145–#148 head branches.
- **Cherry-pick duplication risk if the stack lands later:** YES.
  If we cherry-pick `87c2f4f` to a fresh branch from develop and
  merge it, then later the SDD stack also merges through to
  develop, the squashed content (ADR-005 + Canonical Artifact Rule
  + helper + tests) would land twice. Git's merge would surface
  the conflicts but the noise/risk of accidental partial revert is
  real.

---

## 3. Real state of `develop`

- **Current SHA:** `8724ca2` (PR #142, 2026-05-20:
  `fix(plan-shell): door leaf hinge_world for vertical walls (FP-015)`).
- **Develop contains PR #150 content?** **NO.** None of the
  following exist on develop:
  - `tools/su_runner_safety.py`
  - `tests/test_su_runner_safety.py`
  - LL-013, LL-014, LL-015 in `docs/learning/lessons_learned.md`
  - FP-016/017/018/019 in `docs/learning/failure_patterns.md`
  - CLAUDE.md §18 (Canonical Artifact Rule)
  - Updated `.ai_bridge/CURRENT_STATE.md` (still shows the
    pre-2026-05-23 snapshot)
  - Session 2026-05-23 entry in `.ai_bridge/HANDOFF.md`
  - `docs/diagnostics/2026-05-23_consolidation_hygiene_audit.md`
  - `docs/adr/ADR-005-spec-driven-development.md` (still doesn't
    exist on develop — it's in #145 chain content)
- **`CURRENT_STATE.md` on develop:** stale (last update before
  2026-05-23 cycle).
- **CLAUDE.md §18 on develop:** does not exist. §17 is the last
  numbered section.

---

## 4. PR-by-PR status

### #145 — feat(sdd): spec-driven development framework + harness (Phase 1)

- **CI:** all 3 checks green (test, quality-gates, ruby-syntax).
- **Mergeable:** YES.
- **Conflicts with develop:** none reported by GitHub.
- **Risk for landing on develop:** LOW. Foundational framework;
  no existing pipeline code modified.
- **Required to unblock #146+:** YES — the stack base.

### #146 — feat(sdd): Phase 2 — CI gate + coverage report

- **CI:** test ✅, quality-gates ✅, ruby-syntax ✅, **spec-harness
  ❌ FAILURE**.
- **Mergeable:** YES (GitHub mergeable bit only blocks on conflict, not on failed checks).
- **spec-harness failure interpretation:** likely the new check is
  testing against the partial state of the stack. May resolve
  after #145 lands and the stack re-bases. Needs investigation
  before promoting.
- **Risk:** MEDIUM — CI failure on a stack-internal PR.

### #147 — docs: CONTRIBUTING.md + pipeline_overview.md

- **CI:** all 3 checks green.
- **Mergeable:** YES.
- **Risk:** LOW (pure docs).

### #148 — feat(sdd): spec YAML linter + contract scaffolding

- **CI:** test ✅, quality-gates ✅, ruby-syntax ✅, **spec-harness
  ❌ FAILURE**.
- **Mergeable:** YES.
- **Risk:** MEDIUM (same spec-harness concern as #146).

### #149 — chore: workflow concurrency + PyYAML pin + README doc map

- **CI:** test ✅, quality-gates ✅, ruby-syntax ✅, **spec-harness
  ❌ FAILURE** (re-ran 2026-05-23T05:23:21Z — likely re-triggered
  after #150 squash-merged into this branch's head).
- **Mergeable:** YES.
- **Risk:** MEDIUM — now contains #150's content too.

### #150 — docs(adr): ADR-005 — Spec-Driven Development formalisation (MERGED)

- **State:** MERGED at `87c2f4f` (2026-05-23T05:23:02Z).
- **CI on merge:** all 3 checks green at time of merge.
- **Merged into:** `chore/workflow-and-deps-hardening` (#149's head
  branch).
- **Scope creep**: this PR began as just ADR-005 formalisation but
  acquired the entire Canonical Artifact Rule + SU runner mode
  protocol consolidation in 2 follow-up commits (`dac78a5`,
  `5335d5e`, `6f210d8`). The body was updated to reflect the
  expanded scope before merge, but the scope is now larger than a
  single-ADR PR — relevant for cascade-merge decision.

---

## 5. Risks of cascade-merge (#149 → #148 → … → #145 → develop)

### CI risks

- **spec-harness ❌ FAILURE on #146, #148, #149** — none of them
  are green. Cascading 5 merges with red CI on 3 violates the
  project's gate discipline.
- After each merge, GitHub re-targets the next PR's base, which
  triggers fresh CI runs that may not converge to green
  automatically. Each rebase is a new investigation.

### Conflict risks

- All 6 PRs in the stack currently report `MERGEABLE`, but
  GitHub's mergeable bit reflects PAIRWISE conflict at the time
  the PR was opened or last updated. Cascade merges change the
  base; subsequent re-bases may surface conflicts.
- `docs/learning/failure_patterns.md` is the highest-risk file
  for cross-PR conflict: PR #144 (FP-016 "Soft barrier near-miss")
  and the #150 squash (FP-016 "Path proliferation" + FP-017/18/19)
  edit the same numeric ID range. See
  `2026-05-23_failure_pattern_id_audit.md`.

### Scope risks

- Cascade-merging 5 PRs into develop in one session is a large
  surface area: SDD framework (#145), Phase 2 CI (#146), docs
  (#147), spec linter (#148), workflow + dep pin (#149), and the
  ADR-005 + consolidation content from #150 — all entering
  develop within minutes.
- Hard to attribute regressions if anything breaks downstream.
- ROI per merge needs to be weighed against the consolidated risk.

### Hidden functional changes

- #149 contains a PyYAML version pin; pin changes can break
  transitively if other tools depend on a specific PyYAML version.
- #148 adds a SDD linter; if its rules are stricter than the rest
  of the codebase complies with, future PRs may fail it
  unexpectedly.
- #146 wires the SDD harness as a CI gate. If `spec-harness`
  failure on this PR is structural (not a base-branch artefact),
  merging it lights up that gate on every subsequent PR.

### Docs/state staleness

- After 5 cascade merges, the `.ai_bridge/CURRENT_STATE.md` from
  the #150 squash (already pointing to develop @ #142 + canonical
  rule) lands on develop. By then the actual develop SHA will be
  much further than what CURRENT_STATE.md describes. Need a
  refresh commit post-cascade.
- HANDOFF.md section "Session 2026-05-23" describes a state where
  PR #150 was the merge target; once it actually reaches develop,
  the narrative needs adjustment.

### Risk of breaking `develop`

- LOW for #145, #147 (clean CI; foundational/docs-only).
- MEDIUM for #146, #148, #149 (spec-harness FAILURE on each).
- MEDIUM for #150-content (scope larger than original PR; new
  helper + tests are isolated but the LL/FP renumbering is
  pending).

---

## 6. Cross-cutting concerns

### FP ID collision (companion audit)

See `docs/diagnostics/2026-05-23_failure_pattern_id_audit.md` for
the full inventory. Summary:

- PR #144 targets develop with **FP-016** = "Soft barrier
  near-miss" (opened 2026-05-21).
- PR #150 (merged into the stack) brought **FP-016** = "Path
  proliferation" + FP-017/18/19 = three other anti-patterns from
  the 2026-05-23 consolidation cycle.
- When the SDD stack eventually merges into develop AND PR #144
  is also merged, the second-to-arrive will hit a real file
  conflict in `docs/learning/failure_patterns.md` and in
  `tests/test_failure_patterns_regression_catalog.py`.

### Pre-merge validation gap (root cause of this incident)

The 5-condition checklist Felipe gave before merging #150:

1. PR is mergeable ✅
2. CI final green ✅
3. No forgotten untracked files that should enter ✅
4. develop stays clean after merge ❌ **interpreted ambiguously**
5. No functional changes to production exporter without gate ✅

Condition 4 was understood as "develop has no uncommitted dirty
state" but the user clearly meant "develop receives the merged
content". The PR's `baseRefName` should have been the first thing
checked. New rule for future: see §7.

---

## 7. New safety rule (proposed; not yet documented)

Before approving any merge, the validation MUST include:

- **Expected target branch** (what the developer/agent intended).
- **Real `baseRefName`** of the PR (from `gh pr view --json baseRefName`).
- **If they don't match, STOP.**
- **Stack membership:** is this PR part of a multi-PR stack? If
  yes, merging it lands content only in the intermediate
  branch — develop won't receive it until upstream PRs also merge.
- **Conflict scan:** open PRs that touch the same files OR claim
  the same numeric IDs (FP-NNN, LL-NNN, ADR-NNN).
- **CI-on-merge-target:** check whether the PR's CI was green
  against the actual base, not the user's mental model of the base.

Proposed home for this rule (post-decision):
- `CLAUDE.md §0` (git flow) — add "stack/target validation"
  paragraph
- New LL entry (number TBD per FP audit) — "Verify PR baseRefName
  before signing off on merge"
- `docs/protocols/pr_merge_checklist.md` (NEW) — formal
  pre-merge checklist with the above items

---

## 8. Decision options for Felipe

### Option A — Merge the SDD stack in order (#145 → … → #149 → develop)

**When this is right:** if Felipe + the team are confident the SDD
framework should land on develop NOW, and willing to investigate
the `spec-harness ❌` on #146/#148/#149 before each merge.

**Steps:**
1. Investigate why `spec-harness` fails on #146/#148/#149.
2. Resolve the FP-016 collision BEFORE merging the stack (otherwise
   PR #144 conflicts on next merge attempt).
3. Merge in order: #145 → #146 → #147 → #148 → #149.
4. Each merge triggers GitHub to re-target the next PR's base to
   develop; re-run CI; verify green; merge.
5. PR #150's content (already in #149's head) arrives on develop
   when #149 lands.

**Pros:** Single coherent landing; develop catches up on 5 weeks
of SDD work.
**Cons:** Large surface area; ≥3 CI investigations needed; FP-016
must be resolved first; ~30–60 min if everything goes well, longer
if conflicts appear.

### Option B — Cherry-pick #150 to a clean branch from develop

**When this is right:** if the SU runner safety (LL-015 + helper)
is urgent and the SDD stack will take time, and we want the
canonical artifact rule + helper on develop ASAP.

**Steps:**
1. Branch `safety/su-runner-mode-protocol` from develop.
2. Cherry-pick the 3 commits from `87c2f4f`'s history (dac78a5,
   5335d5e, 6f210d8), OR re-author them as a single tighter
   commit.
3. Resolve FP-016 collision in this branch (renumber to
   FP-017..020 per audit doc).
4. Open new PR targeting develop.
5. Document that when the SDD stack eventually lands, the cherry-
   picked content will need to be reconciled (git will surface
   conflict on `docs/learning/failure_patterns.md` and
   `tests/test_failure_patterns_regression_catalog.py` — should be
   easy to resolve since the renumbered version IS what we want).
6. Coordinate with the #145–#149 chain owners so they're aware.

**Pros:** Safety helper + Canonical Artifact Rule reach develop
fast; allows the #145–#149 chain to mature on its own pace; no
spec-harness ❌ blocker.
**Cons:** Duplicate content lives in two places until SDD stack
also lands; needs careful conflict resolution at that point.

### Option C — Leave #150 inside the stack; fix FP IDs in stack; defer landing

**When this is right:** if the SDD work should land as a unit AND
we're not in a rush on runner safety.

**Steps:**
1. Open small follow-up PR on `chore/workflow-and-deps-hardening`
   that renumbers FP-016..019 → FP-017..020 (per audit doc).
2. Wait for #145–#149 to be ready and green.
3. When the stack lands, all this content arrives together.

**Pros:** No duplication; everything lands as a coherent unit.
**Cons:** Safety helper not on develop until the entire SDD chain
lands; if the chain stalls (e.g., spec-harness investigation drags),
runner safety is blocked.

### Felipe's stated preference

From his last message: *"Minha preferência inicial: não fazer merge
cascata automático. Primeiro report, depois decisão."* — agent
delivers this report and waits for explicit A/B/C signal before
acting.

---

## Appendix — diagnostic commands used

```bash
# PR metadata (per PR)
gh pr view <N> --repo GFCDOTA/sketchup-mcp \
  --json number,title,headRefName,baseRefName,state,mergeable,mergedAt,mergeCommit,statusCheckRollup

# Commit reachability
git merge-base --is-ancestor 87c2f4f origin/develop
git branch -a --contains 87c2f4f

# FP IDs per branch
git show "origin/<branch>:docs/learning/failure_patterns.md" \
  | grep -E "^## FP-" | tail -5
```
