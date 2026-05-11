"""One-shot runner for the human-openings ground-truth pipeline.

Chains the 5 steps (extract -> apply -> gate -> overlay -> SKP) into
a single command. Fails loud if the human annotation PNG is missing
or the gate verdict is FAIL.

Default paths are the planta_74 conventions:
- Annotation:  fixtures/planta_74/human_openings_annotation.png
- Consensus:   runs/vector/consensus_model.json (or --consensus)
- Truth out:   fixtures/planta_74/human_openings_truth.json
- Patched:     runs/vector/consensus_human.json
- Report:      fixtures/planta_74/human_openings_report.json
- Overlay:     fixtures/planta_74/human_openings_overlay.png

The runner does NOT spawn SketchUp by default. Pass --run-skp to
chain the smoke harness on top (Will spawn SU 2026, slow).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], step: str) -> None:
    print(f"\n=== {step} ===")
    print("  $ " + " ".join(cmd))
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        print(f"[FAIL] step '{step}' returned exit code {res.returncode}",
              file=sys.stderr)
        sys.exit(res.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="One-shot human-openings ground-truth runner."
    )
    ap.add_argument("--annotation", type=Path,
                    default=Path("fixtures/planta_74/human_openings_annotation.png"),
                    help="Annotated PNG (must exist; pipeline fails loud if missing).")
    ap.add_argument("--consensus", type=Path,
                    default=Path("runs/vector/consensus_model.json"),
                    help="Input consensus_model.json with walls + rooms.")
    ap.add_argument("--pdf", type=Path, default=Path("planta_74.pdf"))
    ap.add_argument("--truth-out", type=Path,
                    default=Path("fixtures/planta_74/human_openings_truth.json"))
    ap.add_argument("--consensus-out", type=Path,
                    default=Path("runs/vector/consensus_human.json"))
    ap.add_argument("--report-out", type=Path,
                    default=Path("fixtures/planta_74/human_openings_report.json"))
    ap.add_argument("--overlay-out", type=Path,
                    default=Path("fixtures/planta_74/human_openings_overlay.png"))
    ap.add_argument("--mode", choices=["replace", "merge"], default="replace",
                    help="apply_human_openings mode. 'replace' (default): "
                         "human wins, detector openings discarded.")
    ap.add_argument("--no-strict-gate", action="store_true",
                    help="Don't exit non-zero on gate FAIL (still prints "
                         "the report).")
    ap.add_argument("--run-skp", action="store_true",
                    help="After the gate passes, spawn the smoke SKP "
                         "export (slow; spawns SU 2026).")
    ap.add_argument("--pdf-width-pts", type=float, default=595.0)
    ap.add_argument("--pdf-height-pts", type=float, default=842.0)
    args = ap.parse_args()

    py = sys.executable

    if not args.annotation.exists():
        print(
            f"[blocker] missing required file: {args.annotation}\n"
            f"  Drop the human-annotated PNG at that path and rerun.\n"
            f"  See fixtures/planta_74/README.md for the color contract\n"
            f"  (green = interior_door, magenta = window, orange = glazed_balcony).",
            file=sys.stderr,
        )
        sys.exit(64)  # EX_USAGE — missing input artifact

    if not args.consensus.exists():
        print(
            f"[blocker] missing consensus: {args.consensus}\n"
            f"  Run the canonical 3-stage build first:\n"
            f"    python -m tools.build_vector_consensus {args.pdf} "
            f"--out {args.consensus} --detect-openings\n"
            f"    python -m tools.extract_room_labels {args.pdf} "
            f"--out labels.json\n"
            f"    python -m tools.rooms_from_seeds {args.consensus} "
            f"labels.json --out {args.consensus} --method polygonize",
            file=sys.stderr,
        )
        sys.exit(64)

    # Step 1: extract
    _run([py, "-m", "tools.extract_human_openings",
          str(args.annotation),
          "--consensus", str(args.consensus),
          "--out", str(args.truth_out),
          "--pdf-width-pts", str(args.pdf_width_pts),
          "--pdf-height-pts", str(args.pdf_height_pts)],
         step="1/5 extract_human_openings")

    # Step 2: apply
    _run([py, "-m", "tools.apply_human_openings",
          "--consensus", str(args.consensus),
          "--truth", str(args.truth_out),
          "--out", str(args.consensus_out),
          "--mode", args.mode],
         step="2/5 apply_human_openings")

    # Step 3: gate
    gate_cmd = [py, "-m", "tools.structural_checks_human",
                "--consensus", str(args.consensus_out),
                "--truth", str(args.truth_out),
                "--out", str(args.report_out)]
    if not args.no_strict_gate:
        gate_cmd.append("--strict")
    _run(gate_cmd, step="3/5 structural_checks_human")

    # Step 4: overlay
    _run([py, "-m", "tools.render_human_openings_overlay",
          "--pdf", str(args.pdf),
          "--truth", str(args.truth_out),
          "--consensus", str(args.consensus_out),
          "--out", str(args.overlay_out)],
         step="4/5 render_human_openings_overlay")

    # Step 5: SKP (optional)
    if args.run_skp:
        _run([py, "scripts/smoke/smoke_skp_export.py",
              "--consensus", str(args.consensus_out),
              "--force-skp"],
             step="5/5 smoke_skp_export")
    else:
        print("\n=== 5/5 skipped (smoke_skp_export) ===")
        print("  Pass --run-skp to spawn SU 2026 and export the .skp.")

    print("\n[ok] human-openings pipeline complete.")
    print(f"  truth:       {args.truth_out}")
    print(f"  consensus:   {args.consensus_out}")
    print(f"  gate report: {args.report_out}")
    print(f"  overlay:     {args.overlay_out}")


if __name__ == "__main__":
    main()
