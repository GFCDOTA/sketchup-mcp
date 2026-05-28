"""FP-030 — Visual Oracle Gate contract tests.

Verifica que manifest, schema e tooling existem com o shape correto.
Não roda o builder real (custa SU + tempo); para isso, rodar
`python -m tools.run_skp_visual_review --fixture planta_74 --out artifacts/review/planta_74/<run>` localmente.

Companion to test_opening_routing_invariants.py: aqueles testes
pinam invariantes de routing; estes pinam infraestrutura do Visual
Oracle Gate.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "fixtures" / "visual_oracle_examples" / "manifest.json"
SCHEMA = REPO_ROOT / "schemas" / "visual_findings.schema.json"
SKILL = REPO_ROOT / ".claude" / "skills" / "skp-visual-self-correction" / "SKILL.md"
SPEC = REPO_ROOT / "docs" / "specs" / "FP-030_visual_oracle_gate.md"
TOOL = REPO_ROOT / "tools" / "run_skp_visual_review.py"
REVIEWER_PROMPT = REPO_ROOT / "tools" / "prompts" / "visual_oracle_reviewer.md"


# ---- existence ------------------------------------------------------


def test_manifest_exists():
    assert MANIFEST.exists(), f"missing: {MANIFEST.relative_to(REPO_ROOT)}"


def test_schema_exists():
    assert SCHEMA.exists(), f"missing: {SCHEMA.relative_to(REPO_ROOT)}"


def test_skill_exists():
    assert SKILL.exists(), f"missing: {SKILL.relative_to(REPO_ROOT)}"


def test_spec_exists():
    assert SPEC.exists(), f"missing: {SPEC.relative_to(REPO_ROOT)}"


def test_tool_exists():
    assert TOOL.exists(), f"missing: {TOOL.relative_to(REPO_ROOT)}"


def test_reviewer_prompt_exists():
    assert REVIEWER_PROMPT.exists(), (
        f"missing: {REVIEWER_PROMPT.relative_to(REPO_ROOT)}"
    )


# ---- manifest shape -------------------------------------------------


def test_manifest_shape():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema_version"] == "visual_oracle_examples_manifest.v1"
    assert isinstance(data.get("examples"), list)
    assert len(data["examples"]) >= 10, "expected ≥ 10 examples"


def test_manifest_has_good_real_baseline():
    """At least one good_real example must exist as the canonical
    PASS reference, not just synthetic positives."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    good_real_ids = [
        e["id"] for e in data["examples"]
        if e.get("image", "").startswith("good_real/")
    ]
    assert good_real_ids, (
        "missing at least one good_real/* example "
        "(canonical PASS baseline from artifacts/<plant>/)"
    )


def test_manifest_examples_reference_existing_files():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = MANIFEST.parent
    missing = []
    for ex in data["examples"]:
        img = base / ex["image"]
        exp = base / ex["expected_json"]
        if not img.exists():
            missing.append(str(img.relative_to(REPO_ROOT)))
        if not exp.exists():
            missing.append(str(exp.relative_to(REPO_ROOT)))
    assert not missing, f"manifest references missing files: {missing}"


def test_ambiguous_wall_stub_examples_carry_ambiguity_note():
    """bad_wall_stubs_* contains annotations that include door jambs
    (correct geometry). The manifest must flag this so heuristics
    don't train on it as pure FAIL."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for ex in data["examples"]:
        if ex["id"] in {"bad_wall_stubs_labelled", "bad_wall_stubs_marked"}:
            assert "ambiguity_note" in ex, (
                f"{ex['id']} must carry ambiguity_note to prevent "
                f"false-positive training"
            )


# ---- confidence tiers (FP-030 example policy) -----------------------


VALID_CONFIDENCE_TIERS = {
    "good_real_baseline",
    "bad_real_confirmed",
    "bad_real_ambiguous",
    "good_synthetic_teaching",
    "bad_synthetic_teaching",
}


def test_manifest_declares_confidence_tiers_dictionary():
    """Manifest must publish the 5-tier vocabulary so consumers know
    the canonical names."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tiers = data.get("confidence_tiers")
    assert isinstance(tiers, dict)
    assert set(tiers.keys()) == VALID_CONFIDENCE_TIERS, (
        f"manifest confidence_tiers keys must be exactly the 5 "
        f"canonical names; got {set(tiers.keys())}"
    )


def test_every_example_has_confidence_tier():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for ex in data["examples"]:
        tier = ex.get("confidence_tier")
        assert tier in VALID_CONFIDENCE_TIERS, (
            f"{ex['id']} has invalid or missing confidence_tier: {tier}"
        )


def test_bad_real_ambiguous_examples_are_WARN_only():
    """bad_real_ambiguous can contribute to WARN but NEVER train hard
    FAIL. The manifest verdict reflects this."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for ex in data["examples"]:
        if ex.get("confidence_tier") == "bad_real_ambiguous":
            assert ex["expected_verdict"] in {"WARN"}, (
                f"{ex['id']} is bad_real_ambiguous but verdict is "
                f"{ex['expected_verdict']}; must be WARN per FP-030 § "
                f"confidence tiers"
            )


def test_bad_wall_stubs_have_ambiguous_or_false_positive_regions():
    """bad_wall_stubs_*.expected.json must list the false-positive
    region categories so oracle can disambiguate before flagging."""
    base = MANIFEST.parent
    for stub_id in ("bad_wall_stubs_labelled", "bad_wall_stubs_marked"):
        exp_path = base / "bad_real" / f"{stub_id}.expected.json"
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        regions = exp.get("ambiguous_or_false_positive_regions")
        assert isinstance(regions, list) and regions, (
            f"{stub_id}.expected.json must carry non-empty "
            f"ambiguous_or_false_positive_regions array"
        )


# ---- schema shape ---------------------------------------------------


def test_schema_required_fields():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["title"] == "visual_findings.v1"
    required = set(schema["required"])
    assert {"schema_version", "fixture", "attempt",
            "top_level_verdict", "axes", "findings"} <= required


def test_schema_finding_required_fields():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    finding_required = set(
        schema["properties"]["findings"]["items"]["required"]
    )
    expected = {"id", "severity", "axis", "type",
                "location", "evidence_image", "evidence"}
    assert expected <= finding_required, (
        f"finding required fields incomplete: {finding_required}"
    )


def test_schema_severity_enum():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    sev = schema["properties"]["findings"]["items"]["properties"]["severity"]
    assert set(sev["enum"]) == {"WARN", "FAIL"}, (
        "FAIL must block, WARN must not auto-pass — PASS not allowed in "
        "findings (use top_level_verdict for PASS)."
    )


# ---- tool / spec linkage --------------------------------------------


def test_spec_references_schema_and_tool():
    text = SPEC.read_text(encoding="utf-8")
    assert "schemas/visual_findings.schema.json" in text
    assert "tools/run_skp_visual_review.py" in text


def test_skill_references_spec():
    text = SKILL.read_text(encoding="utf-8")
    assert "FP-030" in text
    assert "visual_findings.json" in text


def test_tool_has_main_entrypoint():
    """Sanity: the tool is importable / runnable without SU."""
    text = TOOL.read_text(encoding="utf-8")
    assert "def main(" in text
    assert "if __name__ == \"__main__\":" in text
