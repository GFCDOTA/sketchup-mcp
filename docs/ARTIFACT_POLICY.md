# ARTIFACT_POLICY — separation of human-facing deliverables vs agent inputs

> **Status:** Canonical
> **Type:** Permanent operational policy for repository artifacts
> **Updated:** 2026-05-25
> **Companion docs:** [`REPO_HYGIENE.md`](REPO_HYGIENE.md) (file categories
> + .gitignore rules), [`PROJECT_STATE.md`](PROJECT_STATE.md) §4
> (canonical artifacts catalogue), [`../CLAUDE.md`](../CLAUDE.md) §23
> (short rule), [`AGENT_COORDINATION.md`](AGENT_COORDINATION.md)
> (worktree isolation — applies when committing artifacts too).

This document is the **policy**. It tells you where deliverable
`.skp` files go, what `runs/` is for vs `artifacts/` is for, and
the inviolable rule that gates every PR claiming SKP success.

---

## 0. The rule (read this first)

**`.skp` is the primary deliverable of this project.**

- `/runs/` is scratch / temporary. Anything that lands there is
  expected to be regenerated on demand.
- BUT any `.skp` that is used for **canonical success**, **user
  review**, **fidelity comparison**, **claimed working output**,
  or **demo/proof that the pipeline works** MUST be promoted out
  of `/runs/` and committed to a tracked path.
