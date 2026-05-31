#!/usr/bin/env python3
"""Promote a build from runs/<plant>/ to the canonical artifacts/<plant>/.

This closes the TODO in specs/skp_artifact_layout.md and memory/artifact_policy.md:
manually copying + sidecar-rewriting + side-by-side generation is error-prone;
this script makes promotion a single deterministic command.

What it does
------------
1.  Validates the run dir has the minimum required files (.skp, renders, report).
2.  Copies .skp + renders + geometry_report.json to artifacts/<plant>/.
3.  Rewrites the sidecar (skp_path → canonical, adds source_run_path).
4.  Generates side_by_side_pdf_vs_skp.png via compose_side_by_side (if PDF exists).
5.  Writes/updates README.md provenance stub.

What it does NOT do
-------------------
- Run gates / tests  (caller is responsible — promote only after green gates).
- Touch fixtures/  or consensus.json  (never mutates canonical inputs).
- Replace existing artifacts without --force (safe by default).
- Decide IMPROVED/SAME/WORSE  (that is VISUAL_REVIEW, Felipe's call).

Usage
-----
    python -m tools.promote_artifact planta_74
    python -m tools.promote_artifact planta_74 --run-dir runs/planta_74
    python -m tools.promote_artifact planta_74 --force   # overwrite existing
    python -m tools.promote_artifact planta_74 --dry-run # show plan, no changes
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that MUST exist in the run dir before promotion is allowed.
REQUIRED_FILES = [
    "{plant}.skp",
    "model_top.png",
    "model_iso.png",
    "geometry_report.json",
]

# Files copied 1-to-1 from run → artifact (name mapping: run_name → artifact_name).
COPY_MAP = {
    "{plant}.skp": "{plant}.skp",
    "model_top.png": "{plant}_top.png",
    "model_iso.png": "{plant}_iso.png",
    "geometry_report.json": "geometry_report.json",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_run_dir(plant: str, run_dir: Path | None) -> Path:
    if run_dir:
        return run_dir
    # Conventional default: runs/<plant>/
    return REPO_ROOT / "runs" / plant


def _validate_run(run_dir: Path, plant: str) -> list[str]:
    """Return list of missing required files (empty = ok)."""
    missing = []
    for template in REQUIRED_FILES:
        name = template.format(plant=plant)
        if not (run_dir / name).exists():
            missing.append(name)
    return missing


def _rewrite_sidecar(
    artifact_skp: Path,
    source_run_skp: Path,
    consensus_sha256: str | None,
    promoted_at: str,
) -> dict:
    """Load the run-side sidecar, rewrite skp_path + add source_run_path, write next to artifact."""
    run_sidecar = source_run_skp.with_suffix(source_run_skp.suffix + ".metadata.json")
    if run_sidecar.exists():
        meta = json.loads(run_sidecar.read_text(encoding="utf-8"))
    else:
        # No sidecar in the run — build a minimal one from what we know.
        meta = {
            "schema_version": "1.0.0",
            "exporter": "build_plan_shell_skp",
            "consensus_sha256": consensus_sha256 or "",
            "created_at": promoted_at,
        }
    # Rewrite: skp_path → canonical artifact path; preserve build provenance.
    meta["skp_path"] = str(artifact_skp)
    meta["source_run_path"] = str(source_run_skp)
    meta["promoted_at"] = promoted_at

    artifact_sidecar = artifact_skp.with_suffix(artifact_skp.suffix + ".metadata.json")
    artifact_sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _generate_side_by_side(plant: str, artifact_dir: Path, dry_run: bool) -> str:
    """Call compose_side_by_side if the PDF is available. Returns status string."""
    # PDF is expected at <repo_root>/<plant>.pdf  (conventional location).
    pdf = REPO_ROOT / f"{plant}.pdf"
    top = artifact_dir / f"{plant}_top.png"
    iso = artifact_dir / f"{plant}_iso.png"
    out = artifact_dir / "side_by_side_pdf_vs_skp.png"

    if not pdf.exists():
        return f"SKIPPED (no PDF found at {pdf})"
    if not top.exists() or not iso.exists():
        return "SKIPPED (renders not yet copied)"

    if dry_run:
        return f"DRY-RUN (would compose {pdf.name} + top + iso → {out.name})"

    cmd = [
        sys.executable, "-m", "tools.compose_side_by_side",
        "--pdf", str(pdf),
        "--top", str(top),
        "--iso", str(iso),
        "--out", str(out),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60
        )
        if result.returncode != 0:
            return f"FAILED: {(result.stderr or result.stdout or '?')[:200]}"
        return f"OK ({out.name})"
    except Exception as e:
        return f"FAILED: {e}"


def _write_readme(plant: str, artifact_dir: Path, meta: dict,
                  git_sha: str, dry_run: bool) -> None:
    """Write/update the provenance README stub."""
    readme = artifact_dir / "README.md"
    consensus_path = f"fixtures/{plant}/consensus.json"
    # Prefer the consensus path from the sidecar if available.
    promoted_at = meta.get("promoted_at", _now_iso())
    content = f"""# {plant}

