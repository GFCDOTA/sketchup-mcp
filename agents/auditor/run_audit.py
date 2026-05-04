"""Read-only repo auditor.

Scans the repository, captures health metrics, writes
reports/repo_audit.md and reports/repo_audit.json. Does NOT modify
any other file. Does NOT execute pipeline code.

Usage:
    python agents/auditor/run_audit.py
    python agents/auditor/run_audit.py --out reports/
    python agents/auditor/run_audit.py --json-only

Contract: docs/agents/repo_auditor.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Finding:
    """A single audit finding. Identity is `(kind, key)`; that pair
    is what the diff uses to match findings across runs.
    """
    kind: str       # e.g. "ruff_code", "suspicious_root_py"
    key: str        # the specific instance, e.g. "F401" or "stale.py"
    severity: str   # "critical" | "attention" | "ok"
    message: str    # human-readable summary

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "key": self.key,
                "severity": self.severity, "message": self.message}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        return cls(
            kind=str(d.get("kind", "")),
            key=str(d.get("key", "")),
            severity=str(d.get("severity", "attention")),
            message=str(d.get("message", "")),
        )


def _run(cmd: list[str], cwd: Path = REPO_ROOT, timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command, return (rc, stdout, stderr). Never raises."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return -2, "", f"COMMAND NOT FOUND: {e}"
    except Exception as e:
        return -3, "", f"{type(e).__name__}: {e}"


def check_git_status() -> dict[str, Any]:
    rc, out, err = _run(["git", "status", "-s"])
    branch_rc, branch_out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    head_rc, head_out, _ = _run(["git", "rev-parse", "HEAD"])
    return {
        "branch": branch_out.strip() if branch_rc == 0 else "unknown",
        "head_commit": head_out.strip() if head_rc == 0 else "unknown",
        "working_tree_clean": rc == 0 and not out.strip(),
        "uncommitted_files_count": len(out.strip().splitlines()) if out.strip() else 0,
    }


def check_runs_dir() -> dict[str, Any]:
    runs = REPO_ROOT / "runs"
    if not runs.exists():
        return {"exists": False, "subdir_count": 0, "tracked_files": 0}
    subdirs = [d for d in runs.iterdir() if d.is_dir()]
    rc, out, _ = _run(["git", "ls-files", "runs/"])
    tracked = len(out.strip().splitlines()) if rc == 0 and out.strip() else 0
    return {
        "exists": True,
        "subdir_count": len(subdirs),
        "tracked_files": tracked,
        "subdir_categories": _categorize_runs([d.name for d in subdirs]),
    }


def _categorize_runs(names: list[str]) -> dict[str, int]:
    cats = {
        "baseline": 0, "cycle": 0, "oracle": 0, "synth": 0,
        "planta_74m2": 0, "openings_refine": 0, "vector": 0,
        "proto": 0, "validation": 0, "verify": 0, "other": 0,
    }
    for n in names:
        ln = n.lower()
        matched = False
        for cat in cats:
            if cat == "other":
                continue
            if ln.startswith(cat) or cat in ln:
                cats[cat] += 1
                matched = True
                break
        if not matched:
            cats["other"] += 1
    return {k: v for k, v in cats.items() if v > 0}


def check_ruff() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, "-m", "ruff", "check", ".", "--statistics"])
    if rc < 0:
        return {"installed": False, "error": err.strip()}
    if "No module named ruff" in err:
        return {"installed": False, "error": "ruff not installed"}
    counts: dict[str, int] = {}
    total = 0
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\S+)\s+", line)
        if m:
            n = int(m.group(1))
            code = m.group(2)
            counts[code] = n
            total += n
    return {
        "installed": True,
        "total_violations": total,
        "by_code": counts,
        "exit_code": rc,
    }


def check_pytest() -> dict[str, Any]:
    rc, out, err = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    m = re.search(r"(\d+) tests collected", out + err)
    collected = int(m.group(1)) if m else None
    errors_match = re.search(r"(\d+) errors?", err)
    errors = int(errors_match.group(1)) if errors_match else 0
    return {
        "collected": collected,
        "collection_errors": errors,
        "exit_code": rc,
    }


def check_root_python_files() -> dict[str, Any]:
    py_files = sorted([f.name for f in REPO_ROOT.glob("*.py") if f.is_file()])
    expected = {"main.py"}
    suspicious = [f for f in py_files if f not in expected]
    return {
        "total": len(py_files),
        "files": py_files,
        "expected": sorted(expected),
        "suspicious": suspicious,
    }


def check_render_scripts() -> dict[str, Any]:
    locations = {
        "root": list(REPO_ROOT.glob("render_*.py")),
        "tools": list((REPO_ROOT / "tools").glob("render_*.py"))
                 if (REPO_ROOT / "tools").exists() else [],
        "scripts": list((REPO_ROOT / "scripts").glob("render_*.py"))
                  if (REPO_ROOT / "scripts").exists() else [],
        "scripts_preview": list((REPO_ROOT / "scripts" / "preview").glob("render_*.py"))
                           if (REPO_ROOT / "scripts" / "preview").exists() else [],
    }
    return {loc: sorted(p.name for p in files) for loc, files in locations.items()}


def check_sys_path_shims() -> dict[str, Any]:
    rc, out, _ = _run(["git", "grep", "-n", "sys.path", "--", "*.py"])
    if rc != 0:
        return {"count": 0, "sample": []}
    lines = out.strip().splitlines()
    return {
        "count": len(lines),
        "sample": lines[:20],  # cap to avoid overwhelming
    }


def check_subprocess_use() -> dict[str, Any]:
    rc, out, _ = _run(["git", "grep", "-n", "subprocess\\.", "--", "*.py"])
    if rc != 0:
        return {"count": 0, "sample": []}
    lines = out.strip().splitlines()
    return {
        "count": len(lines),
        "sample": lines[:20],
    }


def check_hardcoded_paths() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    patterns = [
        ("C:/Users/", "Windows user home"),
        ("E:/Claude/", "Other-machine Claude path"),
        ("/home/", "POSIX user home"),
    ]
    for pat, desc in patterns:
        rc, out, _ = _run(["git", "grep", "-n", pat, "--", "*.py", "*.rb"])
        if rc == 0 and out.strip():
            for line in out.strip().splitlines()[:10]:
                findings.append({"pattern": pat, "desc": desc, "match": line})
    return {"count": len(findings), "findings": findings}


def check_patches() -> dict[str, Any]:
    patches_dir = REPO_ROOT / "patches"
    if not patches_dir.exists():
        return {"exists": False}
    files = sorted([p.name for p in patches_dir.glob("*.py")])
    archive = sorted([p.name for p in (patches_dir / "archive").glob("*.py")]) \
              if (patches_dir / "archive").exists() else []
    return {
        "exists": True,
        "active": files,
        "archived": archive,
    }


def check_large_files() -> dict[str, Any]:
    rc, out, _ = _run(["git", "ls-files"])
    if rc != 0:
        return {"error": "git ls-files failed", "files": []}
    big_files = []
    for fname in out.strip().splitlines():
        fpath = REPO_ROOT / fname
        if fpath.exists():
            try:
                size = fpath.stat().st_size
                if size > 1_000_000:  # > 1 MB
                    big_files.append({"path": fname, "size_bytes": size})
            except OSError:
                pass
    big_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {"count": len(big_files), "top10": big_files[:10]}


def check_todo_fixme() -> dict[str, Any]:
    rc, out, _ = _run(["git", "grep", "-cnE", "TODO|FIXME|XXX", "--",
                       "*.py", "*.rb", "*.md"])
    if rc != 0:
        return {"total_lines_with_marker": 0, "by_file": {}}
    by_file = {}
    total = 0
    for line in out.strip().splitlines():
        if ":" in line:
            fname, count = line.rsplit(":", 1)
            try:
                n = int(count)
                by_file[fname] = n
                total += n
            except ValueError:
                pass
    top20 = dict(sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:20])
    return {
        "total_lines_with_marker": total,
        "files_with_markers": len(by_file),
        "top20": top20,
    }


def check_entrypoints() -> dict[str, Any]:
    """Sanity-check that key entrypoints still exist and respond to --help."""
    results = {}
    candidates = [
        ("main.py", [sys.executable, "main.py", "--help"]),
        ("validator/run.py", [sys.executable, "-m", "validator.run", "--help"]),
        ("api/app.py", [sys.executable, "-c",
                        "import api.app; print('ok')"]),
        ("sketchup_mcp_server", [sys.executable, "-c",
                                 "import sketchup_mcp_server.server; print('ok')"]),
    ]
    for name, cmd in candidates:
        rc, out, err = _run(cmd, timeout=10)
        results[name] = {
            "exit_code": rc,
            "ok": rc == 0,
            "first_line": (out or err).strip().splitlines()[0] if (out or err).strip() else "",
        }
    return results


def build_report() -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "git": check_git_status(),
        "runs": check_runs_dir(),
        "ruff": check_ruff(),
        "pytest": check_pytest(),
        "root_python_files": check_root_python_files(),
        "render_scripts": check_render_scripts(),
        "sys_path_shims": check_sys_path_shims(),
        "subprocess_use": check_subprocess_use(),
        "hardcoded_paths": check_hardcoded_paths(),
        "patches": check_patches(),
        "large_files": check_large_files(),
        "todo_fixme": check_todo_fixme(),
        "entrypoints": check_entrypoints(),
    }
    # findings is the canonical, diff-friendly view of the report.
    # Each Finding is keyed by (kind, key), so any two reports can
    # be compared via set arithmetic to get NEW / RESOLVED / PERSISTING.
    report["findings"] = [f.to_dict() for f in derive_findings(report)]
    return report


# ---------------------------------------------------------------------------
# Findings & delta tracking (v2)
# ---------------------------------------------------------------------------


def derive_findings(report: dict[str, Any]) -> list[Finding]:
    """Synthesize a flat findings list from the per-section report.

    Each finding has stable identity `(kind, key)` so two runs can
    be compared even if the human-readable message changes.
    """
    findings: list[Finding] = []

    # Ruff: one finding per code, severity "attention" (lint debt).
    for code, n in (report.get("ruff", {}).get("by_code") or {}).items():
        findings.append(Finding(
            kind="ruff_code", key=str(code), severity="attention",
            message=f"{n} {code} violation{'s' if int(n) != 1 else ''}",
        ))

    # Suspicious root-level .py files.
    for f in report.get("root_python_files", {}).get("suspicious", []) or []:
        findings.append(Finding(
            kind="suspicious_root_py", key=str(f), severity="attention",
            message=f"unexpected .py at repo root: {f}",
        ))

    # Hardcoded paths (CI risk).
    for f in report.get("hardcoded_paths", {}).get("findings", []) or []:
        match = str(f.get("match", ""))
        findings.append(Finding(
            kind="hardcoded_path", key=match[:120], severity="attention",
            message=f"hardcoded path ({f.get('desc', '?')}): {match}",
        ))

    # Active patches (informational; presence/absence is the signal).
    for p in report.get("patches", {}).get("active", []) or []:
        findings.append(Finding(
            kind="active_patch", key=str(p), severity="ok",
            message=f"patch active: {p}",
        ))

    # Archived (high-risk) patches.
    for p in report.get("patches", {}).get("archived", []) or []:
        findings.append(Finding(
            kind="archived_patch", key=str(p), severity="ok",
            message=f"patch archived: {p}",
        ))

    # Large tracked files.
    for entry in report.get("large_files", {}).get("top10", []) or []:
        findings.append(Finding(
            kind="large_file", key=str(entry.get("path", "")),
            severity="attention",
            message=f"{int(entry.get('size_bytes', 0)):,} bytes",
        ))

    # Broken entrypoints.
    for name, info in (report.get("entrypoints") or {}).items():
        if not info.get("ok"):
            findings.append(Finding(
                kind="broken_entrypoint", key=str(name), severity="critical",
                message=f"entrypoint {name} exits {info.get('exit_code')}",
            ))

    # Pytest collection errors (critical: tests can't even collect).
    pytest = report.get("pytest", {})
    if int(pytest.get("collection_errors") or 0) > 0:
        findings.append(Finding(
            kind="pytest_collection_errors",
            key=str(pytest.get("collection_errors")),
            severity="critical",
            message=f"pytest reports {pytest.get('collection_errors')} "
                    f"collection error(s)",
        ))

    # Render scripts spread across multiple locations (debt signal).
    rs = report.get("render_scripts", {}) or {}
    populated = sorted(loc for loc, files in rs.items() if files)
    if len(populated) >= 2:
        findings.append(Finding(
            kind="render_scripts_duplicated",
            key=",".join(populated),
            severity="attention",
            message=f"render_*.py spread across {len(populated)} "
                    f"locations: {', '.join(populated)}",
        ))

    # Working-tree dirty at audit time (transient but useful).
    git_info = report.get("git", {}) or {}
    if not git_info.get("working_tree_clean", True):
        findings.append(Finding(
            kind="working_tree_dirty",
            key=str(git_info.get("uncommitted_files_count", 0)),
            severity="attention",
            message=f"{git_info.get('uncommitted_files_count')} "
                    f"uncommitted file(s) at audit time",
        ))

    return sorted(findings, key=lambda f: (f.kind, f.key))


def diff_findings(curr: list[Finding],
                  prev: list[Finding]) -> dict[str, list[dict[str, str]]]:
    """Set difference on `(kind, key)` identity.

    NEW       — present in curr, absent in prev.
    RESOLVED  — present in prev, absent in curr.
    PERSISTING— present in both. (Message is taken from `curr` so
                                  the latest text wins.)
    """
    curr_map = {(f.kind, f.key): f for f in curr}
    prev_map = {(f.kind, f.key): f for f in prev}

    new_keys = sorted(set(curr_map) - set(prev_map))
    resolved_keys = sorted(set(prev_map) - set(curr_map))
    persisting_keys = sorted(set(curr_map) & set(prev_map))

    return {
        "new": [curr_map[k].to_dict() for k in new_keys],
        "resolved": [prev_map[k].to_dict() for k in resolved_keys],
        "persisting": [curr_map[k].to_dict() for k in persisting_keys],
    }


def latest_prior_snapshot(
    out_dir: Path, exclude: Path | None = None
) -> Path | None:
    """Most recent `repo_audit_<timestamp>.json` snapshot in `out_dir`.

    `exclude` lets the caller skip a snapshot they just wrote (so a
    rerun in the same second doesn't read its own output).
    """
    if not out_dir.exists():
        return None
    snapshots = sorted(out_dir.glob("repo_audit_*.json"))
    if exclude:
        snapshots = [s for s in snapshots if s.resolve() != exclude.resolve()]
    return snapshots[-1] if snapshots else None


def load_findings_from_snapshot(snapshot: Path) -> list[Finding]:
    """Read findings out of a snapshot file. Tolerates both v2
    (explicit `findings` array) and v1 (derive from raw report).
    """
    try:
        data = json.loads(snapshot.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("findings")
    if isinstance(raw, list) and raw:
        return [Finding.from_dict(d) for d in raw if isinstance(d, dict)]
    # v1 fallback: synthesize from the raw report shape.
    return derive_findings(data)


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report as human-readable markdown."""
    lines = [
        "# Repo Audit Report",
        "",
        f"**Generated:** {report['timestamp']}",
        f"**Repo:** `{report['repo_root']}`",
        "",
        "---",
        "",
        "## Git",
        "",
        f"- Branch: `{report['git']['branch']}`",
        f"- HEAD: `{report['git']['head_commit'][:12]}`",
        f"- Working tree: {'✅ clean' if report['git']['working_tree_clean'] else '🟡 dirty'}",
        f"- Uncommitted files: {report['git']['uncommitted_files_count']}",
        "",
        "## runs/",
        "",
    ]
    runs = report["runs"]
    if not runs.get("exists"):
        lines.append("- ❌ runs/ directory does not exist")
    else:
        lines.append(f"- Subdirs on disk: **{runs['subdir_count']}**")
        lines.append(f"- Tracked files (gitignored exceptions): {runs['tracked_files']}")
        if runs.get("subdir_categories"):
            lines.append("- Categories:")
            for cat, n in sorted(runs["subdir_categories"].items(),
                                 key=lambda x: -x[1]):
                lines.append(f"  - `{cat}`: {n}")
    lines.extend(["", "## Ruff", ""])
    ruff = report["ruff"]
    if not ruff.get("installed"):
        lines.append(f"- ❌ Not installed: {ruff.get('error', 'unknown')}")
    else:
        lines.append(f"- Total violations: **{ruff['total_violations']}**")
        if ruff["by_code"]:
            lines.append("- Top codes:")
            for code, n in sorted(ruff["by_code"].items(),
                                  key=lambda x: -x[1])[:10]:
                lines.append(f"  - `{code}`: {n}")
    lines.extend(["", "## Pytest collection", ""])
    pt = report["pytest"]
    lines.append(f"- Tests collected: **{pt.get('collected')}**")
    lines.append(f"- Collection errors: {pt.get('collection_errors', 0)}")
    lines.append(f"- pytest exit code: {pt.get('exit_code')}")

    lines.extend(["", "## Root-level Python files", ""])
    rpy = report["root_python_files"]
    lines.append(f"- Total: {rpy['total']}")
    if rpy["suspicious"]:
        lines.append(f"- 🟡 Suspicious (not in expected set): {len(rpy['suspicious'])}")
        for f in rpy["suspicious"][:20]:
            lines.append(f"  - `{f}`")

    lines.extend(["", "## Render scripts inventory", ""])
    rs = report["render_scripts"]
    for loc, files in rs.items():
        if files:
            lines.append(f"- `{loc}/` ({len(files)}): {', '.join(files)}")

    lines.extend(["", "## sys.path shims (acoplamento frágil)", ""])
    sp = report["sys_path_shims"]
    lines.append(f"- Count: {sp['count']}")
    if sp["sample"]:
        lines.append("- Sample (first 5):")
        for s in sp["sample"][:5]:
            lines.append(f"  - `{s}`")

    lines.extend(["", "## subprocess usage", ""])
    sub = report["subprocess_use"]
    lines.append(f"- Count: {sub['count']}")

    lines.extend(["", "## Hardcoded paths (CI risk)", ""])
    hp = report["hardcoded_paths"]
    lines.append(f"- Findings: **{hp['count']}**")
    for f in hp["findings"][:10]:
        lines.append(f"  - `{f['pattern']}` ({f['desc']}): `{f['match']}`")

    lines.extend(["", "## Patches", ""])
    patches = report["patches"]
    if patches.get("exists"):
        lines.append(f"- Active: {len(patches['active'])} ({', '.join(patches['active'])})")
        lines.append(f"- Archived: {len(patches['archived'])} ({', '.join(patches['archived'])})")
    else:
        lines.append("- ❌ patches/ does not exist")

    lines.extend(["", "## Large files (> 1 MB)", ""])
    lf = report["large_files"]
    lines.append(f"- Count: {lf['count']}")
    for f in lf.get("top10", [])[:5]:
        lines.append(f"  - `{f['path']}` — {f['size_bytes']:,} bytes")

    lines.extend(["", "## TODO/FIXME/XXX", ""])
    tf = report["todo_fixme"]
    lines.append(f"- Total lines with markers: {tf['total_lines_with_marker']}")
    lines.append(f"- Files affected: {tf['files_with_markers']}")
    if tf.get("top20"):
        lines.append("- Top 5:")
        for f, n in list(tf["top20"].items())[:5]:
            lines.append(f"  - `{f}`: {n}")

    lines.extend(["", "## Entry points sanity", ""])
    ep = report["entrypoints"]
    for name, info in ep.items():
        marker = "✅" if info["ok"] else "🟡"
        lines.append(f"- {marker} `{name}` (exit {info['exit_code']})")

    diff = report.get("diff_vs_prior") or {}
    if diff:
        lines.extend(["", "## Diff vs previous run", ""])
        prior = diff.get("prior_snapshot")
        if prior:
            lines.append(f"- Previous snapshot: `{prior}`")
        else:
            lines.append("- No previous snapshot — first run.")
        new_list = diff.get("new", []) or []
        resolved = diff.get("resolved", []) or []
        persisting = diff.get("persisting", []) or []
        lines.append(
            f"- **{len(new_list)} new** · "
            f"**{len(resolved)} resolved** · "
            f"**{len(persisting)} persisting**"
        )
        if new_list:
            lines.extend(["", "### NEW", ""])
            for f in new_list[:30]:
                lines.append(
                    f"- 🆕 `{f['kind']}/{f['key']}` "
                    f"({f['severity']}): {f['message']}"
                )
            if len(new_list) > 30:
                lines.append(f"- … and {len(new_list) - 30} more")
        if resolved:
            lines.extend(["", "### RESOLVED", ""])
            for f in resolved[:30]:
                lines.append(
                    f"- ✅ `{f['kind']}/{f['key']}` "
                    f"({f['severity']}): {f['message']}"
                )
            if len(resolved) > 30:
                lines.append(f"- … and {len(resolved) - 30} more")
        if persisting:
            lines.extend(["", "### PERSISTING", ""])
            counts: dict[str, int] = {}
            for f in persisting:
                counts[f["kind"]] = counts.get(f["kind"], 0) + 1
            for kind, n in sorted(counts.items(), key=lambda x: -x[1]):
                lines.append(f"- `{kind}`: {n}")

    lines.extend([
        "",
        "---",
        "",
        "**Read-only audit.** No files modified outside `reports/`.",
        "Generated by `agents/auditor/run_audit.py` per contract in",
        "`docs/agents/repo_auditor.md`.",
    ])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out", default="reports", type=Path,
                   help="Output directory (default: reports/)")
    p.add_argument("--json-only", action="store_true",
                   help="Skip rendering markdown report")
    p.add_argument("--no-snapshot", action="store_true",
                   help="Do not write the timestamped history snapshot "
                        "(repo_audit_<ts>.{json,md}). Diff vs prior is "
                        "still computed from existing snapshots.")
    args = p.parse_args(argv)

    out_dir = (
        (REPO_ROOT / args.out).resolve()
        if not args.out.is_absolute() else args.out
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[auditor] Scanning repo at {REPO_ROOT}")
    print(f"[auditor] Output: {out_dir}")
    print("[auditor] Read-only — no files outside reports/ will be modified.")

    report = build_report()

    # ---- Diff vs the most recent prior snapshot, if any ----
    findings_now = [Finding.from_dict(d) for d in report.get("findings", [])]
    prior = latest_prior_snapshot(out_dir)
    if prior is not None:
        prev = load_findings_from_snapshot(prior)
        diff = diff_findings(findings_now, prev)
        report["diff_vs_prior"] = {"prior_snapshot": prior.name, **diff}
    else:
        # First run: every finding is NEW by definition.
        report["diff_vs_prior"] = {
            "prior_snapshot": None,
            "new": [f.to_dict() for f in findings_now],
            "resolved": [],
            "persisting": [],
        }
    d = report["diff_vs_prior"]
    print(
        f"[auditor] Findings: {len(findings_now)} "
        f"(new={len(d['new'])}, resolved={len(d['resolved'])}, "
        f"persisting={len(d['persisting'])})"
    )

    # ---- Canonical (overwrite) outputs ----
    json_path = out_dir / "repo_audit.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[auditor] JSON: {json_path}")

    md_text = render_markdown(report) if not args.json_only else None
    if md_text is not None:
        md_path = out_dir / "repo_audit.md"
        md_path.write_text(md_text, encoding="utf-8")
        print(f"[auditor] Markdown: {md_path}")

    # ---- History snapshot (per .claude/agents/repo-auditor.md) ----
    if not args.no_snapshot:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap_json = out_dir / f"repo_audit_{ts}.json"
        snap_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[auditor] Snapshot: {snap_json.name}")
        if md_text is not None:
            (out_dir / f"repo_audit_{ts}.md").write_text(md_text, encoding="utf-8")

    print("[auditor] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
