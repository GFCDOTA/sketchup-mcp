"""Pacote visual (L3) da porta Shaker na cozinha real: ANTES (gabinete de frente lisa) x DEPOIS (porta Shaker), mesma camera, mesmo modelo.

Roda do repo (cwd = raiz do worktree), com `PYTHONPATH=.` e `PT_TO_M=0.0259`:
    python artifacts/review/fp046/l3_package/render_l3.py <saida> <base_mobiliado.skp> <request.json>
Refaz o fluxo `shaker_flow.run_request` numa copia do .skp mobiliado (gera `kitchen_parent.skp` = ANTES e `kitchen_shaker.skp` = DEPOIS) e
renderiza as MESMAS cameras nos dois. Gera `manifest.json` (commit, SHA-256 dos .skp e das imagens, cameras) e `visual_review.json`
com estado PENDING_HUMAN: NENHUM veredito visual e emitido aqui. As cores vem do NOME do material (cor derivada, sem textura/acabamento).
"""
import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.rooms.kitchen.capabilities import shaker_flow
from tools.sketchup import jobs

OUT = Path(sys.argv[1]).resolve()
BASE = Path(sys.argv[2]).resolve()
REQ = json.loads(Path(sys.argv[3]).read_text("utf-8"))
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1600, 1200


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(res):
    if res.get("pid"):
        jobs.close(pid=int(res["pid"]), force=True, confirm=True)
        pids.append(int(res["pid"]))


