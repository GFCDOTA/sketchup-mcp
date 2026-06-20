"""furniture_normalizer.py — Furniture Normalizer (Asset Catalog v1). Transforma um
movel em COMPONENTE canonico (manifesto conforme interior/schemas/furniture_asset.schema.json):
escala/orientacao/anchors/clearance/qualidade conhecidos, e registra no catalogo.

Dois caminhos:
  - normalize_parametric(): movel PROPRIO (tier C) a partir do spec + parts + gate.
  - normalize_asset(): .skp de TERCEIRO (tier B, 3DW) a partir do inspect.json +
    analysis.json (inspect_skp.rb + furniture_reference_analyzer.py).

NAO espelha o asset pesado no repo publico: tier A/B guardam so manifesto + thumbnail +
proveniencia; o .skp fica em assets/third_party_cache/ (gitignored). Felipe dropa os
.skp do 3DW la; o normalizer canoniza.

Uso: python tools/furniture_normalizer.py --seed-sofa   (registra o sofa parametrico)
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "assets/catalog/furniture_catalog.json"
FURN = ROOT / "assets/furniture"

# clearance profissional por tipo (m): circulacao/uso minimo na frente, laterais, fundo
DEFAULT_CLEARANCE = {
    "sofa": {"front": 0.75, "sides": 0.20, "back": 0.05},
    "bed": {"front": 0.70, "sides": 0.60, "back": 0.05},
    "wardrobe": {"front": 0.90, "sides": 0.05, "back": 0.0},
    "rack": {"front": 0.40, "sides": 0.10, "back": 0.0},
    "nightstand": {"front": 0.45, "sides": 0.05},
    "table": {"sides": 0.70},
}
# faixa de escala humana plausivel por tipo (m) — width,depth,height min/max
SCALE_RANGE = {
    "sofa": {"width": (1.4, 3.6), "depth": (0.8, 1.8), "height": (0.6, 1.0)},
    "bed": {"width": (0.9, 2.1), "depth": (1.9, 2.2), "height": (0.3, 1.3)},
    "wardrobe": {"width": (0.6, 3.5), "depth": (0.5, 0.7), "height": (1.8, 2.6)},
}

_OPP = {"+X": "-X", "-X": "+X", "+Y": "-Y", "-Y": "+Y"}


def _scale_ok(ftype, bb):
    r = SCALE_RANGE.get(ftype)
    if not r:
        return None
    w, d, h = bb
    return all(r[k][0] <= v <= r[k][1] for k, v in (("width", w), ("depth", d), ("height", h)))


def upsert_catalog(manifest):
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    cat = json.loads(CATALOG.read_text("utf-8")) if CATALOG.exists() else {"version": 1, "assets": []}
    cat["assets"] = [a for a in cat["assets"] if a["id"] != manifest["id"]]
    cat["assets"].append({k: manifest.get(k) for k in
                          ("id", "type", "tier", "variant", "style_tags", "dimensions_m",
                           "thumbnail", "quality")})
    cat["assets"].sort(key=lambda a: (a["type"], a["id"]))
    CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")
    return cat


def write_manifest(manifest):
    d = FURN / manifest["type"] / "manifests"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{manifest['id']}.json"
    p.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    upsert_catalog(manifest)
    return p


def normalize_parametric(asset_id, ftype, spec_dict, parts, gate_result, builder,
                         style_tags, thumbnail=None):
    """Manifesto de movel PARAMETRICO (tier C)."""
    bb = spec_dict.get("bbox_m") or [spec_dict["width"], spec_dict["depth"], spec_dict["height"]]
    kinds = sorted({p["kind"] for p in parts})
    front = spec_dict.get("front_axis", "-Y")
    return {
        "id": asset_id, "type": ftype, "tier": "C_parametric",
        "source": f"parametric:{builder['module']}", "license_mode": "own",
        "variant": spec_dict.get("variant"), "style_tags": style_tags,
        "dimensions_m": {"width": round(bb[0], 3), "depth": round(bb[1], 3), "height": round(bb[2], 3)},
        "canonical_orientation": {"front_axis": front, "back_axis": _OPP.get(front, "+Y"), "up_axis": "+Z"},
        "anchors": {"floor_origin": [0, 0, 0],
                    "back_center": [round(bb[0] / 2, 3), round(bb[1], 3), 0],
                    "front_center": [round(bb[0] / 2, 3), 0.0, 0]},
        "clearance_m": DEFAULT_CLEARANCE.get(ftype, {"front": 0.5, "sides": 0.1}),
        "required_parts": spec_dict.get("required_parts", []),
        "parts_present": kinds,
        "quality": {"scale_checked": _scale_ok(ftype, bb) is not False,
                    "orientation_checked": True,
                    "materials_checked": all(p.get("rgb") for p in parts),
                    "not_single_block": len(parts) > 1 and len(kinds) >= 3,
                    "thumbnail_checked": bool(thumbnail),
                    "gate": gate_result.get("result", "UNVALIDATED")},
        "thumbnail": thumbnail, "skp": None, "builder": builder,
    }


def normalize_asset(asset_id, inspect, analysis, provenance, style_tags, skp_cache_rel=None):
    """Manifesto de .skp de TERCEIRO (tier B, 3DW) a partir de inspect+analysis."""
    bb = inspect["bbox"]["size_m"]
    ftype = analysis.get("object_hypothesis", "decor")
    front = (analysis.get("front_axis") or "-Y")[:2]
    return {
        "id": asset_id, "type": ftype, "tier": "B_curated_3dw",
        "source": f"3dwarehouse:{provenance}", "provenance": provenance,
        "license_mode": "combined_work_only",
        "variant": analysis.get("variant"), "style_tags": style_tags,
        "dimensions_m": {"width": bb[0], "depth": bb[1], "height": bb[2]},
        "canonical_orientation": {"front_axis": front, "back_axis": _OPP.get(front, "+Y"), "up_axis": "+Z"},
        "anchors": {"floor_origin": [0, 0, 0]},
        "clearance_m": DEFAULT_CLEARANCE.get(ftype, {"front": 0.5, "sides": 0.1}),
        "parts_present": sorted(analysis.get("parts_detected", {}).keys()),
        "quality": {"scale_checked": _scale_ok(ftype, bb), "orientation_checked": False,
                    "materials_checked": len(inspect.get("materials", [])) > 0,
                    "not_single_block": not analysis.get("is_single_block", True),
                    "thumbnail_checked": False, "gate": "UNVALIDATED"},
        "thumbnail": None, "skp": skp_cache_rel,
    }


def _seed_sofa():
    """Registra o sofa parametrico straight 3-lug como 1o asset do catalogo (tier C)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.sofa_builder import build_sofa, sofa_spec
    from tools.sofa_gate import gate
    spec = sofa_spec("straight", 3)
    parts, _ = build_sofa(spec)
    g = gate(spec, parts)
    # thumbnail: reaproveita o iso dos fixtures (mostra os 3 variants)
    src = ROOT / "artifacts/review/furniture/sofa/sofa_fixtures_iso.png"
    thumb_dir = FURN / "sofa/thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_rel = None
    if src.exists():
        shutil.copy(src, thumb_dir / "sofa_parametric_straight_3seat_iso.png")
        thumb_rel = "assets/furniture/sofa/thumbnails/sofa_parametric_straight_3seat_iso.png"
    m = normalize_parametric(
        "sofa_parametric_straight_3seat", "sofa", spec.to_dict(), parts, g,
        builder={"module": "tools.sofa_builder", "fn": "build_sofa", "spec": "sofa_spec('straight',3)"},
        style_tags=["modern", "neutral", "dark_gray"], thumbnail=thumb_rel)
    p = write_manifest(m)
    print(f"manifest -> {p.relative_to(ROOT)}")
    print(f"  type={m['type']} tier={m['tier']} dims={m['dimensions_m']} gate={m['quality']['gate']}"
          f" not_single_block={m['quality']['not_single_block']}")
    print(f"catalog -> {CATALOG.relative_to(ROOT)} ({len(json.loads(CATALOG.read_text('utf-8'))['assets'])} asset(s))")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-sofa", action="store_true", help="registra o sofa parametrico no catalogo")
    args = ap.parse_args()
    if args.seed_sofa:
        _seed_sofa()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
