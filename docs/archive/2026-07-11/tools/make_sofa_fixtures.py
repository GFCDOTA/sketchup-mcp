"""make_sofa_fixtures.py — slice 4: gera os micro-fixtures de sofa (straight,
chaise_right, chaise_left) lado a lado numa cena, escreve os boxes (formato
place_layout, com z0_in) + metadata por fixture. O .skp + renders top/front/iso
saem do build_furniture_skp.rb via SU (PowerShell). NAO toca na planta.

Uso: python tools/make_sofa_fixtures.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.sofa_builder import build_sofa, parts_to_boxes, sofa_spec   # noqa: E402

FIXTURES = [("straight", 3), ("chaise_right", 3), ("chaise_left", 3)]
GAP_X = 1.2   # espaco entre fixtures na cena (m)
ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".claude/scratch"
OUT = ROOT / "artifacts/review/furniture/sofa"


def make():
    boxes, meta, ox = [], [], 0.0
    for variant, seats in FIXTURES:
        parts, m = build_sofa(sofa_spec(variant, seats))
        boxes += parts_to_boxes(parts, ox=ox)
        m["offset_x_m"] = round(ox, 2)
        m["parts"] = [{"label": p["label"], "kind": p["kind"]} for p in parts]
        meta.append(m)
        ox += m["bbox_m"][0] + GAP_X
    return boxes, meta


if __name__ == "__main__":
    SCRATCH.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    boxes, meta = make()
    (SCRATCH / "sofa_fixtures_boxes.json").write_text(json.dumps(boxes), encoding="utf-8")
    (OUT / "sofa_fixtures_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print("fixtures:", [(m["variant"], f"{m['n_parts']}p") for m in meta],
          "| total boxes", len(boxes))
    print("  kinds por fixture:", [sorted(set(p["kind"] for p in m["parts"])) for m in meta])
