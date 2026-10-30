"""autonomous_status.py — relatorio `AUTONOMOUS ENGINEERING STATUS` a partir do estado REAL (FP-057 P7).

    python -m tools.validation.autonomous_status [--write docs/reports/fp057/status/<data>.md]

Le Issues, PRs abertos, execution_state e as politicas; nao inventa nada: cada linha vem de um fato consultavel. Declara os limites da
automacao (sem runner 24/7, token do Project, revisor independente) em vez de omiti-los.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from collections import Counter

from tools.validation import backlog_discovery as bd
from tools.validation import dependency_graph as dg
from tools.validation import execution_state as es


def render(issues: list[dict], prs: list[dict], statuses: dict[int, str] | None, state: dict, policy: dict, runner: bool,
           token: bool, today: str, readiness: dict[int, dict] | None = None) -> str:
    g = dg.build(issues, statuses)
    ver = bd.evaluate(g, prs, {}, readiness)
    elig = [v for v in ver if v.eligible]
    open_n = [v.node for v in ver]
    causes = Counter(n.cause or "sem-causa" for n in open_n if n.blocked)
    review = sorted(n.number for n in open_n if n.status == "GPT Review")
    claims = es.active_claims(state)
    L = [f"# AUTONOMOUS ENGINEERING STATUS — {today}", ""]
    L += ["## Execução", f"- tarefa ativa: {state.get('current_issue') or 'nenhuma'} (branch {state.get('current_branch') or '-'})",
          f"- claims ativos: {', '.join('#%d(%s)' % (n, c['state']) for n, c in sorted(claims.items())) or 'nenhum'}",
          f"- PRs abertos: {', '.join('#%d' % p['number'] for p in sorted(prs, key=lambda p: p['number'])) or 'nenhum'}", ""]
    counts = bd.summarize(ver)
    L += ["## Backlog", f"- Issues abertas: {len(open_n)} · " + " · ".join(f"{k}: {len(v)}" for k, v in counts.items()),
          "- bloqueios por causa: " + (", ".join(f"{k}={v}" for k, v in sorted(causes.items())) or "nenhum"),
          "- aguardando revisão independente (GPT Review): " + (", ".join("#%d" % n for n in review) or "nenhuma"), ""]
    L += ["## Próximas elegíveis (ordem do scheduler)"] + [f"{i}. #{v.node.number} {v.node.title[:90]}" + (f" — próximo passo ({'offline' if v.offline else 'SketchUp'}): {v.next_step[:140]}" if v.next_step else "") for i, v in enumerate(elig[:5], 1)] + [""]
    reviewers = policy.get("reviewers", [])
    L += ["## Limites da automação (declarados)",
          f"- runner autônomo 24/7: {'configurado' if runner else 'NÃO configurado — a execução só ocorre durante uma sessão ativa'}",
          f"- token do Project em Actions (BACKLOG_PROJECT_TOKEN): {'presente' if token else 'AUSENTE — sincronização do board é PARCIAL (#508)'}",
          f"- revisor independente verificável: {', '.join(reviewers) if reviewers else 'NENHUM configurado — Issues P0/gpt-review-required não chegam a Done (#524)'}",
          "- veredito visual: sempre do proprietário (PENDING_HUMAN); este relatório não o declara.", ""]
    return "\n".join(L)


def main(argv: list[str]) -> int:
    from tools.validation.backlog_gate import ROOT
    issues, statuses, prs = bd.load(statuses=True)
    pol = ROOT / "docs/governance/review_policy.json"
    policy = json.loads(pol.read_text(encoding="utf-8")) if pol.exists() else {}
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    text = render(issues, prs, statuses, es.load(es.state_path()), policy, runner=bool(os.environ.get("AUTONOMOUS_RUNNER")),
                  token=bool(os.environ.get("BACKLOG_PROJECT_TOKEN")), today=today, readiness=bd.load_readiness())
    if "--write" in argv:
        out = ROOT / argv[argv.index("--write") + 1]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
