"""Pipeline benchmark — measure stage-by-stage timing without changing
pipeline behavior.

Reads a PDF, runs each stage of the vector and (optionally) raster
pipeline, captures wall-clock time + RSS memory peak per stage, and
emits a JSON report.

Usage:
    python scripts/benchmark/bench_pipeline.py --pdf planta.pdf --out reports/perf_baseline.json
    python scripts/benchmark/bench_pipeline.py --pdf planta.pdf --runs 3 --warmup 1
    python scripts/benchmark/bench_pipeline.py --help

Does NOT modify pipeline code, schema, thresholds, or outputs.
Stages that are unavailable (e.g. SketchUp not installed) are marked
'skipped' instead of failing the whole run.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _peak_rss_mb() -> float:
    """Best-effort peak RSS in MB. Returns 0.0 if unavailable."""
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in KB on Linux, bytes on macOS
        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024 * 1024)
        return usage.ru_maxrss / 1024
    except ImportError:
        # Windows: use psutil if available, otherwise 0
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except ImportError:
            return 0.0


@contextmanager
def _stage_timer(name: str, results: dict[str, dict[str, Any]]):
    """Context manager that times a stage and records into results."""
    gc.collect()
    rss_before = _peak_rss_mb()
    t0 = time.perf_counter()
    status = "ok"
    error_msg = ""
    try:
        yield
    except Exception as e:
        status = "failed"
        error_msg = f"{type(e).__name__}: {e}"
        # do NOT re-raise — bench should keep going to next stage
    finally:
        elapsed = time.perf_counter() - t0
        rss_after = _peak_rss_mb()
        results[name] = {
            "status": status,
            "elapsed_s": round(elapsed, 4),
            "rss_before_mb": round(rss_before, 1),
            "rss_after_mb": round(rss_after, 1),
            "rss_delta_mb": round(rss_after - rss_before, 1),
            "error": error_msg or None,
        }


def _run_one_pass(pdf_path: Path, out_dir: Path) -> dict[str, Any]:
    """Single benchmark pass — runs each stage in order, captures
    timing per stage. Returns dict of stage_name -> stage_metrics."""
    results: dict[str, dict[str, Any]] = {}

    # ---- Vector pipeline (the recommended path for vectorial PDFs) ----

    consensus_path = out_dir / "consensus_model.json"
    labels_path = out_dir / "labels.json"

    with _stage_timer("vector_consensus", results):
        # build_vector_consensus: PDF -> walls + soft_barriers
        from tools.build_vector_consensus import main as bvc_main
        bvc_main([str(pdf_path), "--out", str(consensus_path)])

    with _stage_timer("extract_room_labels", results):
        from tools.extract_room_labels import main as erl_main
        erl_main([str(pdf_path), "--out", str(labels_path)])

    with _stage_timer("rooms_from_seeds", results):
        from tools.rooms_from_seeds import main as rfs_main
        rfs_main([str(consensus_path), str(labels_path)])

    with _stage_timer("extract_openings_vector", results):
        from tools.extract_openings_vector import main as eov_main
        eov_main([
            str(pdf_path),
            "--consensus", str(consensus_path),
            "--mode", "replace",
        ])

    # ---- Render (matplotlib, no SketchUp dependency) ----
    with _stage_timer("render_axon_top", results):
        try:
            from tools.render_axon import main as ra_main
            ra_main([
                str(consensus_path),
                "--out", str(out_dir / "axon_top.png"),
                "--mode", "top",
            ])
        except (ImportError, ModuleNotFoundError) as e:
            results["render_axon_top"] = {
                "status": "skipped",
                "elapsed_s": 0.0,
                "rss_before_mb": 0.0,
                "rss_after_mb": 0.0,
                "rss_delta_mb": 0.0,
                "error": f"render_axon unavailable: {e}",
            }

    # ---- SketchUp export (optional — requires SU2026 installed) ----
    skp_path = out_dir / "out.skp"
    su_exe = Path("C:/Program Files/SketchUp/SketchUp 2026/SketchUp/SketchUp.exe")
    if su_exe.exists():
        with _stage_timer("sketchup_export", results):
            from tools.skp_from_consensus import main as sfc_main
            sfc_main([
                str(consensus_path),
                "--out", str(skp_path),
                "--timeout", "180",
            ])
    else:
        results["sketchup_export"] = {
            "status": "skipped",
            "elapsed_s": 0.0,
            "rss_before_mb": 0.0,
            "rss_after_mb": 0.0,
            "rss_delta_mb": 0.0,
            "error": "SketchUp 2026 not installed on this machine",
        }

    # ---- Validator (optional — depends on PNG manifest existing) ----
    with _stage_timer("validation", results):
        try:
            from validator.run import main as vr_main
            vr_main(["--once"])
        except SystemExit:
            # validator/run.py uses argparse with sys.exit; treat as ok
            pass
        except Exception as e:
            results["validation"]["status"] = "failed"
            results["validation"]["error"] = f"{type(e).__name__}: {e}"

    return results


def _summarize_runs(runs: list[dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Aggregate N runs into median/min/max per stage."""
    if not runs:
        return {}
    stage_names = list(runs[0].keys())
    summary: dict[str, Any] = {}
    for stage in stage_names:
        timings = [r[stage]["elapsed_s"] for r in runs if r[stage]["status"] == "ok"]
        statuses = [r[stage]["status"] for r in runs]
        if timings:
            summary[stage] = {
                "status_counts": {s: statuses.count(s) for s in set(statuses)},
                "elapsed_s_median": round(statistics.median(timings), 4),
                "elapsed_s_min": round(min(timings), 4),
                "elapsed_s_max": round(max(timings), 4),
                "elapsed_s_cv": round(
                    statistics.stdev(timings) / statistics.mean(timings)
                    if len(timings) >= 2 else 0.0,
                    4,
                ),
                "rss_after_mb_max": max(r[stage]["rss_after_mb"] for r in runs),
            }
        else:
            summary[stage] = {
                "status_counts": {s: statuses.count(s) for s in set(statuses)},
                "elapsed_s_median": None,
                "elapsed_s_min": None,
                "elapsed_s_max": None,
                "elapsed_s_cv": None,
                "rss_after_mb_max": None,
            }
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Benchmark the floor-plan extraction pipeline stage by stage.",
    )
    p.add_argument("--pdf", required=True, type=Path,
                   help="Path to input PDF (e.g. planta_74.pdf)")
    p.add_argument("--out", default="reports/perf_baseline.json", type=Path,
                   help="Output JSON path (default: reports/perf_baseline.json)")
    p.add_argument("--runs", type=int, default=1,
                   help="Number of measurement runs (median is reported)")
    p.add_argument("--warmup", type=int, default=0,
                   help="Number of warmup runs (discarded)")
    p.add_argument("--scratch", default=None, type=Path,
                   help="Scratch dir for intermediate outputs (default: tmp under out parent)")
    p.add_argument("--label", default="",
                   help="Free-form label for this benchmark run")
    args = p.parse_args(argv)

    pdf_path = args.pdf.resolve()
    if not pdf_path.exists():
        print(f"[bench] ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scratch = args.scratch or (out_path.parent / "_bench_scratch")
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(REPO_ROOT))

    print(f"[bench] PDF: {pdf_path}")
    print(f"[bench] Runs: {args.runs} (warmup: {args.warmup})")
    print(f"[bench] Out:  {out_path}")
    print(f"[bench] Scratch: {scratch}")

    pdf_sha = _file_sha256(pdf_path)
    print(f"[bench] PDF SHA256: {pdf_sha[:16]}...")

    # Warmup runs (discarded)
    for i in range(args.warmup):
        warmup_dir = scratch / f"warmup_{i}"
        warmup_dir.mkdir(parents=True, exist_ok=True)
        print(f"[bench] Warmup run {i + 1}/{args.warmup}...")
        _run_one_pass(pdf_path, warmup_dir)

    # Measurement runs
    runs: list[dict[str, dict[str, Any]]] = []
    for i in range(args.runs):
        run_dir = scratch / f"run_{i}"
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"[bench] Run {i + 1}/{args.runs}...")
        run_results = _run_one_pass(pdf_path, run_dir)
        runs.append(run_results)
        # Print quick summary for this run
        for stage, m in run_results.items():
            status_marker = {"ok": "✓", "failed": "✗", "skipped": "—"}.get(m["status"], "?")
            print(f"  {status_marker} {stage:30s} {m['elapsed_s']:>8.3f}s  ({m['status']})")

    summary = _summarize_runs(runs)

    report = {
        "schema_version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "git_commit": _git_commit(),
        "git_branch": _git_branch(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "input": {
            "pdf_path": str(pdf_path),
            "pdf_sha256": pdf_sha,
            "pdf_size_bytes": pdf_path.stat().st_size,
        },
        "command": " ".join([sys.executable, *sys.argv]),
        "config": {
            "runs": args.runs,
            "warmup": args.warmup,
            "scratch": str(scratch),
        },
        "summary": summary,
        "runs_raw": runs,
    }

    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[bench] Report written to {out_path}")
    print(f"[bench] Total stages: {len(summary)}")

    # Total time per run summary
    total_per_run = [
        sum(r[s]["elapsed_s"] for s in r if r[s]["status"] == "ok")
        for r in runs
    ]
    if total_per_run:
        print(f"[bench] Total time (ok stages, median of {len(total_per_run)}): "
              f"{statistics.median(total_per_run):.2f}s")

    return 0


if __name__ == "__main__":
    sys.exit(main())