- **No PR may claim "SKP generated successfully" unless the
  reviewable `.skp` is committed in a human-facing artifact folder.**
  If you cannot commit the `.skp` (size > LFS threshold, machine
  doesn't have SU, whatever), the task FAILS — do not silently
  drop the deliverable.

The reviewer (Felipe) cares about the `.skp`. Renders and reports
are supporting evidence. The `.skp` is the proof.

---

## 1. The two-folder split

```
artifacts/
  human_review/                  ← Felipe / reviewer-facing
    <plant_name>/
      <plant>_<descriptor>.skp   ← THE DELIVERABLE
      <plant>_<descriptor>.png   ← optional supporting render
      README.md                  ← what / why / how to regenerate
  agent_inputs/                  ← agent / test plane
    <plant_name>/
      consensus_*.json           ← OR pointer README to canonical paths
      shell_polygon.json
      geometry_report.json
      README.md
```

Both subtrees are **tracked in git**. Neither is gitignored.

### `artifacts/human_review/**` — what Felipe cares about

- MUST contain the `.skp`.
- MAY contain renders, reports, or any visual confirmation.
- Per-plant subfolder (e.g. `quadrado/`, `planta_74/`).
- README per plant explaining what the artifact is, which input
  generated it, the exact regen command, and provenance (date,
  builder, sha256 of the SKP).

### `artifacts/agent_inputs/**` — agent / test plane

- Holds JSON inputs, reports, debug data, consensus snapshots that
  agents and tests need.
- These are **internal**, not primary deliverables.
- When a canonical input already lives at a tracked path (e.g.
  `fixtures/quadrado/consensus_with_window.json`), the
  `agent_inputs/<plant>/README.md` is a **pointer doc** to that
  canonical path — do NOT duplicate the file (avoids
  synchronisation hazards + breaks no existing test references).
- New fixtures or one-off debug snapshots without a canonical home
  may live directly in `agent_inputs/<plant>/`.

---

## 2. Promotion rule (`runs/` → `artifacts/`)

Promote a `.skp` from `runs/` to `artifacts/human_review/` when ANY
of these is true:

| Trigger | Example |
|---|---|
| The `.skp` is the canonical reference for a spec | `quadrado_canonical_with_window.skp` (this commit) |
| A PR body claims "SKP generated successfully" or equivalent | any feature PR shipping a new pipeline path |
| The `.skp` is needed for fidelity comparison or visual review | `planta_74_current.skp` (when produced) |
| The `.skp` is the proof that a fix works | regression-fix PRs that produce a new "after" SKP |
| A reviewer (human) is asked to open it in SU | any user-review request |

### Promotion procedure

```bash
# 1. Identify the run-dir .skp:
ls runs/<run_id>/*.skp

# 2. Pick the canonical name (per-plant; descriptive):
mkdir -p artifacts/human_review/<plant_name>
cp runs/<run_id>/quadrado.skp \
   artifacts/human_review/<plant_name>/<plant>_<descriptor>.skp

# 3. (Optional but recommended) Capture supporting render:
python tools/quadrado/render_view.py \
       --skp artifacts/human_review/<plant>/<file>.skp \
       --out artifacts/human_review/<plant>/<file>.png

# 4. Update the README in artifacts/human_review/<plant>/ with:
#    - what this SKP is
#    - which consensus / fixture generated it
#    - exact regen command
#    - date built + sha256
#    - PR number / commit SHA that promoted it

# 5. Commit in a focused commit:
git add artifacts/human_review/<plant>/
git commit -m "chore(artifact): promote <plant> canonical SKP to human_review"
```

---

## 3. Gate enforcement

`tools/repo_health_gate.py` recognises `artifacts/human_review/`
and `artifacts/agent_inputs/` as allowed paths for `.skp` (and
other generated suffixes). Tracked `.skp` files under those paths
do NOT fire E002 (`generated-in-wrong-path`).

Tracked `.skp` files OUTSIDE the allowed paths still fire E002 —
the gate enforces the no-bury-the-deliverable rule.

### What the gate DOES NOT check (yet)

The gate cannot mechanically verify that a PR claiming SKP success
includes a committed `.skp`. That's a PR-review responsibility for
now. Future enhancement: PR-body scanning + cross-check against the
diff (out of scope for this policy doc).

---

## 4. File size + Git LFS

For most plants the `.skp` is small (quadrado: ~66 KB; planta_74:
~700 KB on recent builds). No LFS configuration needed for the
typical case.

If a future plant produces a `.skp` exceeding 5 MB:

1. **Do not skip the commit.** The deliverable is the SKP.
2. Configure Git LFS for `.skp` tracking:
   ```bash
   git lfs install
   git lfs track "artifacts/human_review/**/*.skp"
   git add .gitattributes
   git commit -m "chore(lfs): track artifacts/human_review/**/*.skp via LFS"
   ```
3. Then commit the SKP normally — LFS handles the storage layer.

The gate's `E005 heavy-file-no-allowlist` detector (5 MB threshold)
will trip on a non-LFS `.skp` above the threshold; treat that as
the "configure LFS now" signal.

---

## 5. What does NOT belong in `artifacts/`

- **Generated debug dumps** (`runs/<id>/debug_walls.svg`, etc.) —
  stay in `runs/`, gitignored.
- **One-off scratch renders** during exploration — stay in `runs/`.
- **`.skp` from a failed / broken build** — do not promote; either
  fix the build or do not claim success.
- **Per-cycle smoke harness outputs** — stay in `runs/`.

The boundary: if a human ever needs to OPEN this file to validate
something, it goes in `artifacts/`. If only a script needs it, it
stays in `runs/`.

---

## 6. Migration path for existing tracked `.skp` files

As of 2026-05-25 the repo contains exactly one tracked `.skp`:
`fixtures/planta_74/skp_final_model.skp`. It is currently at a
canonical path that pre-dates this policy.

**Decision:** keep `fixtures/planta_74/skp_final_model.skp` at its
current path for now (existing references in docs / scripts). When
a future PR refreshes that planta_74 SKP, promote the new build to
`artifacts/human_review/planta_74/planta_74_current.skp` and either
deprecate the `fixtures/planta_74/skp_final_model.skp` path or have
both for a transition period (documented in the new
`artifacts/human_review/planta_74/README.md`).

Do NOT mass-move existing tracked `.skp` files in this PR — the
policy is forward-looking, not a backward-compat rewrite.

---

## 7. Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-25 | (this commit) | Initial canonical policy doc. Promotes the quadrado canonical `.skp` from `runs/quadrado_v4_canonical/` to `artifacts/human_review/quadrado/`. Establishes the `artifacts/` two-folder split, the promotion procedure, the gate allowlist, and the LFS escape hatch. |
