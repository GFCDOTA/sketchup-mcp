"""task_scheduler.py — escolhe e reivindica a proxima tarefa elegivel; retoma execucoes interrompidas (FP-057 P2).

    python -m tools.validation.task_scheduler status             # estado, claims e proxima tarefa
    python -m tools.validation.task_scheduler next [--project]   # so mostra a proxima elegivel e as razoes das demais
    python -m tools.validation.task_scheduler claim [--issue N] --agent NOME --branch B --base SHA
    python -m tools.validation.task_scheduler recover            # o que fazer com cada claim interrompido
    python -m tools.validation.task_scheduler release --issue N

Nao executa a tarefa: devolve a decisao e persiste o checkpoint. A Issue/PR/board continuam canonicos no GitHub.
"""
from __future__ import annotations

import argparse
import json
import sys

from tools.validation import backlog_discovery as bd
from tools.validation import dependency_graph as dg
from tools.validation import execution_state as es


def decide(issues: list[dict], prs: list[dict], state: dict, statuses: dict[int, str] | None = None,
           only_issue: int | None = None, agent: str = "claude") -> tuple[bd.Verdict | None, list[bd.Verdict]]:
    """Proxima tarefa elegivel (ou a pedida, se elegivel) considerando os claims ATIVOS de OUTRAS execucoes. Puro.
    Se ESTA execucao ja tem uma tarefa reivindicada e nao concluida, ela vem primeiro (`action=resume`; use `plan_recovery`)."""
    g = dg.build(issues, statuses)
    claims = es.active_claims(state)
    others = {n: {"agent": c["agent"], "components": c["components"]} for n, c in claims.items() if c["agent"] != agent}
    verdicts = bd.evaluate(g, prs, others)
    own = [n for n, c in sorted(claims.items()) if c["agent"] == agent and c["state"] != "DONE"]
    if own and only_issue is None:
        mine = next((v for v in bd.evaluate(g, [], others) if v.node.number == own[0]), None)
        if mine is not None:
            mine.eligible, mine.reasons, mine.action = True, [], "resume"
            return mine, verdicts

    if only_issue is not None:
        return next((v for v in verdicts if v.node.number == only_issue and v.eligible), None), verdicts
    return bd.next_task(verdicts), verdicts


def take(state: dict, verdict: bd.Verdict, agent: str, branch: str, base: str) -> dict:
    """Reivindica a tarefa e registra o checkpoint (idempotente para o mesmo agente)."""
    comps = [dg.component(verdict.node)]
    c = es.claim(state, verdict.node.number, agent, branch, base, comps)
    state["active_spec"], state["active_phase"] = verdict.node.spec, verdict.node.fase
    return c


def checkpoint_after(state: dict, verdicts: list[bd.Verdict], prs: list[dict], limit: int = 5) -> None:
    state["next_eligible_issues"] = [v.node.number for v in verdicts if v.eligible][:limit]
    state["blocked_issues"] = sorted(v.node.number for v in verdicts if v.node.blocked)
    state["open_pull_requests"] = sorted(p["number"] for p in prs)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("status", "next", "claim", "recover", "release"))
    ap.add_argument("--project", action="store_true")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--agent", default="claude")
    ap.add_argument("--branch", default="")
    ap.add_argument("--base", default="")
    a = ap.parse_args(argv)
    path = es.state_path()
    if a.cmd == "release":
        with es.locked(path):
            st = es.load(path)
            es.release(st, a.issue)
            es.save(st, path)
        print(f"#{a.issue} liberada")
        return 0
    issues, statuses, prs = bd.load(statuses=a.project)
    with es.locked(path):
        st = es.load(path)
        if a.cmd == "recover":
            from tools.validation.backlog_gate import REPO, _gh
            for n, c in sorted(st["claims"].items()):
                pr = next((p for p in prs if p.get("headRefName") == c["branch"]), None)
                merged = None
                if pr is None and c["branch"]:
                    found = json.loads(_gh("pr", "list", "--repo", REPO, "--state", "merged", "--head", c["branch"], "--json", "number"))
                    merged = bool(found)
                facts = {"branch_exists": bool(c["branch"]), "pr": ({"number": pr["number"], "state": "OPEN", "merged": False,
                                                                       "checks": "pending"} if pr else ({"merged": True} if merged else None)),
                         "issue_closed": any(i["number"] == int(n) and i["state"] == "CLOSED" for i in issues), "board_synced": False}
                print(f"#{n} ({c['state']}, lease {c['lease_expires']}): {es.plan_recovery(c, facts)}")
            return 0
        task, verdicts = decide(issues, prs, st, statuses, a.issue)
        checkpoint_after(st, verdicts, prs)
        if a.cmd == "claim":
            if task is None:
                print("nenhuma tarefa elegivel para reivindicar")
                es.save(st, path)
                return 1
            take(st, task, a.agent, a.branch, a.base)
            print(f"reivindicada: {task}")
        elif a.cmd == "status":
            print(json.dumps({k: st[k] for k in ("current_issue", "current_branch", "claims", "next_eligible_issues", "blocked_issues",
                                                 "open_pull_requests")}, indent=1, ensure_ascii=False))
        if a.cmd in ("next", "status"):
            print(bd.render(verdicts, 15))
        es.save(st, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
