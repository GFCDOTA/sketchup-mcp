# Hygiene audit — post-Cycle-12d (2026-05-08)

> Per CLAUDE.md §15. Triggered after the Cycle 12 / 12b / 12d
> cockpit wave landed (PRs #68/#69/#70/#71/#72). Goal: identify
> root-level files that are stale enough to archive, without
> breaking active references. **Outcome: no files archived this
> cycle.** This doc is the audit ledger so the next pass starts from
> the same baseline.

## Method

For each root-level `.py` and `.md` candidate, grepped the entire
repo (`README.md`, `CLAUDE.md`, `OVERVIEW.md`, `AGENTS.md`,
`pyproject.toml`, `.github/workflows/*.yml`, `tests/`, `tools/`,
`scripts/`, `docs/` excluding `docs/_archive/`) for references.
Classification rules:

- **ACTIVE** — at least one reference outside `docs/_archive/` and
  not a self-reference, AND the reference describes current
  behaviour.
- **DOCUMENTED TECH DEBT** — already flagged in
  `pyproject.toml [tool.ruff].extend-exclude` with a hardening
  plan; preserve until the planned refactor lands.
- **HISTORICAL / PRESERVE** — referenced from `docs/ops/`,
  `patches/README.md`, or `docs/architecture/` as a future-refactor
  anchor.
- **ARCHIVE CANDIDATE** — only references are inside
  `docs/_archive/*` or self.
- **UNCLEAR** — has live references but unclear whether the file
  itself is still alive.

## Inventory + classification

### ACTIVE (5)

| File | Why kept |
|---|---|
| `main.py` | `[project.scripts]` entry point (pyproject); CLAUDE.md §1.6 high-risk protection. |
| `CLAUDE.md` | Constitution, read at every session start. |
| `README.md` | Repo entry point. |
| `AGENTS.md` | Pipeline invariants (CLAUDE.md §2). |
| `OVERVIEW.md` | Canonical onboarding doc; referenced by CLAUDE.md and §10 baseline notes. |

### DOCUMENTED TECH DEBT (3)

Already flagged in `pyproject.toml [tool.ruff].extend-exclude` with
the comment "tech debt — hardcoded local paths
(C:/Users/felip_local/...); documented in
`docs/repo_hardening_plan.md`, will be turned into CLI args":

| File | Status |
|---|---|
| `proto_colored.py` | ruff-excluded; awaiting CLI-arg refactor |
| `proto_red.py` | ruff-excluded; awaiting CLI-arg refactor |
| `render_sidebyside.py` | ruff-excluded; awaiting CLI-arg refactor |

### HISTORICAL / PRESERVE (5)

Referenced from non-archive ops/patches/architecture docs that
treat them as live anchors. Removing them would orphan those
references.

| File | Reference |
|---|---|
| `PROMPT-FELIPE.md` | `patches/README.md` line 194 |
| `PROMPT-RENAN.md` | `docs/_archive/2026-04-f1-cycle/*` (5 mentions) — but treated as live handoff template |
| `peek_pdf.py` | `docs/ops/hygiene_2026-05-06.md` debug aid |
| `crop_legend.py` | sibling of `proto_*` cluster, no active import but kept for parity |
| `make_test_pdf.py` | `docs/diagnostics/2026-05-08_cycle11b_vector_pdf_inventory.md` lines 2–3 |

### UNCLEAR / DEFER TO HUMAN (4)

The `render_*` cluster lives in a transitional state. Architecture
plan references them as future deprecation wrappers but they are
not actively imported by anything live.

| File | Note |
|---|---|
| `render_debug.py` | `docs/architecture/target_repo_architecture.md` line 128 — deprecation-wrapper pattern proposed |
| `render_native.py` | `OVERVIEW.md` line 85 — "Overlays variados para conferência visual" |
| `render_semantic.py` | Referenced from `OVERVIEW.md` cluster |
| `render_proto_overlays.py` | imports `png_history` module; `docs/png_history_protocol.md` line 7 documents it |
| `render_with_openings.py` | `docs/png_history_protocol.md` line 7 table |

These should NOT be moved without coordinating with
`docs/repo_hardening_plan.md` step 5 (`renderers/` migration).

### ARCHIVE CANDIDATES — recommended SECOND audit before action (5)

The agent flagged these as "references only in `docs/_archive/*`",
but the `_archive/` cycle ran in 2026-04 and these files might still
be invoked manually. Recommend ONE more pass next session:

- `analyze_overpoly.py`
- `preprocess_walls.py`
- `proto_runner.py`
- `proto_skel.py`
- `proto_v2.py`

Conservative recommendation: leave for now. The cost of keeping a
~10KB orphan script is much lower than the cost of breaking a
manual diagnostic reflex Felipe has built. Re-evaluate when the
next wave of repo hardening (`docs/repo_hardening_plan.md`) lands.

## Action this cycle

**None.** The audit ledger itself is the deliverable. Per
CLAUDE.md §15: "Preserve by default … When in doubt → archive /
quarantine instead of delete." The audit found no candidate that
clears both bars (no live reference + no plausible manual use).

## Followup tasks queued for later

1. Resolve the `render_*` cluster migration into `packages/renderers/`
   per `docs/architecture/target_repo_architecture.md`. Until then
   `render_debug.py`, `render_native.py`, `render_semantic.py`,
   `render_proto_overlays.py`, `render_with_openings.py` stay put.
2. Refactor `proto_colored.py` / `proto_red.py` /
   `render_sidebyside.py` to accept CLI args (kill the hardcoded
   `C:/Users/felip_local/...` paths). After that they can be
   un-excluded from ruff.
3. Re-audit the 5 "ARCHIVE CANDIDATES" with explicit human sign-off
   before moving anything.

## See also

- CLAUDE.md §15 — Repository Hygiene Protocol
- `docs/ops/hygiene_2026-05-06.md` — previous hygiene pass
- `docs/repo_hardening_plan.md` — pending migration plan
- `docs/architecture/target_repo_architecture.md` — target shape
