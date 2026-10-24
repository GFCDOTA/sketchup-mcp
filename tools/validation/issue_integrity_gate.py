"""issue_integrity_gate.py — Issues, criterios de aceite e bloqueios coerentes (Quality Guardian, P1).

Complementa `backlog_gate` (que compara Issues x Project). Aqui so Issues, labels, corpo e SPECs; roda no CI sem token de Projects.

- ACCEPTANCE_MISSING        Issue aberta (nao Epic) sem secao de criterios de aceite com ao menos um item `- [ ]`.
- BLOCK_REASON_MISSING      label `blocked` sem exatamente um `bloqueio:<causa>` (technical | dependency | evidence | human-decision |
                           external | environment: taxonomia da FP-057).
- BLOCK_REASON_WITHOUT_BLOCK  `bloqueio:*` numa Issue sem `blocked` (ou fechada): causa de bloqueio que nao bloqueia mais.
- BLOCK_EPIC                Epic agregadora com `blocked` ou `aprovacao-humana-pendente`: Epic nao e decisao humana individual.
- BLOCK_HUMAN_FLAG_MISMATCH `bloqueio:human-decision` sem `aprovação-humana-pendente` (ou o inverso fora de Epic).
- BLOCK_HUMAN_NO_ALTERNATIVES  decisao humana sem secao `Alternativas` e `Recomenda`: o dono recebe opcoes verificadas, nao um pedido aberto.
- BLOCK_EXTERNAL_NO_REQUIREMENT  `bloqueio:external` sem secao `Requisito externo`; `bloqueio:environment` sem secao `Recuperação`.
- BLOCK_DEPENDENCY_STALE    `bloqueio:dependency` cujas dependencias (#N do corpo) estao todas fechadas (ou nenhuma aberta).
- SPEC_LABEL_UNKNOWN        label `spec:X` sem arquivo `docs/specs/X*.md` (X = o que vier antes de `/`).

Excecoes legitimas: `docs/governance/backlog_exceptions.json` (`{"<n>": {"<CODIGO>": "motivo"}}`).
Uso:  python -m tools.validation.issue_integrity_gate      (exit 1 se houver divergencia; precisa de `gh` autenticado)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tools.validation.backlog_gate import REPO, Finding, _gh

ROOT = Path(__file__).resolve().parent.parent.parent
CAUSES = ("technical", "dependency", "evidence", "human-decision", "external", "environment")
HUMAN_FLAG = "aprovação-humana-pendente"
_ACCEPT = re.compile(r"critérios? de aceite", re.IGNORECASE)
_CHECK = re.compile(r"^\s*-\s*\[[ xX]\]", re.MULTILINE)
_DEPS = re.compile(r"\*\*Dependências:\*\*\s*(.*)")


def _names(issue: dict) -> set[str]:
    return {lab["name"] for lab in issue.get("labels", [])}


def _is_epic(issue: dict) -> bool:
    return "tipo:epic" in _names(issue)


def _spec_exists(label: str, specs: set[str]) -> bool:
    key = label.split(":", 1)[1].split("/")[0]
    return any(s.startswith(key) for s in specs)


def check(issues: dict[int, dict], specs: set[str], exceptions: dict | None = None) -> list[Finding]:
    found: list[Finding] = []
    for n, iss in sorted(issues.items()):
        names, body, open_ = _names(iss), iss.get("body") or "", iss.get("state") == "OPEN"
        causes = sorted(x.split(":", 1)[1] for x in names if x.startswith("bloqueio:"))
        if open_ and not _is_epic(iss):
            m = _ACCEPT.search(body)
            if not (m and _CHECK.search(body[m.start():])):
                found.append(Finding(n, "ACCEPTANCE_MISSING", "sem secao de criterios de aceite com itens"))
        if open_ and "blocked" in names and len(causes) != 1:
            found.append(Finding(n, "BLOCK_REASON_MISSING", f"blocked com causas={causes} (esperado exatamente 1 de {CAUSES})"))
        if causes and not ("blocked" in names and open_):
            found.append(Finding(n, "BLOCK_REASON_WITHOUT_BLOCK", f"label {causes} fora de uma Issue aberta e bloqueada"))
        if any(c not in CAUSES for c in causes):
            found.append(Finding(n, "BLOCK_REASON_MISSING", f"causa desconhecida: {causes}"))
        if _is_epic(iss) and ("blocked" in names or HUMAN_FLAG in names):
            found.append(Finding(n, "BLOCK_EPIC", "Epic agregadora nao e decisao humana nem fica bloqueada"))
        human = "human-decision" in causes
        if open_ and not _is_epic(iss) and human != (HUMAN_FLAG in names):
            found.append(Finding(n, "BLOCK_HUMAN_FLAG_MISMATCH", f"human-decision={human}, flag={HUMAN_FLAG in names}"))
        if open_ and human and not (re.search(r"alternativas", body, re.I) and re.search(r"recomenda", body, re.I)):
            found.append(Finding(n, "BLOCK_HUMAN_NO_ALTERNATIVES", "decisao humana sem 'Alternativas' e 'Recomendação'"))
        if open_ and "external" in causes and not re.search(r"requisito externo", body, re.I):
            found.append(Finding(n, "BLOCK_EXTERNAL_NO_REQUIREMENT", "bloqueio externo sem secao 'Requisito externo'"))
        if open_ and "environment" in causes and not re.search(r"recupera[çc][ãa]o", body, re.I):
            found.append(Finding(n, "BLOCK_EXTERNAL_NO_REQUIREMENT", "bloqueio de ambiente sem secao 'Recuperação'"))
        if open_ and "dependency" in causes:
            m = _DEPS.search(body)
            deps = [int(x) for x in re.findall(r"#(\d+)", m.group(1))] if m else []
            real = [d for d in deps if d in issues and not _is_epic(issues[d])]
            if not any(issues[d]["state"] == "OPEN" for d in real):
                found.append(Finding(n, "BLOCK_DEPENDENCY_STALE", f"nenhuma dependencia aberta entre {real}"))
        for lab in sorted(names):
            if lab.startswith("spec:") and not _spec_exists(lab, specs):
                found.append(Finding(n, "SPEC_LABEL_UNKNOWN", f"{lab} sem arquivo em docs/specs/"))
    ok = exceptions or {}
    return [f for f in found if f.code not in ok.get(str(f.issue), {})]


def load() -> dict[int, dict]:
    raw = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000", "--json", "number,state,labels,body"))
    return {i["number"]: i for i in raw}


def main() -> int:
    exc_path = ROOT / "docs/governance/backlog_exceptions.json"
    exceptions = json.loads(exc_path.read_text(encoding="utf-8")) if exc_path.exists() else {}
    specs = {p.name for p in (ROOT / "docs/specs").glob("*.md")}
    findings = check(load(), specs, exceptions)
    for f in findings:
        print(f)
    print(f"issue_integrity_gate: {len(findings)} divergencia(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
