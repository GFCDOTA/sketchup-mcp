# REPO_HYGIENE — policy for files, .md, and generated artifacts

> **Status:** Canonical
> **Type:** Policy (not a per-cycle audit report)
> **Updated:** 2026-05-24
> **Companion docs:** [`PROJECT_STATE.md`](PROJECT_STATE.md),
> [`HANDOFF.md`](HANDOFF.md), [`../CLAUDE.md`](../CLAUDE.md) §15.
> **Per-cycle audit reports:** under `reports/` (e.g.,
> [`../reports/repo_hygiene_report.md`](../reports/repo_hygiene_report.md))
> and `docs/ops/` (e.g., `docs/ops/repo_hygiene_audit_2026-05-10.md`).

This document is the **policy**. It tells you how to classify a file,
when to preserve, when to archive, when to delete, and how to add a
`Status:` marker. It is stable.

For the **inventory** ("what is each .md right now?") see the
per-cycle audit report under `reports/`. For the per-cycle audit
**conclusion** ("what did the last hygiene cycle decide to keep/move?")
see `docs/ops/repo_hygiene_audit_*.md`.

---

## 1. The five file categories

Every tracked file in this repo falls into exactly one of these
categories. When a file's role changes, its category changes — and
that change is captured by editing the file's `Status:` header (for
markdown) or by moving it (for everything else).

| Category | Definition | Lives at |
|---|---|---|
| **Canonical** | Single source of truth for some fact. Removing this file would break the project. | `CLAUDE.md`, `README.md`, `OVERVIEW.md`, `AGENTS.md`, `docs/PROJECT_STATE.md`, `docs/HANDOFF.md`, `docs/GATES.md`, `docs/REPO_HYGIENE.md`, `docs/ANTI_FORGETTING.md`, all `docs/adr/ADR-*.md`, `docs/specs/*`, `fixtures/quadrado/*`, `fixtures/planta_74/*` (the curated subset). |
| **Active** | Code, test, doc, fixture, or asset that is referenced by canonical content or by CI. Live working surface. | `tools/**`, `tests/**`, `scripts/**`, `cockpit/**`, `renderers/**`, `validator/**`, `sketchup_mcp_server/**`, `api/**`, `model/**`, all the pipeline-stage packages (`ingest`, `extract`, etc.), `pyproject.toml`, `Gemfile.lint`, `.rubocop.yml`, `.github/workflows/**`. |
| **Archived** | Historically valuable but superseded. Kept for audit / forensic value but explicitly NOT canonical. | Under `docs/_archive/<date-or-cycle-name>/`. Top of file has `Status: Archived. Superseded by <path>.` |
| **Generated** | Output of a script / pipeline / build. Reproducible from source. NEVER hand-edited, NEVER canonical. | Under `runs/**`, `out/**`, `review/**`, `reports/**` (some), `runs/png_history/manifest.jsonl`, `runs/<id>/_cockpit_cache/**`. Gitignored unless explicitly tracked. |
| **Delete candidate** | No reference from any canonical or active file, no historical value, no diagnostic value. | NOWHERE — by the time you can answer "yes, definitely no value", you have already removed it in a chore commit. Until then, it sits where it sits with a clear `Status: Delete candidate — pending audit cycle <N>` header. |

Files that don't clearly belong to one category get the most
conservative one. `Active` beats `Delete candidate` until evidence
proves otherwise.

---

## 2. Markdown status policy

Every `.md` file in this repo SHOULD eventually carry a `Status:`
line in its header (after the H1 title). The line is one of:

```markdown
> **Status:** Canonical
> **Status:** Active
> **Status:** Archived. Superseded by <path/to/replacement.md>
> **Status:** Archived. Historical reference, no replacement.
> **Status:** Generated (do not edit). Produced by <script.py>.
> **Status:** Delete candidate — pending audit cycle <N>
```

Files added before this policy may not carry the line. **Do not run a
bulk rewrite** to add the line — instead, when you touch a `.md` for
any reason, add the appropriate `Status:` header in the same commit.

Files explicitly exempt from `Status:` (because their role is obvious
from path): `README.md` at any nested level (always Active for the
directory it documents), `CHANGELOG.md` if introduced.

---

## 3. The "do not delete blindly" protocol

Before removing or moving ANY file:

1. **Grep for references.** Search `CLAUDE.md`, `README.md`,
   `OVERVIEW.md`, `docs/`, `tests/`, `scripts/`, `tools/`,
   `cockpit/`, CI workflows (`.github/workflows/`), Python imports,
   Ruby `require`/`load`, smoke command lines, manifest files, the
   dashboard.
2. **Check `git log -- <file>`** for recent activity. A file touched
   in the last 30 days is almost certainly active.
3. **Classify** with the five-category scheme. If the candidate is
   anything other than `Delete candidate` or `Generated`, **stop** —
   it does not get deleted in this pass.
4. **Preserve by default**: ground truth, baselines, regression
   snapshots, reports referenced by tests, fixtures referenced by
   docs, artifacts needed to reproduce bugs, anything under protected
   paths (`runs/`, `patches/`, `docs/`, `vendor/` per
   [`../CLAUDE.md`](../CLAUDE.md) §1).
