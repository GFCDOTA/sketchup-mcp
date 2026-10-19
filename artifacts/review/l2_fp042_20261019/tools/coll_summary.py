import json, sys
c = json.load(open(sys.argv[1], encoding="utf-8"))
rows = c["rows"]; out = {}
for i, a in enumerate(rows):
    for b in rows[i+1:]:
        if a["module"] == b["module"] or "ALLOW" in (a["overlap_policy"], b["overlap_policy"]):
            continue
        p = [min(a["skp_max"][k], b["skp_max"][k]) - max(a["skp_min"][k], b["skp_min"][k]) for k in range(3)]
        if all(v > 0.001 for v in p):
            key = (a["module"].split(" · ")[-1], b["module"].split(" · ")[-1])
            d = min(p)
            if d > out.get(key, (0,))[0]:
                out[key] = (round(d, 4), a["label"], b["label"], [round(v, 3) for v in p])
for k, v in sorted(out.items(), key=lambda kv: -kv[1][0]):
    print(f"{k[0]} x {k[1]}: pen_min_axis={v[0]} m  ({v[1]} x {v[2]}) xyz={v[3]}")
