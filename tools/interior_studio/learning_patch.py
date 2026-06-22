"""learning_patch.py — LEARNING_PATCH v1 (stdlib): resposta GPT → patch DRAFT → diff → Felipe aprova → aplica.

Decisão do GPT (2026-06-21): NUNCA aplicar resposta direto no DNA. A resposta do Consult GPT vira um patch
RASTREÁVEL em `status=draft`; o Felipe vê o DIFF (o que de fato vai mudar, sem duplicar) e aprova/rejeita;
só então o patch altera `felipe_style_dna.md` + anti-patterns do juiz + learning log. Geração AUTOMÁTICA,
aplicação MANUAL. NÃO toca :8765 nem geometria. Idempotente (aplicar reusa o dedupe do ingest).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tools.interior_studio import cycles as ic_cycles
from tools.interior_studio import gpt_review_bundle as ic_bundle
from tools.interior_studio.consult_gpt_bridge import ingest as ci

ROOT = Path(__file__).resolve().parents[2]
PATCHES_DIR = ROOT / ".ai_bridge" / "learning_patches"


def _dir() -> Path:
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    return PATCHES_DIR


def _now(now: str | None) -> str:
    return now or time.strftime("%Y-%m-%dT%H:%M:%S")


def list_patches() -> list[dict]:
    out = []
    for p in sorted(_dir().glob("LP-*.json")):
        try:
            out.append(json.loads(p.read_text("utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def get_patch(pid: str) -> dict | None:
    p = _dir() / f"{pid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_patch(p: dict) -> dict:
    (_dir() / f"{p['patch_id']}.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), "utf-8")
    return p


def _next_id(asset: str | None) -> str:
    tag = (asset or "GEN").upper()
    n = 0
    for p in list_patches():
        pid = p.get("patch_id", "")
        if pid.startswith(f"LP-{tag}-"):
            try:
                n = max(n, int(pid.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"LP-{tag}-{n + 1:03d}"


def from_answer(parsed: dict, *, cycle: dict | None = None, now: str | None = None,
                answer_path: str = "") -> dict:
    """Gera um LEARNING_PATCH DRAFT a partir de um ARCHITECT_ANSWER já parseado. NÃO aplica nada."""
    cycle = cycle or ic_cycles.current_cycle() or {}
    git = ic_bundle._git_info()
    refs = cycle.get("references") or {}
    patch = {
        "patch_id": _next_id(cycle.get("asset")),
        "created_at": _now(now), "status": "draft", "source": "Consult GPT",
        "source_question_id": parsed.get("question_id"), "source_answer_id": None,
        "cycle_id": cycle.get("cycle_id"), "project": cycle.get("project"),
        "room": cycle.get("room"), "asset": cycle.get("asset"),
        "theme": cycle.get("theme") or "BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE",
        "branch": git.get("branch"), "commit_sha": git.get("sha"),
        "applies_to": ["felipe_style_dna", "anti_patterns", "learning_log"],
        "confidence": parsed.get("confidence") or "medium",
        "requires_felipe_confirmation": True,
        "verdict": parsed.get("verdict"), "summary": parsed.get("summary"),
        "evidence": {"reference_ids": (refs.get("main") or []) + (refs.get("approved") or []),
                     "render_paths": [], "source_urls": [],
                     "raw_question_path": "", "raw_answer_path": answer_path},
        "proposed_changes": {
            "new_rules": parsed.get("dna_updates") or [],
            "anti_patterns": parsed.get("anti_patterns") or [],
            "visual_tokens": [], "material_lessons": [], "maintenance_lessons": [],
            "forbidden_patterns": [], "build_spec_constraints": [], "golden_sample_candidates": []},
        "next_microtask": parsed.get("next_microtask") or {},
        "review": {"approved_by": None, "approved_at": None, "rejected_reason": None},
        "applied": {"applied_at": None, "files_changed": []},
    }
    return save_patch(patch)


def compute_diff(patch: dict) -> dict:
    """O que de fato MUDA se aprovar (sem duplicar o que já está no DNA / no juiz)."""
    pc = patch.get("proposed_changes") or {}
    dna_text = ci.FELIPE_DNA.read_text("utf-8") if ci.FELIPE_DNA.exists() else ""
    existing = ci._norm(dna_text)
    nr = pc.get("new_rules") or []
    rules_add = [r for r in nr if ci._norm(r) and ci._norm(r) not in existing]
    rules_dup = [r for r in nr if r not in rules_add]
    have_ap: set = set()
    if ci.JUDGE_RULES.exists():
        try:
            have_ap = {ci._norm(a.get("what", "")) for a in json.loads(ci.JUDGE_RULES.read_text("utf-8")).get("anti_patterns", [])}
        except (json.JSONDecodeError, OSError):
            pass
    ap = pc.get("anti_patterns") or []
    anti_add = [a for a in ap if ci._norm(a) and ci._norm(a) not in have_ap]
    anti_dup = [a for a in ap if a not in anti_add]
    return {"rules_add": rules_add, "rules_dup": rules_dup, "anti_add": anti_add, "anti_dup": anti_dup}


def approve(patch_id: str, *, now: str | None = None) -> dict:
    """Felipe aprovou → APLICA (dedupe) no DNA + juiz, marca applied, atualiza o ciclo ligado."""
    p = get_patch(patch_id)
    if not p:
        return {"ok": False, "error": f"patch {patch_id} não encontrado"}
    if p.get("status") == "applied":
        return {"ok": False, "error": "patch já aplicado"}
    pc = p.get("proposed_changes") or {}
    rules = ci._apply_dna(pc.get("new_rules") or [], patch_id)
    antis = ci._apply_anti_patterns(pc.get("anti_patterns") or [], patch_id)
    files = []
    if rules:
        files.append(".claude/memory/felipe_style_dna.md")
    if antis:
        files.append("references/design_rules/felipe_visual_judge_rules.json")
    p["status"] = "applied"
    p["review"]["approved_by"] = "Felipe"
    p["review"]["approved_at"] = _now(now)
    p["applied"] = {"applied_at": _now(now), "files_changed": files,
                    "rules_added": rules, "anti_patterns_added": antis}
    save_patch(p)
    if p.get("cycle_id"):
        c = ic_cycles.get_cycle(p["cycle_id"])
        if c:
            lr = c.setdefault("learning", {})
            lr.setdefault("new_rules", [])
            lr.setdefault("anti_patterns", [])
            lr.setdefault("patches", [])
            for r in rules:
                if r not in lr["new_rules"]:
                    lr["new_rules"].append(r)
            for a in antis:
                if a not in lr["anti_patterns"]:
                    lr["anti_patterns"].append(a)
            if patch_id not in lr["patches"]:
                lr["patches"].append(patch_id)
            ic_cycles.save_cycle(c)
    return {"ok": True, "patch_id": patch_id, "rules_added": rules,
            "anti_patterns_added": antis, "files_changed": files}


def reject(patch_id: str, reason: str | None = None, *, now: str | None = None) -> dict:
    p = get_patch(patch_id)
    if not p:
        return {"ok": False, "error": f"patch {patch_id} não encontrado"}
    p["status"] = "rejected"
    p["review"]["rejected_reason"] = (reason or "").strip() or "(sem motivo)"
    p["review"]["approved_at"] = _now(now)
    save_patch(p)
    return {"ok": True, "patch_id": patch_id, "status": "rejected"}


def latest_draft() -> dict | None:
    drafts = [p for p in list_patches() if p.get("status") == "draft"]
    return sorted(drafts, key=lambda x: x.get("patch_id", ""))[-1] if drafts else None


def applied_rules() -> list[str]:
    """Regras já aplicadas via patch (pro learning log)."""
    out: list[str] = []
    for p in list_patches():
        if p.get("status") == "applied":
            ap = p.get("applied") or {}
            out += ap.get("rules_added") or (p.get("proposed_changes") or {}).get("new_rules") or []
    return out


def patches_state() -> dict:
    """Estado pro dashboard: draft atual + seu diff + lista recente + contagens."""
    allp = list_patches()
    draft = latest_draft()
    return {"draft": draft, "diff": compute_diff(draft) if draft else None,
            "patches": [{"patch_id": p["patch_id"], "status": p["status"], "asset": p.get("asset"),
                         "verdict": p.get("verdict"),
                         "rules": len((p.get("proposed_changes") or {}).get("new_rules") or []),
                         "anti": len((p.get("proposed_changes") or {}).get("anti_patterns") or [])}
                        for p in sorted(allp, key=lambda x: x.get("patch_id", ""), reverse=True)[:8]],
            "counts": {"draft": sum(1 for p in allp if p.get("status") == "draft"),
                       "applied": sum(1 for p in allp if p.get("status") == "applied"),
                       "rejected": sum(1 for p in allp if p.get("status") == "rejected")}}
