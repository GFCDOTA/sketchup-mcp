# Prompt Quality Rubric

> Rubric and Prompt Contract Template for autonomous tasks in
> sketchup-mcp. Loaded by `/afk-maintain`, `/prepare-pr`, and
> `.claude/agents/agent-coordinator.md`. Anchored to `CLAUDE.md`
> §1, §2, §3, §4, §5, §6.

## Why this exists

Autonomous loops in this repo touch a pipeline with hard safety rules:
geometry thresholds (`classify/service.py:160`, `topology/service.py`),
`consensus_model.json` schema (`docs/SCHEMA-V2.md`), the Ruby/SketchUp
exporter (`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`),
archive patches (`patches/archive/07-09`), and the develop-first git
flow.

A vague prompt to an autonomous agent means:

- A PR opens against `main` instead of `develop` (CLAUDE.md §0).
- A "small refactor" silently changes `WALL_HEIGHT_M` or `snap_tolerance` (§1.3).
- The auditor's finding gets fixed by editing `tools/skp_from_consensus.py`
  when the actual scope was `validator/scorers/base.py` (§1.4 vs §1.6).
- The smoke gate (`scripts/smoke/smoke_skp_export.py`) is skipped because
  the prompt didn't list it as required validation (§3, §1.10).

This rubric is the pre-flight checklist. Every autonomous task fills the
**Prompt Contract Template** below before execution. The
`agent-coordinator` rejects any task missing required fields. The
`/prepare-pr` Quality Gate refuses to draft a PR body if the same
fields are missing from the work just done.

---

## The 15 criteria

### 1. Sufficient context

The prompt names the repo state, the anchor in the codebase, and the
relevant `CLAUDE.md` sections.

**Anchored example:** "On branch `agents/<name>` from develop (clean
working tree). CLAUDE.md §1.3 forbids changing geometry thresholds. The
auditor flagged `tools/extract_openings_vector.py:412` as a hardcoded
path."

**Anti-example:** "fix the auditor finding."

### 2. Explicit goal

One sentence, singular outcome.

**Anchored example:** "Replace the hardcoded `Path('runs/planta_74')`
in `tools/extract_openings_vector.py:412` with a `--runs-root` CLI
argument."

**Anti-example:** "improve the openings module."

### 3. Clear action verb

The verb is one of: add / remove / replace / rename / move / extract /
document / measure / benchmark / validate. Not "improve", "clean up",
or "refactor" without scope.

**Anchored example:** "Add a `--runs-root` argument to the argparse
parser in `tools/extract_openings_vector.py`."

**Anti-example:** "make it cleaner."

### 4. Allowed scope

Whitelist of files the task is permitted to touch.

**Anchored example:**

```
- tools/extract_openings_vector.py
- tests/test_extract_openings_vector.py
```

**Anti-example:** "anything in `tools/`."

### 5. Forbidden scope

Explicit no-touch list, anchored to `CLAUDE.md` §1.

**Anchored example:**

```
- tools/consume_consensus.rb        (Ruby/SU — §1.4)
- tools/inspect_walls_report.rb     (Ruby/SU — §1.4)
- tools/skp_from_consensus.py       (high-risk entrypoint — §1.6)
- topology/service.py               (thresholds — §1.3)
- classify/service.py               (thresholds — §1.3)
- patches/archive/                  (HIGH risk — §1.5)
- consensus_model.json schema       (§1.2, docs/SCHEMA-V2.md)
```

**Anti-example:** any list shorter than the relevant `CLAUDE.md` §1
items.

### 6. Constraints

Hard limits beyond scope: line budget, dependency policy, no-binary,
hook-respect.

**Anchored example:** "Diff < 500 lines (§4). No new dependencies (any
addition needs `[dl]` extra approval, §12). No `--no-verify` or
`--no-gpg-sign` (§0)."

**Anti-example:** "be careful."

### 7. Sequential steps

Numbered, deterministic, each step independently verifiable.

**Anchored example:**

