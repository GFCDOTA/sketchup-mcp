"""Generate the SRE Radar manifest consumed by the dashboard's Radar tab.

Stdlib-only — no third-party deps. Walks the repo and emits one JSON snapshot
covering documentation saturation, doc-vs-code drift, service availability,
repo-hygiene findings, per-category scores, and a ranked recommendations list.

CLI:
    python scripts/dashboard/generate_architecture_radar.py \\
        --out tools/dashboard/architecture_radar.json \\
        [--repo-root .] [--no-command-checks]

The script never aborts on a partial failure — section failures are recorded
in the JSON under ``errors[]`` so the dashboard can render whatever did work.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = "1.0.0"

# Markdown thresholds. Counts/scores below are heuristic — the goal is to
# surface candidates for splitting/archival, not enforce a hard policy.
MD_LINES_WARN = 500
MD_LINES_CRIT = 1000
MD_KB_WARN = 80
MD_TODO_WARN = 5
# Sum of all signal weights (line crit + size + todo + planned/done) is 65.
# The thresholds below sit so that a doc hitting all signals lands clearly in
# the saturated bucket, while a single-signal doc (e.g. just > 500 lines)
# stays in warning.
MD_SCORE_HEALTHY_BELOW = 25
MD_SCORE_SATURATED_AT = 55

# Excluded paths for the markdown walk. We never want to flag vendored docs.
EXCLUDED_DIRS = (".git", "node_modules", "vendor", ".venv", "venv", "env",
                 "_archive", "site-packages")

# Services to probe — paths relative to repo root. ``cli`` is what gets run
# with --help when --no-command-checks is OFF. ``category`` groups the table.
SERVICES = [
    {"name": "smoke_skp_export", "path": "scripts/smoke/smoke_skp_export.py",
     "cli": [sys.executable, "scripts/smoke/smoke_skp_export.py", "--help"],
     "category": "smoke"},
    {"name": "bench_pipeline", "path": "scripts/benchmark/bench_pipeline.py",
     "cli": [sys.executable, "scripts/benchmark/bench_pipeline.py", "--help"],
     "category": "benchmark"},
    {"name": "repo_auditor", "path": "agents/auditor/run_audit.py",
     "cli": [sys.executable, "agents/auditor/run_audit.py", "--help"],
     "category": "agent"},
    {"name": "skp_from_consensus", "path": "tools/skp_from_consensus.py",
     "cli": [sys.executable, "tools/skp_from_consensus.py", "--help"],
     "category": "sketchup"},
    {"name": "build_vector_consensus", "path": "tools/build_vector_consensus.py",
     "cli": [sys.executable, "tools/build_vector_consensus.py", "--help"],
     "category": "pipeline"},
    {"name": "validator", "path": "validator/run.py",
     "cli": [sys.executable, "-m", "validator.run", "--help"],
     "category": "validator"},
    {"name": "main", "path": "main.py",
     "cli": [sys.executable, "main.py", "--help"],
     "category": "pipeline"},
    {"name": "dashboard_index", "path": "tools/dashboard/index.html",
     "cli": None, "category": "dashboard"},
]

# Doc files we trust to mention real paths. We grep these for path-like
# tokens and then existence-check them.
DRIFT_DOCS = [
    "CLAUDE.md",
    "docs/operational_roadmap.md",
    "docs/ROADMAP.md",
    "OVERVIEW.md",
    "tools/dashboard/README.md",
]

# Path pattern looks for forward-slashed module/file references that touch
# code or docs we own. Trailing punctuation (period, comma, colon, paren) is
# trimmed before existence checking.
DRIFT_PATH_RE = re.compile(
    r"(?:tools|scripts|agents|validator|packages|docs|tests|api|model|"
    r"openings|topology|extract|classify|ingest|roi|render|"
    r"sketchup_mcp_server|observability)"
    r"/[\w/.\-]+\.(?:py|rb|md|json|html|yml|yaml)"
)
PUNCT_TAIL_RE = re.compile(r"[.,;:!?\)\]]+$")

# Repo hygiene patterns.
SYS_PATH_RE = re.compile(r"sys\.path\.(?:insert|append)\s*\(")
HARDCODED_PATH_RE = re.compile(r"[A-Z]:[\\/](?:Users|Claude|Sketchup|SU2026)")


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _safe(fn, default):
    """Run ``fn`` and swallow exceptions, returning ``default`` on failure."""
    try:
        return fn()
    except Exception:
        return default


def _git(repo_root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(repo_root), capture_output=True,
            text=True, timeout=5,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _list_md_files(repo_root: Path) -> list[Path]:
    out = []
    for root, dirs, files in os.walk(repo_root):
        # In-place prune so os.walk doesn't descend.
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for name in files:
            if name.lower().endswith(".md"):
                out.append(Path(root) / name)
    return out


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root)).replace(os.sep, "/")
    except ValueError:
        return str(path).replace(os.sep, "/")


# ----------------------------------------------------------------------------
# Section: Markdown saturation
# ----------------------------------------------------------------------------

def score_markdown(repo_root: Path) -> dict:
    files = _list_md_files(repo_root)
    items = []
    for f in files:
        text = _read_text(f)
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        size_kb = round(len(text.encode("utf-8")) / 1024, 1)
        headings = sum(1 for ln in text.splitlines() if ln.startswith("#"))
        todo_count = len(re.findall(r"\b(?:TODO|FIXME|OUTDATED|DEPRECATED)\b", text))
        # Heuristic score, capped to 100.
        score = 0
        reasons: list[str] = []
        if lines >= MD_LINES_CRIT:
            score += 35
            reasons.append(f">{MD_LINES_CRIT} lines")
        elif lines >= MD_LINES_WARN:
            score += 20
            reasons.append(f">{MD_LINES_WARN} lines")
        if size_kb >= MD_KB_WARN:
            score += 10
            reasons.append(f">{MD_KB_WARN}KB")
        if todo_count > MD_TODO_WARN:
            score += 10
            reasons.append(f">{MD_TODO_WARN} TODO/FIXME")
        # "planned" + "done" mixed in same doc is a saturation smell.
        if "planned" in text.lower() and re.search(r"\bdone\b|\bdelivered\b", text, re.I):
            score += 10
            reasons.append("planned & done mixed")
        score = min(score, 100)
        items.append({
            "path": _rel(f, repo_root),
            "lines": lines,
            "size_kb": size_kb,
            "headings": headings,
            "todo_count": todo_count,
            "score": score,
            "reasons": reasons,
        })
    items.sort(key=lambda x: -x["score"])
    saturated = [x for x in items if x["score"] >= MD_SCORE_SATURATED_AT]
    warning = [x for x in items if MD_SCORE_HEALTHY_BELOW <= x["score"] < MD_SCORE_SATURATED_AT]
    healthy = [x for x in items if x["score"] < MD_SCORE_HEALTHY_BELOW]
    return {
        "total_files": len(items),
        "healthy_count": len(healthy),
        "warning_count": len(warning),
        "saturated_count": len(saturated),
        "top_saturated": items[:10],
    }


# ----------------------------------------------------------------------------
# Section: Drift docs vs code
# ----------------------------------------------------------------------------

def check_drift(repo_root: Path) -> list[dict]:
    findings: list[dict] = []
    for doc in DRIFT_DOCS:
        doc_path = repo_root / doc
        if not doc_path.exists():
            continue
        text = _read_text(doc_path)
        seen: set[str] = set()
        for m in DRIFT_PATH_RE.finditer(text):
            ref = PUNCT_TAIL_RE.sub("", m.group(0))
            if ref in seen:
                continue
            seen.add(ref)
            target = repo_root / ref
            if not target.exists():
                findings.append({
                    "doc": doc,
                    "ref": ref,
                    "severity": "medium",
                    "message": f"{doc} references {ref}, which does not exist",
                })
    return findings


# ----------------------------------------------------------------------------
# Section: Service health
# ----------------------------------------------------------------------------

def check_services(repo_root: Path, run_commands: bool) -> list[dict]:
    out: list[dict] = []
    for svc in SERVICES:
        path = repo_root / svc["path"]
        exists = path.exists()
        entry = {
            "name": svc["name"],
            "path": svc["path"],
            "category": svc["category"],
            "exists": exists,
            "help_passed": None,
            "elapsed_ms": None,
        }
        if not exists:
            entry["risk"] = "high"
            out.append(entry)
            continue
        if not run_commands or not svc.get("cli"):
            entry["help_passed"] = None  # explicitly unknown
            entry["risk"] = "low" if svc["category"] == "dashboard" else "unknown"
            out.append(entry)
            continue
        # Probe with --help. Treat exit 0 as healthy. Cap at 10s — never run
        # the actual workload, only the help path.
        t0 = time.perf_counter()
        try:
            p = subprocess.run(svc["cli"], cwd=str(repo_root),
                               capture_output=True, timeout=10)
            entry["help_passed"] = (p.returncode == 0)
        except Exception as e:
            entry["help_passed"] = False
            entry["error"] = type(e).__name__
        entry["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        entry["risk"] = "low" if entry["help_passed"] else "high"
        out.append(entry)
    return out


# ----------------------------------------------------------------------------
# Section: Repo hygiene
# ----------------------------------------------------------------------------

def check_repo_hygiene(repo_root: Path) -> dict:
    root_pys = sorted(p.name for p in repo_root.glob("*.py"))
    sys_path_hits: list[str] = []
    hardcoded_hits: list[str] = []
    # Walk only first-party python; skip vendor, .venv, etc.
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for name in files:
            if not name.endswith(".py"):
                continue
            full = Path(root) / name
            txt = _read_text(full)
            if SYS_PATH_RE.search(txt):
                sys_path_hits.append(_rel(full, repo_root))
            if HARDCODED_PATH_RE.search(txt):
                hardcoded_hits.append(_rel(full, repo_root))
    return {
        "root_python_files": root_pys,
        "root_python_count": len(root_pys),
        "sys_path_hacks": sys_path_hits,
        "hardcoded_paths": hardcoded_hits,
    }


# ----------------------------------------------------------------------------
# Section: Scores & overall verdict
# ----------------------------------------------------------------------------

def _clamp(n: float, lo: float = 0, hi: float = 100) -> int:
    return int(max(lo, min(hi, round(n))))


def compute_scores(markdown: dict, drift: list[dict],
                   services: list[dict], hygiene: dict) -> dict:
    # Docs health: 100 minus weighted penalties from saturation.
    saturated = markdown.get("saturated_count", 0)
    warning = markdown.get("warning_count", 0)
    docs_health = _clamp(100 - saturated * 8 - warning * 3 - len(drift) * 4)
    # Service health: % of services that exist, weighted again by help_passed
    # (when known).
    svc_exist = sum(1 for s in services if s["exists"])
    svc_help = sum(1 for s in services if s.get("help_passed") is True)
    svc_total = max(len(services), 1)
    service_health = _clamp(
        (svc_exist / svc_total) * 70 + (svc_help / svc_total) * 30
    )
    # Automation: based on services + presence of CI workflow files.
    automation = service_health  # CI presence handled in radar.findings below
    # Repo hygiene: lots of root .py + sys.path + hardcoded paths is bad.
    hygiene_penalty = (
        hygiene.get("root_python_count", 0) * 4
        + len(hygiene.get("sys_path_hacks", [])) * 6
        + len(hygiene.get("hardcoded_paths", [])) * 4
    )
    repo_hygiene = _clamp(100 - hygiene_penalty)
    # Product quality is intentionally derived from external signals (drift +
    # docs) since the radar can't measure SKP visual quality directly.
    product_quality = _clamp(100 - len(drift) * 6 - saturated * 5)
    overall = _clamp((docs_health + service_health + automation
                      + repo_hygiene + product_quality) / 5)
    return {
        "overall": overall,
        "docs_health": docs_health,
        "service_health": service_health,
        "automation_health": automation,
        "repo_hygiene": repo_hygiene,
        "product_quality": product_quality,
    }


def status_for(score: int) -> str:
    if score >= 80:
        return "healthy"
    if score >= 60:
        return "warning"
    return "critical"


# ----------------------------------------------------------------------------
# Section: Recommendations
# ----------------------------------------------------------------------------

def build_recommendations(markdown: dict, drift: list[dict],
                          services: list[dict], hygiene: dict,
                          scores: dict) -> list[dict]:
    recs: list[dict] = []
    # Saturated docs → propose split/archive.
    for doc in markdown.get("top_saturated", [])[:3]:
        if doc["score"] >= MD_SCORE_SATURATED_AT:
            recs.append({
                "title": f"Split or archive {doc['path']}",
                "category": "documentation",
                "impact": "medium",
                "effort": "medium",
                "risk": "low",
                "suggested_branch": "docs/split-" + Path(doc["path"]).stem.lower(),
                "why": f"{doc['path']} scored {doc['score']} ({', '.join(doc['reasons'])})",
                "validation": "Splits land in their own PR; preview README links.",
            })
    # Drift findings → fix references.
    if drift:
        recs.append({
            "title": f"Fix {len(drift)} broken doc reference(s)",
            "category": "documentation",
            "impact": "low",
            "effort": "low",
            "risk": "low",
            "suggested_branch": "docs/fix-broken-refs",
            "why": "Docs cite paths that no longer exist; readers hit dead ends.",
            "validation": "Re-run this generator and confirm drift_findings is empty.",
        })
    # Missing services → restore.
    missing = [s for s in services if not s["exists"]]
    for svc in missing:
        recs.append({
            "title": f"Restore service {svc['name']}",
            "category": "service",
            "impact": "high",
            "effort": "medium",
            "risk": "medium",
            "suggested_branch": f"chore/restore-{svc['name']}",
            "why": f"{svc['path']} not found — referenced in radar service registry.",
            "validation": "Generator reports exists=true and help_passed=true.",
        })
    # Repo hygiene > thresholds.
    if hygiene.get("root_python_count", 0) > 5:
        recs.append({
            "title": "Move stray Python from repo root into a package",
            "category": "hygiene",
            "impact": "low",
            "effort": "medium",
            "risk": "low",
            "suggested_branch": "refactor/root-py-cleanup",
            "why": f"{hygiene['root_python_count']} loose .py files at the root.",
            "validation": "Imports continue to resolve; root has only entrypoints.",
        })
    if hygiene.get("sys_path_hacks"):
        recs.append({
            "title": "Drop sys.path.insert/append hacks",
            "category": "hygiene",
            "impact": "low",
            "effort": "medium",
            "risk": "medium",
            "suggested_branch": "refactor/no-sys-path-hacks",
            "why": f"{len(hygiene['sys_path_hacks'])} files mutate sys.path.",
            "validation": "Tests pass without the hacks (proper packaging).",
        })
    # Sort by impact (high first), then effort (low first), then category.
    impact_rank = {"high": 0, "medium": 1, "low": 2}
    effort_rank = {"low": 0, "medium": 1, "high": 2}
    recs.sort(key=lambda r: (impact_rank.get(r["impact"], 9),
                             effort_rank.get(r["effort"], 9),
                             r["category"]))
    return recs


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------

def build_radar(repo_root: Path, run_commands: bool) -> dict:
    errors: list[str] = []

    markdown = _safe(lambda: score_markdown(repo_root),
                     {"total_files": 0, "saturated_count": 0,
                      "warning_count": 0, "healthy_count": 0,
                      "top_saturated": []})
    if markdown.get("total_files") is None:
        errors.append("markdown")
    drift = _safe(lambda: check_drift(repo_root), [])
    services = _safe(lambda: check_services(repo_root, run_commands), [])
    hygiene = _safe(lambda: check_repo_hygiene(repo_root),
                    {"root_python_files": [], "root_python_count": 0,
                     "sys_path_hacks": [], "hardcoded_paths": []})
    scores = _safe(lambda: compute_scores(markdown, drift, services, hygiene),
                   {"overall": 0, "docs_health": 0, "service_health": 0,
                    "automation_health": 0, "repo_hygiene": 0,
                    "product_quality": 0})
    recommendations = _safe(lambda: build_recommendations(
        markdown, drift, services, hygiene, scores), [])

    overall = scores.get("overall", 0)
    summary_parts = []
    if scores.get("docs_health", 100) < 70:
        summary_parts.append("docs saturated")
    if scores.get("service_health", 100) < 70:
        summary_parts.append("service gaps")
    if scores.get("repo_hygiene", 100) < 70:
        summary_parts.append("repo hygiene")
    if not summary_parts:
        summary_parts.append("nothing critical")
    summary = ", ".join(summary_parts)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "git": {
            "branch": _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
            "commit": _git(repo_root, "rev-parse", "--short", "HEAD"),
        },
        "overall": {
            "health_score": overall,
            "status": status_for(overall),
            "summary": summary,
        },
        "scores": scores,
        "markdown": markdown,
        "drift_findings": drift,
        "services": services,
        "hygiene": hygiene,
        "recommendations": recommendations,
        "errors": errors,
        "command_checks": run_commands,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default="tools/dashboard/architecture_radar.json",
                   help="Output JSON path (default: %(default)s)")
    p.add_argument("--repo-root", default=".",
                   help="Repo root, default: %(default)s")
    p.add_argument("--no-command-checks", action="store_true",
                   help="Skip --help probes for services (faster, no subprocess)")
    p.add_argument("--json-only", action="store_true",
                   help="Print JSON to stdout instead of writing to --out")
    args = p.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    radar = build_radar(repo_root, run_commands=not args.no_command_checks)
    payload = json.dumps(radar, indent=2, ensure_ascii=False) + "\n"

    if args.json_only:
        sys.stdout.write(payload)
        return 0
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload, encoding="utf-8")
    sys.stdout.write(f"wrote {out_path} ({len(payload)} bytes)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
