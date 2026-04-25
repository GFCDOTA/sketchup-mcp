"""Run YOLOv8 floor-plan detector on planta_74 images and emit JSON + annotated PNG."""
import json
import os
import time
from pathlib import Path

from ultralytics import YOLO

WEIGHTS = r"E:\Claude\sketchup-mcp-exp-dedup\dashboard\models\yolo_floorplan.pt"
IS_FALLBACK = False
OUT_DIR = Path(r"E:\Claude\sketchup-mcp-exp-dedup\dashboard\detections")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATES = [
    r"E:\Claude\sketchup-mcp\runs\planta_74\raw_page.png",
    r"E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74\overlay_audited.png",
]

print(f"Loading weights: {WEIGHTS}")
model = YOLO(WEIGHTS)
print(f"model.names = {model.names}")
print(f"model.task  = {getattr(model, 'task', '?')}")

results_summary = []

for img in CANDIDATES:
    if not os.path.exists(img):
        print(f"SKIP missing: {img}")
        continue
    print(f"\n--- Inferring on {img} ---")
    t0 = time.time()
    res = model.predict(
        source=img,
        conf=0.25,
        save=True,
        project=str(OUT_DIR),
        name=f"yolo_{Path(img).stem}",
        exist_ok=True,
        verbose=False,
    )
    dt = time.time() - t0
    r = res[0]
    h, w = r.orig_shape
    dets = []
    totals = {}
    boxes = r.boxes
    if boxes is not None and len(boxes) > 0:
        for b in boxes:
            cls_id = int(b.cls.item())
            cls_name = model.names[cls_id]
            conf = float(b.conf.item())
            xyxy = [float(v) for v in b.xyxy[0].tolist()]
            dets.append({"class": cls_name, "conf": round(conf, 4),
                         "bbox": [round(c, 2) for c in xyxy]})
            totals[cls_name] = totals.get(cls_name, 0) + 1
    annotated_png = Path(r.save_dir) / Path(img).name
    payload = {
        "model": Path(WEIGHTS).name,
        "image": img,
        "image_size": [int(w), int(h)],
        "detections": dets,
        "totals": totals,
        "totals_summary": {
            "doors":   sum(v for k, v in totals.items() if "door" in k.lower()),
            "windows": sum(v for k, v in totals.items() if "window" in k.lower()),
            "walls":   sum(v for k, v in totals.items() if "wall" in k.lower()),
        },
        "latency_seconds": round(dt, 3),
        "is_fallback": IS_FALLBACK,
        "annotated_png": str(annotated_png),
        "model_classes": model.names,
    }
    results_summary.append(payload)
    print(f"  detections={len(dets)} totals={totals} latency={dt:.2f}s")
    print(f"  annotated -> {annotated_png}")

# Pick raw_page.png as canonical "final" target if present, else first
canonical = None
for p in results_summary:
    if "raw_page.png" in p["image"]:
        canonical = p
        break
if canonical is None and results_summary:
    canonical = results_summary[0]

if canonical is None:
    raise SystemExit("no images processed")

# Attach also-ran for transparency
canonical["also_ran"] = [
    {"image": p["image"],
     "detections_count": len(p["detections"]),
     "totals": p["totals"],
     "annotated_png": p["annotated_png"]}
    for p in results_summary if p["image"] != canonical["image"]
]

out_json = OUT_DIR / "yolo_final_planta_74.json"
out_json.write_text(json.dumps(canonical, indent=2, ensure_ascii=False))
print(f"\nWROTE {out_json}")
print(f"canonical image: {canonical['image']}")
print(f"canonical totals: {canonical['totals']}")
