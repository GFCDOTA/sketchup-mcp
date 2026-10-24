"""backlog_gate.py — o quadro (GitHub Project) nao pode mentir sobre o estado das Issues.

Regras (cada uma devolve um `Finding` com codigo estavel):

- DONE_NOT_CLOSED          item em Done, mas a Issue segue aberta.
- CLOSED_NOT_DONE          Issue fechada como concluida, mas o item nao esta em Done.
- DONE_WITHOUT_EVIDENCE    Done/fechada sem comentario `**Evidencia ...` com commit ou teste citado.
- DONE_WITHOUT_PROOF       Done com "Estado da prova" NOT_TESTED ou BLOCKED.
- DONE_HUMAN_PENDING       Done com "Aprovacao humana pendente" = Sim.
- PROOF_WITHOUT_EVIDENCE   "Estado da prova" acima de NOT_TESTED sem comentario de evidencia.
- PROOF_LABEL_MISMATCH     label `prova:X` diferente do campo do Project.
- BLOCKED_LABEL_MISMATCH   Status Blocked sem label `blocked`, ou label `blocked` fora de Blocked.
- DEPENDENCY_OPEN          item Done com dependencia (#N) ainda aberta.
- DEPENDENCY_UNKNOWN       dependencia aponta para Issue inexistente.
- NOT_IN_PROJECT           Issue aberta fora do Project.

Nada vale por inferencia: o commit relacionado nao fecha item, o comentario de evidencia sim.
Excecao legitima so em `docs/governance/backlog_exceptions.json` (`{"<n>": {"<CODIGO>": "motivo"}}`).

Uso:  python -m tools.validation.backlog_gate [--no-project]   (exit 1 se houver divergencia)
`--no-project` (CI sem token de Projects) so aplica as regras que dependem de Issues e labels.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXCEPTIONS = ROOT / "docs/governance/backlog_exceptions.json"
REPO = "GFCDOTA/sketchup-mcp"
OWNER, PROJECT = "GFCDOTA", "1"
_EVIDENCE = re.compile(r"^\s*\*\*Evid[eê]ncia", re.IGNORECASE)
_CITES = re.compile(r"\b[0-9a-f]{7,40}\b|pytest|passed|L2")
_NOT_PROVEN = {"NOT_TESTED", "BLOCKED", None, ""}


@dataclass(frozen=True)
class Finding:
    issue: int
    code: str
    detail: str

    def __str__(self) -> str:
        return f"#{self.issue} {self.code}: {self.detail}"


def _has_evidence(issue: dict) -> bool:
    return any(_EVIDENCE.match(c.get("body", "")) and _CITES.search(c.get("body", "")) for c in issue.get("comments", []))


def _label(issue: dict, prefix: str) -> str | None:
    for lab in issue.get("labels", []):
        if lab["name"].startswith(prefix):
            return lab["name"][len(prefix):]
    return None


def _deps(item: dict) -> list[int]:
    return [int(x) for x in re.findall(r"#(\d+)", item.get("dependências") or "")]


def check(issues: dict[int, dict], items: dict[int, dict] | None, exceptions: dict | None = None) -> list[Finding]:
    """`issues`: numero -> {state, stateReason, labels, comments}. `items`: numero -> campos do Project (None = sem Project)."""
    found: list[Finding] = []
    for n, iss in sorted(issues.items()):
        closed_ok = iss["state"] == "CLOSED" and iss.get("stateReason", "COMPLETED") == "COMPLETED"
        item = items.get(n) if items is not None else None
        status = item.get("status") if item else None
        proof = (item or {}).get("estado da prova") or _label(iss, "prova:")
        done = status == "Done" or (items is None and closed_ok)

        if items is not None and iss["state"] == "OPEN" and item is None:
            found.append(Finding(n, "NOT_IN_PROJECT", "Issue aberta fora do Project"))
        if item:
            if status == "Done" and iss["state"] != "CLOSED":
                found.append(Finding(n, "DONE_NOT_CLOSED", "Status Done com a Issue aberta"))
            if closed_ok and status != "Done":
                found.append(Finding(n, "CLOSED_NOT_DONE", f"Issue concluida, Status={status}"))
            if status == "Done" and proof in _NOT_PROVEN:
                found.append(Finding(n, "DONE_WITHOUT_PROOF", f"Estado da prova={proof}"))
            if status == "Done" and item.get("aprovação humana pendente") == "Sim":
                found.append(Finding(n, "DONE_HUMAN_PENDING", "aprovacao humana pendente"))
            has_blocked = any(lab["name"] == "blocked" for lab in iss["labels"])
            if (status == "Blocked") != has_blocked and iss["state"] == "OPEN":
                found.append(Finding(n, "BLOCKED_LABEL_MISMATCH", f"Status={status}, label blocked={has_blocked}"))
            field = item.get("estado da prova")
            lab = _label(iss, "prova:")
            if field and lab and field != lab:
                found.append(Finding(n, "PROOF_LABEL_MISMATCH", f"campo={field}, label={lab}"))
            if status == "Done":
                for d in _deps(item):
                    dep = issues.get(d)
                    if dep is None:
                        found.append(Finding(n, "DEPENDENCY_UNKNOWN", f"#{d}"))
                    elif dep["state"] == "OPEN":
                        found.append(Finding(n, "DEPENDENCY_OPEN", f"Done com #{d} aberta"))
        if done and not _has_evidence(iss):
            found.append(Finding(n, "DONE_WITHOUT_EVIDENCE", "sem comentario '**Evidencia' com commit/teste"))
        if proof not in _NOT_PROVEN and not _has_evidence(iss):
            found.append(Finding(n, "PROOF_WITHOUT_EVIDENCE", f"prova {proof} sem comentario de evidencia"))
    ok = exceptions or {}
    return [f for f in found if f.code not in ok.get(str(f.issue), {})]


def _gh(*args: str) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return out.stdout


def load(use_project: bool) -> tuple[dict, dict | None]:
    raw = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000",
                         "--json", "number,state,stateReason,labels,comments"))
    issues = {i["number"]: i for i in raw}
    if not use_project:
        return issues, None
    rows = json.loads(_gh("project", "item-list", PROJECT, "--owner", OWNER, "--limit", "1000", "--format", "json"))["items"]
    return issues, {r["content"]["number"]: r for r in rows if r.get("content", {}).get("number")}


def main(argv: list[str]) -> int:
    issues, items = load("--no-project" not in argv)
    exceptions = json.loads(EXCEPTIONS.read_text(encoding="utf-8")) if EXCEPTIONS.exists() else {}
    findings = check(issues, items, exceptions)
    for f in findings:
        print(f)
    print(f"backlog_gate: {len(findings)} divergencia(s) em {len(issues)} Issue(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