pids: list[int] = []
trace = shaker_flow.run_request(copy.deepcopy(REQ), out_dir=OUT / "flow", base_skp=BASE, mode="interactive")
(OUT / "flow_trace.json").write_text(json.dumps(trace, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
assert trace["state"] in ("DONE_L2_VERIFIED", "ALREADY_DONE"), trace["state"]
after_skp = Path(trace["evidence"]["skp"] if "evidence" in trace else trace["skp"])
before_skp = after_skp.with_name("kitchen_parent.skp")
assert before_skp.is_file() and after_skp.is_file()

# --- cameras: a MESMA para antes e depois, derivadas da pose/medidas do pedido (a porta olha para +y local)
inp = REQ["inputs"]
mm = lambda k: inp[k]["value"] * {"mm": 0.001, "cm": 0.01, "m": 1.0}[inp[k]["unit"]]  # noqa: E731
cw, cd, ch = mm("dimensions.width"), mm("dimensions.depth"), mm("dimensions.height")
px, py, pz = mm("pose.x"), mm("pose.y"), mm("pose.z")
th = math.radians(inp["pose.rotation_deg"]["value"])


def world(x, y, z):
    return [round(px + math.cos(th) * x - math.sin(th) * y, 4), round(py + math.sin(th) * x + math.cos(th) * y, 4), round(pz + z, 4)]


views = [
    {"name": "top", "preset": "top"},
    {"name": "iso", "eye_m": world(cw / 2 + 0.95, cd + 0.95, ch + 0.75), "target_m": world(cw / 2, cd * 0.9, ch * 0.5), "fov": 32},
    {"name": "front", "eye_m": world(cw / 2, cd + 1.40, ch * 0.55), "target_m": world(cw / 2, cd, ch * 0.5), "fov": 42},
    {"name": "detail_oblique", "eye_m": world(cw / 2 - 0.35, cd + 0.80, ch + 0.80), "target_m": world(cw / 2, cd, ch * 0.5), "fov": 34},
]
shots = {}
for label, skp in (("before", before_skp), ("after", after_skp)):
    r = jobs.render_views(str(skp), views=views, width=W, height=H, focus_contains="Cabinet_", out_dir=str(OUT / f"render_{label}"), mode="interactive")
    close(r)
    assert r["status"] == "OK", (label, r.get("status"), r.get("reason"), r.get("result"))
    shots[label] = {v["name"]: Path(v["path"]) for v in r["result"]["views"]}
    print("render", label, r["status"], flush=True)

# --- imagens finais (copias nomeadas) + folhas de contato
FINAL = OUT / "package"
FINAL.mkdir(exist_ok=True)
try:
    font = ImageFont.truetype("arial.ttf", 44)
    small = ImageFont.truetype("arial.ttf", 30)
except OSError:
    font = small = ImageFont.load_default()
LABEL = {"before": "ANTES: frente lisa", "after": "DEPOIS: porta Shaker"}
TITLE = {"top": "TOP (planta, ortografica)", "iso": "ISO (3/4 frontal)", "front": "FRENTE", "detail_oblique": "DETALHE OBLIQUO (extra, p/ ver o rebaixo)"}
manifest_images = {}
sheets = {}
for name in (v["name"] for v in views):
    pair = []
    for label in ("before", "after"):
        dst = FINAL / f"{name}_{label}.png"
        dst.write_bytes(shots[label][name].read_bytes())
        manifest_images[f"{name}_{label}.png"] = sha(dst)
        pair.append(Image.open(dst).convert("RGB"))
    w, h = pair[0].size
    sheet = Image.new("RGB", (w * 2 + 30, h + 130), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    d.text((20, 12), TITLE[name], fill=(20, 20, 20), font=font)
    for i, (label, im) in enumerate(zip(("before", "after"), pair)):
        sheet.paste(im, (i * (w + 30), 70))
        d.text((i * (w + 30) + 12, 74 + h + 4), LABEL[label], fill=(180, 30, 30) if label == "before" else (20, 90, 160), font=small)
    out = FINAL / f"sheet_{name}.png"
    sheet.save(out)
    sheets[name] = out
    manifest_images[out.name] = sha(out)
# folha geral (3 vistas pedidas + detalhe) reduzida
tiles = [Image.open(sheets[n]).convert("RGB") for n in ("top", "iso", "front", "detail_oblique")]
tw = 1400
tiles = [t.resize((tw, int(t.height * tw / t.width))) for t in tiles]
overview = Image.new("RGB", (tw * 2 + 20, sum(t.height for t in tiles[:2]) + 20), (245, 245, 245))
overview2 = Image.new("RGB", (tw * 2 + 20, sum(t.height for t in tiles[2:]) + 20), (245, 245, 245))
y = 0
for t in tiles[:2]:
    overview.paste(t, (0, y))
    y += t.height + 20
y = 0
for t in tiles[2:]:
    overview2.paste(t, (0, y))
    y += t.height + 20
overview = overview.crop((0, 0, tw, overview.height - 20))
overview2 = overview2.crop((0, 0, tw, overview2.height - 20))
overview.save(FINAL / "overview_1_top_iso.png")
overview2.save(FINAL / "overview_2_front_detail.png")
for n in ("overview_1_top_iso.png", "overview_2_front_detail.png"):
    manifest_images[n] = sha(FINAL / n)

ev = trace.get("evidence") or {}
manifest = {
    "schema_version": "fp046_l3_visual_package.v1",
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
    "sketchup_version": ev.get("sketchup_version"), "pids": pids + list(trace.get("pids", [])),
    "before_skp": {"path": str(before_skp), "sha256": sha(before_skp), "meaning": "cozinha real + gabinete de FRENTE LISA (pai da Shaker)"},
    "after_skp": {"path": str(after_skp), "sha256": sha(after_skp), "meaning": "mesmo gabinete com a frente substituida pela porta Shaker"},
    "base_furnished_copy_sha256": trace.get("base_sha256"), "flow_state": trace["state"],
    "cabinet_request": {"pose_m": [px, py, pz], "rotation_deg": inp["pose.rotation_deg"]["value"], "size_m": [cw, cd, ch]},
    "shaker_request": REQ["shaker"], "cameras": views, "image_size_px": [W, H],
    "images_sha256": manifest_images,
    "colors": "derivadas do NOME do material (hash), sem textura/acabamento: NAO sao a cor real da madeira",
    "limits": ["frame e painel tem o mesmo material: o rebaixo aparece pelas arestas e pelo angulo, nao por cor",
               "sem sombras/V-Ray: nao e render fotorrealista", "valores da porta sao do pedido de teste"],
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
review = {
    "schema_version": "fp046_visual_review.v1", "state": "PENDING_HUMAN", "decision": None, "reviewer": None, "date": None,
    "applies_to": {"after_skp_sha256": manifest["after_skp"]["sha256"], "before_skp_sha256": manifest["before_skp"]["sha256"],
                   "images_sha256": manifest_images},
    "note": "Nenhum veredito visual foi emitido por IA. A decisao e do Felipe (APPROVED | CHANGES_REQUESTED) e vale so para estes hashes.",
}
(OUT / "visual_review.json").write_text(json.dumps(review, indent=1, ensure_ascii=False), encoding="utf-8")
print("OK", len(manifest_images), "imagens; before", manifest["before_skp"]["sha256"][:12], "after", manifest["after_skp"]["sha256"][:12])
