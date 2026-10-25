"""FP-042/P3: exact owner map; classification, not visual SketchUp proof."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/specs/fp042_inventory.v1.json"
OWNER_TABLE = {
  "interior/__init__.py": "interior_public_package",
  "interior/class_specs/__init__.py": "shared_furniture_class_spec",
  "interior/composer/__init__.py": "cross_room_scene_composition",
  "interior/composer/scene_composer.py": "cross_room_scene_composition",
  "interior/planners/__init__.py": "planner_engine_package",
  "interior/planners/living_room_planner.py": "living_planner_legacy_facade",
  "interior/planners/placement_brain.py": "placement_engine_legacy_facade",
  "interior/renderers/__init__.py": "renderer_provider_legacy_facade",
  "interior/renderers/enscape_preview_provider.py": "renderer_provider_legacy_facade",
  "interior/renderers/render_provider.py": "renderer_provider_legacy_facade",
  "interior/renderers/sketchup_basic_provider.py": "renderer_provider_legacy_facade",
  "interior/renderers/vray_final_provider.py": "renderer_provider_legacy_facade",
  "interior/schemas/__init__.py": "shared_schema_contract",
  "interior/schemas/design_intent.schema.json": "shared_schema_contract",
  "interior/schemas/furniture_asset.schema.json": "shared_schema_contract",
  "interior/schemas/furniture_intent.schema.json": "shared_schema_contract",
  "interior/schemas/scene_intent.schema.json": "shared_schema_contract",
  "interior/semantics/__init__.py": "shared_spatial_semantics",
  "interior/semantics/room_graph.py": "spatial_semantics_legacy_facade",
  "interior/semantics/wall_affordance.py": "spatial_semantics_legacy_facade",
  "interior/specs/__init__.py": "room_design_intent_reference",
  "interior/specs/planta_74_r004_kitchen.designintent.json": "room_design_intent_reference",
  "interior/style_packs/__init__.py": "shared_style_pack",
  "interior/style_packs/black_wood_gold_boutique.json": "shared_style_pack",
  "interior/style_packs/modern_warm_minimal.json": "shared_style_pack",
  "interior/validators/__init__.py": "interior_semantic_validation",
  "interior/validators/bed_gate.py": "interior_semantic_validation",
  "tools/rooms/bedroom/validation/bed_gate.py": "interior_semantic_validation",
  "interior/validators/bed_placement_gate.py": "interior_semantic_validation",
  "tools/rooms/bedroom/validation/bed_placement_gate.py": "interior_semantic_validation",
  "interior/validators/furniture_visual_gate.py": "interior_semantic_validation",
  "tools/validation/furniture_visual_gate.py": "interior_semantic_validation",
  "interior/validators/nightstand_gate.py": "interior_semantic_validation",
  "tools/rooms/bedroom/validation/nightstand_gate.py": "interior_semantic_validation",
  "interior/validators/scene_spatial_gate.py": "interior_semantic_validation",
  "tools/validation/scene_spatial_gate.py": "interior_semantic_validation",
  "interior/validators/sofa_placement_gate.py": "interior_semantic_validation",
  "tools/rooms/living/validation/sofa_placement_gate.py": "interior_semantic_validation",
  "interior/validators/validation_report.py": "interior_semantic_validation",
  "tools/validation/validation_report.py": "interior_semantic_validation",
  "interior/validators/wardrobe_gate.py": "interior_semantic_validation",
  "tools/rooms/bedroom/validation/wardrobe_gate.py": "interior_semantic_validation",
  "tools/rooms/living/capabilities/ruby/sofa_program/build_sofa_3seat_v1.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/build_sofa_eval_suite.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/build_sofa_from_config.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/sofa_components.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/sofa_fabric_material.py": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/sofa_generator.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/sofa_primitives.rb": "sofa_legacy_evaluation_script",
  "tools/rooms/living/capabilities/ruby/sofa_program/sofa_vray_render.rb": "sofa_legacy_evaluation_script",
  "tests/test_room_module_architecture.py": "regression_test_suite",
  "tools/rooms/bedroom/capabilities/make_synthetic_bedrooms.py": "synthetic_bedroom_fixture_tool",
  "tools/rooms/bedroom/capabilities/place_bedroom_skp.py": "bedroom_sketchup_cli",
  "tools/knowledge/rag_embed_backend.py": "cross_room_rag_infrastructure",
  "tools/rooms/balcony/__init__.py": "tools.rooms.balcony",
  "tools/rooms/bedroom/__init__.py": "tools.rooms.bedroom",
  "tools/rooms/living/__init__.py": "tools.rooms.living",
  "tools/rooms/service/__init__.py": "tools.rooms.service",
  "tools/rooms/living/capabilities/sofa_class_matrix.py": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/sofa_furnish_fase1_compare.py": "living_visual_gate_and_cli",
  "tools/rooms/living/validation/sofa_gate.py": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/sofa_premium_harness.py": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/ruby/sofa_premium_harness.rb": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/ruby/sofa_premium_integrate.rb": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/sofa_venezia_compare.py": "living_visual_gate_and_cli",
  "tools/rooms/living/capabilities/sofa_venezia_room.py": "living_visual_gate_and_cli",
  "tools/rooms/living/components.py": "tools.rooms.living",
  "tests/test_fp042_living_component_ownership.py": "regression_test_suite",
  "tools/rooms/bedroom/furnishing.py": "tools.rooms.bedroom",
  "tests/test_fp042_bedroom_furnishing_adapter.py": "regression_test_suite",
  "tools/rooms/living/furnishing.py": "tools.rooms.living",
  "tests/test_fp042_living_furnishing_adapter.py": "regression_test_suite",
  "tools/rooms/service/layout.py": "tools.rooms.service",
  "tests/test_fp042_service_layout_ownership.py": "regression_test_suite",
  "tools/rooms/kitchen/layout.py": "tools.rooms.kitchen",
  "tools/rooms/bathroom/layout.py": "tools.rooms.bathroom",
  "tests/test_fp042_kitchen_bathroom_builder_ownership.py": "regression_test_suite",
  "tools/rooms/bedroom/layout.py": "tools.rooms.bedroom",
  "tools/rooms/bedroom/designer.py": "tools.rooms.bedroom",
  "tests/test_fp042_bedroom_planner_ownership.py": "regression_test_suite",
  "tools/rooms/living/planner.py": "tools.rooms.living",
  "tests/test_fp042_living_planner_ownership.py": "regression_test_suite",
  "tools/rooms/shared/armchair_builder.py": "tools.rooms.shared",
  "tools/rooms/living/armchair_class.py": "tools.rooms.living",
  "tools/rooms/bedroom/bed_class.py": "tools.rooms.bedroom",
  "tools/rooms/living/coffee_table_class.py": "tools.rooms.living",
  "tools/rooms/living/dining_table_class.py": "tools.rooms.living",
  "tools/rooms/living/rack_class.py": "tools.rooms.living",
  "tools/rooms/living/sofa_class.py": "tools.rooms.living",
  "tests/test_fp042_furniture_classes_ownership.py": "regression_test_suite",
  "tools/rooms/bedroom/layout_decisions.py": "tools.rooms.bedroom",
  "tools/rooms/bathroom/solver_policy.py": "tools.rooms.bathroom",
  "tools/rooms/p3_ownership.py": "cross_room_ownership_audit",
  "tests/test_fp042_p3_ownership.py": "regression_test_suite"
}
EVIDENCE = "FP042_P3_EXPLICIT_PATH_AND_ROLE_NOT_L2"


def audit_p3(index):
    items = [e for e in index.get("entries", []) if e.get("phase") == "P3"]
    found = {e["path"]: e for e in items}
    invalid = sorted(p for p, e in found.items()
                     if p not in OWNER_TABLE
                     or e.get("runtime_owner") != OWNER_TABLE[p]
                     or e.get("status") != "VERIFIED_RUNTIME_PATH_OWNER_ROLE"
                     or e.get("ownership_evidence") != EVIDENCE)
    missing = sorted(set(OWNER_TABLE) - set(found))
    return {"result": "FAIL" if invalid or missing else "PASS",
            "checked": len(items), "invalid": invalid, "missing": missing,
            "proof": "EXACT_PATH_AND_OWNER_NOT_VISUAL_L2"}


def main():
    report = audit_p3(json.loads(INVENTORY.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
