"""review_verification.py — aprovacao independente VERIFICAVEL (FP-057 P4).

O texto `GPT-REVIEW: APPROVED` sozinho nao prova nada: qualquer um (inclusive o executor) o escreve. Uma aprovacao so vale quando
o comentario tem o bloco estruturado e TODOS os fatos conferem:

    GPT-REVIEW: APPROVED | CHANGES_REQUESTED
    PR: #N
    SHA: <commit revisado: prefixo >= 7 do HEAD do PR>
    Reviewer: <login autorizado>
    Date: YYYY-MM-DD
    Evidence: <o que foi lido/executado>

Regras (fail-closed; sem politica, sem revisor autorizado ou sem fato do PR => NAO verificada):
- o AUTOR do comentario esta em `review_policy.reviewers` e NAO em `executor_logins` (o executor nao aprova o proprio trabalho);
- `Reviewer:` bate com o autor; `PR:` existe e a Issue e citada por ele (`Refs #N`);
- `SHA` e prefixo do HEAD atual do PR — commit novo depois da revisao a **invalida** (STALE);
- `Date` nao e anterior ao commit revisado nem ao futuro; `CHANGES_REQUESTED` nunca conta como aprovacao.
Limite declarado: com UMA conta do GitHub para executor e revisor a independencia nao e verificavel pelo GitHub; por isso
`reviewers` comeca vazio e a aprovacao independente fica pendente ate o proprietario configurar identidades distintas.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

_FIELD = {k: re.compile(rf"^\s*{k}\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE) for k in ("PR", "SHA", "Reviewer", "Date", "Evidence")}
_VERDICT = re.compile(r"^\s*GPT-REVIEW\s*:\s*(APPROVED|CHANGES_REQUESTED)\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass
class Review:
    status: str                                       # APPROVED | CHANGES_REQUESTED | STALE | INVALID
    reasons: list[str] = field(default_factory=list)
    pr: int | None = None
    sha: str | None = None


def parse(body: str) -> dict | None:
    m = _VERDICT.search(body or "")
    if not m:
        return None
    out = {"verdict": m.group(1).upper()}
    for k, rx in _FIELD.items():
        f = rx.search(body)
        out[k.lower()] = f.group(1).strip() if f else None
    out["pr"] = int(re.sub(r"\D", "", out["pr"] or "") or 0) or None
    return out


def verify(comment: dict, issue_number: int, policy: dict, pr_facts, now: dt.datetime | None = None) -> Review | None:
    """`comment`: {body, author:{login}, createdAt}. `pr_facts(n)` -> {"headRefOid","headDate","refs":[issues],"exists":bool} ou None.
    Devolve None se o comentario nao e uma revisao; senao um `Review` (INVALID/STALE trazem as razoes)."""
    p = parse(comment.get("body", ""))
    if p is None:
        return None
    why: list[str] = []
    login = (comment.get("author") or {}).get("login", "")
    reviewers = [x.lower() for x in policy.get("reviewers", [])]
    executors = [x.lower() for x in policy.get("executor_logins", [])]
    if not reviewers:
        why.append("nenhum revisor autorizado configurado (review_policy.reviewers vazio)")
    elif login.lower() not in reviewers:
        why.append(f"autor {login!r} nao e revisor autorizado")
    if login.lower() in executors:
        why.append(f"autor {login!r} e o executor: nao aprova o proprio trabalho")
    if (p.get("reviewer") or "").lower() != login.lower():
        why.append("campo Reviewer nao bate com o autor do comentario")
    if not p["pr"]:
        why.append("sem PR no bloco")
    facts = pr_facts(p["pr"]) if p["pr"] else None
    sha = (p.get("sha") or "").lower()
    if p["pr"] and not facts:
        why.append(f"PR #{p['pr']} nao verificavel (fato indisponivel: fail-closed)")
    if facts:
        if not facts.get("exists", True):
            why.append(f"PR #{p['pr']} inexistente")
        if issue_number not in facts.get("refs", []):
            why.append(f"PR #{p['pr']} nao cita a Issue #{issue_number}")
        if len(sha) < 7 or not facts.get("headRefOid", "").lower().startswith(sha):
            stale = len(sha) >= 7 and bool(facts.get("headRefOid"))
            if not why:
                return Review("STALE", [f"SHA revisado {sha[:8]} != HEAD atual {facts.get('headRefOid', '')[:8]}: commit novo invalida a aprovacao"],
                              p["pr"], sha)
            why.append("SHA nao confere com o HEAD do PR" if stale else "SHA ausente ou curto demais")
        try:
            day = dt.date.fromisoformat(p.get("date") or "")
            head_day = dt.date.fromisoformat((facts.get("headDate") or "")[:10])
            today = (now or dt.datetime.now(dt.timezone.utc)).date()
            if day < head_day or day > today:
                why.append(f"Date {day} fora de [{head_day}, {today}]")
        except ValueError:
            why.append("Date ausente ou invalida")
    if not p.get("evidence"):
        why.append("sem Evidence")
    if why:
        return Review("INVALID", why, p["pr"], sha)
    return Review(p["verdict"], [], p["pr"], sha)


def has_valid_approval(issue: dict, policy: dict, pr_facts, now: dt.datetime | None = None) -> tuple[bool, list[str]]:
    """True se existe aprovacao verificada VIGENTE (a mais recente prevalece: CHANGES_REQUESTED/STALE depois dela a anula)."""
    reviews = [r for c in sorted(issue.get("comments", []), key=lambda c: c.get("createdAt", ""))
               if (r := verify(c, issue["number"], policy, pr_facts, now)) is not None]
    if not reviews:
        return False, ["nenhuma revisao independente registrada"]
    last = reviews[-1]
    if last.status == "APPROVED":
        return True, []
    return False, [f"ultima revisao: {last.status} — " + "; ".join(last.reasons or ["correcoes solicitadas"])]
