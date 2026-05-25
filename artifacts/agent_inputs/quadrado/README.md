# Quadrado — agent inputs (internal)

> **Status:** Canonical (pointer doc)
> **Type:** Internal — agent / test inputs
> **Updated:** 2026-05-25
> **Policy:** [`../../../docs/ARTIFACT_POLICY.md`](../../../docs/ARTIFACT_POLICY.md)
> **Human-facing counterpart:** [`../../human_review/quadrado/`](../../human_review/quadrado/)

This folder is the **agent / test plane** for the quadrado canonical
fixture. It exists per the artifact-separation policy
(`docs/ARTIFACT_POLICY.md`) but, to avoid duplicating canonical files
and breaking existing references in ADRs + smoke tests, the actual
JSON inputs continue to live at their original canonical paths. This
README is the pointer table.

## Canonical input files (live at their original tracked paths)

| Role | Canonical path |
|---|---|
| Input consensus (with window — the build input for `quadrado_canonical_with_window.skp`) | [`../../../fixtures/quadrado/consensus_with_window.json`](../../../fixtures/quadrado/consensus_with_window.json) |
| Input consensus (empty room — sanity check fixture) | [`../../../fixtures/quadrado/consensus_empty.json`](../../../fixtures/quadrado/consensus_empty.json) |
| Expected shell polygon (canonical) | [`../../../docs/specs/_assets/quadrado_canonical_shell_polygon.json`](../../../docs/specs/_assets/quadrado_canonical_shell_polygon.json) |
| Expected geometry report (canonical) | [`../../../docs/specs/_assets/quadrado_canonical_geometry_report.json`](../../../docs/specs/_assets/quadrado_canonical_geometry_report.json) |
| Reference render (PNG) | [`../../../docs/specs/_assets/quadrado_canonical_success_render.png`](../../../docs/specs/_assets/quadrado_canonical_success_render.png) |

## Why pointers, not copies

Duplicating these files into `artifacts/agent_inputs/quadrado/`
would:

- Break smoke tests that reference the `fixtures/quadrado/` and
  `docs/specs/_assets/` paths directly.
- Require coupled updates to ADR-002, ADR-007, ADR-003, and the
  quadrado spec, all of which cite those paths.
- Introduce a synchronisation hazard (two copies, one drifts).

Going forward, agent_inputs/ may hold:

- **New** input fixtures created for future slices that don't yet have
  canonical homes elsewhere
- **Cached debug data** produced by tooling runs (when not gitignored)
- **Diagnostic snapshots** captured during a specific cycle

For now, the canonical paths above are the source of truth.

## Cross-references

- Human-reviewable output: [`../../human_review/quadrado/`](../../human_review/quadrado/) (the `.skp` is the deliverable)
- Spec: [`../../../docs/specs/quadrado_demo_spec.md`](../../../docs/specs/quadrado_demo_spec.md)
- Policy: [`../../../docs/ARTIFACT_POLICY.md`](../../../docs/ARTIFACT_POLICY.md)
