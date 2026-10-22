"""FP-051/P0: baseline factual (somente leitura). Prova a LOGICA de classificacao com catalogos sinteticos e as invariantes do catalogo real.

Nao trava os numeros de hoje (o catalogo vai evoluir): o JSON versionado e um retrato datado; aqui se prova que o gerador e deterministico,
nao inventa estado, nao autoriza execucao e nao confunde prova velha, rotulo de fonte ou peca com movel pronto.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.navigation import fp051_baseline as bl

ROOT = Path(__file__).resolve().parents[1]


def cap(cid, *, validation="L2_PASS", visual="NOT_REVIEWED", digest="d1", room="kitchen", impl="IMPLEMENTED"):
    evidence = [{"ref": "x.md", "sketchup_version": "26", "commit": "abc1234", "symbol_digests": {f"python:m.{cid}": digest}}] if validation == "L2_PASS" else []
    return {"id": cid, "room": room, "implementation": {"state": impl, "symbols": [{"lang": "python", "ref": f"m.{cid}"}]},
            "validation": {"state": validation, "fixtures": [], "tests": ["t"], "evidence": evidence}, "visual": {"state": visual}}


def catalog(*caps, bindings=()):
    return {"capabilities": list(caps), "bindings": list(bindings)}


def binding(bid, capability_id=None, gap="falta", sources=("s-ok",)):
    return {"id": bid, "room": "kitchen", "capability_id": capability_id, "gap": gap if capability_id is None else None,
            "recipe_ids": ["r"], "source_ids": list(sources)}


SOURCES = {"s-ok": {"id": "s-ok", "evidence": "TRANSCRIPT_AND_VISUAL_WALKTHROUGH", "human_review": {"reviewer": "Felipe", "recipe_id": "r", "segment": "00:00-00:10"}},
           "s-raw": {"id": "s-raw", "evidence": "TRANSCRIPT_AND_VISUAL_WALKTHROUGH"}}
GOOD = lambda s: "d1"  # noqa: E731
STALE = lambda s: "OUTRO"  # noqa: E731


def base_catalog():
    return catalog(cap("shared.cabinet.parametric"), cap("kitchen.cabinet.shaker-door"), cap("kitchen.cabinet.plain-fronts"),
                   bindings=[binding("bind.kitchen.drawer", gap="sem caixa de gaveta", sources=("s-raw",))])


def test_ready_only_when_every_required_component_has_current_l2():
    m = bl.build_matrix(base_catalog(), SOURCES, GOOD)
    shelf = m["kitchen_base_shaker_shelf"]
    assert shelf["cycle_status"] == "READY_FOR_NEXT_STEP" and shelf["missing_capabilities"] == []
    assert shelf["execution_authorized"] is False and shelf["placement"].startswith("NOT_CHOSEN")      # READY nao autoriza nem escolhe posicao


def test_stale_proof_is_not_l2_and_blocks_ready():
    m = bl.build_matrix(base_catalog(), SOURCES, STALE)
    shelf = m["kitchen_base_shaker_shelf"]
    assert shelf["cycle_status"] == "PENDING_SKETCHUP"
    assert all(c["status"] == "RESOLVED_L1_ONLY" and c["reason"] == "prova L2 velha" for c in shelf["required"].values())
    state = bl.capability_state(base_catalog()["capabilities"][0], STALE)
    assert state["evidence_current"] is False and state["stale_symbols"]


def test_binding_without_capability_is_a_gap_with_the_review_state_of_its_sources():
    m = bl.build_matrix(base_catalog(), SOURCES, GOOD)
    drawer = m["kitchen_base_drawer"]
    assert drawer["cycle_status"] == "BLOCKED_CAPABILITY_MISSING" and drawer["missing_capabilities"] == ["drawer_box"]
    src = drawer["required"]["drawer_box"]["sources"]
    assert src == [{"source_id": "s-raw", "evidence": "TRANSCRIPT_AND_VISUAL_WALKTHROUGH", "human_review": False}]   # rotulo != revisao humana
    assert drawer["optional_not_available"] == ["slides_hardware"]


def test_human_review_is_scoped_to_the_recipe_that_recorded_it():
    ok = bl.source_review(["s-ok"], SOURCES, ["r"])
    assert ok == [{"source_id": "s-ok", "evidence": "TRANSCRIPT_AND_VISUAL_WALKTHROUGH", "human_review": True}]
    other = bl.source_review(["s-ok"], SOURCES, ["outra-recipe"])                 # mesma fonte, OUTRA recipe: nao herda a revisao
    assert other[0]["human_review"] is False
    assert other[0]["human_review_other_scope"] == {"recipe_id": "r", "segment": "00:00-00:10"}
    cat = catalog(cap("shared.cabinet.parametric"), bindings=[binding("bind.kitchen.drawer", gap="x", sources=("s-ok",))])
    cat["bindings"][0]["recipe_ids"] = ["outra-recipe"]
    drawer = bl.build_matrix(cat, SOURCES, GOOD)["kitchen_base_drawer"]["required"]["drawer_box"]["sources"]
    assert drawer[0]["human_review"] is False and "human_review_other_scope" in drawer[0]


def test_alternative_satisfies_a_component_only_with_current_l2():
    cat = catalog(cap("shared.cabinet.parametric"), cap("kitchen.cabinet.plain-fronts"), cap("kitchen.cabinet.shaker-door", validation="L1_PASS"))
    shelf = bl.build_matrix(cat, SOURCES, GOOD)["kitchen_base_shaker_shelf"]
    assert shelf["required"]["front"]["status"] == "RESOLVED_L2" and shelf["required"]["front"]["via_alternative"] is True
    broken = catalog(cap("shared.cabinet.parametric"), cap("kitchen.cabinet.plain-fronts", validation="L1_PASS"),
                     cap("kitchen.cabinet.shaker-door", validation="L1_PASS"))
    assert bl.build_matrix(broken, SOURCES, GOOD)["kitchen_base_shaker_shelf"]["cycle_status"] == "PENDING_SKETCHUP"


def test_missing_planned_or_unknown_capability_blocks():
    cat = catalog(cap("shared.cabinet.parametric"), cap("kitchen.cabinet.shaker-door", impl="PLANNED", validation="UNTESTED"))
    shelf = bl.build_matrix(cat, SOURCES, GOOD)["kitchen_base_shaker_shelf"]
    assert shelf["cycle_status"] == "BLOCKED_CAPABILITY_MISSING" and shelf["missing_capabilities"] == ["front"]
    untested = catalog(cap("shared.cabinet.parametric"), cap("kitchen.cabinet.shaker-door", validation="UNTESTED"))
    assert bl.build_matrix(untested, SOURCES, GOOD)["kitchen_base_shaker_shelf"]["cycle_status"] == "BLOCKED_L1_UNPROVEN"


def test_metrics_do_not_inflate_progress():
    cat = base_catalog()
    cat["capabilities"].append(cap("bedroom.wardrobe.build", validation="L1_PASS", room="bedroom"))
    profiles = {"kitchen": {"capability_ids": ["shared.cabinet.parametric", "kitchen.cabinet.plain-fronts"]},
                "bedroom": {"capability_ids": ["shared.cabinet.parametric", "bedroom.wardrobe.build"]}}
    m = bl.metrics(cat, profiles, GOOD)
    assert m["capabilities_L2_com_prova_vigente"]["count"] == 3
    assert m["reused_capabilities_cross_room"]["ids"] == ["shared.cabinet.parametric"]            # so conta com L2 vigente + 2 perfis
    assert m["furniture_placed_in_correct_room_L2"]["count"] == 0 and m["rooms_approved_L3"]["count"] == 0
    assert m["blocked_gaps"]["ids"] == ["bind.kitchen.drawer"]
    stale = bl.metrics(cat, profiles, STALE)
    assert stale["capabilities_L2_com_prova_vigente"]["count"] == 0 and stale["reused_capabilities_cross_room"]["count"] == 0
    approved = copy.deepcopy(cat)
    approved["capabilities"][1]["visual"]["state"] = "APPROVED"
    assert bl.metrics(approved, profiles, GOOD)["rooms_approved_L3"]["rooms"] == ["kitchen"]


def test_real_baseline_is_deterministic_and_claims_have_unique_ids():
    a, b = bl.build({"snapshot_date": "x"}), bl.build({"snapshot_date": "x"})
    assert a == b and a["external"] == {"snapshot_date": "x"} and a["schema_version"] == bl.SCHEMA
    ids = [c["id"] for c in a["spec_claims"]]
    assert len(ids) == len(set(ids)) and all(isinstance(c["ok"], bool) for c in a["spec_claims"])
    assert json.dumps(a, sort_keys=True)                                                         # serializavel, sem objetos soltos


def test_real_catalog_never_claims_l2_with_stale_proof_and_no_candidate_is_authorized():
    base = bl.build()
    assert [c["id"] for c in base["capabilities"] if c["validation"] == "L2_PASS" and not c["evidence_current"]] == []
    assert all(f["execution_authorized"] is False and f["placement"].startswith("NOT_CHOSEN") for f in base["furniture_matrix"].values())
    for f in base["furniture_matrix"].values():
        if f["cycle_status"] == "READY_FOR_NEXT_STEP":
            assert all(c["status"] == "RESOLVED_L2" for c in f["required"].values())


def test_committed_snapshot_is_valid_and_has_the_external_block():
    snap = json.loads((ROOT / "docs/reports/fp051/fp051_baseline.json").read_text(encoding="utf-8"))
    assert snap["schema_version"] == bl.SCHEMA and "furniture_matrix" in snap and "metrics" in snap
    ext = snap["external"]
    assert ext["snapshot_date"] == "2026-10-21" and {"346", "347", "355"} <= set(ext["prs"])
    assert all(ext["prs"][n]["isDraft"] is True for n in ("346", "347", "355"))                 # o que a validacao observou


def test_generator_reads_files_only(monkeypatch):
    """P0 nao toca SketchUp, rede nem escreve fora do --out."""
    import subprocess
    calls = []
    real = subprocess.check_output
    monkeypatch.setattr(subprocess, "check_output", lambda cmd, *a, **k: (calls.append(cmd), real(cmd, *a, **k))[1])
    bl.build()
    assert all(c[0] == "git" and c[1] == "rev-parse" for c in calls), calls                      # unico subprocesso: o HEAD do git


@pytest.mark.parametrize("fid", sorted(bl.FURNITURE_CANDIDATES))
def test_candidates_carry_no_dimension_position_or_wall(fid):
    spec = json.dumps(bl.FURNITURE_CANDIDATES[fid], ensure_ascii=False).lower()
    for forbidden in ("mm", "wall_id", "anchor_id", "pose", "width", "depth", "height"):
        assert forbidden not in spec, forbidden


def test_flow_checks_that_the_human_review_covers_the_requested_recipe():
    """Trava da correcao do follow-up do #357: o achado `flow:source_verified-checks-review-scope` precisa continuar resolvido."""
    claims = {c["id"]: c for c in bl.build()["spec_claims"]}
    assert claims["flow:source_verified-checks-review-scope"]["ok"] is True
