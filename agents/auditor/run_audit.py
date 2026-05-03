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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


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
    return {
        "schema_version": "1.0.0",
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
    args = p.parse_args(argv)

    out_dir = (REPO_ROOT / args.out).resolve() if not args.out.is_absolute() else args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[auditor] Scanning repo at {REPO_ROOT}")
    print(f"[auditor] Output: {out_dir}")
    print("[auditor] Read-only — no files outside reports/ will be modified.")

    report = build_report()

    json_path = out_dir / "repo_audit.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[auditor] JSON: {json_path}")

    if not args.json_only:
        md_path = out_dir / "repo_audit.md"
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"[auditor] Markdown: {md_path}")

    print("[auditor] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
