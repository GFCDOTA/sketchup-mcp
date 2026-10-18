"""semantic_geometry_contract_gate.py — verifica que toda peça relevante do
spatial model tem geometry_intent DECLARADO (central, por kind/module — ver
core/spatial_semantics.py), não adivinhado por forma/tamanho/bbox a cada gate.

Origem: consulta GPT-Docker 2026-08-12 (arquitetura pós-mortem da sessão de
circulação). Este gate NÃO julga se a geometria está certa — geometry_sanity.py
e furniture_overlap_gate.py fazem isso. Ele julga só se o CONTRATO existe.

Três estados (não apenas PASS/FAIL — migração é gradual, não big-bang):

  PASS
      Peça tem geometry_intent via kind_exact/kind_prefix/module (registro
      central explícito em core/spatial_semantics.KIND_REGISTRY/
      MODULE_REGISTRY) OU builder setou geometry_intent diretamente no box.

  WARN_LEGACY_SEMANTICS
      Peça caiu no fallback (nenhum registro bate) MAS é geometria simples —
      retângulo, sem rotação. Baixo risco: o pior caso é herdar o default
      FURNITURE/BLOCK/EXCLUSIVE, que é o comportamento conservador de sempre.
      Não bloqueia — é a fila de migração visível (grep 'default_fallback').

  FAIL_MISSING_SEMANTICS
      Peça caiu no fallback E é geometria complexa (não-retangular OU
      rotacionada) — exatamente a classe de bug real desta sessão (vaso
      arredondado, almofada girada, discos octogonais). Geometria complexa
      SEM contrato declarado é perigosa por definição: o gate não tem como
      saber se a forma é intencional ou um bug, então força declaração.

Uso: python -m tools.semantic_geometry_contract_gate [room_id|all]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.spatial_semantics import resolve_geometry_intent               # noqa: E402
from tools.geometry_sanity import _is_rectangle                          # noqa: E402


def _is_complex_shape(box: dict) -> bool:
    """Retângulo axis-aligned = simples. Rotacionado ou não-retangular = complexo."""
    cs = box.get("corners")
    if not cs:
        return False
    if not _is_rectangle(cs):
        return True
    xs = {round(c[0], 1) for c in cs}
    ys = {round(c[1], 1) for c in cs}
    return not (len(xs) <= 2 and len(ys) <= 2)   # retangulo mas girado


def audit(boxes: list[dict]) -> dict:
    """boxes: lista de peças (mesmo shape do geometry_sanity.audit). Devolve
    {overall, n_pass, n_warn, n_fail, findings}. NUNCA muta os boxes (só lê —
    diferente de core.spatial_semantics.annotate, que preenche)."""
    findings = []
    n_pass = n_warn = n_fail = 0
    for b in boxes:
        if b.get("geometry_intent") and b.get("_semantics_provenance") in (
                None, "explicit", "kind_exact", "kind_prefix", "module"):
            n_pass += 1
            continue
        intent, provenance = resolve_geometry_intent(b.get("kind"), b.get("module"))
        if provenance != "default_fallback":
            n_pass += 1
            continue
        complex_shape = _is_complex_shape(b)
        entry = {"label": b.get("label"), "kind": b.get("kind"), "module": b.get("module"),
                 "resolved_intent": intent, "complex_shape": complex_shape}
        if complex_shape:
            entry["status"] = "FAIL_MISSING_SEMANTICS"
            n_fail += 1
        else:
            entry["status"] = "WARN_LEGACY_SEMANTICS"
            n_warn += 1
        findings.append(entry)
    overall = "FAIL" if n_fail else ("WARN" if n_warn else "PASS")
    return {"overall": overall, "n_parts": len(boxes), "n_pass": n_pass,
            "n_warn": n_warn, "n_fail": n_fail, "findings": findings}


def gate_room(con, room_id: str) -> dict:
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"overall": "FAIL", "room": room_id, "findings": [{"detail": "cômodo inexistente"}]}
    brain = BRAINS.get(r["room_type"])
    boxes, _ = brain(con, room_id) if brain else ([], {})
    res = audit(boxes or [])
    res["room"] = room_id
    res["room_name"] = r["name"]
    return res


def main():
    from tools.furnish_apartment import CONSENSUS
    from tools.room_type import classify_rooms
    con = json.loads(CONSENSUS.read_text("utf-8"))
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    rooms = [arg] if arg != "all" else [r["id"] for r in classify_rooms(con)]
    worst = "PASS"
    for rid in rooms:
        res = gate_room(con, rid)
        tag = {"PASS": "ok", "WARN": "warn", "FAIL": "FAIL"}[res["overall"]]
        print(f"[{tag:4}] {res.get('room_name', rid)} — pass={res.get('n_pass',0)} "
              f"warn={res.get('n_warn',0)} fail={res.get('n_fail',0)}")
        for f in res.get("findings", []):
            print(f"        {f.get('status', f)} {f.get('kind')}/{f.get('module')}")
        if res["overall"] == "FAIL":
            worst = "FAIL"
        elif res["overall"] == "WARN" and worst != "FAIL":
            worst = "WARN"
    print(f"\nsemantic_geometry_contract_gate => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
