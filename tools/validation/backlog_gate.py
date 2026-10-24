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
- DEPENDENCY_OPEN          item Done com dependencia (#N) ainda aberta (Epic pai aberto nao bloqueia o filho).
- DEPENDENCY_UNKNOWN       dependencia aponta para Issue inexistente.
- NOT_IN_PROJECT           Issue aberta fora do Project.
- DONE_WITHOUT_GPT_REVIEW  Issue fechada depois de `effective_from` (docs/governance/review_policy.json) que exige revisao
                           independente (label `prio:P0` ou `gpt-review-required`) sem aprovacao VERIFICADA
                           (`review_verification`: revisor autorizado e distinto do executor, PR, SHA igual ao HEAD, data, evidencia;
                           o texto `GPT-REVIEW: APPROVED` sozinho NAO vale); ate la ela fica em *GPT Review*, nao em Done.

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


def _needs_gpt_review(iss: dict, policy: dict | None) -> bool:
    if not policy or iss.get("state") != "CLOSED" or iss.get("stateReason", "COMPLETED") != "COMPLETED":
        return False
    if (iss.get("closedAt") or "") < policy.get("effective_from", "9999"):
        return False
    labels = {lab["name"] for lab in iss.get("labels", [])}
    return bool(labels & set(policy.get("labels", ())))


def check(issues: dict[int, dict], items: dict[int, dict] | None, exceptions: dict | None = None,
          review_policy: dict | None = None, pr_lookup=None, now=None) -> list[Finding]:
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
                    elif dep["state"] == "OPEN" and not any(lab["name"] == "tipo:epic" for lab in dep["labels"]):
                        found.append(Finding(n, "DEPENDENCY_OPEN", f"Done com #{d} aberta"))
        needs_review = _needs_gpt_review(iss, review_policy) or (
            status == "Done" and _needs_gpt_review({**iss, "state": "CLOSED"}, review_policy))
        if needs_review:
            from tools.validation.review_verification import has_valid_approval
            ok, why = has_valid_approval({**iss, "number": n}, review_policy or {}, pr_lookup or (lambda _n: None), now)
            if not ok:
                found.append(Finding(n, "DONE_WITHOUT_GPT_REVIEW", "revisao independente nao verificada: " + "; ".join(why)))
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
                         "--json", "number,state,stateReason,labels,comments,closedAt"))
    issues = {i["number"]: i for i in raw}
    if not use_project:
        return issues, None
    rows = json.loads(_gh("project", "item-list", PROJECT, "--owner", OWNER, "--limit", "1000", "--format", "json"))["items"]
    return issues, {r["content"]["number"]: r for r in rows if r.get("content", {}).get("number")}


def _pr_lookup():
    """Fatos do PR para verificar revisoes (HEAD, data do ultimo commit, Issues citadas). None se `gh` falhar: fail-closed."""
    cache: dict[int, dict | None] = {}

    def lookup(n: int):
        if n not in cache:
            try:
                d = json.loads(_gh("pr", "view", str(n), "--repo", REPO, "--json", "headRefOid,commits,body"))
                refs = [int(x) for x in re.findall(r"(?<![A-Za-z])(?:refs?|relates to)\s*:?\s*#(\d+)", d.get("body") or "", re.I)]
                cache[n] = {"exists": True, "headRefOid": d["headRefOid"], "headDate": (d["commits"][-1]["committedDate"] if d["commits"] else ""),
                            "refs": refs}
            except (RuntimeError, ValueError, KeyError, IndexError):
                cache[n] = None
        return cache[n]
    return lookup


def main(argv: list[str]) -> int:
    issues, items = load("--no-project" not in argv)
    exceptions = json.loads(EXCEPTIONS.read_text(encoding="utf-8")) if EXCEPTIONS.exists() else {}
    pol_path = ROOT / "docs/governance/review_policy.json"
    policy = json.loads(pol_path.read_text(encoding="utf-8")) if pol_path.exists() else None
    findings = check(issues, items, exceptions, policy, _pr_lookup())
    for f in findings:
        print(f)
    print(f"backlog_gate: {len(findings)} divergencia(s) em {len(issues)} Issue(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
