"""defect_intake.py — defeito novo vira Issue (sem duplicar), com criterios, dependencias e decisao de interrupcao (FP-057 P3).

Fluxo da SPEC §7: evidencia -> procurar Issue existente -> classificar -> causa-raiz/hipotese -> componentes e SPECs -> Issue com
criterios e prioridade -> interrompe a tarefa atual? Nunca cria SPEC nova; nunca cria Issue duplicada (reusa e comenta a
evidencia UMA vez, pelo hash dela). Funcoes puras; a escrita no GitHub entra por callbacks (`create`, `comment`) para testar sem rede.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

STOP = {"de", "da", "do", "das", "dos", "a", "o", "e", "em", "no", "na", "nos", "nas", "com", "para", "por", "que", "um", "uma",
        "ao", "se", "ou", "como", "sem", "sobre", "the", "of", "to", "in", "and"}
SEVERITY = ("CRITICAL", "HIGH", "NORMAL")


@dataclass
class Defect:
    title: str
    evidence: str                              # o que foi observado (comando, medida, arquivo)
    kind: str = "bug"                          # bug | technical-debt
    prio: str = "P1"
    spec: str = "FP-056"
    fase: str = "-"
    cause: str = "hipotese: a investigar"
    components: list[str] = field(default_factory=list)
    deps: list[int] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    severity: str = "NORMAL"                   # CRITICAL = invalida a implementacao/evidencia em curso


def tokens(text: str) -> set[str]:
    s = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return {t for t in re.findall(r"[a-z0-9_]+", s) if t not in STOP and len(t) > 1}


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def evidence_id(defect: Defect) -> str:
    return hashlib.sha256(defect.evidence.strip().encode("utf-8")).hexdigest()[:12]


def find_duplicate(issues: list[dict], defect: Defect, threshold: float = 0.55) -> dict | None:
    """Issue (aberta ou fechada) que ja cobre este defeito: titulo semelhante OU a mesma evidencia ja registrada OU o mesmo
    componente citado com titulo medianamente semelhante. Prefere aberta; entre iguais, a de menor numero."""
    eid = evidence_id(defect)
    best = None
    for i in sorted(issues, key=lambda x: (x["state"] != "OPEN", x["number"])):
        body = i.get("body") or ""
        sim = similarity(i.get("title", ""), defect.title)
        same_evidence = f"evidence:{eid}" in body
        same_component = bool(defect.components) and any(c in body or c in i.get("title", "") for c in defect.components) and sim >= 0.1
        if sim >= threshold or same_evidence or same_component:
            best = i
            break
    return best


def render_body(defect: Defect) -> str:
    comps = ", ".join(f"`{c}`" for c in defect.components) or "—"
    deps = ", ".join(f"#{d}" for d in defect.deps) or "—"
    acc = defect.acceptance or ["Causa provada e registrada na SPEC afetada", "Teste vermelho a partir da evidência, verde após a correção",
                                "Consumidores revalidados (gates do Quality Guardian)"]
    tipo = "Technical Debt" if defect.kind == "technical-debt" else "Bug"
    return (f"**Tipo:** {tipo} · **Prioridade:** {defect.prio} · **SPEC:** {defect.spec} · **Fase:** {defect.fase} · "
            f"**Aprovação humana pendente:** não\n**Dependências:** {deps}\n\n## Contexto\n{defect.cause}\n\n## Evidência\n"
            f"{defect.evidence}\n\n<!-- evidence:{evidence_id(defect)} -->\n\n## Componentes afetados\n{comps}\n\n"
            "## Critérios de aceite\n" + "\n".join(f"- [ ] {a}" for a in acc) +
            "\n\n> Origem: entrada automática de defeitos (FP-057 P3).")


def labels_for(defect: Defect) -> list[str]:
    return [f"tipo:{defect.kind}", f"prio:{defect.prio}", "prova:NOT_TESTED", f"spec:{defect.spec}", f"fase:{defect.fase}"]


def file_defect(issues: list[dict], defect: Defect, create, comment) -> dict:
    """Registra o defeito: reusa a Issue existente (comenta a evidencia nova UMA vez) ou cria. Devolve a acao tomada."""
    dup = find_duplicate(issues, defect)
    eid = evidence_id(defect)
    if dup is not None:
        already = f"evidence:{eid}" in (dup.get("body") or "") or any(f"evidence:{eid}" in (c.get("body") or "") for c in dup.get("comments", []))
        if not already:
            comment(dup["number"], f"**Nova evidência do mesmo defeito**\n\n{defect.evidence}\n\n<!-- evidence:{eid} -->")
        return {"action": "REUSED", "issue": dup["number"], "state": dup["state"], "commented": not already}
    n = create(defect.title, labels_for(defect), render_body(defect))
    return {"action": "CREATED", "issue": n, "commented": False}


def should_interrupt(current: dict | None, defect: Defect) -> bool:
    """Politica de interrupcao (SPEC §7): defeito CRITICO que toca a mesma area da tarefa corrente, ou que invalida a evidencia dela,
    tem prioridade; independente e so registrado. `current`: {"issue", "components": [...], "invalidated_by": [evidence ids]}."""
    if defect.severity != "CRITICAL":
        return False
    if current is None:
        return True
    return bool(set(defect.components) & set(current.get("components", []))) or evidence_id(defect) in current.get("invalidated_by", [])
