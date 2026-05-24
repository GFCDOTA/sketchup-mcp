# HANDOFF — canonical onboarding for any new session, machine, or human

> **Status:** Canonical
> **Type:** Stable onboarding doc (NOT per-session log)
> **Updated:** 2026-05-24
> **Companion docs:** [`PROJECT_STATE.md`](PROJECT_STATE.md) for state
> snapshot, [`REPO_HYGIENE.md`](REPO_HYGIENE.md) for file policy,
> [`GATES.md`](GATES.md) for validation gates,
> [`ANTI_FORGETTING.md`](ANTI_FORGETTING.md) for permanent rules.

For per-session "what happened last cycle" logs, see
[`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) (append-only,
chronologically newest entry on top) and
[`../.ai_bridge/CURRENT_STATE.md`](../.ai_bridge/CURRENT_STATE.md)
(overwrite-on-update single-snapshot).

This file is **stable** — it tells the next person/agent how to
become productive. It does NOT track day-to-day work.

---

## 1. First-thing-to-read order

If you are picking this repo up on a new machine or new session, read
in this exact order:

1. [`../CLAUDE.md`](../CLAUDE.md) — operational constitution (39 KB,
   20 sections; §0–§3 are inviolable).
2. [`PROJECT_STATE.md`](PROJECT_STATE.md) — what the project is, where
   it is now, what works, what's canonical.
3. [`ANTI_FORGETTING.md`](ANTI_FORGETTING.md) — permanent rules and
   the reasoning behind them.
4. [`GATES.md`](GATES.md) — validation gates and commands.
5. [`../OVERVIEW.md`](../OVERVIEW.md) — full architectural map (only
   if `PROJECT_STATE.md` left you wanting more context).
6. [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) — most recent
   session's exit state (top entry).
7. [`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md) —
   ROI-ordered queue of next moves.

Total reading time: about 20 minutes. Skipping #1 or #3 will cause you
to repeat mistakes that are already documented.

---

## 2. Setup on a fresh machine

### 2.1 Pre-requisites

- Python ≥ 3.11 (tested on 3.12.13)
- Git
- Optional, only for `.skp` export: SketchUp 2026 installed at
  `C:\Program Files\SketchUp\SketchUp 2026\` (Windows only).
- Optional, only for vision critique: Ollama with `qwen2.5vl:7b`
  on `localhost:11434`.

### 2.2 Clone and install

```bash
git clone https://github.com/GFCDOTA/sketchup-mcp.git
cd sketchup-mcp

python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

pip install -e .              # core
pip install -e ".[dev]"       # pytest + ruff
pip install -e ".[cockpit]"   # Streamlit cockpit (optional)
pip install -e ".[dl]"        # torch + CubiCasa5K oracle (heavy, optional)
```

### 2.3 First-run sanity check

```bash
# Validate the project state on this machine
python scripts/project_state_check.py

# Run the cheap unit suite
pytest -q

# Run the canonical fixture smoke gate
pytest tests/test_quadrado_canonical_smoke.py -v
```

If `project_state_check.py` fails, **STOP** and read its output —
it tells you exactly which canonical doc / fixture / gate is missing
or inconsistent. Do not proceed until it returns exit 0.

### 2.4 Build the planta_74 baseline locally

Reproduces the canonical 33/11/11/8 baseline from clone state.
Detailed in [`../OVERVIEW.md`](../OVERVIEW.md) §4.4.

```bash
python -m tools.build_vector_consensus planta_74.pdf \
       --out runs/vector/consensus_model.json

python -m tools.extract_room_labels planta_74.pdf \
       --out runs/vector/labels.json

python -m tools.rooms_from_seeds runs/vector/consensus_model.json \
       runs/vector/labels.json

python -m tools.extract_openings_vector planta_74.pdf \
       --consensus runs/vector/consensus_model.json \
       --mode replace --classify-kind --detect-wall-gaps

python -m tools.classify_openings_by_room_context \
       runs/vector/consensus_model.json \
       --out runs/vector/consensus_classified.json
```

Output `runs/vector/consensus_classified.json` should have 33 walls,
11 rooms, 11 openings, 8 soft_barriers.

### 2.5 Build the quadrado canonical SKP (needs SU 2026)

```bash
python -m tools.build_plan_shell_skp \
       fixtures/quadrado/consensus_with_window.json \
       --out runs/quadrado_validation/quadrado.skp
