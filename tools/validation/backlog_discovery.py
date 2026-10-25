"""backlog_discovery.py — qual e a proxima tarefa elegivel? (FP-057 P1)

Entrada: Issues (+ status do Project, PRs abertos e reivindicacoes quando conhecidos). Saida: um veredito por Issue aberta —
elegivel ou nao, com as RAZOES (nunca silencio) — e a ordem de prioridade da SPEC §4. Puro: nenhuma escrita, nenhum relogio.

Elegivel = aberta, nao-Epic, com criterios de aceite, sem `blocked`, com todas as dependencias nao-Epic concluidas, sem decisao
humana/credencial/ambiente pendente, sem PR aberto que a cite (`Refs #N`), sem reivindicacao ativa, fora de `GPT Review`
(aguarda revisao independente) e sem conflito de componentes com outra reivindicacao.
Bloqueada por `technical` e item cuja dependencia acabou (`BLOCK_STALE`) sao devolvidas como elegiveis com `resume`/`unblock`:
o bloqueio real nao some porque o agente seguiu trabalhando, mas a causa resolvida reabre a tarefa.

Prioridade (menor rank = antes): 0 integridade/seguranca de artefatos (P0) · 1 falso PASS e gate incorreto · 2 destrava varias ·
3 regressao · 4 integracao FP-055/056 · 5 correcao funcional de comodo · 6 debito tecnico · 7 funcionalidade · 8 resto.
Dentro do rank: mais dependentes abertos primeiro (caminho critico), depois prioridade P0..P3, depois o numero.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tools.validation import dependency_graph as dg

_INTEGRITY = re.compile(r"artifacts/|\.skp|can[oô]nic|oficial|protegid|seguran[cç]a|grava|credencial|segredo", re.I)
_FALSE_PASS = re.compile(r"falso pass|pass vazio|\bgate\b|pr[eé]-voo|fail[- ]closed|n[ãa]o bloqueia|limiar|baseline|forj", re.I)
_REGRESSION = re.compile(r"regress", re.I)
_ROOMS = re.compile(r"c[ôo]modo|banho|su[ií]te|cozinha|lavabo|sala|\bA\.S\.|churrasqueira|tapete|porta|apoio|barreira|laje", re.I)
_REFS = re.compile(r"\b(?:refs?|relates to)\s*:?\s*#(\d+)", re.IGNORECASE)
PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass
class Verdict:
    node: dg.Node
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    action: str = "implement"            # implement | resume | unblock
    rank: int = 8
    blocks: int = 0
    next_step: str | None = None                 # da auditoria (task_readiness): proximo passo executavel agora
    offline: bool | None = None
    needs_sketchup: bool | None = None
    completion_blockers: list = field(default_factory=list)   # o que impede CONCLUIR: [{cause, ref, detail}]

    @property
    def key(self) -> tuple:
        # dentro do rank, o que pode ser CONCLUIDO de ponta a ponta (sem impedimento de conclusao) vem antes do que so comeca
        return (self.rank, bool(self.completion_blockers), -self.blocks, PRIO.get(self.node.prio, 9), self.node.number)

    def __str__(self) -> str:
        head = f"#{self.node.number} [{'ELEGIVEL ' + self.action if self.eligible else 'inelegivel'}] {self.node.title[:70]}"
        if not self.eligible:
            return head + "  <- " + "; ".join(self.reasons)
        tail = ""
        if self.next_step:
            kind = "offline" if self.offline else "SketchUp" if self.needs_sketchup else "?"
            tail += f"\n      proximo passo ({kind}): {self.next_step}"
        for b in self.completion_blockers:
            tail += f"\n      para concluir: {b['cause']} {b['ref']} - {b['detail']}"
        return head + tail


def category(node: dg.Node, blocks: int) -> int:
    t = node.title
    if node.prio == "P0" and _INTEGRITY.search(t):
        return 0
    if _FALSE_PASS.search(t):
        return 1
    if blocks >= 2:
        return 2
    if _REGRESSION.search(t) or "regressão" in node.labels:
        return 3
    if node.spec in ("FP-055", "FP-056", "FP-057") and node.kind in ("story", "task", "bug", "technical-debt"):
        return 4
    if _ROOMS.search(t):
        return 5
    if node.kind == "technical-debt":
        return 6
    if node.kind == "story":
        return 7
    return 8


def evaluate(g: dg.Graph, prs: list[dict] | None = None, claims: dict[int, dict] | None = None,
             readiness: dict[int, dict] | None = None) -> list[Verdict]:
    """Um `Verdict` por Issue aberta, ordenado pela prioridade (elegiveis primeiro). `claims`: {issue: {"components": [...]}}."""
    active_pr: dict[int, int] = {}
    for pr in prs or []:
        for n in {int(x) for x in _REFS.findall(pr.get("body") or "")}:
            active_pr[n] = pr["number"]
    claimed_components = {c for v in (claims or {}).values() for c in v.get("components", [])}
    out: list[Verdict] = []
    for n, node in sorted(g.nodes.items()):
        if node.state != "OPEN":
            continue
        reasons: list[str] = []
        action = "implement"
        if node.kind == "epic":
            reasons.append("EPIC: organizacao, nao e tarefa")
        if not node.has_acceptance and node.kind != "epic":
            reasons.append("NO_ACCEPTANCE_CRITERIA")
        if n in (claims or {}):
            reasons.append(f"CLAIMED: outra execucao ativa ({(claims or {})[n].get('agent', '?')})")
        if n in active_pr:
            reasons.append(f"ACTIVE_PR: #{active_pr[n]} cita esta Issue")
        if node.human_only_open_criteria and node.kind != "epic":
            reasons.append("HUMAN_VERDICT: o criterio que falta e do proprietario (veredito/decisao)")
        if node.status == "GPT Review":
            reasons.append("PENDING_REVIEW: aguarda revisao independente")
        open_deps = g.open_hard_deps(n)
        if open_deps:
            reasons.append(f"DEP_OPEN: {', '.join('#%d' % d for d in open_deps)}")
        if node.blocked:
            cause = node.cause or "sem-causa"
            if cause == "human-decision":
                reasons.append("HUMAN_DECISION: aguarda o proprietario")
            elif cause == "external":
                reasons.append("EXTERNAL: requisito externo pendente")
            elif cause == "environment":
                reasons.append("ENVIRONMENT: recuperar ou escalar o ambiente")
            elif cause == "evidence":
                reasons.append("EVIDENCE: aguarda prova (tarefa de validacao propria)")
            elif cause == "dependency" and not open_deps:
                action = "unblock"                                   # a causa acabou: reabre
            elif cause == "technical":
                action = "resume"                                    # investigar e corrigir
            elif cause != "dependency":
                reasons.append(f"BLOCKED: causa {cause}")
        elif node.human_flag:
            reasons.append("HUMAN_DECISION: aprovacao humana pendente")
        if re.match(r"\s*DECIS[ÃA]O\b", node.title, re.I) and not any(r.startswith("HUMAN") for r in reasons):
            reasons.append("HUMAN_DECISION: item de decisao")
        ready = (readiness or {}).get(n)
        if ready and ready.get("state") == "BLOCKED":
            reasons.append(f"{ready['cause']}: {ready['detail']} ({ready['ref']})")
        eligible = not reasons
        if eligible and node.status == "In Progress":
            action = "resume"
        v = Verdict(node, eligible, reasons, action, rank=category(node, len(g.dependents(n))), blocks=len(g.dependents(n)))
        if eligible and dg.component(node) in claimed_components:
            v.eligible, v.reasons = False, [f"COMPONENT_CONFLICT: {dg.component(node)} em uso por outra reivindicacao"]
        if ready and ready.get("state") == "READY" and v.eligible:
            v.next_step, v.offline, v.needs_sketchup = ready["next_step"], ready["offline"], ready["needs_sketchup"]
            v.completion_blockers = list(ready.get("completion_blockers", []))
        out.append(v)
    out.sort(key=lambda v: (not v.eligible, v.key))
    return out


def classify(v: Verdict) -> str:
    # READY / BLOCKED / PENDING_REVIEW / ENVIRONMENT / IN_PROGRESS (PR ou claim ativo) / EPIC - a contagem honesta do backlog aberto
    if v.node.kind == "epic":
        return "EPIC"
    if v.eligible:
        return "READY"
    text = " ".join(v.reasons)
    if "PENDING_REVIEW" in text or v.node.status == "GPT Review":
        return "PENDING_REVIEW"
    if v.node.cause == "environment" or text.startswith("ENVIRONMENT") or "; ENVIRONMENT" in text:
        return "ENVIRONMENT"
    if "ACTIVE_PR" in text:
        return "PENDING_REVIEW" if "gpt-review-required" in v.node.labels else "IN_PROGRESS"
    if text.startswith("CLAIMED"):
        return "IN_PROGRESS"
    return "BLOCKED"


def summarize(verdicts: list[Verdict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {k: [] for k in ("READY", "BLOCKED", "PENDING_REVIEW", "ENVIRONMENT", "IN_PROGRESS", "EPIC")}
    for v in verdicts:
        out[classify(v)].append(v.node.number)
    return out


def load_readiness() -> dict[int, dict]:
    from tools.validation import task_readiness
    return task_readiness.load()


def next_task(verdicts: list[Verdict]) -> Verdict | None:
    return next((v for v in verdicts if v.eligible), None)


def render(verdicts: list[Verdict], limit_ineligible: int = 40) -> str:
    el = [v for v in verdicts if v.eligible]
    inel = [v for v in verdicts if not v.eligible]
    counts = summarize(verdicts)
    lines = [f"Elegiveis: {len(el)} · inelegiveis: {len(inel)}", "Contagem: " + " · ".join(f"{k}={len(v)}" for k, v in counts.items()), ""]
    lines += [f"{i + 1}. {v}" for i, v in enumerate(el)]
    lines += ["", "Inelegiveis (razao registrada):"] + [f"- {v}" for v in inel[:limit_ineligible]]
    return "\n".join(lines)


def load(statuses: bool = False) -> tuple[list[dict], dict[int, str] | None, list[dict]]:
    """(issues, status do Project ou None, PRs abertos) via `gh`. O Project so e lido quando pedido (custa cota GraphQL)."""
    import json

    from tools.validation.backlog_gate import OWNER, PROJECT, REPO, _gh
    issues = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000",
                            "--json", "number,title,state,stateReason,labels,body"))
    prs = json.loads(_gh("pr", "list", "--repo", REPO, "--state", "open", "--json", "number,body,headRefName"))
    st = None
    if statuses:
        rows = json.loads(_gh("project", "item-list", PROJECT, "--owner", OWNER, "--limit", "1000", "--format", "json"))["items"]
        st = {r["content"]["number"]: r.get("status") for r in rows if r.get("content", {}).get("number")}
    return issues, st, prs


def main(argv: list[str]) -> int:
    issues, st, prs = load(statuses="--project" in argv)
    g = dg.build(issues, st)
    verdicts = evaluate(g, prs, readiness=load_readiness())
    print(render(verdicts))
    findings = dg.analyze(g)
    for f in findings:
        print(f)
    return 0 if not [f for f in findings if f.code in ("DEP_MISSING", "DEP_CYCLE", "DEP_SELF")] else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
