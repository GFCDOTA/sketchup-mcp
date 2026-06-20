"""render_scene_views.py — RenderHarness do Intent-to-Scene: gera as evidencias
visuais de uma cena composta (runs/scenes/<id>/scene_parts.json do SceneComposer):

  top_view.png        — planta da cena (todas as parts, camera zenital)
  three_quarter.png   — 3/4 humano SU-FREE (mpl; esconde as 2 paredes junto da
                        camera = dollhouse view; elev/azim vem do composer)
  contact_sheet.png   — top + 3/4 lado a lado com faixa de titulo (pro juiz GPT)
  scene.skp + sketchup_top.png/sketchup_3_4.png — OPCIONAL via SketchUp
                        (build_furniture_skp.rb); SO roda se o SketchUp NAO estiver
                        aberto (no-disrupt) e --su for pedido/auto disponivel.

V-Ray fica explicitamente FORA desta slice (regra: nao otimizar V-Ray antes da
composicao passar o SpatialGate).

Uso: python -m tools.render_scene_views [runs/scenes/<id>] [--su auto|off]
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.scale import M_TO_IN                      # noqa: E402
from tools.render_parts_iso import render_parts     # noqa: E402


def load_scene(scene_dir):
    d = Path(scene_dir)
    scene = json.loads((d / "scene.json").read_text("utf-8"))
    parts = json.loads((d / "scene_parts.json").read_text("utf-8"))
    return scene, parts


def _visible_parts(parts, hide_walls):
    """Dollhouse: esconde as paredes pedidas + SEMPRE o teto (o ceiling existe
    so pro caminho V-Ray interior; top/3/4/SU ficam abertos)."""
    hidden = tuple(f"wall_{w}" for w in (hide_walls or [])) + ("ceiling",)
    return [p for p in parts if not str(p.get("label", "")).startswith(hidden)]


_TILE_KINDS = ("floor", "wall", "rug_field", "rug_border")


def _edges(lo, hi, tile, snaps=()):
    n = max(1, int(math.ceil((hi - lo) / tile))) if (hi - lo) > tile else 1
    es = {round(lo + (hi - lo) * i / n, 4) for i in range(n + 1)}
    es.update(round(s, 4) for s in snaps if lo + 1e-6 < s < hi - 1e-6)
    return sorted(es)


def _tile_shell(parts, tile=0.45, cut_rects=()):
    """Divide piso/paredes/tapete em ladrilhos <= tile (m) SO pro render mpl 3/4: o
    painter sort do mplot3d falha com poligono gigante (piso engolia tapete/mesa);
    faces de tamanho comparavel ordenam direito. Tiles saem com edge=False (sem
    linha de grade = nao le como azulejo). cut_rects (bboxes de tapete) viram
    BURACO no piso — sem face coplanar sob o tapete = sem briga de z. O
    scene_parts canonico fica intacto (SU/gate)."""
    out = []
    for p in parts:
        if p["kind"] not in _TILE_KINDS or p.get("verts8"):
            out.append(p)
            continue
        cuts = cut_rects if p["kind"] == "floor" else ()
        sx = _edges(p["x0"], p["x1"], tile, [c for r in cuts for c in (r[0], r[2])])
        sy = _edges(p["y0"], p["y1"], tile, [c for r in cuts for c in (r[1], r[3])])
        sz = _edges(p["z0"], p["z1"], tile)
        for i in range(len(sx) - 1):
            for j in range(len(sy) - 1):
                cx, cy = (sx[i] + sx[i + 1]) / 2, (sy[j] + sy[j + 1]) / 2
                if any(r[0] - 1e-6 <= cx <= r[2] + 1e-6 and r[1] - 1e-6 <= cy <= r[3] + 1e-6
                       for r in cuts):
                    continue
                for k in range(len(sz) - 1):
                    q = dict(p, edge=False)
                    q["x0"], q["x1"] = sx[i], sx[i + 1]
                    q["y0"], q["y1"] = sy[j], sy[j + 1]
                    q["z0"], q["z1"] = sz[k], sz[k + 1]
                    out.append(q)
    return out


def scene_boxes(parts):
    """parts world-space (m) -> boxes do build_furniture_skp.rb (inches, corners,
    z0_in). Pecas com verts8 usam o QUAD INFERIOR como corners (footprint REAL —
    inclusive girado em angulo livre; o fz_solid do .rb levanta qualquer poligono);
    altura = extrusao reta, entao taper de cupula vira prisma da boca (limitacao
    leve documentada). O render mpl preserva o verts8 completo."""
    boxes = []
    for p in parts:
        x0, y0, x1, y1 = (p["x0"] * M_TO_IN, p["y0"] * M_TO_IN,
                          p["x1"] * M_TO_IN, p["y1"] * M_TO_IN)
        if p.get("verts8"):
            corners = [[round(v[0] * M_TO_IN, 2), round(v[1] * M_TO_IN, 2)]
                       for v in p["verts8"][:4]]
        else:
            corners = [[round(x0, 2), round(y0, 2)], [round(x1, 2), round(y0, 2)],
                       [round(x1, 2), round(y1, 2)], [round(x0, 2), round(y1, 2)]]
        # label namespaced pelo item: o .rb nomeia material fz_<label> — "top" da
        # side_table colidia com "top" da coffee_table e herdava a cor errada
        label = p.get("label", p["kind"])
        if p.get("item"):
            label = f"{p['item']}__{label}"
        boxes.append({
            "kind": p["kind"], "label": label,
            "x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2),
            "corners": corners,
            "h_in": round((p["z1"] - p["z0"]) * M_TO_IN, 2),
            "z0_in": round(p["z0"] * M_TO_IN, 2),
            "rgb": p["rgb"], "ambiguous": False, "decorative": False,
        })
    return boxes


def _su_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq SketchUp.exe"],
                         capture_output=True, text=True)
    return "SketchUp.exe" in (out.stdout or "")


def _render_su(scene, parts, out_dir):
    """Render canonico opcional via SU (modelo limpo, boxes). No-disrupt: pula se o
    SketchUp ja esta aberto. Devolve dict de status."""
    if _su_running():
        return {"status": "skipped", "reason": "SketchUp em uso (no-disrupt) — feche o SU e rode de novo"}
    try:
        from interior.renderers.render_provider import RenderRequest
        from interior.renderers.sketchup_basic_provider import SketchUpBasicProvider
    except Exception as e:  # noqa: BLE001
        return {"status": "skipped", "reason": f"provider indisponivel: {e}"}
    prov = SketchUpBasicProvider()
    if not prov.available():
        return {"status": "skipped", "reason": "SU exe/base ausentes"}
    # a camera iso do build_furniture_skp.rb e' FIXA de sudeste-elevado ->
    # o dollhouse SU abre south+east (independente da camera mpl do composer)
    vis = _visible_parts(parts, ["south", "east"])
    req = RenderRequest(
        boxes=scene_boxes(vis),
        out_skp=str(out_dir / "scene.skp"),
        renderer="furniture", label=f"scene_{scene['scene_id']}",
        renders={"top": str(out_dir / "sketchup_top.png"),
                 "iso": str(out_dir / "sketchup_3_4.png")})
    res = prov.render(req)
    return {"status": res.status, "skp": res.skp, "renders": res.renders,
            "timing_s": res.timing_s, "error": res.error}


def _contact_sheet(images, out_png, title):
    from PIL import Image, ImageDraw
    PANEL_H, GAP, BAND = 760, 24, 52
    panels = []
    for label, path in images:
        if not Path(path).exists():
            continue
        im = Image.open(path).convert("RGB")
        w = int(im.width * PANEL_H / im.height)
        panels.append((label, im.resize((w, PANEL_H), Image.LANCZOS)))
    if not panels:
        return None
    W = sum(p.width for _, p in panels) + GAP * (len(panels) + 1)
    H = BAND + PANEL_H + GAP * 2
    sheet = Image.new("RGB", (W, H), (246, 244, 240))
    dr = ImageDraw.Draw(sheet)
    dr.text((GAP, 16), title, fill=(40, 38, 36))
    x = GAP
    for label, p in panels:
        sheet.paste(p, (x, BAND + GAP))
        dr.text((x + 4, BAND + 2), label, fill=(90, 86, 80))
        x += p.width + GAP
    sheet.save(out_png)
    return str(out_png)


def render_views(scene_dir, su="auto"):
    scene, parts = load_scene(scene_dir)
    # SEMPRE absoluto: o SketchUp resolve save/write_image contra o CWD DELE —
    # path relativo aqui = .skp/PNG salvos fora do run dir com log de sucesso
    out = Path(scene_dir).resolve()
    cam = scene["camera"]
    sid = scene["scene_id"]

    top = render_parts(parts, out / "top_view.png", elev=90, azim=-90,
                       title=f"{sid} — top")
    rugs = [pl["bbox"][:4] for pl in scene.get("placements", []) if pl["type"] == "rug"]
    vis = _tile_shell(_visible_parts(parts, cam.get("hide_walls")), cut_rects=rugs)
    tq = render_parts(vis, out / "three_quarter.png",
                      elev=cam["elev_deg"], azim=cam["azim_deg"],
                      title=f"{sid} — 3/4 ({cam['kind']})")

    su_info = {"status": "off"}
    if su == "auto":
        su_info = _render_su(scene, parts, out)

    sheet_imgs = [("top", top), ("3/4 mpl", tq)]
    if su_info.get("renders", {}).get("iso"):
        sheet_imgs.append(("3/4 SketchUp", su_info["renders"]["iso"]))
    sheet = _contact_sheet(sheet_imgs, out / "contact_sheet.png",
                           f"{sid} | style={scene.get('style_id')} | SU-free composition evidence")

    manifest = {"scene_id": sid, "views": {"top_view": top, "three_quarter": tq,
                                           "contact_sheet": sheet},
                "renderer": "matplotlib_parts_iso (SU-free, deterministico)",
                "camera": cam, "sketchup": su_info,
                "vray": "deferred — so depois do SpatialGate PASS"}
    (out / "render_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("scene_dir", nargs="?",
                    default=str(ROOT / "runs/scenes/living_room_modern_warm_minimal"))
    ap.add_argument("--su", choices=("auto", "off"), default="auto")
    ns = ap.parse_args()
    d, su = Path(ns.scene_dir), ns.su
    m = render_views(d, su=su)
    print(f"=== RenderHarness: {m['scene_id']} ===")
    for k, v in m["views"].items():
        print(f"  {k:14} -> {v}")
    print(f"  sketchup: {m['sketchup'].get('status')}"
          + (f" ({m['sketchup'].get('reason', m['sketchup'].get('error', ''))})"
             if m['sketchup'].get('status') != 'success' else f" skp={m['sketchup'].get('skp')}"))