```
1. Read tools/extract_openings_vector.py around line 412.
2. Add --runs-root argparse arg with default Path('runs').
3. Replace the hardcoded path with the parsed arg.
4. Update the docstring.
5. Add a test in tests/test_extract_openings_vector.py.
6. Run pytest tests/test_extract_openings_vector.py -q.
```

**Anti-example:** "do it however you think best."

### 8. Output format

What the final artifact looks like: PR body shape, file paths produced,
report shape.

**Anchored example:** "PR body following `CLAUDE.md` §4 PR Standard
(Summary / What changed / What did NOT change / Validation / Risks /
Rollback / Next steps). Files touched: 2 (the `.py` + 1 test)."

**Anti-example:** "open a PR."

### 9. Mandatory validation

Exact commands, expected pass criteria, baseline reference.

**Anchored example:**

```
python -m pytest tests/test_extract_openings_vector.py -q
python -m ruff check tools/extract_openings_vector.py
# Baseline on develop: 200 passed / 16 failed / 2 skipped.
# This change must not introduce new failures vs baseline.
```

**Anti-example:** "tests should pass."

### 10. Stop criteria

Conditions that halt the task without completing the PR.

**Anchored example:** "Halt if pytest reports a new failure not in the
baseline. Halt if ruff reports a category not previously selected. Halt
if the diff touches any file in **Forbidden scope**."

**Anti-example:** "stop if something looks wrong."

### 11. Rollback

Exact reversal commands.

**Anchored example:**

```
git revert <commit-sha>                       # if merged
git push origin --delete agents/<name>        # if branch only
```

**Anti-example:** "we can always revert."

### 12. Before/after evidence

Mechanical proof the change did the intended thing without side effects.

**Anchored example:**

- Before: `python -m pytest tests/test_extract_openings_vector.py -q` →
  fails or passes with hardcoded-path assumption.
- After: same command → passes; new test exercises `--runs-root` override.
- Diff stats reproducible: `git diff origin/develop...HEAD --stat`.

For visual artifacts (renders, plans), follow the repo convention of
side-by-side PNG with the source PDF reference.

**Anti-example:** "looks fine on my machine."

### 13. When to ask the human

Triggers that always escalate, never proceed silently:

- Schema change (`consensus_model.json`, `docs/SCHEMA-V2.md`) — §1.2
- Threshold change (`WALL_HEIGHT_M`, `PARAPET_HEIGHT_M`, `PARAPET_RGB`,
  `snap_tolerance`, `len(strokes) > 200`) — §1.3
- Edit to `tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`,
  `tools/autorun_*.rb`, `tools/su_boot.rb`,
  `tools/skp_from_consensus.py` — §1.4 + §1.6
- Apply any patch under `patches/archive/` — §1.5
- New dependency outside the `[dl]` extra — §12
- Anything that would `--no-verify` or `--no-gpg-sign` — §0
- A "fix" that resolves a case by violating a Pipeline Invariant — §2

### 14. When to proceed autonomously

Safe by default:

- Docs-only changes outside `docs/SCHEMA-V2.md`
- New tests that don't change pipeline behavior
- Updates to `.claude/agents/*.md` and `.claude/commands/*.md` that
  preserve allow/deny lists
- Auditor improvements under `agents/auditor/`
- Smoke gate additions that don't change the pipeline contract
- Bench harness additions under `scripts/`
- Cache infrastructure additions

The conservative-default rule (§5) still applies: when in doubt, prefer
documenting over changing code.

### 15. When only to document

Some findings are observations, not work items. Document them and stop:

- CI flakiness without root cause → `docs/learning/failure_patterns.md`
- Architectural decision after exploration → `docs/learning/decision_log.md`
- "This worked, here's why" → `docs/learning/lessons_learned.md`
- "This prompt pattern was wrong, here's the fix" → `docs/learning/prompt_improvements.md`
- Repo-state snapshot → `reports/<topic>_<timestamp>.md`

Documenting is a complete task. It does not need to lead to a code PR.

---

## The 8-item review checklist

