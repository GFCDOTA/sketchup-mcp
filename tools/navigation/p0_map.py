"""Gate do mapa de reorganização (FP-043 P0): origem → destino → consumidores → risco.

O mapa (`docs/specs/fp043_p0_map.v1.json`) é a fonte da verdade do que se move, quando e com
que compatibilidade. Este gate o mantém EXATO, no estilo do `inventory_gate` da FP-042 (fail-closed):

- todo item do escopo (raiz, tools/, scripts/, ops/, interior/) tem entrada — nada fica sem
  destino ou sem retenção justificada;
- nenhuma entrada sobra para item que não existe mais, salvo movimentos já executados
  (`status: done`), que exigem o destino rastreado (e a origem ausente, a menos que o caminho
  antigo seja fachada);
- disposição, fase, risco, justificativa e destino seguem o vocabulário do próprio mapa;
- `decision` sempre carrega a pergunta aberta; `facade` aponta para um canônico que existe.

Não prova que o destino é o melhor, nem que a migração é segura: isso é o trabalho de cada PR de
movimento (consumidores revisados, imports frios, CLI, suites de escala).

Uso: python -m tools.navigation.p0_map [--check] [--summary]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from tools.navigation.consumers import REPO, scope_items, tracked_files

MAP_PATH = REPO / "docs/specs/fp043_p0_map.v1.json"
SCHEMA = "fp043_p0_map.v1"
DISPOSITIONS = ("retain", "facade", "move", "decision")
PHASES = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8")
RISKS = ("high", "medium", "low")
STATUSES = ("planned", "done")
# compat que mantém o caminho antigo vivo depois do movimento
KEEPS_OLD_PATH = frozenset({"facade_at_old_path", "facade_permanent_in_window"})


def load(path: Path = MAP_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(doc: dict, tracked: list[str]) -> dict:
    if doc.get("schema_version") != SCHEMA or not isinstance(doc.get("items"), list):
        return {"result": "FAIL", "errors": ["INVALID_SCHEMA"]}
    tracked_set = set(tracked)
    rows = [r for r in doc["items"] if isinstance(r, dict)]
    names = [r.get("item") for r in rows]
    errors: dict[str, list[str]] = {}

    def flag(code: str, what: str) -> None:
        errors.setdefault(code, []).append(what)

    for n, c in Counter(names).items():
        if c > 1:
            flag("DUPLICATE_ITEM", str(n))
    expected = set(scope_items(tracked))
    present = set()
    for r in rows:
        item = r.get("item")
        if not isinstance(item, str) or not item:
            flag("INVALID_RECORD", str(item))
            continue
        status = r.get("status", "planned")
        if status not in STATUSES:
            flag("INVALID_STATUS", item)
        if r.get("disposition") not in DISPOSITIONS:
            flag("INVALID_DISPOSITION", item)
        if r.get("phase") not in PHASES:
            flag("INVALID_PHASE", item)
        if r.get("risk") not in RISKS:
            flag("INVALID_RISK", item)
        if not (isinstance(r.get("rationale"), str) and len(r["rationale"].strip()) >= 20):
            flag("MISSING_RATIONALE", item)
        disp, dest = r.get("disposition"), r.get("destination")
        if disp in ("facade", "move") and not (isinstance(dest, str) and dest):
            flag("MISSING_DESTINATION", item)
        if disp == "decision" and not (isinstance(r.get("open_question"), str) and r["open_question"].strip()):
            flag("DECISION_WITHOUT_QUESTION", item)
        if disp == "facade" and isinstance(dest, str) and dest not in tracked_set:
            flag("FACADE_CANONICAL_MISSING", f"{item} -> {dest}")
        if disp == "move" and r.get("compat") is None:
            flag("MOVE_WITHOUT_COMPAT", item)
        done = status == "done"
        keeps = r.get("compat") in KEEPS_OLD_PATH
        if done and disp == "move":
            literal = isinstance(dest, str) and not dest.endswith("/") and "<" not in dest and "(" not in dest
            if literal and dest not in tracked_set:
                flag("DONE_DESTINATION_MISSING", f"{item} -> {dest}")
            if not keeps:
                if item in tracked_set or any(t.startswith(item) for t in tracked_set if item.endswith("/")):
                    flag("DONE_ORIGIN_STILL_PRESENT", item)
                continue  # origem legitimamente ausente: não entra no escopo atual
        present.add(item)
    missing = sorted(expected - present)
    stale = sorted(present - expected)
    if missing:
        errors["MISSING_ITEMS"] = missing
    if stale:
        errors["STALE_ITEMS"] = stale
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "items": len(rows), "scope": len(expected),
            "proof": "MAPA_COBRE_O_ESCOPO_NAO_PROVA_MIGRACAO_SEGURA"}


def summary(doc: dict) -> dict:
    rows = doc["items"]
    return {
        "baseline_commit": doc.get("baseline_commit"),
        "items": len(rows),
        "by_disposition": dict(Counter(r["disposition"] for r in rows)),
        "by_risk": dict(Counter(r["risk"] for r in rows)),
        "by_phase": dict(sorted(Counter(r["phase"] for r in rows).items())),
        "by_status": dict(Counter(r.get("status", "planned") for r in rows)),
        "open_questions": [{"item": r["item"], "question": r["open_question"]} for r in rows if r.get("open_question")],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate do mapa de reorganização FP-043/P0")
    ap.add_argument("--check", action="store_true", help="falha (exit 1) se o mapa não cobre o escopo")
    ap.add_argument("--summary", action="store_true")
    ns = ap.parse_args(argv)
    doc = load()
    if ns.summary:
        print(json.dumps(summary(doc), indent=1, ensure_ascii=False))
    res = check(doc, tracked_files())
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 1 if ns.check and res["result"] != "PASS" else 0


if __name__ == "__main__":
    sys.exit(main())
