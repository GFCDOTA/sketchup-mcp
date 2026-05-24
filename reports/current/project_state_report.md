# Project State Report

> **Status:** Generated (do not edit). Produced by `scripts/project_state_check.py`.
> **Generated:** 2026-05-24
> **Branch:** chore/repo-governance-anti-forgetting

## Summary

| Tier | Count |
|---|---|
| Hard PASS | 30 |
| Hard FAIL | 0 |
| Soft WARN | 9 |

Hard checks cover canonical docs, fixtures, scripts, CI workflows, and
the Status: header policy. Soft checks cover canonical tests / assets
that legitimately live on a feature branch ahead of develop.

## Hard failures

_none_ — every canonical doc / fixture / script listed in
`scripts/project_state_check.py` is present and non-empty.

## Soft warnings (feature-branch artifacts)

| Kind | Path | Note |
|---|---|---|
| gate    | `tests/test_quadrado_canonical_smoke.py`           | lives on `feature/window-aperture-semantics` |
| gate    | `tests/test_wall_shell_canonical.py`               | lives on `feature/window-aperture-semantics` |
| gate    | `tests/test_window_aperture_contract.py`           | lives on `feature/window-aperture-semantics` |
| gate    | `tests/test_window_aperture_geometry.py`           | lives on `feature/window-aperture-semantics` |
| fixture | `fixtures/quadrado/consensus_with_window.json`     | lives on `feature/window-aperture-semantics` |
| fixture | `fixtures/quadrado/consensus_empty.json`           | lives on `feature/window-aperture-semantics` |
| asset   | `docs/specs/_assets/quadrado_canonical_shell_polygon.json` | lives on `feature/window-aperture-semantics` |
| asset   | `docs/specs/_assets/quadrado_canonical_geometry_report.json` | lives on `feature/window-aperture-semantics` |
| asset   | `docs/specs/_assets/quadrado_canonical_success_render.png` | lives on `feature/window-aperture-semantics` |

These promote to hard failures the moment `feature/window-aperture-semantics`
lands on `develop` and they are still missing. Use `--strict` to surface
them locally.

## How to reproduce

```bash
python scripts/project_state_check.py            # human readable
python scripts/project_state_check.py --json     # machine readable
python scripts/project_state_check.py --strict   # WARN becomes FAIL
```

## Next action

When `feature/window-aperture-semantics` merges to develop, this report
should re-run and show `Soft WARN: 0`. If any soft entry is still
missing after the merge, file it against the merge PR.
