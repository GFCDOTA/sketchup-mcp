"""FP-042: P3 exact-path owner map rejects unknown and inconsistent files."""
import json
from tools.rooms.p3_ownership import OWNER_TABLE, INVENTORY, audit_p3


def test_all_p3_paths_have_explicit_runtime_owners():
    index = json.loads(INVENTORY.read_text("utf-8"))
    report = audit_p3(index)
    assert report["result"] == "PASS", report
    # A contagem cai com cada fachada removida na FP-044 (F2: scripts/sofa_fabric_material.py; F6: lotes de comodo; D-012: a ultima fachada do sofa; FP-045/F2: a fachada do RAG embed):
    # arquivo e linha da tabela saem juntos.
    assert report["checked"] == len(OWNER_TABLE) == 94   # +bedroom/layout_decisions.py (#381), +bathroom/solver_policy.py (FP-054 F2A)


def test_missing_or_unknown_p3_path_fails_closed():
    index = json.loads(INVENTORY.read_text("utf-8"))
    rows = [dict(e) for e in index["entries"] if e["phase"] == "P3"]
    assert audit_p3({"entries": rows[:-1]})["result"] == "FAIL"
    rows.append({"path": "tools/unknown_room.py", "phase": "P3"})
    assert audit_p3({"entries": rows})["result"] == "FAIL"


def test_runtime_and_legacy_paths_have_different_roles():
    # (a fachada de sofa_class saiu na FP-044/F6; test_all_p3_paths_* exige OWNER_TABLE == inventario)
    assert OWNER_TABLE["tools/rooms/living/sofa_class.py"] == "tools.rooms.living"
    assert OWNER_TABLE["interior/planners/living_room_planner.py"] == "living_planner_legacy_facade"
    assert OWNER_TABLE["tools/knowledge/rag_embed_backend.py"] == "cross_room_rag_infrastructure"