```

Validates wall-shell canonical (4-vertex outer ring) + window aperture
(3D carve through host wall, glass at mid-thickness).

---

## 3. Where to find what

| Question | Read |
|---|---|
| What is this project? | [`PROJECT_STATE.md`](PROJECT_STATE.md) §1 |
| What's the current state? | [`PROJECT_STATE.md`](PROJECT_STATE.md) §2 |
| What works? | [`PROJECT_STATE.md`](PROJECT_STATE.md) §3 |
| What are the canonical fixtures and outputs? | [`PROJECT_STATE.md`](PROJECT_STATE.md) §4 |
| What rules must I not forget? | [`ANTI_FORGETTING.md`](ANTI_FORGETTING.md) |
| How do I run a validation gate? | [`GATES.md`](GATES.md) |
| Is this file I'm looking at canonical or stale? | [`REPO_HYGIENE.md`](REPO_HYGIENE.md) §"Markdown status policy" + the `Status:` header on the file itself |
| What's the git flow? | [`../CLAUDE.md`](../CLAUDE.md) §0 |
| What are the inviolable safety rules? | [`../CLAUDE.md`](../CLAUDE.md) §1 |
| What are the pipeline invariants? | [`../CLAUDE.md`](../CLAUDE.md) §2 |
| Architectural decisions? | [`adr/README.md`](adr/README.md) — ADR index |
| Past failure patterns? | [`learning/failure_patterns.md`](learning/failure_patterns.md) |
| Past positive lessons? | [`learning/lessons_learned.md`](learning/lessons_learned.md) |
| What did the last session do? | [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) top entry |
| What's the next ROI item? | [`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md) |

---

## 4. Decisions you do NOT need to re-make

These are decided and codified. Do not relitigate without a hard
trigger:

- Two-track pipeline (raster + vector) coexists. Raster is OUTDATED on
  `planta_74` but kept for evidence. New work targets vector.
- `polygonize` returning `[]` is valid output (`rooms=[]`). Not a bug
  to "fix" silently.
- `bbox` is NEVER a substitute for a room.
- Ground truth NEVER flows into extractor output.
- `consensus_model.json` schema is locked at v1.0 (vector) and
  `observed_model.json` at v2.1.0 (raster).
- SketchUp is the LAST gate, not the first. Cheap gates first.
- `planta_74.pdf` is the canonical real-data baseline (33/11/11/8).
- `fixtures/quadrado/` is the canonical synthetic baseline for
  wall-shell + window semantics.
- Windows are wall-hosted partial-height apertures (3D carve), never
  door-like full-height voids.
- Wall shell uses corner-extended footprints + post-boolean
  canonicalisation. No tecos / no slivers.

---

## 5. Common pitfalls when handing off (read once)

These have actually happened on this repo. Do not repeat:

- **Treating `.ai_bridge/HANDOFF.md` as canonical project state.** It
  is per-session and may be stale by days/weeks. `PROJECT_STATE.md` is
  the canonical state.
- **Inventing a parallel demo / fixture under `runs/` and calling it
  canonical.** `runs/` is gitignored. If it's not committed, it's
  not canonical. Use `fixtures/` for canonical inputs and
  `docs/specs/_assets/` for canonical expected outputs.
- **Reading code instead of `CLAUDE.md` first.** The constitution
  encodes rules that the code does not enforce yet. Bypassing it
  re-creates known failure patterns.
- **Committing on `main` or `develop` directly.** Blocked by
  `pre_bash_guard.py` hook + §0 rule. Always branch.
- **Running `ruff --fix .` over the whole repo.** Banned by §1.
  Limited-scope `ruff --fix path/to/file.py` is fine when needed.
- **Treating the raster `planta_74` baseline (94 walls / 14 rooms) as
  current.** It's OUTDATED. The vector baseline is 33/11/11/8.
- **Killing every `SketchUp.exe` process when a smoke run finishes.**
  Banned — the SU runner mode protocol (§18) requires per-PID
  termination only in headless mode, and never `taskkill /IM`.
- **Editing `runs/<id>/consensus.json` and then trying to ship the
  edit as a change.** `runs/` is gitignored. Edits to live consensus
  go via `cockpit/overrides.py` (see ADR-001/ADR-002) or are committed
  as fixtures.

---

## 6. When you finish a cycle

Per [`../CLAUDE.md`](../CLAUDE.md) §14 / §17, every cycle ends by:

1. Updating [`../.ai_bridge/CURRENT_STATE.md`](../.ai_bridge/CURRENT_STATE.md)
   (overwrite the snapshot — current branch, open PRs, top of queue).
2. Prepending a fresh entry to
   [`../.ai_bridge/HANDOFF.md`](../.ai_bridge/HANDOFF.md) (append at
   top so newest is on top).
3. Refreshing [`../.ai_bridge/TODO_NEXT.md`](../.ai_bridge/TODO_NEXT.md)
   with what's left.
4. If a permanent rule, baseline, or fixture changed, updating
   [`PROJECT_STATE.md`](PROJECT_STATE.md) + adding an entry to its §9.
5. If you learned something durable, adding to
   [`learning/lessons_learned.md`](learning/lessons_learned.md) (LL-xxx)
   or [`learning/failure_patterns.md`](learning/failure_patterns.md)
   (FP-xxx).
6. Running the state-check gate before committing:
   `python scripts/project_state_check.py`.

A cycle is NOT complete until all six are done. See
[`../CLAUDE.md`](../CLAUDE.md) §17 for the twelve-question stop gate.

---

## 7. Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial canonical handoff doc. Consolidates onboarding flow + setup steps + decision-list-not-to-relitigate + cycle exit checklist. |