5. **When in doubt → archive, not delete.** Move to
   `docs/_archive/<date>/` with a `Status: Archived` header.
6. **Cleanup ships in its own commit** — separate from any algorithmic
   change. Never mix repo cleanup with a fix. See
   [`../CLAUDE.md`](../CLAUDE.md) §15.

If you skip any step, you are violating policy.

---

## 4. Generated vs canonical — the boundary

Generated artifacts must satisfy ALL of these:
- Produced by a documented script that any clone can run.
- Path is gitignored (or explicitly listed under "tracked generated").
- File header (if any) carries `Status: Generated (do not edit).`
- Never the sole source of any fact in `PROJECT_STATE.md` or any ADR.

Canonical artifacts must satisfy ALL of these:
- Hand-curated or explicitly promoted from a generated output via a
  documented commit (e.g., "promote canonical success render").
- Tracked in git.
- Referenced by at least one canonical doc OR test.
- If it CAN be regenerated (e.g., a PNG), the script that regenerates
  it produces a byte-identical (or at minimum semantically equivalent)
  result.

Examples:

| File | Category | Why |
|---|---|---|
| `runs/quadrado_v4_canonical/quadrado.skp` | Generated | Reproducible from `fixtures/quadrado/consensus_with_window.json`. Lives in gitignored `runs/`. |
| `docs/specs/_assets/quadrado_canonical_success_render.png` | Canonical | Promoted from a `runs/` output and committed as the reference image. Referenced by `docs/specs/quadrado_demo_spec.md`. |
| `fixtures/quadrado/consensus_with_window.json` | Canonical | Hand-curated input fixture. Sole source of the canonical quadrado test. |
| `fixtures/planta_74/visual_evidence/diff_walls.png` | Canonical | Curated visual evidence for the 2026-05-14 visual fidelity gate. Referenced by `docs/protocols/visual_fidelity_gate_protocol.md`. |
| `runs/png_history/manifest.jsonl` | Generated | Appended by `tools/png_history.py` on every render. Gitignored under `/runs/`. |

---

## 5. Tracked vs ignored

What MUST be tracked (committed):
- All source code (`.py`, `.rb`).
- All canonical fixtures (`fixtures/**`).
- All `docs/**` except whatever is explicitly archived under
  `docs/_archive/<old-cycle>/` — those are tracked too, just clearly
  marked.
- `pyproject.toml`, `Gemfile.lint`, `requirements.txt`,
  `.rubocop.yml`, `.mcp.json`, `.env.example`.
- All CI configuration (`.github/workflows/**`).
- All `.claude/agents/**`, `.claude/commands/**`, `.claude/hooks/**`,
  `.claude/settings.json`.
- `tests/**`, `scripts/**`, `tools/**`.
- `ground_truth/**`, `patches/**`.
- `vendor/CubiCasa5k/README.md` + `.gitkeep` placeholders (the
  weights stay ignored, see vendor README).

What MUST be ignored (.gitignore):
- `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`,
  `.venv`, `*.egg-info`.
- `/runs/`, `/out/`, `/review/`.
- `*.log`, `.coverage`, `htmlcov/`, `dist/`, `build/`.
- `.idea/`, `.vscode/`, `.DS_Store`, `Thumbs.db`.
- `vendor/CubiCasa5k/weights/*.pkl|*.pth`,
  `vendor/CubiCasa5k/repo/`.
- `.claude/*` except the four team-shared subdirs above.
- `.env`, `.env.*` except `.env.example`.

What MAY be tracked even though it looks generated (allowed exceptions):
- `docs/diagnostics/*.png` and `*.svg` — explicit diagnostic evidence
  attached to a documented incident. Always near a `*.md` that
  references them.
- `docs/specs/_assets/*` — promoted canonical reference outputs.
- `fixtures/planta_74/visual_evidence/*.png` — canonical visual
  evidence for the visual fidelity gate.
- `fixtures/planta_74/skp_*.png`, `skp_*.skp` — promoted SKP outputs
  used as references in protocol docs.

These exceptions ALL satisfy "hand-curated and referenced by
canonical doc". A generated PNG sitting in `runs/` is NOT an
exception.

---

## 6. The single-cycle hygiene loop

Every autonomous cycle includes a lightweight hygiene pass:

1. Scan recent commits — anything land under `runs/` by mistake?
2. Scan root — any new `.py` or `.md` not classified?
3. Run `python scripts/project_state_check.py` — does any canonical
   doc / fixture / gate look stale?
4. If a deletion or archive is needed → open a SEPARATE `chore:`
   commit. Never bundle hygiene with algorithm changes.

Heavier audits (full inventory, all-`.md` classification, hygiene
report) ship as their own PR with `chore(repo): ...` titles. See
[`../CLAUDE.md`](../CLAUDE.md) §15 for the rules every hygiene PR
must follow + the §15 mandatory report fields:

- files removed (with reasons)
- files archived (with destination)
- files preserved (with the reference paths)
- reference searches performed (greps)
- validations executed (pytest / smoke / dashboard build)

---

## 7. Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial policy doc. Consolidates the five-category scheme + status header policy + don't-delete-blindly protocol + tracked-vs-ignored rules. Supersedes the implicit policy that lived only inside `docs/ops/repo_hygiene_audit_2026-05-10.md`. |
