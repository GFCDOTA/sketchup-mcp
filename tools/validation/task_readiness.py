"""task_readiness.py — o que cada tarefa PODE fazer agora, auditado e verificavel (FP-057, correcao do scheduler).

O scheduler sabe de dependencias, labels e PRs, mas nao sabe se o PROXIMO PASSO tecnico de uma Issue "elegivel" e executavel agora,
nem o que impede o FIM dela. `docs/governance/task_readiness.json` guarda essa auditoria por Issue:

  state READY    ha um proximo passo concreto executavel agora (`next_step`), com `offline` (sem SketchUp) e `needs_sketchup`
                 declarados; `completion_blockers` lista o que impede CONCLUIR (nao comecar): [{cause, ref, detail}].
  state BLOCKED  nenhum passo executavel agora: `cause` + `ref` + `detail`.
Causas (taxonomia unica): HUMAN_DECISION · ENVIRONMENT · EVIDENCE · DEPENDENCY · EXTERNAL · REVIEW.
Cada `ref` aponta para uma Issue (`#N`, que precisa existir) ou para um arquivo do repo (que precisa existir): impedimento sem
rastro nao vale. Entrada de Issue fechada e `READINESS_STALE`. Nao enfraquece nenhum gate: so acrescenta razoes ao scheduler.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "docs/governance/task_readiness.json"
CAUSES = ("HUMAN_DECISION", "ENVIRONMENT", "EVIDENCE", "DEPENDENCY", "EXTERNAL", "REVIEW")
_REF = re.compile(r"^#(\d+)$")


def load(path: Path = PATH) -> dict[int, dict]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data.get("tasks", {}).items()}


def _check_ref(ref: str, issues: dict[int, dict], root: Path) -> str | None:
    m = _REF.match(ref or "")
    if m:
        return None if int(m.group(1)) in issues else f"Issue {ref} inexistente"
    target = (ref or "").split("#", 1)[0]
    return None if target and (root / target).exists() else f"arquivo {ref!r} inexistente"


def validate(tasks: dict[int, dict], issues: dict[int, dict], root: Path = ROOT) -> list[tuple[str, int, str]]:
    """[(codigo, issue, detalhe)]. `issues`: {numero: {"state": ...}}."""
    out: list[tuple[str, int, str]] = []
    for n, e in sorted(tasks.items()):
        iss = issues.get(n)
        if iss is None:
            out.append(("READINESS_UNKNOWN_ISSUE", n, "entrada para Issue inexistente"))
            continue
        if iss.get("state") != "OPEN":
            out.append(("READINESS_STALE", n, "entrada para Issue fechada: remover"))
            continue
        state = e.get("state")
        blockers = e.get("completion_blockers", [])
        if state == "READY":
            if not e.get("next_step"):
                out.append(("READINESS_READY_WITHOUT_NEXT_STEP", n, "READY exige next_step concreto"))
            if not isinstance(e.get("offline"), bool) or not isinstance(e.get("needs_sketchup"), bool):
                out.append(("READINESS_READY_FLAGS", n, "READY exige offline e needs_sketchup booleanos"))
            elif e["needs_sketchup"] and e["offline"]:
                out.append(("READINESS_READY_FLAGS", n, "offline e needs_sketchup nao podem ser ambos verdadeiros"))
        elif state == "BLOCKED":
            blockers = [{"cause": e.get("cause"), "ref": e.get("ref"), "detail": e.get("detail")}]
        else:
            out.append(("READINESS_BAD_STATE", n, f"state invalido: {state!r}"))
            continue
        for b in blockers:
            if b.get("cause") not in CAUSES:
                out.append(("READINESS_BAD_CAUSE", n, f"causa fora da taxonomia: {b.get('cause')!r}"))
            if not b.get("detail"):
                out.append(("READINESS_NO_DETAIL", n, "impedimento sem detalhe"))
            err = _check_ref(b.get("ref"), issues, root)
            if err:
                out.append(("READINESS_BAD_REF", n, err))
        if not e.get("audited_at"):
            out.append(("READINESS_NO_DATE", n, "entrada sem audited_at"))
    return out