## Build provenance

- Input: `{consensus_path}`
- Built: {promoted_at[:10]}
- Promoted: {promoted_at}
- Commit: {git_sha}

## Reproduce

```bash
python -m tools.build_plan_shell_skp \\
  {consensus_path} \\
  --out runs/{plant}/{plant}.skp

python -m tools.promote_artifact {plant}
```

## Status

- room_fidelity: (fill after VISUAL_REVIEW)
- wall_fidelity: (fill after VISUAL_REVIEW)
- contract_tests: (run `pytest tests/ -q`)

## VISUAL_REVIEW

Compare `side_by_side_pdf_vs_skp.png` to the original PDF.
Verdict (IMPROVED / SAME / WORSE) is Felipe's call — never auto.
"""
    if not dry_run:
        readme.write_text(content, encoding="utf-8")


def _git_sha(repo: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(repo), timeout=10,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def promote(
    plant: str,
    *,
    run_dir: Path | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Promote a run to the canonical artifact directory.

    Returns 0 on success, non-zero on error.
    """
    run_dir = _resolve_run_dir(plant, run_dir)
    artifact_dir = REPO_ROOT / "artifacts" / plant

    print(f"[promote] plant     : {plant}")
    print(f"[promote] run_dir   : {run_dir}")
    print(f"[promote] artifact  : {artifact_dir}")
    print(f"[promote] dry_run   : {dry_run}  force: {force}")

    # 1. Validate run dir
    missing = _validate_run(run_dir, plant)
    if missing:
        print(f"[promote] ERROR: run_dir missing required files: {missing}")
        print(f"[promote]        Build first, then promote.")
        return 1

    # 2. Check existing artifact
    if artifact_dir.exists() and not force:
        existing_skp = artifact_dir / f"{plant}.skp"
        if existing_skp.exists():
            print(f"[promote] WARN: {existing_skp} already exists. Use --force to overwrite.")
            return 2

    now = _now_iso()
    git_sha = _git_sha(REPO_ROOT)

    if not dry_run:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy files
    for run_tmpl, art_tmpl in COPY_MAP.items():
        src = run_dir / run_tmpl.format(plant=plant)
        dst = artifact_dir / art_tmpl.format(plant=plant)
        if src.exists():
            if not dry_run:
                shutil.copy2(src, dst)
            print(f"[promote] copy    : {src.name} → {dst.name}")
        else:
            print(f"[promote] SKIP    : {src.name} (not found in run)")

    # 4. Rewrite sidecar
    artifact_skp = artifact_dir / f"{plant}.skp"
    source_run_skp = run_dir / f"{plant}.skp"
    consensus_sha = None
    # Try to get consensus sha from the run-side geometry_report.json
    report_path = run_dir / "geometry_report.json"
    if report_path.exists():
        try:
            rpt = json.loads(report_path.read_text(encoding="utf-8"))
            consensus_sha = rpt.get("consensus_sha256") or rpt.get("consensus_sha")
        except Exception:
            pass
    if not dry_run:
        meta = _rewrite_sidecar(artifact_skp, source_run_skp, consensus_sha, now)
    else:
        meta = {"promoted_at": now}
        print(f"[promote] DRY-RUN : would rewrite sidecar ({plant}.skp.metadata.json)")

    # 5. Side-by-side
    sbs_status = _generate_side_by_side(plant, artifact_dir, dry_run)
    print(f"[promote] side-by-side: {sbs_status}")

    # 6. README provenance
    _write_readme(plant, artifact_dir, meta, git_sha, dry_run)
    if not dry_run:
        print(f"[promote] readme  : README.md written")
    else:
        print(f"[promote] DRY-RUN : would write README.md")

    print(f"[promote] {'DRY-RUN COMPLETE' if dry_run else 'DONE'} — "
          f"{'no files written' if dry_run else str(artifact_dir)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plant", help="Plant name (e.g. planta_74, quadrado)")
    ap.add_argument("--run-dir", type=Path,
                    help="Path to the run directory (default: runs/<plant>/)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing artifacts/<plant>/")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would happen without writing anything")
    args = ap.parse_args()
    return promote(
        args.plant,
        run_dir=args.run_dir,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
