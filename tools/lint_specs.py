"""Standalone linter for ``specs/**/*.spec.yaml`` files.

Cheaper than running the full ``spec_harness`` when the only question
is "do my specs PARSE correctly and use known rule types?". The
harness needs a consensus + reports to evaluate; the linter only
needs the spec files themselves. Used by CI as a pre-check and by
operators editing specs locally.

Checks performed per spec:

  - YAML parses (no syntax error);
  - Document root is a mapping;
  - Required top-level keys present: ``schema_version``, ``target``,
    ``contracts``;
  - ``contracts`` is a list;
  - Each contract has ``id``, ``severity``, ``rule``;
  - ``severity`` is one of {critical, warn, info};
  - ``rule.type`` is a known dispatcher in
    ``tools.spec_harness._RULE_DISPATCHERS``;
  - No duplicate contract ``id`` within the same spec file;
  - Across all spec files in the scan, no duplicate contract ``id``
    globally (so cross-file references — e.g., the spec_coverage
    KNOWN_FP_SPEC_LINKS table — stay unambiguous).

Exit code:

  0 — every spec passed every check
  1 — at least one spec failed; details in stderr / stdout

Usage:

  python -m tools.lint_specs                  # scan default specs/
  python -m tools.lint_specs --specs-dir X    # scan X
  python -m tools.lint_specs --strict-warns   # promote warnings to errors

The linter does NOT modify spec files. Run after edits, before commit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml  # noqa: I001 — third-party last (repo convention)

from tools.spec_harness import _RULE_DISPATCHERS

VALID_SEVERITIES = frozenset({"critical", "warn", "info"})


def lint_one(path: Path) -> tuple[list[str], list[str]]:
    """Lint a single spec YAML. Returns (errors, warnings).

    Errors block the linter (exit 1); warnings are reported but don't
    fail unless ``--strict-warns`` is passed at the CLI level.
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return ([f"cannot read {path}: {e}"], [])

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return ([f"{path}: YAML parse error: {e}"], [])

    if not isinstance(data, dict):
        return ([f"{path}: root must be a mapping, got {type(data).__name__}"], [])

    # Required top-level keys.
    for key in ("schema_version", "target", "contracts"):
        if key not in data:
            errors.append(f"{path}: missing required top-level key {key!r}")

    contracts = data.get("contracts")
    if not isinstance(contracts, list):
        errors.append(
            f"{path}: 'contracts' must be a list, got {type(contracts).__name__}"
        )
        return (errors, warnings)

    seen_ids: set[str] = set()
    for i, c in enumerate(contracts):
        if not isinstance(c, dict):
            errors.append(
                f"{path}: contracts[{i}] must be a mapping, got "
                f"{type(c).__name__}"
            )
            continue
        cid = c.get("id")
        if not cid or not isinstance(cid, str):
            errors.append(
                f"{path}: contracts[{i}] missing string 'id'")
            continue
        if cid in seen_ids:
            errors.append(
                f"{path}: contracts[{i}] id={cid!r} duplicates an earlier "
                "contract id in the same spec file"
            )
        seen_ids.add(cid)

        sev = c.get("severity") or "warn"
        if sev not in VALID_SEVERITIES:
            errors.append(
                f"{path}: contract {cid!r} severity {sev!r} not in "
                f"{sorted(VALID_SEVERITIES)}"
            )

        rule = c.get("rule")
        if not isinstance(rule, dict):
            errors.append(
                f"{path}: contract {cid!r} missing 'rule' mapping")
            continue
        rule_type = rule.get("type")
        if not rule_type:
            errors.append(
                f"{path}: contract {cid!r} rule missing 'type'")
            continue
        if rule_type not in _RULE_DISPATCHERS:
            errors.append(
                f"{path}: contract {cid!r} unknown rule type "
                f"{rule_type!r}; supported: {sorted(_RULE_DISPATCHERS)}"
            )

        # Soft checks (warnings) — encourage but don't enforce.
        if not c.get("description"):
            warnings.append(
                f"{path}: contract {cid!r} missing 'description' "
                "(operator-facing rationale)"
            )

    return (errors, warnings)


def lint_dir(specs_dir: Path) -> tuple[list[str], list[str], int]:
    """Lint every ``*.spec.yaml`` under ``specs_dir`` recursively.

    Returns (all_errors, all_warnings, files_scanned). Cross-file
    checks (e.g., global ID uniqueness) are folded into all_errors.
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []
    yamls = sorted(specs_dir.rglob("*.spec.yaml"))
    global_ids: dict[str, Path] = {}
    for sp in yamls:
        errs, warns = lint_one(sp)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        # Collect contract ids for the cross-file uniqueness pass.
        if errs:
            # Skip cross-file check for files that already failed —
            # error stream would otherwise drown in cascades.
            continue
        try:
            data = yaml.safe_load(sp.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        for c in (data or {}).get("contracts") or []:
            cid = c.get("id") if isinstance(c, dict) else None
            if not cid:
                continue
            if cid in global_ids and global_ids[cid] != sp:
                all_errors.append(
                    f"contract id {cid!r} appears in BOTH "
                    f"{global_ids[cid]} and {sp} — IDs must be globally "
                    "unique so KNOWN_FP_SPEC_LINKS references resolve"
                )
            else:
                global_ids[cid] = sp
    return (all_errors, all_warnings, len(yamls))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs-dir", type=Path, default=Path("specs"))
    ap.add_argument("--strict-warns", action="store_true",
                    help="treat warnings as errors (exit 1 on any)")
    args = ap.parse_args(argv)

    if not args.specs_dir.exists():
        print(f"[err] specs dir {args.specs_dir} does not exist",
              file=sys.stderr)
        return 1

    errors, warnings, n = lint_dir(args.specs_dir)

    for w in warnings:
        print(f"[warn] {w}")
    for e in errors:
        print(f"[err]  {e}", file=sys.stderr)

    failed = bool(errors) or (args.strict_warns and warnings)
    if failed:
        print(
            f"\n[summary] {len(errors)} error(s), {len(warnings)} "
            f"warning(s) across {n} spec file(s) — FAIL",
            file=sys.stderr,
        )
        return 1
    print(
        f"\n[summary] 0 errors, {len(warnings)} warning(s) across "
        f"{n} spec file(s) — OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
