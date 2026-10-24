"""recovery_proof.py — prova de recuperacao ponta a ponta no GitHub real (FP-057 P6).

    python -m tools.validation.recovery_proof [--keep]

Cria uma Issue SINTETICA (label `tipo:task`, titulo `[RECOVERY-PROOF]`), roda o fluxo real e fecha como NOT_PLANNED:
  1. a Issue sintetica e descoberta como elegivel e reivindicada (claim com lease);
  2. "reinicio": o estado e recarregado do disco por outra instancia; o claim sobrevive e o scheduler manda RETOMAR (nao reabrir);
  3. com um PR aberto de checks `fail` o plano de recuperacao e corrigir o MESMO PR; com `pass`, mergear; PR mergeado, so reconciliar;
  4. operacao com efeito externo (`once`) executa uma unica vez mesmo apos o reinicio;
  5. o plano do board para a Issue nao cria cartao duplicado e nao a leva a Done (fechada NOT_PLANNED);
  6. uma tarefa de revisao independente pendente nao impede o scheduler de escolher outra elegivel.
Nada oficial e tocado: o estado vive em arquivo temporario e a Issue sintetica fecha no fim. Saida: JSON em stdout.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from tools.validation import backlog_discovery as bd
from tools.validation import backlog_reconcile as br
from tools.validation import dependency_graph as dg
from tools.validation import execution_state as es
from tools.validation import task_scheduler as ts

ACCEPT = "## Critérios de aceite\n- [ ] prova de recuperacao executada\n"
AGENT = "recovery-proof"


def synthetic(n: int, labels=(), state="OPEN", title="[RECOVERY-PROOF] sintetica") -> dict:
    return {"number": n, "title": title, "state": state, "stateReason": "COMPLETED", "body": ACCEPT, "comments": [],
            "labels": [{"name": x} for x in ("tipo:task", "prio:P3", *labels)]}


def run(issue_no: int, pr_no: int) -> dict:
    """Cenario completo sobre `issue_no` real (sintetica) e PR ficticio de fatos injetados. Devolve {checks: {nome: bool}, ...}."""
    out: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "runs" / "governance" / "execution_state.json"
        issue = synthetic(issue_no)
        other = synthetic(issue_no + 1000000, title="[RECOVERY-PROOF] outra elegivel")
        review = synthetic(issue_no + 2000000, ["gpt-review-required"], title="[RECOVERY-PROOF] aguardando revisao")
        statuses = {review["number"]: "GPT Review"}

        # 1. descoberta + claim
        with es.locked(path):
            st = es.load(path)
            task, _ = ts.decide([issue, other, review], [], st, statuses, issue_no, AGENT)
            assert task is not None and task.eligible
            ts.take(st, task, AGENT, "feat/recovery-proof", "deadbee")
            es.advance(st, issue_no, "EDITING")
            assert es.once(st, f"open-pr:{issue_no}")
            es.save(st, path)
        out["claimed"] = True

        # 2. reinicio: outra instancia le o disco; o claim sobrevive e manda retomar
        with es.locked(path):
            st2 = es.load(path)
            resumed, _ = ts.decide([issue, other, review], [], st2, statuses, None, AGENT)
        out["resume_after_restart"] = bool(resumed and resumed.node.number == issue_no and resumed.action == "resume")

        # 3. plano de recuperacao a partir de fatos
        c = st2["claims"][str(issue_no)]
        phase = lambda pr: es.plan_recovery(c, {"branch_exists": True, "pr": pr, "board_synced": False, "issue_closed": False})[0]   # noqa: E731
        out["recovery"] = {"checks_fail": phase({"number": pr_no, "state": "OPEN", "merged": False, "checks": "fail"}),
                           "checks_pending": phase({"number": pr_no, "state": "OPEN", "merged": False, "checks": "pending"}),
                           "checks_pass": phase({"number": pr_no, "state": "OPEN", "merged": False, "checks": "pass"}),
                           "merged": phase({"number": pr_no, "merged": True})}

        # 4. efeito externo uma unica vez, mesmo apos reinicio
        with es.locked(path):
            st3 = es.load(path)
            out["once_second_time_blocked"] = es.once(st3, f"open-pr:{issue_no}") is False

        # 5. board: sem duplicata, nunca Done para NOT_PLANNED
        closed = {**issue, "state": "CLOSED", "stateReason": "NOT_PLANNED"}
        moves, anomalies = br.plan([closed], [{"number": issue_no, "status": "Backlog"}], [], {}, None)
        out["board_no_done_for_not_planned"] = not any(m.to == "Done" for m in moves)
        dup_moves, dup_an = br.plan([issue], [{"number": issue_no, "status": "Ready"}, {"number": issue_no, "status": "Backlog"}], [], {})
        out["duplicate_card_reported"] = [a.code for a in dup_an] == ["DUPLICATE_CARD"]
        _ = anomalies, dup_moves

        # 6. revisao pendente nao trava o resto
        g = dg.build([other, review], statuses)
        v = bd.next_task(bd.evaluate(g, [], {}))
        out["pending_review_does_not_block_others"] = bool(v and v.node.number == other["number"])
    out["ok"] = all(v is True for k, v in out.items() if isinstance(v, bool)) and out["recovery"] == {
        "checks_fail": "EDITING", "checks_pending": "CI_PENDING", "checks_pass": "MERGING", "merged": "BOARD_SYNC"}
    return out


def main(argv: list[str]) -> int:
    from tools.validation.backlog_gate import REPO, _gh
    url = _gh("issue", "create", "--repo", REPO, "--title", "[RECOVERY-PROOF] sintetica (fecha sozinha)", "--label", "tipo:task",
              "--body", ACCEPT + "\nIssue sintetica da prova P6 (FP-057). Fecha como NOT_PLANNED ao fim da execucao.").strip().splitlines()[-1]
    n = int(url.rsplit("/", 1)[1])
    try:
        # a Issue real e relida do GitHub para provar que o ciclo usa dados reais
        real = json.loads(_gh("issue", "view", str(n), "--repo", REPO, "--json", "number,title,state,stateReason,labels,body"))
        res = run(real["number"], 0)
        res["issue"] = n
    finally:
        if "--keep" not in argv:
            _gh("issue", "close", str(n), "--repo", REPO, "--reason", "not planned",
                "--comment", "Issue sintetica da prova de recuperacao FP-057 P6; encerrada automaticamente.")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
