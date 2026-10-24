"""backlog_reconcile.py — reconcilia Issues, PRs e o Project conforme a tabela de transicoes da SPEC §10 (FP-057 P5).

    python -m tools.validation.backlog_reconcile            # so o plano, sem escrever
    python -m tools.validation.backlog_reconcile --apply    # aplica (precisa de token com escopo `project`)

As Issues sao canonicas; o Project e a vista. Transicoes (so quando o FATO existe; nada por mensagem de progresso):
  Backlog -> Ready            dependencias nao-Epic satisfeitas e elegivel (`backlog_discovery`);
  Ready/Backlog -> In Progress  claim ativo OU PR (rascunho ou pendente) citando a Issue;
  In Progress -> GPT Review   PR pronto e verde E a Issue exige revisao independente (label `gpt-review-required`/politica);
  In Progress -> Blocked      `blocked` + causa comprovada (label `bloqueio:*`);
  GPT Review -> In Progress   ultima revisao CHANGES_REQUESTED ou STALE (commit novo);
  GPT Review -> Done          Issue FECHADA + aprovacao verificada vigente + evidencia (o `backlog_gate` e a autoridade);
  In Progress -> Done         Issue FECHADA com evidencia e sem revisao exigida;
  Blocked -> Ready            causa resolvida (dependencia fechada / `BLOCK_STALE`).
Nunca move para Done sem Issue fechada com `**Evidência`; nunca cria cartao duplicado (`DUPLICATE_CARD` e reportado); se o status atual
mudou desde a leitura (`CONCURRENT_CHANGE`) pula a mudanca; rate limit adia (`DEFERRED`) e registra quando tentar de novo; sem token
a automacao e reportada como PARCIAL. Falha do Project nunca altera o resultado tecnico (que mora nas Issues).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from dataclasses import dataclass

from tools.validation import backlog_discovery as bd
from tools.validation import dependency_graph as dg
from tools.validation.review_verification import has_valid_approval

_EVID = re.compile(r"^\s*\*\*Evid[eê]ncia", re.IGNORECASE)
GRAPHQL_RESERVE = 400            # cota minima deixada para o resto do trabalho
COST_PER_MOVE = 8                # estimativa conservadora (item-edit + leitura amortizada)


@dataclass(frozen=True)
class Move:
    issue: int
    frm: str | None
    to: str
    reason: str


@dataclass(frozen=True)
class Anomaly:
    code: str
    issue: int
    detail: str

    def __str__(self) -> str:
        return f"#{self.issue} {self.code}: {self.detail}"


class RateLimited(RuntimeError):
    def __init__(self, reset_at: str, remaining: int):
        super().__init__(f"GraphQL: restam {remaining}; tentar de novo apos {reset_at}")
        self.reset_at, self.remaining = reset_at, remaining


def _has_evidence(issue: dict) -> bool:
    return any(_EVID.match(c.get("body", "")) for c in issue.get("comments", []))


def _requires_review(labels: set[str], policy: dict) -> bool:
    return bool(labels & set(policy.get("labels", ("gpt-review-required",))))


def _closed_needs_review(issue: dict, policy: dict) -> bool:
    """Mesma regra do `backlog_gate` (so fechamentos apos `effective_from`): o reconcile nunca contradiz o gate."""
    from tools.validation.backlog_gate import _needs_gpt_review
    return _needs_gpt_review(issue, {**policy, "labels": policy.get("labels", ())})


def plan(issues: list[dict], cards: list[dict], prs: list[dict], policy: dict, pr_lookup=None, claims: dict | None = None,
         now: dt.datetime | None = None) -> tuple[list[Move], list[Anomaly]]:
    """(movimentos, anomalias). `cards`: itens do Project [{"number", "status"}] — duplicatas aparecem como anomalia. Puro."""
    anomalies: list[Anomaly] = []
    seen: dict[int, str | None] = {}
    for c in cards:
        if c["number"] in seen:
            anomalies.append(Anomaly("DUPLICATE_CARD", c["number"], "mais de um cartao para a mesma Issue"))
        seen.setdefault(c["number"], c.get("status"))
    by_num = {i["number"]: i for i in issues}
    g = dg.build(issues, seen)
    verdicts = {v.node.number: v for v in bd.evaluate(g, prs, claims)}
    pr_refs: dict[int, list[dict]] = {}
    for p in prs:
        for n in {int(x) for x in re.findall(r"(?<![A-Za-z])(?:refs?|relates to)\s*:?\s*#(\d+)", p.get("body") or "", re.I)}:
            pr_refs.setdefault(n, []).append(p)
    moves: list[Move] = []
    for n, issue in sorted(by_num.items()):
        cur = seen.get(n)
        node = g.nodes[n]
        names = {lab["name"] for lab in issue.get("labels", [])}
        closed_ok = node.completed
        target, why = None, ""
        if node.kind == "epic":
            continue
        if issue["state"] == "CLOSED":
            if not closed_ok:
                continue                                                   # nao planejada: o cartao nao vira Done
            if not _has_evidence(issue):
                if cur == "Done":
                    anomalies.append(Anomaly("DONE_WITHOUT_EVIDENCE", n, "cartao em Done sem comentario `**Evidência`"))
                else:
                    anomalies.append(Anomaly("CLOSED_WITHOUT_EVIDENCE", n, "fechada sem evidencia: nao vai para Done"))
                continue
            if _closed_needs_review(issue, policy):
                ok, reasons = has_valid_approval({**issue, "number": n}, policy, pr_lookup or (lambda _n: None), now)
                if ok:
                    target, why = "Done", "fechada, com evidencia e aprovacao independente verificada"
                else:
                    target, why = "GPT Review", "fechada com evidencia; aguarda revisao independente: " + "; ".join(reasons)
            else:
                target, why = "Done", "fechada com evidencia; sem revisao independente exigida"
        elif cur == "Done":
            anomalies.append(Anomaly("DONE_NOT_CLOSED", n, "cartao em Done com a Issue aberta"))
            target, why = "In Progress", "Issue aberta nao pode estar em Done"
        elif node.blocked and node.cause not in (None, "dependency"):
            target, why = "Blocked", f"bloqueio {node.cause} comprovado"
        elif node.blocked and node.cause == "dependency" and g.open_hard_deps(n):
            target, why = "Blocked", "dependencia aberta: " + ", ".join(f"#{d}" for d in g.open_hard_deps(n))
        else:
            prs_n = pr_refs.get(n, [])
            ready_green = any(not p.get("isDraft") and p.get("checks") == "pass" for p in prs_n)
            if prs_n and ready_green and _requires_review(names, policy):
                target, why = "GPT Review", "PR pronto e verde; revisao independente exigida"
                ok, reasons = has_valid_approval({**issue, "number": n}, policy, pr_lookup or (lambda _n: None), now)
                if cur == "GPT Review" and not ok and any(("CHANGES_REQUESTED" in r or "STALE" in r) for r in reasons):
                    target, why = "In Progress", "revisao pediu correcoes ou ficou STALE com commit novo"
            elif prs_n or (claims and n in claims):
                target, why = "In Progress", "execucao assumida (claim ativo ou PR aberto)"
            elif cur == "Blocked" and verdicts.get(n) and verdicts[n].eligible:
                target, why = "Ready", "causa do bloqueio resolvida"
            elif cur in (None, "Backlog") and verdicts.get(n) and verdicts[n].eligible:
                target, why = "Ready", "dependencias satisfeitas e elegivel"
        if target and target != cur:
            moves.append(Move(n, cur, target, why))
    return moves, anomalies


def automation_state(has_token: bool, remaining: int | None) -> str:
    """Estado da automacao do Project: COMPLETE | PARTIAL (sem token) | DEFERRED (cota esgotada) | UNKNOWN."""
    if not has_token:
        return "PARTIAL"
    if remaining is None:
        return "UNKNOWN"
    return "DEFERRED" if remaining < GRAPHQL_RESERVE else "COMPLETE"


def check_budget(remaining: int, reset_at: str, n_moves: int) -> None:
    """Levanta `RateLimited` se aplicar `n_moves` deixaria a cota abaixo da reserva (adia, nao falha o resultado tecnico)."""
    if remaining - n_moves * COST_PER_MOVE < GRAPHQL_RESERVE:
        raise RateLimited(reset_at, remaining)


def apply(moves: list[Move], current_status: dict[int, str | None], set_status, remaining: int, reset_at: str) -> dict:
    """Aplica via `set_status(issue, status)`. Pula `CONCURRENT_CHANGE` (status mudou desde a leitura); adia por cota.
    Devolve {"applied": [...], "skipped": [...], "deferred": bool, "retry_after": reset_at|None}."""
    out = {"applied": [], "skipped": [], "deferred": False, "retry_after": None}
    try:
        check_budget(remaining, reset_at, len(moves))
    except RateLimited as exc:
        out.update(deferred=True, retry_after=exc.reset_at)
        return out
    for m in moves:
        if current_status.get(m.issue) != m.frm:
            out["skipped"].append((m.issue, "CONCURRENT_CHANGE"))
            continue
        set_status(m.issue, m.to)
        out["applied"].append((m.issue, m.frm, m.to))
    return out


def main(argv: list[str]) -> int:
    from tools.validation.backlog_gate import OWNER, PROJECT, REPO, ROOT, _gh, _pr_lookup
    do_apply = "--apply" in argv
    issues = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000",
                            "--json", "number,title,state,stateReason,closedAt,labels,body,comments"))
    prs_raw = json.loads(_gh("pr", "list", "--repo", REPO, "--state", "open", "--json", "number,body,isDraft,statusCheckRollup"))
    prs = [{**p, "checks": ("pass" if p.get("statusCheckRollup") and all(c.get("conclusion") in ("SUCCESS", "SKIPPED", "NEUTRAL")
                                                                         and c.get("status") == "COMPLETED" for c in p["statusCheckRollup"]) else "pending")}
           for p in prs_raw]
    rows = json.loads(_gh("project", "item-list", PROJECT, "--owner", OWNER, "--limit", "1000", "--format", "json"))["items"]
    cards = [{"number": r["content"]["number"], "status": r.get("status"), "id": r["id"]} for r in rows if r.get("content", {}).get("number")]
    pol_path = ROOT / "docs/governance/review_policy.json"
    policy = json.loads(pol_path.read_text(encoding="utf-8")) if pol_path.exists() else {}
    moves, anomalies = plan(issues, cards, prs, policy, _pr_lookup())
    rl = json.loads(_gh("api", "rate_limit"))["resources"]["graphql"]
    reset = dt.datetime.fromtimestamp(rl["reset"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"automacao do Project: {automation_state(True, rl['remaining'])} (cota GraphQL {rl['remaining']}/{rl['limit']}, reinicia {reset})")
    for m in moves:
        print(f"#{m.issue}: {m.frm} -> {m.to}  [{m.reason}]")
    for a in anomalies:
        print(a)
    print(f"backlog_reconcile: {len(moves)} movimento(s), {len(anomalies)} anomalia(s)")
    if do_apply and moves:
        from tools.validation.board_sync import PROJECT_ID
        fields = {f["name"]: f for f in json.loads(_gh("project", "field-list", PROJECT, "--owner", OWNER, "--format", "json"))["fields"]}
        ids = {c["number"]: c["id"] for c in cards}
        status_by = {c["number"]: c["status"] for c in cards}

        def set_status(n, status):
            opt = next(o["id"] for o in fields["Status"]["options"] if o["name"] == status)
            _gh("project", "item-edit", "--id", ids[n], "--project-id", PROJECT_ID, "--field-id", fields["Status"]["id"],
                "--single-select-option-id", opt)
        res = apply(moves, status_by, set_status, rl["remaining"], reset)
        print(json.dumps(res, ensure_ascii=False))
    return 1 if any(a.code in ("DONE_NOT_CLOSED", "DUPLICATE_CARD", "DONE_WITHOUT_EVIDENCE") for a in anomalies) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
