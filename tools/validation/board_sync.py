"""board_sync.py — PR <-> Issue <-> Project (Quality Guardian, P2).

    python -m tools.validation.board_sync --pr <N> [--dry-run]

Regra de estado para as Issues citadas por `Refs #N` no corpo do PR:
- PR em rascunho, ou com algum check obrigatorio ainda pendente/reprovado  -> `In Progress`  (implementacao ou testes nao prontos);
- PR pronto (nao rascunho) e TODOS os checks verdes                          -> `GPT Review` (aguarda revisao independente);
- PR mergeado                                                                -> continua `GPT Review`: Done so com os criterios de
                                                                               aceite e a evidencia (comentario `**Evidência`) conferidos pelo `backlog_gate`.
Issue em `Blocked`, ou de decisao humana, nao e movida por PR. Reprovacao de gate: o motivo vai num comentario do PR
(`--comment-failure`), o merge segue bloqueado pelo check obrigatorio.

Precisa de token com escopo `project` (secret BACKLOG_PROJECT_TOKEN no Actions; `gh auth` local). Sem ele, so imprime o plano.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from tools.validation.backlog_gate import OWNER, PROJECT, REPO, _gh

PROJECT_ID = "PVT_kwDOCgzHsM4BoiZO"
_REFS = re.compile(r"\brefs?\s*:?\s*#(\d+)", re.IGNORECASE)


def target_status(pr: dict) -> str:
    """Estado alvo das Issues do PR (funcao pura, testada)."""
    if pr.get("isDraft"):
        return "In Progress"
    checks = pr.get("statusCheckRollup") or []
    if not checks or any(c.get("status") != "COMPLETED" or c.get("conclusion") not in ("SUCCESS", "SKIPPED", "NEUTRAL") for c in checks):
        return "In Progress"
    return "GPT Review"


def plan(pr: dict, items: dict[int, dict]) -> list[tuple[int, str, str]]:
    """[(issue, status_atual, status_alvo)] so onde muda e a Issue pode ser movida por PR."""
    out = []
    target = target_status(pr)
    for n in sorted({int(x) for x in _REFS.findall(pr.get("body") or "")}):
        it = items.get(n)
        if it is None:
            continue
        cur = it.get("status")
        if cur in ("Blocked", "Done") or cur == target:
            continue
        if cur == "GPT Review" and target == "In Progress" and pr.get("state") == "MERGED":
            continue
        out.append((n, cur, target))
    return out


def _project_items() -> dict[int, dict]:
    rows = json.loads(_gh("project", "item-list", PROJECT, "--owner", OWNER, "--limit", "1000", "--format", "json"))["items"]
    return {r["content"]["number"]: r for r in rows if r.get("content", {}).get("number")}


def _apply(n: int, status: str) -> None:
    fields = {f["name"]: f for f in json.loads(_gh("project", "field-list", PROJECT, "--owner", OWNER, "--format", "json"))["fields"]}
    opt = next(o["id"] for o in fields["Status"]["options"] if o["name"] == status)
    item = _project_items()[n]
    _gh("project", "item-edit", "--id", item["id"], "--project-id", PROJECT_ID, "--field-id", fields["Status"]["id"],
        "--single-select-option-id", opt)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    pr = json.loads(_gh("pr", "view", str(a.pr), "--repo", REPO, "--json", "body,isDraft,state,statusCheckRollup"))
    moves = plan(pr, _project_items())
    for n, cur, tgt in moves:
        print(f"#{n}: {cur} -> {tgt}")
        if not a.dry_run:
            _apply(n, tgt)
    print(f"board_sync: {len(moves)} movimento(s) para o PR #{a.pr}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
