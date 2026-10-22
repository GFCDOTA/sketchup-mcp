"""Fragmentos de especialista: ponteiros validados, um dono por capacidade/binding, nada de execucao."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.rooms import specialist_fragments as sf

ROOT = Path(__file__).resolve().parents[1]


def _real():
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sf.fragment_paths(ROOT)]


def test_real_fragments_pass_and_cover_every_room_capability_and_binding():
    res = sf.verify(ROOT)
    assert res["result"] == "PASS", res["errors"]
    assert set(res["rooms"]) == {"kitchen", "living", "bedroom", "bathroom", "service", "closet", "home_office", "balcony",
                                 "circulation"}


def test_fragments_never_authorize_execution_nor_copy_profile_fields():
    for _, frag in _real():
        assert "execution_authorized" not in frag and "tool_allowlist" not in frag     # quem decide execucao e o plan()
        assert frag["stop_conditions"]


def test_owner_lookup_finds_the_fragment_that_answers_a_capability_or_gap():
    assert [(f["room"], f["id"]) for f in sf.owner_of("kitchen.cabinet.shaker-door", ROOT)] == [("kitchen", "cabinetry")]
    assert [(f["room"], f["id"]) for f in sf.owner_of("bind.kitchen.countertop", ROOT)] == [("kitchen", "countertop_and_sink")]


def _mutate(fn):
    frags = copy.deepcopy(_real())
    fn(frags)
    return sf.verify(ROOT, frags)["errors"]


def _frag(frags, room, fid):
    return next(f for p, f in frags if f["room"] == room and f["id"] == fid)


@pytest.mark.parametrize("mutation, code", [
    (lambda fs: _frag(fs, "kitchen", "ergonomics")["capability_ids"].append("living.sofa.class"), "CAPABILITY_NOT_IN_PROFILE"),
    (lambda fs: _frag(fs, "kitchen", "ergonomics")["capability_ids"].append("kitchen.layout.galley"), "CAPABILITY_OWNERSHIP"),
    (lambda fs: _frag(fs, "kitchen", "cabinetry")["capability_ids"].remove("kitchen.cabinet.shaker-door"), "CAPABILITY_OWNERSHIP"),
    (lambda fs: _frag(fs, "kitchen", "cabinetry")["binding_ids"].append("bind.living.sofa"), "BINDING_OF_OTHER_ROOM"),
    (lambda fs: _frag(fs, "kitchen", "cabinetry")["binding_ids"].append("bind.nao.existe"), "BINDING_NOT_FOUND"),
    (lambda fs: _frag(fs, "kitchen", "countertop_and_sink")["binding_ids"].append("bind.kitchen.layout"), "BINDING_CAPABILITY_ELSEWHERE"),
    (lambda fs: _frag(fs, "kitchen", "countertop_and_sink")["binding_ids"].remove("bind.kitchen.countertop"), "BINDING_OWNERSHIP"),
    (lambda fs: _frag(fs, "living", "sofa")["recipe_ids"].append("cabinet.countertop-separate-and-bevel"), "RECIPE_NOT_IN_PROFILE"),
    (lambda fs: _frag(fs, "kitchen", "reference_truth")["demos"].append("artifacts/nao/existe.json"), "PATH_MISSING"),
    (lambda fs: _frag(fs, "kitchen", "reference_truth")["skills"].append("skill-que-nao-existe"), "SKILL_MISSING"),
    (lambda fs: _frag(fs, "kitchen", "reference_truth").pop("focus"), "SCHEMA"),
    (lambda fs: _frag(fs, "kitchen", "reference_truth").update(execution_authorized=True), "SCHEMA"),
])
def test_each_rule_has_a_failing_case(mutation, code):
    assert code in _mutate(mutation)


def test_id_must_match_the_file_and_folder():
    frags = _real()
    path, frag = frags[0]
    moved = [(path.with_name("outro.fragment.v1.json"), frag)] + frags[1:]
    assert "FRAGMENT_PATH_MISMATCH" in sf.verify(ROOT, moved)["errors"]
