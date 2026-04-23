"""F11 — Multiplant validation runner.

Runs the PDF pipeline for every expected-JSON fixture in runs/validation/ and
emits a CSV report describing whether the observed model still matches the
frozen expectations.

Two fixture schemas are supported:

  GOLDEN-style (exact counts + optional snapshot hash gate):
    {
      "pdf_filename": "p12_red.pdf",
      "expected_walls": 33,
      "expected_walls_tolerance": 2,
      "expected_rooms": 19,
      "expected_rooms_tolerance": 0,
      "expected_openings": 6,
      "expected_openings_tolerance": 1,
      "expected_largest_ratio_min": 1.0,
      "expected_orphan_node_max": 0,
      "expected_topology_snapshot_sha256": "<hex>"  # optional exact gate
    }

  RANGE-style (healthy bands, no hash gate):
    {
      "pdf_filename": "planta_74.pdf",
      "expected_walls_range": [120, 240],
      "expected_rooms_range": [11, 35],
      "expected_openings_range": [8, 30],
      "expected_largest_ratio_min": 0.90,
      "expected_orphan_node_max": 5
    }

The runner is deliberately dependency-light: argparse + stdlib only. It imports
the pipeline lazily so --help stays fast.

Exit codes:
  0  — every fixture overall_ok = True
  1  — at least one fixture failed
  2  — misconfiguration (missing PDF, unparsable fixture, etc.)

Determinism gate:
  --determinism-check NAME runs the fixture NAME three times and asserts the
  topology_snapshot_sha256 is identical across runs. Defaults to p12_red (the
  GOLDEN fixture). Skipped automatically when the fixture has no expected hash.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_DIR = REPO_ROOT / "runs" / "validation"

# Where to look for each PDF declared by a fixture. Order matters: first hit wins.
PDF_SEARCH_DIRS = [
    REPO_ROOT,
    REPO_ROOT / "runs" / "proto",
]

# Optional per-PDF peitoris override (keeps the p12 GOLDEN gate honest).
PEITORIS_MAP = {
    "p12_red.pdf": REPO_ROOT / "runs" / "proto" / "p12_peitoris.json",
}


@dataclass
class FixtureResult:
    plant_name: str
    pdf_filename: str
    walls_got: int = 0
    walls_ok: bool = False
    rooms_got: int = 0
    rooms_ok: bool = False
    openings_got: int = 0
    openings_ok: bool = False
    ratio_got: float = 0.0
    ratio_ok: bool = False
    orphan_got: int = 0
    orphan_ok: bool = False
    hash_got: str = ""
    hash_ok: bool = True  # defaults True when no hash gate is configured
    overall_ok: bool = False
    error: str = ""
    failures: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return {
            "plant_name": self.plant_name,
            "pdf_filename": self.pdf_filename,
            "walls_got": self.walls_got,
            "walls_ok": self.walls_ok,
            "rooms_got": self.rooms_got,
            "rooms_ok": self.rooms_ok,
            "openings_got": self.openings_got,
            "openings_ok": self.openings_ok,
            "ratio_got": f"{self.ratio_got:.4f}",
            "ratio_ok": self.ratio_ok,
            "orphan_got": self.orphan_got,
            "orphan_ok": self.orphan_ok,
            "hash_got": self.hash_got,
            "hash_ok": self.hash_ok,
            "overall_ok": self.overall_ok,
            "error": self.error,
            "failures": ";".join(self.failures),
        }


def _load_fixtures(validation_dir: Path) -> list[tuple[str, dict]]:
    if not validation_dir.exists():
        raise FileNotFoundError(f"validation dir missing: {validation_dir}")
    fixtures: list[tuple[str, dict]] = []
    for path in sorted(validation_dir.glob("*_expected.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"bad JSON in {path}: {exc}") from exc
        plant_name = path.stem.removesuffix("_expected")
        fixtures.append((plant_name, spec))
    return fixtures


def _resolve_pdf(pdf_filename: str) -> Path:
    for d in PDF_SEARCH_DIRS:
        candidate = d / pdf_filename
        if candidate.exists():
            return candidate
    searched = ", ".join(str(d) for d in PDF_SEARCH_DIRS)
    raise FileNotFoundError(
        f"pdf {pdf_filename!r} not found in any of: {searched}"
    )


def _run_pipeline(pdf_path: Path, output_dir: Path) -> dict:
    # Lazy import keeps --help fast and avoids side effects when fixtures are
    # simply being listed/linted.
    sys.path.insert(0, str(REPO_ROOT))
    from model.pipeline import run_pdf_pipeline  # noqa: WPS433

    peitoris_path = PEITORIS_MAP.get(pdf_path.name)
    peitoris = None
    if peitoris_path is not None and peitoris_path.exists():
        peitoris = json.loads(peitoris_path.read_text(encoding="utf-8"))
    result = run_pdf_pipeline(
        pdf_bytes=pdf_path.read_bytes(),
        filename=pdf_path.name,
        output_dir=output_dir,
        peitoris=peitoris,
    )
    return result.observed_model


def _compare(spec: dict, observed: dict, plant_name: str) -> FixtureResult:
    pdf_filename = spec.get("pdf_filename", "")
    result = FixtureResult(plant_name=plant_name, pdf_filename=pdf_filename)

    walls = len(observed.get("walls", []))
    rooms = len(observed.get("rooms", []))
    openings = len(observed.get("openings", []))
    conn = observed.get("metadata", {}).get("connectivity", {}) or {}
    ratio = float(conn.get("largest_component_ratio") or 0.0)
    orphan = int(conn.get("orphan_node_count") or 0)
    hash_got = observed.get("metadata", {}).get("topology_snapshot_sha256") or ""

    result.walls_got = walls
    result.rooms_got = rooms
    result.openings_got = openings
    result.ratio_got = ratio
    result.orphan_got = orphan
    result.hash_got = hash_got

    # Walls gate (GOLDEN exact+tol OR RANGE).
    if "expected_walls" in spec:
        lo = spec["expected_walls"] - int(spec.get("expected_walls_tolerance", 0))
        hi = spec["expected_walls"] + int(spec.get("expected_walls_tolerance", 0))
        result.walls_ok = lo <= walls <= hi
        if not result.walls_ok:
            result.failures.append(f"walls={walls} not in [{lo},{hi}]")
    elif "expected_walls_range" in spec:
        lo, hi = spec["expected_walls_range"]
        result.walls_ok = lo <= walls <= hi
        if not result.walls_ok:
            result.failures.append(f"walls={walls} not in [{lo},{hi}]")
    else:
        result.walls_ok = True

    # Rooms gate.
    if "expected_rooms" in spec:
        lo = spec["expected_rooms"] - int(spec.get("expected_rooms_tolerance", 0))
        hi = spec["expected_rooms"] + int(spec.get("expected_rooms_tolerance", 0))
        result.rooms_ok = lo <= rooms <= hi
        if not result.rooms_ok:
            result.failures.append(f"rooms={rooms} not in [{lo},{hi}]")
    elif "expected_rooms_range" in spec:
        lo, hi = spec["expected_rooms_range"]
        result.rooms_ok = lo <= rooms <= hi
        if not result.rooms_ok:
            result.failures.append(f"rooms={rooms} not in [{lo},{hi}]")
    else:
        result.rooms_ok = True

    # Openings gate.
    if "expected_openings" in spec:
        lo = spec["expected_openings"] - int(spec.get("expected_openings_tolerance", 0))
        hi = spec["expected_openings"] + int(spec.get("expected_openings_tolerance", 0))
        result.openings_ok = lo <= openings <= hi
        if not result.openings_ok:
            result.failures.append(f"openings={openings} not in [{lo},{hi}]")
    elif "expected_openings_range" in spec:
        lo, hi = spec["expected_openings_range"]
        result.openings_ok = lo <= openings <= hi
        if not result.openings_ok:
            result.failures.append(f"openings={openings} not in [{lo},{hi}]")
    else:
        result.openings_ok = True

    # Largest component ratio.
    ratio_min = float(spec.get("expected_largest_ratio_min", 0.0))
    result.ratio_ok = ratio >= ratio_min
    if not result.ratio_ok:
        result.failures.append(f"largest_component_ratio={ratio:.4f} < {ratio_min}")

    # Orphan nodes.
    orphan_max = int(spec.get("expected_orphan_node_max", 10**9))
    result.orphan_ok = orphan <= orphan_max
    if not result.orphan_ok:
        result.failures.append(f"orphan_node_count={orphan} > {orphan_max}")

    # Snapshot hash (GOLDEN-only).
    expected_hash = spec.get("expected_topology_snapshot_sha256")
    if expected_hash:
        result.hash_ok = hash_got == expected_hash
        if not result.hash_ok:
            result.failures.append(
                f"topology_snapshot_sha256 drift: got {hash_got!r}, expected {expected_hash!r}"
            )

    result.overall_ok = (
        result.walls_ok
        and result.rooms_ok
        and result.openings_ok
        and result.ratio_ok
        and result.orphan_ok
        and result.hash_ok
    )
    return result


def _write_report(results: list[FixtureResult], validation_dir: Path, timestamp: str) -> Path:
    report_path = validation_dir / f"report_{timestamp}.csv"
    fieldnames = [
        "plant_name",
        "pdf_filename",
        "walls_got",
        "walls_ok",
        "rooms_got",
        "rooms_ok",
        "openings_got",
        "openings_ok",
        "ratio_got",
        "ratio_ok",
        "orphan_got",
        "orphan_ok",
        "hash_got",
        "hash_ok",
        "overall_ok",
        "error",
        "failures",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.as_row())
    return report_path


def _determinism_check(
    fixtures: list[tuple[str, dict]],
    target: str,
    runs: int = 3,
) -> tuple[bool, list[str], str]:
    """Run `target` fixture `runs` times, return (ok, hashes, message).

    Skipped (ok=True, message="skipped") when the fixture isn't GOLDEN (no
    expected_topology_snapshot_sha256), because a range-style fixture has no
    determinism contract to enforce.
    """
    match = next(((n, s) for n, s in fixtures if n == target), None)
    if match is None:
        return False, [], f"fixture {target!r} not found"
    _, spec = match
    if not spec.get("expected_topology_snapshot_sha256"):
        return True, [], f"skipped (no hash gate on {target})"
    pdf_path = _resolve_pdf(spec["pdf_filename"])
    hashes: list[str] = []
    for i in range(runs):
        with tempfile.TemporaryDirectory(prefix=f"determ_{target}_{i}_") as td:
            obs = _run_pipeline(pdf_path, Path(td))
        hashes.append(obs.get("metadata", {}).get("topology_snapshot_sha256") or "")
    unique = set(hashes)
    if len(unique) == 1 and next(iter(unique)) != "":
        return True, hashes, f"stable hash {hashes[0]}"
    return False, hashes, f"divergent hashes: {hashes}"


def _print_summary(results: list[FixtureResult], determinism_msg: str) -> None:
    print("=" * 72)
    print("F11 multiplant validation summary")
    print("=" * 72)
    for r in results:
        flag = "PASS" if r.overall_ok else "FAIL"
        print(
            f"[{flag}] {r.plant_name:<20} walls={r.walls_got} "
            f"rooms={r.rooms_got} openings={r.openings_got} "
            f"ratio={r.ratio_got:.3f} orphan={r.orphan_got}"
        )
        if r.error:
            print(f"         error: {r.error}")
        for f in r.failures:
            print(f"         - {f}")
    print("-" * 72)
    print(f"determinism: {determinism_msg}")
    ok = sum(1 for r in results if r.overall_ok)
    print(f"{ok}/{len(results)} fixtures passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F11 multiplant validation runner for plan-extract-v2.",
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=VALIDATION_DIR,
        help=f"directory containing *_expected.json fixtures (default: {VALIDATION_DIR})",
    )
    parser.add_argument(
        "--determinism-check",
        default="p12_red",
        help="fixture name to run 3x for hash-stability gate (default: p12_red). "
        "Use --no-determinism-check to skip.",
    )
    parser.add_argument(
        "--no-determinism-check",
        action="store_true",
        help="skip determinism gate entirely",
    )
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="print fixture inventory without running the pipeline (debug only)",
    )
    args = parser.parse_args(argv)

    try:
        fixtures = _load_fixtures(args.validation_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not fixtures:
        print(f"error: no *_expected.json in {args.validation_dir}", file=sys.stderr)
        return 2

    if args.skip_pipeline:
        for name, spec in fixtures:
            print(f"{name}: {spec.get('pdf_filename', '<no pdf>')}")
        return 0

    results: list[FixtureResult] = []
    for name, spec in fixtures:
        pdf_filename = spec.get("pdf_filename", "")
        result = FixtureResult(plant_name=name, pdf_filename=pdf_filename)
        try:
            pdf_path = _resolve_pdf(pdf_filename)
        except FileNotFoundError as exc:
            result.error = str(exc)
            result.overall_ok = False
            results.append(result)
            continue
        with tempfile.TemporaryDirectory(prefix=f"validate_{name}_") as td:
            try:
                observed = _run_pipeline(pdf_path, Path(td))
            except Exception as exc:  # noqa: BLE001 — keep the runner resilient
                result.error = f"{type(exc).__name__}: {exc}"
                result.overall_ok = False
                results.append(result)
                continue
        result = _compare(spec, observed, plant_name=name)
        results.append(result)

    if args.no_determinism_check:
        determinism_ok, _, determinism_msg = True, [], "disabled via --no-determinism-check"
    else:
        determinism_ok, _, determinism_msg = _determinism_check(
            fixtures, target=args.determinism_check, runs=3
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = _write_report(results, args.validation_dir, timestamp)
    _print_summary(results, determinism_msg)
    print(f"report: {report_path}")

    all_passed = all(r.overall_ok for r in results) and determinism_ok
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
