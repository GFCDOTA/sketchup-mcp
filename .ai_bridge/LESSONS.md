# Lessons — accumulated learning

> Append-only. Each lesson is a one-paragraph insight + the
> evidence that produced it. When a lesson becomes a permanent rule
> (changes future agent behavior), promote to `CLAUDE.md`. When
> it's purely a bug pattern, also mirror to
> `docs/learning/failure_patterns.md`.

---

## 2026-05-07 — Verify "bug reports" against live HEAD before fixing

### Lesson

A user (or another agent) flagged a bug at `skp_export/consume_consensus.rb`
with `r[:polygon].size` allegedly broken. Investigation showed the
file path doesn't exist in HEAD; the actual `tools/consume_consensus.rb`
uses `polygon_pts` correctly and has no `dry_run` method. The bug
report was based on a stale workspace zip.

### Evidence

- `find . -name consume_consensus.rb` → only `tools/consume_consensus.rb`
- `grep dry_run tools/consume_consensus.rb` → no match
- `git log --all --diff-filter=AM -- 'skp_export/*'` → empty
- `ls /e/Claude/sketchup-mcp-exp-dedup/` → directory does not exist

### Rule (per §14 + §8 "never fabricate")

When a bug report references files / methods / paths, verify they
exist in the live HEAD before touching anything. A "fix" against a
non-existent symbol violates §8.

---

## 2026-05-07 — Inspector v2 schema additive evolution preserved 13 downstream consumers

### Lesson

The decision to keep all v0 top-level keys alongside the new
`structural` section let `inspect_metrics.py` continue working
without code change beyond a one-line preference (`structural.get`
with legacy fallback). Zero regressions in 13 existing tests.

### Evidence

- 193 → 204 in-scope tests pass after the inspector v2 change
  (only the 11 new ones added)
- E2E smoke run on planta_74 produced bit-identical SKP shape
- `inspect_metrics.py.from_dict` change was 7 lines

### Rule

Schema evolution defaults to additive. Breaking changes require
explicit migration path in the loader + a major version bump.

---

## 2026-05-07 — Default-preserve in hygiene cycle is the right safety bias

### Lesson

First hygiene pass under §15 deleted only 1 file (a 41 MB rar) +
removed 5 merged feature branches. Every other suspect (`proto_*.py`,
`PROMPT-*.md`, `runs/<old>/`) was preserved with a documented
reason. Result: 0 breakage, full audit trail in
`docs/ops/hygiene_2026-05-06.md`.

### Evidence

- `git status` clean after pass
- 204 in-scope tests still pass
- Smoke gate PASS

### Rule

In a hygiene cycle, when in doubt → preserve + document. Aggressive
deletion is cheaper to apply later than to recover from.

---

<!-- New lessons below this line, newest at top -->
