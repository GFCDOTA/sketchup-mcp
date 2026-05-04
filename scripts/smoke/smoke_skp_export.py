"""SketchUp smoke harness — gates A through H.

Enforces the rule from CLAUDE.md §3: SketchUp is the LAST gate.
Cheap gates run first; SU spawns only after JSON, previews, and the
content-hash cache all agree the work is needed.

Gate sequence
-------------
A. Preparation       — verify env, ensure out-dir, locate sketchup.exe.
B. Acquire consensus — load JSON, defaults to runs/vector/consensus_model.json.
C. JSON structural   — walls/rooms/openings shape sanity-checks.
D. Preview PNG       — call tools.render_axon for top + axon (no SU).
E. Hash + cache      — SHA256 of (consensus + skp_from_consensus.py +
                       consume_consensus.rb) compared to a per-run cache marker.
F. Export .skp       — invoke tools.skp_from_consensus (skipped on
                       --skip-skp or cache hit unless --force-skp).
G. Validate .skp     — file exists, size > 1 KiB.
H. Reports           — write sketchup_smoke_report.{json,md}; refresh cache.

Any FAIL gate short-circuits to H (so reports are always written).

Companion doc: docs/validation/sketchup_smoke_workflow.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONSENSUS = REPO_ROOT / "runs" / "vector" / "consensus_model.json"
DEFAULT_SKETCHUP = Path(
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
CACHE_KEY_INPUTS = (
    Path("tools/skp_from_consensus.py"),
    Path("tools/consume_consensus.rb"),
)
# SU 2026 trial blocks the autorun plugin behind a Welcome dialog
# unless a positional .skp is on the command line (FP-007 / LL-009).
# tools.skp_from_consensus auto-picks any .skp in the output dir, so
# we drop a template there before invoking it.
SU_TEMPLATE_CANDIDATES = (
    Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
         r"\resources\en-US\Templates\Temp01a - Simple.skp"),
    Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
         r"\resources\en-US\Templates\Temp01b - Simple.skp"),
)


@dataclass
class GateResult:
    name: str
    status: str  # "pass" | "fail" | "skip"
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    consensus_path: str
    out_dir: str
    started_at: str
    finished_at: str = ""
    verdict: str = "pending"  # "pass" | "fail" | "pending"
    gates: list[GateResult] = field(default_factory=list)
    cache_hit: bool = False
    consensus_sha256: str = ""
    cache_key: str = ""

    def add(self, gate: GateResult) -> GateResult:
        self.gates.append(gate)
        return gate


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path) -> str:
    """Path relative to REPO_ROOT if possible, absolute string otherwise.

    Robust to out-dirs outside the repo (e.g. pytest tmp_path).
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _validate_consensus_shape(data: Any) -> None:
    """Cheap structural check. Raises ValueError on any violation."""
    if not isinstance(data, dict):
        raise ValueError("consensus root must be a JSON object")
    for key in ("walls", "rooms", "openings"):
        if key not in data:
            raise ValueError(f"missing required key: {key}")
        if not isinstance(data[key], list):
            raise ValueError(
                f"{key} must be a list, got {type(data[key]).__name__}"
            )
    for i, w in enumerate(data["walls"]):
        if not isinstance(w, dict):
            raise ValueError(f"walls[{i}] must be an object")
        for sub in ("start", "end"):
            v = w.get(sub)
            if not (
                isinstance(v, list)
                and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v)
            ):
                raise ValueError(
                    f"walls[{i}].{sub} must be [x, y] floats, got {v!r}"
                )


