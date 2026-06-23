"""auditor.py — Consistency/Gap Auditor (GPT: "ouro"; o ÚNICO worker local autônomo que paga).

LÊ os sinais reais (project_state · packs · gpt_verdict · proposals) e PROPÕE gaps de
consistência — NUNCA muta nada. DETERMINÍSTICO (gate = verdade; não usa LLM p/ achar gap —
mais robusto e testável; LLM só serviria p/ frasear, e isso é firula aqui). Cada gap vira um
proposal `consistency_gap` (requires_approval) — o Felipe aprova/rejeita no dash.

Checks:
- C1 duplicate_main — pack com >1 referência ⭐ principal.
- C2 no_json_verdict — asset em estado avançado derivado de markdown frágil (sem gpt_verdict.json) [tie SPEC-E].
- C3 competing_program — cômodo com programa aprovado E proposta pendente.
- C4 stale_program — programa APROVADO que o gate do Arquiteto (SPEC-C) corrigiria (cross-cômodo / sem CORE).
- C5 buggy_pending_program — proposta PENDENTE que o gate corrigiria (gerada antes do SPEC-C; não aprovar como está).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.interior_studio import architect_program as ic_arch
from tools.interior_studio import project_state as ps
from tools.interior_studio import proposals as ic_proposals
from tools.interior_studio import reference_packs as ic_refpacks

ROOT = Path(__file__).resolve().parents[2]
ADVANCED = ("vray_ready", "approved", "learned")


def _gap(kind: str, subject: str, severity: str, title: str, detail: str, **extra) -> dict:
    g = {"id": f"gap_{kind}_{subject}", "type": "consistency_gap", "kind": kind,
         "severity": severity, "title": title, "detail": detail,
         "source_worker": "Auditor de Consistência"}
    g.update(extra)
    return g


def audit() -> list[dict]:
    """Devolve a lista de gaps reais (determinístico, sem efeito colateral)."""
    findings = []
    # C1 — pack com principal (⭐) duplicado
    for asset in ps.ASSET_META:
        pack = ic_refpacks.load_pack(f"{asset}_reference_pack_001")
        mains = [r for r in (pack or {}).get("references", []) if r.get("status") == "main"]
        if len(mains) > 1:
            findings.append(_gap(
                "duplicate_main", asset, "med",
                f"{asset}: {len(mains)} referências marcadas como PRINCIPAL",
                "Um pack deve ter 1 principal (⭐) — escolher uma e despromover as outras.",
                asset=asset))
    # C2 — estado avançado apoiado em markdown frágil (sem gpt_verdict.json) [tie SPEC-E]
    for asset in ps.ASSET_META:
        if asset in ps.FIXED_STATE:
            continue
        st = ps.asset_state(asset)["state"]
        if st in ADVANCED:
            vdir = ROOT / "artifacts/review/furniture" / asset
            if not (vdir.exists() and any(vdir.glob("**/gpt_verdict.json"))):
                findings.append(_gap(
                    "no_json_verdict", asset, "high",
                    f"{asset} está em '{st}' sem gpt_verdict.json estruturado",
                    "Estado avançado derivado de markdown frágil — emitir o sidecar (save_asset_verdict).",
                    asset=asset))
    # proposals: concorrência e obsolescência de programa
    state = ic_proposals.state()
    approved_envs = {p.get("environment") for p in state["approved"]
                     if p.get("type") == "furniture_program"}
    for p in state["pending"]:
        if p.get("type") != "furniture_program":
            continue
        env = p.get("environment", "?")
        # C3 — pending p/ cômodo que JÁ tem programa aprovado
        if env in approved_envs:
            findings.append(_gap(
                "competing_program", env, "med",
                f"cômodo '{env}' tem programa aprovado E proposta pendente",
                "Reconciliar: rejeitar a pendente ou substituir a aprovada.",
                environment=env))
        # C5 — pending que o gate do Arquiteto (SPEC-C) corrigiria (gerada antes do gate)
        _, rep = ic_arch.normalize_program(p.get("items", []), env)
        if rep["removed"] or rep["injected"]:
            findings.append(_gap(
                "buggy_pending_program", env, "med",
                f"proposta pendente de '{env}' viola o gate (cross-cômodo / sem CORE) — não aprovar como está",
                f"removeria={[r['asset'] for r in rep['removed']]} injetaria={rep['injected']} "
                f"— re-propor com o Arquiteto endurecido.",
                environment=env))
    # C4 — programa APROVADO que o gate determinístico (SPEC-C) corrigiria (aprovado antes do gate)
    for p in state["approved"]:
        if p.get("type") == "furniture_program":
            _, rep = ic_arch.normalize_program(p.get("items", []), p.get("environment"))
            if rep["removed"] or rep["injected"]:
                env = p.get("environment", "?")
                findings.append(_gap(
                    "stale_program", env, "high",
                    f"programa aprovado de '{env}' viola o gate (cross-cômodo / sem CORE)",
                    f"removeria={[r['asset'] for r in rep['removed']]} injetaria={rep['injected']} "
                    f"— re-propor e re-aprovar.",
                    environment=env))
    return findings


def audit_and_save() -> dict:
    """Salva os gaps NÃO resolvidos como proposals pending; remove pending obsoletos (gaps que
    sumiram). NUNCA toca approved/rejected (decisão humana). Idempotente."""
    findings = audit()
    fids = {f["id"] for f in findings}
    st = ic_proposals.state()
    handled = {p["id"] for s in ("approved", "rejected") for p in st[s]
               if p.get("type") == "consistency_gap"}
    saved = 0
    for f in findings:
        if f["id"] in handled:
            continue
        ic_proposals.save(f)
        saved += 1
    removed = 0
    for p in st["pending"]:
        if p.get("type") == "consistency_gap" and p["id"] not in fids:
            ic_proposals.delete(p["id"])
            removed += 1
    return {"found": len(findings), "saved": saved, "stale_removed": removed,
            "skipped_handled": len(fids & handled)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--save" in sys.argv:
        print(json.dumps(audit_and_save(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(audit(), ensure_ascii=False, indent=2))