Before any prompt is dispatched (by the user, the coordinator, or a
slash command):

- [ ] **Avoids ambiguity** — every noun has a single referent; every
      verb is in the action-verb list (criterion 3).
- [ ] **Limits allowed files** — Allowed scope is a closed list
      (criterion 4).
- [ ] **Defines branch + PR base** — branch prefix matches `feature/`,
      `fix/`, `chore/`, `docs/`, `perf/`, `refactor/`, `test/`,
      `agents/`, `tooling/`, `validate/`, `hotfix/` (CLAUDE.md §0). PR
      base is `develop` (never `main`, except hotfix).
- [ ] **Defines validation commands** — exact pytest / ruff / smoke
      invocation with pass criteria (criterion 9).
- [ ] **Names what NOT to do** — Forbidden scope explicit (criterion 5).
- [ ] **Defines final output shape** — PR body template, file paths, or
      report path (criterion 8).
- [ ] **One PR = one idea** — no mixing refactor + functional fix +
      perf optimization in one PR (CLAUDE.md §1.9, §4).
- [ ] **Requires before/after evidence** — mechanical proof
      (criterion 12).

If any box is unchecked, the coordinator returns the contract draft to
the user instead of dispatching.

---

## Prompt Contract Template

```
Context:
  <repo state, anchor in code, relevant CLAUDE.md sections>

Goal:
  <one sentence, singular outcome>

Allowed files:
  - <path 1>
  - <path 2>

Forbidden files:
  - <path 1 with §reason>
  - <path 2 with §reason>

Steps:
  1. <action>
  2. <action>

Validation:
  <exact commands + pass criteria + baseline reference>

Stop conditions:
  - <halt trigger 1>
  - <halt trigger 2>

PR body:
  <which template — usually CLAUDE.md §4 PR Standard>

Final output:
  <files written, PR URL, report path>
```

### Worked example — this rubric PR

```
Context:
  Repo sketchup-mcp at branch agents/prompt-quality-rubric, branched
  from develop (clean tree). CLAUDE.md §6 lists docs/learning/ files;
  no Prompt Contract template exists yet. Inspired by general
  prompt-engineering literature (no source reproduced).

Goal:
  Add a 15-criterion rubric, 8-item checklist, and 9-field Prompt
  Contract template, plus enforcement hooks in /prepare-pr,
  /afk-maintain, and agent-coordinator.

Allowed files:
  - docs/learning/prompt_quality_rubric.md            (NEW)
  - docs/learning/prompt_improvements.md              (APPEND PI-009)
  - .claude/commands/prepare-pr.md                    (insert Quality Gate)
  - .claude/commands/afk-maintain.md                  (insert step 4a)
  - .claude/agents/agent-coordinator.md               (add validation duty)
  - CLAUDE.md                                         (2-line cross-ref)
  - tests/test_prompt_quality_rubric.py               (NEW)

Forbidden files:
  - tools/consume_consensus.rb        (Ruby/SU — §1.4)
  - tools/inspect_walls_report.rb     (Ruby/SU — §1.4)
  - tools/skp_from_consensus.py       (high-risk entrypoint — §1.6)
  - topology/service.py               (thresholds — §1.3)
  - classify/service.py               (thresholds — §1.3)
  - consensus_model.json schema       (§1.2, docs/SCHEMA-V2.md)
  - patches/archive/                  (§1.5)
  - .github/workflows/                (CI — would mix scopes)
  - pyproject.toml                    (deps — would mix scopes)

Steps:
  1. Stash dashboard work, branch from develop.
  2. Write docs/learning/prompt_quality_rubric.md.
  3. Update .claude/agents/agent-coordinator.md.
  4. Update .claude/commands/prepare-pr.md.
  5. Update .claude/commands/afk-maintain.md.
  6. Append PI-009 to docs/learning/prompt_improvements.md.
  7. Add cross-refs to CLAUDE.md.
  8. Add tests/test_prompt_quality_rubric.py.
  9. Run verification grep + pytest.
  10. Commit + open PR via /prepare-pr.
  11. Restore dashboard stash.

Validation:
  git diff --stat origin/develop...HEAD
  git diff origin/develop...HEAD --name-only | grep -E '\.(py|rb)$' | grep -v '^tests/' || echo OK
  git diff origin/develop...HEAD --name-only | grep -E '(consume_consensus|skp_from_consensus|topology/service|classify/service|autorun_|su_boot|patches/archive)' || echo OK
  python -m pytest tests/test_prompt_quality_rubric.py -q   # includes the source-title leak guard

Stop conditions:
  - Any of the four greps prints something other than OK.
  - pytest fails on the new structural test.
  - Diff touches any file in Forbidden files.

PR body:
  CLAUDE.md §4 PR Standard.

Final output:
  PR opened against develop with the seven files above.
  Stash restored on dashboard/project-roadmap.
```

