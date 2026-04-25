import json
from collections import Counter

d = json.load(open(r"E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74\consensus_model.json", encoding="utf-8"))
adj = d["adjacency"]
print("total edges:", len(adj["edges"]))
print("total facade:", len(adj["facade_openings"]))

c = Counter()
for e in adj["edges"]:
    c[e["room_a"]] += 1
    c[e["room_b"]] += 1
labels = {r["room_id"]: r.get("label_qwen") or r["room_id"] for r in d["rooms"]}
print()
print("Per-room edge degree:")
for rid, n in sorted(c.items(), key=lambda x: -x[1]):
    print(f"  {labels[rid]:30s} {n}")

print()
print("Unlabeled rooms bboxes:")
for r in d["rooms"]:
    if not r.get("label_qwen"):
        xs = [p[0] for p in r["polygon"]]
        ys = [p[1] for p in r["polygon"]]
        rid = r["room_id"]
        print(f"  {rid}: bbox=({min(xs):.0f},{min(ys):.0f})-({max(xs):.0f},{max(ys):.0f}) area={r['area']:.0f}pt2")

print()
print("Facade openings (might be misclassified):")
for f in adj["facade_openings"]:
    op = next(o for o in d["openings"] if o["opening_id"] == f["opening_id"])
    print(f"  {f['opening_id']:6s} kind={f['kind']:6s} center={op['center']} -> room={labels.get(f['room'], f['room'])}")
