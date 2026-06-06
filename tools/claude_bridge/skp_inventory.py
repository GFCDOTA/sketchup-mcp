#!/usr/bin/env python3
"""SKP file inventory + sha256 dedup for the cockpit "Lixao" pages.

Extracted from server.py (SRP: the HTTP layer shouldn't also own the
.skp file-scan / classification / dedup domain). Pure read-only:
filesystem walk + `git ls-files`. server.py re-exports skp_inventory /
skp_inventory_v2 for its route table; tests hit the helpers here directly.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def skp_inventory() -> dict:
    """Scan the repo for .skp and classify by location so the 'Lixao' page can
    govern what is a deliverable vs evidence vs scratch vs orphan."""
    cats = {"deliverable": [], "review_evidence": [], "runs_scratch": [],
            "fixtures": [], "other": []}
    total_bytes = 0
    try:
        paths = list(REPO_ROOT.rglob("*.skp"))
    except OSError:
        paths = []
    for p in paths:
        try:
            rel = p.relative_to(REPO_ROOT).as_posix()
            size = p.stat().st_size
        except OSError:
            continue
        total_bytes += size
        item = {"path": rel, "mb": round(size / 1e6, 2)}
        if rel.startswith("artifacts/review/"):
            cats["review_evidence"].append(item)
        elif rel.startswith("artifacts/"):
            cats["deliverable"].append(item)
        elif rel.startswith("runs/"):
            cats["runs_scratch"].append(item)
        elif rel.startswith("fixtures/"):
            cats["fixtures"].append(item)
        else:
            cats["other"].append(item)
    for v in cats.values():
        v.sort(key=lambda it: it["mb"], reverse=True)
    return {"total": sum(len(v) for v in cats.values()),
            "total_mb": round(total_bytes / 1e6, 1), "categories": cats}


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _git_skp_sets(repo: Path) -> dict:
    """tracked / ignored / untracked .skp sets for a repo (relative paths), via
    git ls-files (read-only)."""
    def ls(*flags):
        try:
            r = subprocess.run(["git", "-C", str(repo), "ls-files", *flags, "--", "*.skp"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=15)
            return {ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()}
        except (OSError, subprocess.SubprocessError):
            return set()
    return {"tracked": ls(),
            "ignored": ls("--others", "--ignored", "--exclude-standard"),
            "untracked": ls("--others", "--exclude-standard")}


_SKP_ACTION = {"CANONICAL_DELIVERABLE": "KEEP", "REVIEW_ARTIFACT": "ARCHIVE",
               "GENERATED_SCRATCH": "DELETE_CANDIDATE", "DUPLICATE": "DELETE_CANDIDATE",
               "UNKNOWN": "INVESTIGATE"}
_SKP_RANK = {"CANONICAL_DELIVERABLE": 0, "REVIEW_ARTIFACT": 1,
             "GENERATED_SCRATCH": 2, "UNKNOWN": 3}


def _classify_skp(rel: str, git: str) -> str:
    if "artifacts/review/" in rel:
        return "REVIEW_ARTIFACT"
    if "artifacts/" in rel:
        return "CANONICAL_DELIVERABLE"
    if "runs/" in rel or git == "ignored":
        return "GENERATED_SCRATCH"
    return "UNKNOWN"


def _dedup_and_classify(files: list) -> list:
    """Group by sha256 (REAL dedup, not by name/path) + classify + suggest action.
    Within a hash group of >1, the most-canonical copy is the keeper; rest = DUPLICATE."""
    groups = {}
    for f in files:
        groups.setdefault(f["sha"], []).append(f)
    for grp in groups.values():
        for f in grp:
            f["category"] = _classify_skp(f["path"], f.get("git", ""))
            f["dup_count"] = len(grp)
        if len(grp) > 1:
            keeper = min(grp, key=lambda f: _SKP_RANK.get(f["category"], 9))
            for f in grp:
                f["dup_of"] = None if f is keeper else keeper["path"]
                if f is not keeper:
                    f["category"] = "DUPLICATE"
        else:
            grp[0]["dup_of"] = None
    for f in files:
        f["action"] = _SKP_ACTION.get(f["category"], "INVESTIGATE")
    return files


def skp_inventory_v2() -> dict:
    """Lixao v2: every .skp under E:\\Claude, sha256-deduped, with git status
    (tracked/untracked/ignored), classification + suggested action. Read-only."""
    root = REPO_ROOT.parent
    gitsets = {}
    try:
        for p in root.iterdir():
            if p.is_dir() and (p / ".git").exists():
                gitsets[p.name] = _git_skp_sets(p)
    except OSError:
        pass
    skps = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in
                  (".git", "node_modules", "__pycache__", ".pytest_cache", ".venv")]
        for fn in fns:
            if fn.lower().endswith(".skp"):
                skps.append(Path(dp) / fn)
        if len(skps) >= 400:
            break
    files = []
    for sp in skps:
        try:
            rel = sp.relative_to(root).as_posix()
            size = sp.stat().st_size
        except OSError:
            continue
        repo = rel.split("/", 1)[0]
        inrepo = rel.split("/", 1)[1] if "/" in rel else ""
        sets = gitsets.get(repo)
        git = "no-git"
        if sets and inrepo:
            git = ("tracked" if inrepo in sets["tracked"] else
                   "ignored" if inrepo in sets["ignored"] else "untracked")
        files.append({"path": rel, "mb": round(size / 1e6, 2),
                      "sha": _sha256(sp)[:12], "git": git,
                      "has_meta": (sp.parent / "geometry_report.json").exists()
                      or (sp.parent / (sp.name + ".metadata.json")).exists()})
    _dedup_and_classify(files)
    counts = {}
    for f in files:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    dup_groups = len({f["sha"] for f in files if f["dup_count"] > 1})
    return {"total": len(files), "total_mb": round(sum(f["mb"] for f in files), 1),
            "dup_groups": dup_groups, "by_category": counts,
            "files": sorted(files, key=lambda f: (f["category"], -f["mb"]))}