def _compute_cache_key(consensus_sha: str, repo_root: Path) -> str:
    """Cache key combines consensus hash with the source files that
    produce the .skp. If any of those changes, the cache is invalid.
    """
    h = hashlib.sha256()
    h.update(consensus_sha.encode("utf-8"))
    for rel in CACHE_KEY_INPUTS:
        p = repo_root / rel
        if p.exists():
            h.update(_sha256_path(p).encode("utf-8"))
        else:
            h.update(b"absent:" + rel.as_posix().encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def gate_a(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="A. Preparation", status="pass", started_at=_utc_now())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.sketchup is None:
        env = os.environ.get("SKETCHUP_EXE")
        args.sketchup = Path(env) if env else DEFAULT_SKETCHUP
    if args.skip_skp:
        g.message = f"out_dir={out_dir}, --skip-skp set (sketchup not required)"
    elif not args.sketchup.exists():
        g.status = "fail"
        g.message = (
            f"sketchup not found at {args.sketchup}. Set --sketchup, "
            f"env SKETCHUP_EXE, or pass --skip-skp."
        )
    else:
        g.message = f"out_dir={out_dir}, sketchup={args.sketchup}"
    report.out_dir = str(out_dir)
    g.finished_at = _utc_now()
    return g


def gate_b(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="B. Acquire consensus", status="pass",
                   started_at=_utc_now())
    path = Path(args.consensus)
    if not path.exists():
        g.status = "fail"
        g.message = f"consensus not found at {path}"
        g.finished_at = _utc_now()
        return g
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        g.status = "fail"
        g.message = f"JSON parse error: {e}"
        g.finished_at = _utc_now()
        return g
    report.consensus_path = str(path)
    report.consensus_sha256 = _sha256_path(path)
    args._consensus_data = data
    g.message = f"loaded {path.name} ({path.stat().st_size:,} bytes)"
    g.finished_at = _utc_now()
    return g


def gate_c(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="C. JSON structural", status="pass",
                   started_at=_utc_now())
    data = getattr(args, "_consensus_data", None)
    if data is None:
        g.status = "skip"
        g.message = "no consensus data from B"
    else:
        try:
            _validate_consensus_shape(data)
        except ValueError as e:
            g.status = "fail"
            g.message = str(e)
        else:
            g.message = (
                f"walls={len(data['walls'])}, rooms={len(data['rooms'])}, "
                f"openings={len(data['openings'])}"
            )
    g.finished_at = _utc_now()
    return g


def gate_d(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="D. Preview PNG", status="pass", started_at=_utc_now())
    out_dir = Path(report.out_dir)
    consensus = Path(report.consensus_path)
    artifacts: list[str] = []
    for mode, fname in (("top", "preview_top.png"), ("axon", "preview_axon.png")):
        target = out_dir / fname
        cmd = [
            sys.executable, "-m", "tools.render_axon",
            str(consensus),
            "--out", str(target),
            "--mode", mode,
            "--no-history",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(REPO_ROOT), timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            g.status = "fail"
            g.message = f"render_axon {mode} timed out after 120s"
            g.finished_at = _utc_now()
            return g
        if proc.returncode != 0 or not target.exists():
            g.status = "fail"
            g.message = (
                f"render_axon {mode} failed (rc={proc.returncode}): "
                f"{proc.stderr.strip()[:200]}"
            )
            g.finished_at = _utc_now()
            return g
        artifacts.append(_relpath(target))
    g.artifacts = artifacts
    g.message = "rendered top + axon previews"
    g.finished_at = _utc_now()
    return g


def gate_e(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="E. Hash + cache", status="pass", started_at=_utc_now())
    cache_key = _compute_cache_key(report.consensus_sha256, REPO_ROOT)
    report.cache_key = cache_key
    cache_marker = Path(report.out_dir).parent / "_skp_cache.json"
    prev: dict[str, Any] | None = None
    if cache_marker.exists():
        try:
            prev = json.loads(cache_marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = None
    if args.force_skp:
        g.message = f"--force-skp; cache_key={cache_key[:12]}"
    elif (
        prev
        and prev.get("cache_key") == cache_key
        and prev.get("verdict") == "pass"
    ):
        report.cache_hit = True
        g.message = (
            f"cache hit; previous run {prev.get('run_id', '?')} "
            f"produced {prev.get('skp_path', '?')}"
        )
    else:
        g.message = f"cache miss; cache_key={cache_key[:12]}"
    g.finished_at = _utc_now()
    return g


def gate_f(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="F. Export .skp", status="pass", started_at=_utc_now())
    if args.skip_skp:
        g.status = "skip"
        g.message = "--skip-skp"
        g.finished_at = _utc_now()
        return g
    if report.cache_hit and not args.force_skp:
        g.status = "skip"
        g.message = "cache hit"
        g.finished_at = _utc_now()
        return g
    out_dir = Path(report.out_dir)
    consensus = Path(report.consensus_path)
    # tools.skp_from_consensus's --out is a FILE path, not a directory.
    # Use a deterministic name inside out_dir; gate_g and gate_h
    # reference it back via args._skp_path.
    skp_target = out_dir / "model.skp"
    # Bootstrap template so SU 2026 trial doesn't show its Welcome
    # dialog (FP-007). Best-effort: if no template is reachable we
    # still try, and the existing premature-exit error explains why.
    bootstrap_target = out_dir / "_bootstrap.skp"
    if not bootstrap_target.exists():
        template = next(
            (t for t in SU_TEMPLATE_CANDIDATES if t.exists()), None
        )
        if template is not None:
            shutil.copy2(template, bootstrap_target)
    cmd = [
        sys.executable, "-m", "tools.skp_from_consensus",
        str(consensus),
        "--out", str(skp_target),
        "--sketchup", str(args.sketchup),
        "--timeout", str(args.timeout),
    ]
    if args.plugins:
        cmd += ["--plugins", str(args.plugins)]
    # Capture stderr+stdout to a sidecar log so debugging doesn't
    # depend on the truncated message field.
    log_path = out_dir / "skp_from_consensus.log"
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(REPO_ROOT), check=False,
            timeout=max(args.timeout + 30, 60),
        )
    except subprocess.TimeoutExpired as e:
        log_path.write_text(
            f"TIMEOUT after {args.timeout + 30}s\nstdout:\n{e.stdout or ''}"
            f"\nstderr:\n{e.stderr or ''}",
            encoding="utf-8",
        )
        g.status = "fail"
        g.message = f"skp_from_consensus timed out after {args.timeout + 30}s"
        g.artifacts = [_relpath(log_path)]
        g.finished_at = _utc_now()
        return g
    log_path.write_text(
        f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        encoding="utf-8",
    )
    g.artifacts = [_relpath(log_path)]
    if proc.returncode != 0:
        # Combine stdout + stderr because skp_from_consensus uses
        # plain print() for both info and error messages.
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        g.status = "fail"
        g.message = (
            f"skp_from_consensus failed (rc={proc.returncode}); "
            f"see {log_path.name}: {' | '.join(tail)[:300]}"
        )
        g.finished_at = _utc_now()
        return g
    if not skp_target.exists():
        g.status = "fail"
        g.message = (
            f"skp_from_consensus succeeded (rc=0) but {skp_target.name} "
            f"not found; see {log_path.name}"
        )
    else:
        g.artifacts.insert(0, _relpath(skp_target))
        g.message = f"exported {skp_target.name}"
        args._skp_path = skp_target
    g.finished_at = _utc_now()
    return g


def gate_g(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="G. Validate .skp", status="pass",
                   started_at=_utc_now())
    if args.skip_skp:
        g.status = "skip"
        g.message = "--skip-skp"
        g.finished_at = _utc_now()
        return g
    if report.cache_hit and not args.force_skp:
        g.status = "skip"
        g.message = "cache hit; previous .skp not re-validated"
        g.finished_at = _utc_now()
        return g
    skp: Path | None = getattr(args, "_skp_path", None)
    if skp is None or not skp.exists():
        g.status = "fail"
        g.message = "no .skp path from F"
    elif skp.stat().st_size < 1024:
        g.status = "fail"
        g.message = f".skp size {skp.stat().st_size} bytes < 1 KiB threshold"
    else:
        g.message = f".skp size {skp.stat().st_size:,} bytes"
    g.finished_at = _utc_now()
    return g


def gate_h(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="H. Reports", status="pass", started_at=_utc_now())
    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fail = any(x.status == "fail" for x in report.gates)
    report.verdict = "fail" if fail else "pass"
    report.finished_at = _utc_now()

    json_path = out_dir / "sketchup_smoke_report.json"
    md_path = out_dir / "sketchup_smoke_report.md"
    json_path.write_text(
        json.dumps(asdict(report), indent=2), encoding="utf-8"
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    g.artifacts = [_relpath(json_path), _relpath(md_path)]

    if report.verdict == "pass" and not args.skip_skp:
        skp: Path | None = getattr(args, "_skp_path", None)
        if skp is not None or report.cache_hit:
            cache_marker = out_dir.parent / "_skp_cache.json"
            cache_data = {
                "cache_key": report.cache_key,
                "consensus_sha256": report.consensus_sha256,
                "skp_path": _relpath(skp) if skp else None,
                "run_id": out_dir.name,
                "verdict": report.verdict,
                "finished_at": report.finished_at,
            }
            cache_marker.write_text(
                json.dumps(cache_data, indent=2), encoding="utf-8"
            )
            g.artifacts.append(_relpath(cache_marker))
    g.finished_at = _utc_now()
    return g


def _render_markdown(report: SmokeReport) -> str:
    lines = [
        "# SketchUp Smoke Report",
        "",
        f"- consensus: `{report.consensus_path}`",
        f"- out_dir: `{report.out_dir}`",
        f"- consensus sha256: `{report.consensus_sha256[:12]}...`",
        f"- cache_key: `{report.cache_key[:12]}...`",
        f"- cache_hit: {report.cache_hit}",
        f"- started: {report.started_at}",
        f"- finished: {report.finished_at}",
        f"- verdict: **{report.verdict.upper()}**",
        "",
        "## Gates",
        "",
        "| Gate | Status | Message |",
        "|---|---|---|",
    ]
    for g in report.gates:
        msg = g.message.replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {g.name} | {g.status.upper()} | {msg} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="smoke_skp_export",
        description="SketchUp smoke harness — gates A through H",
    )
    ap.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS,
                    help="path to consensus_model.json (default: %(default)s)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="output dir (default: runs/smoke/<UTC timestamp>)")
    ap.add_argument("--sketchup", type=Path, default=None,
                    help="path to SketchUp.exe (default: env SKETCHUP_EXE or "
                         "the canonical SU 2026 path on Windows)")
    ap.add_argument("--plugins", type=Path, default=None,
                    help="plugins dir passed through to tools.skp_from_consensus")
    ap.add_argument("--timeout", type=int, default=180,
                    help="SU export timeout in seconds (default: %(default)s)")
    ap.add_argument("--skip-skp", action="store_true",
                    help="run gates A-E + H only, no SU spawn")
    ap.add_argument("--force-skp", action="store_true",
                    help="bypass cache hit, always run F")
    ap.add_argument("--open", dest="open_after", action="store_true",
                    help="reserved; current implementation always quits SU")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.out_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out_dir = REPO_ROOT / "runs" / "smoke" / ts

    report = SmokeReport(
        consensus_path=str(args.consensus),
        out_dir=str(args.out_dir),
        started_at=_utc_now(),
    )

    pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e, gate_f, gate_g)
    for gate in pipeline:
        result = report.add(gate(args, report))
        if result.status == "fail":
            report.add(gate_h(args, report))
            print(f"smoke verdict: FAIL ({result.name})", file=sys.stderr)
            return 1

    report.add(gate_h(args, report))
    print(f"smoke verdict: {report.verdict.upper()}")
    print(f"reports: {Path(report.out_dir) / 'sketchup_smoke_report.md'}")
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
