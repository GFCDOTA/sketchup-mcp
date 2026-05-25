# tools/legacy/

> **Status:** Active
> **Type:** Directory README — explains what lives here
> **Updated:** 2026-05-24
> **Policy:** [`../../docs/REPO_HYGIENE.md`](../../docs/REPO_HYGIENE.md) §1 (Active category)

Scripts that pre-date the canonical layout but still have at least one
live caller (test, doc, manual workflow). Moved out of the repo root
(W001 in [`../repo_health_gate.py`](../repo_health_gate.py)) so the
root only holds entry points.

| Script | Last live caller | Migration notes |
|---|---|---|
| `proto_colored.py`     | `tests/test_proto_cli.py::test_proto_colored_help_runs` | dual-channel filter (RED walls + BROWN peitoril), CLI refactored 2026-05-08 |
| `proto_red.py`         | `tests/test_proto_cli.py::test_proto_red_help_runs` + `test_proto_red_missing_input_exits_nonzero` | red-channel walls filter, CLI refactored 2026-05-08 |
| `render_sidebyside.py` | `tests/test_proto_cli.py::test_render_sidebyside_help_runs` + `test_render_sidebyside_crop_validator_rejects_bad_spec` | painted-vs-overlay diptych renderer, CLI refactored 2026-05-08 |

## When to delete an entry

A script leaves this directory only when:

1. Every live caller has been migrated to a canonical replacement (or
   the caller itself has been removed).
2. A `git log -- tools/legacy/<script>` confirms no activity in the
   last 90 days.
3. The deletion ships in its own `chore: remove obsolete legacy
   tool` commit with the `rg` reference proof in the message body
   (per [`../../docs/REPO_HYGIENE.md`](../../docs/REPO_HYGIENE.md) §3).

## When to add an entry

Anything currently at repo root with `W001` warning that has at least
one live caller (tests, docs, scripts, CI). For zero-reference scripts,
prefer outright deletion in the don't-delete-blindly chore commit
instead of parking here.