---

## Decision matrix

| Situation | Mode | Why |
|---|---|---|
| Schema change (`consensus_model.json`, `docs/SCHEMA-V2.md`) | ASK | §1.2 — schema is contract |
| Threshold tweak (`snap_tolerance`, `WALL_HEIGHT_M`, ...) | ASK | §1.3 — empirical sweep needed |
| Ruby/SU exporter edit (`tools/consume_consensus.rb`, ...) | ASK | §1.4 — most expensive gate |
| Apply archive patch (`patches/archive/07-09`) | ASK | §1.5 — HIGH risk |
| New dependency outside `[dl]` extra | ASK | §12 — restricted dep policy |
| `git push --no-verify` or `--no-gpg-sign` | ASK | §0 — pre-commit guard exists for a reason |
| Resolve a case by violating Pipeline Invariant | ASK | §2 — never invent rooms/walls |
| Docs typo / copy-edit | AUTONOMOUS | No pipeline impact |
| Update `.claude/agents/*.md` preserving allow/deny | AUTONOMOUS | Agent file evolution is expected |
| Add a smoke gate that doesn't change pipeline | AUTONOMOUS | Pure gate strengthening |
| Add a test that doesn't change behavior | AUTONOMOUS | Test-only diff |
| Auditor improvement (`agents/auditor/`) | AUTONOMOUS | Read-only audit |
| Bench harness addition under `scripts/` | AUTONOMOUS | No pipeline change |
| CI flakiness without identified root cause | DOCUMENT ONLY | → `docs/learning/failure_patterns.md` |
| Architectural decision after research | DOCUMENT ONLY | → `docs/learning/decision_log.md` |
| Lesson from a successful run | DOCUMENT ONLY | → `docs/learning/lessons_learned.md` |
| Prompt-pattern observation | DOCUMENT ONLY | → `docs/learning/prompt_improvements.md` |
| Repo-state snapshot | DOCUMENT ONLY | → `reports/<topic>_<timestamp>.md` |

When the same situation could be ASK or DOCUMENT ONLY, prefer DOCUMENT
(§5 default rule).

---

## Cross-links

- `CLAUDE.md` §1 (Hard Safety Rules) · §2 (Pipeline Invariants) ·
  §4 (PR Standard) · §5 (Default Decision Rule) · §6 (Operational Memory)
- `docs/learning/lessons_learned.md` — positive operational lessons
- `docs/learning/failure_patterns.md` — anti-patterns
- `docs/learning/decision_log.md` — architectural decisions
- `docs/learning/prompt_improvements.md` — prompt pattern history
- `.claude/agents/agent-coordinator.md` — enforcement entry point
- `.claude/commands/afk-maintain.md` — autonomous loop integration (step 4a)
- `.claude/commands/prepare-pr.md` — Quality Gate before PR body draft
- `tests/test_prompt_quality_rubric.py` — structural test that pins this
  file's shape

---

## Provenance

Principles synthesized from general prompt-engineering literature; no
copyrighted text or named work reproduced. The rubric is project-specific:
every example is anchored to real `sketchup-mcp` paths, sections of
`CLAUDE.md`, or commands defined in this repo.
