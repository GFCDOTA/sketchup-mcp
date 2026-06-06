"""furnish_apartment.py — mobilia a planta INTEIRA num UNICO .skp: classifica
cada comodo (tools.room_type), roda o brain certo por tipo, junta TODOS os boxes
e materializa um so planta_74_furnished.skp (+ renders) no shell real. REUSA
tools/place_layout_skp.rb (generico). Pasta fixa artifacts/planta_74/furnished/.

Hoje mobilia: BEDROOM (bedroom_layout). Arquitetura cresce: e so registrar mais
brains em BRAINS (KITCHEN, BATHROOM, LIVING). Felipe 2026-06-05. Placeholders,
NAO 3D Warehouse.

ATENCAO: sem --dry-run, da taskkill SketchUp.exe e LANCA o SketchUp.
Uso: python tools/furnish_apartment.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # roda standalone
from tools import bedroom_designer   # noqa: E402  (quartos: brain novo GPT-approved)
from tools.bathroom_layout import build_boxes as bath_boxes   # noqa: E402
from tools.kitchen_layout import build_boxes as kitchen_boxes   # noqa: E402
from tools.place_layout_skp import build_boxes as living_boxes   # noqa: E402
from tools.room_type import (BATHROOM, BEDROOM, KITCHEN, LIVING,   # noqa: E402
                             classify_rooms)

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
OUT_DIR = ROOT / "artifacts/planta_74/furnished"   # pasta UNICA fixa
RB = ROOT / "tools/place_layout_skp.rb"

def bedroom_designer_boxes(con, room_id):
    """Adapter: roda o bedroom_designer (cama por tamanho do quarto + cabeceira +
    criados + tapete + guarda-roupa + console; GPT-approved) e devolve os boxes no
    formato place_layout. Troca o placeholder 'bed' (BLOCO UNICO azul) pela CAMA
    GOLDEN composta (bed_builder: plinto+estrado+colchao+travesseiros+manta, material
    por papel + bevel) no MESMO footprint/facing. Substitui o place_bedroom_skp antigo."""
    from tools.bed_builder import build_bed, place_bed_boxes
    from tools.furniture_anatomy_spec import bed_spec, wardrobe_spec
    from tools.wardrobe_builder import build_wardrobe, place_wardrobe_boxes
    sm, out = bedroom_designer.run(con, room_id, minimalist=True)
    if out.get("result") != "OK":
        return None, out
    items = out["_winner_items"]
    boxes = bedroom_designer._items_to_boxes(items)
    pt_m = 0.19 / 5.4
    pt_in = pt_m * 39.3700787402

    def _wd_facing(it, default=(0.0, 1.0)):
        f = it.get("facing") or default
        return (float(f[0]), float(f[1]))

    def _wd_dims(box, facing):
        x0, y0, x1, y1 = box.bounds
        fx, fy = facing
        if abs(fy) >= abs(fx):                      # corre em X (largura), profundidade em Y
            return (x1 - x0) * pt_m, (y1 - y0) * pt_m, ((x0 + x1) / 2 * pt_in, (y0 + y1) / 2 * pt_in)
        return (y1 - y0) * pt_m, (x1 - x0) * pt_m, ((x0 + x1) / 2 * pt_in, (y0 + y1) / 2 * pt_in)

    bed_item = next((it for it in items if it.get("type") == "bed"), None)
    if bed_item is not None:
        fx, fy = _wd_facing(bed_item)
        w_m, l_m, cen = _wd_dims(bed_item["box"], (fx, fy))
        nm = str(bed_item.get("name", ""))
        size = next((s for s in ("king", "queen", "casal", "solteiro") if s in nm), "king")
        parts, _ = build_bed(bed_spec(size, width=round(w_m, 3), length=round(l_m, 3)))
        bed_parts = place_bed_boxes(parts, cen, (fx, fy))
        boxes = [b for b in boxes if b.get("kind") != "bed"] + bed_parts
        out["bed_parametric"] = {"size": size, "n_parts": len(bed_parts),
                                 "W_m": round(w_m, 2), "L_m": round(l_m, 2)}

    # GUARDA-ROUPA golden (corpo+portas+puxadores+rodape) no mesmo footprint/facing (portas
    # viram p/ dentro do quarto). Troca o bloco roxo liso 'wardrobe'.
    wd_item = next((it for it in items if it.get("type") == "wardrobe"), None)
    if wd_item is not None:
        wfx, wfy = _wd_facing(wd_item)
        ww_m, wd_m, wcen = _wd_dims(wd_item["box"], (wfx, wfy))
        wparts, _ = build_wardrobe(wardrobe_spec(width=round(ww_m, 3), depth=round(max(wd_m, 0.45), 3)))
        wboxes = place_wardrobe_boxes(wparts, wcen, (wfx, wfy))
        boxes = [b for b in boxes if b.get("kind") != "wardrobe"] + wboxes
        out["wardrobe_parametric"] = {"n_parts": len(wboxes), "W_m": round(ww_m, 2), "D_m": round(wd_m, 2)}
    return boxes, out


def _oriented_box(kind, center_in, facing, w_m, d_m, z0_m, h_m, rgb, label=None):
    """Caixa (rack/mesa/tapete) centrada em center_in (shell inches) com a FRENTE
    (-Y local) apontando 'facing'. Mesma rotacao do place_sofa_boxes -> qualquer
    angulo. w=largura (perp ao facing), d=profundidade (ao longo do facing)."""
    import math
    M2IN = 39.3700787402
    cx, cy = center_in
    fx, fy = facing
    nrm = math.hypot(fx, fy) or 1.0
    fx, fy = fx / nrm, fy / nrm
    theta = math.atan2(fx, -fy)
    ct, st = math.cos(theta), math.sin(theta)
    corners = []
    for lx, ly in ((-w_m / 2, -d_m / 2), (w_m / 2, -d_m / 2),
                   (w_m / 2, d_m / 2), (-w_m / 2, d_m / 2)):
        wx, wy = lx * ct - ly * st, lx * st + ly * ct
        corners.append([round(cx + wx * M2IN, 2), round(cy + wy * M2IN, 2)])
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {"kind": kind, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys),
            "corners": corners, "h_in": round(h_m * M2IN, 2), "z0_in": round(z0_m * M2IN, 2),
            "rgb": rgb, "label": label or kind, "ambiguous": False, "decorative": False}


def living_room_boxes(con, room_id):
    """Sala via COMMON SENSE ENGINE (placement solver): o sofa GOLDEN deixa de
    flutuar no centro — fica ANCORADO numa parede de FRENTE pra TV (eixo sofa->rack),
    fora da circulacao; rack de MADEIRA na parede-TV (limpa), mesa de centro + tapete
    no eixo entre os dois. Corrige o veredito do GPT (objeto PASS, placement FAIL):
    o solver rejeita sofa em circulacao / sem eixo pra TV. Fallback: brain antigo."""
    from tools.sofa_builder import build_sofa, place_sofa_boxes, sofa_spec
    from interior.planners.living_room_planner import plan_living
    plan = plan_living(con, room_id)
    if plan.get("result") != "OK":
        boxes, out = living_boxes(con, room_id)            # fallback: brain antigo
        if boxes:
            boxes = [b for b in boxes if b.get("kind") != "poltrona"]
        out = dict(out or {}); out["placement"] = f"fallback_brain ({plan.get('result')})"
        return boxes, out
    p = plan["plan"]
    sofa_c = tuple(p["sofa"]["center_in"]); sofa_f = tuple(p["sofa"]["facing"])
    rack_c = tuple(p["tv_rack"]["center_in"]); rack_f = tuple(p["tv_rack"]["facing"])
    width_m = round(p["sofa"]["width_m"], 3)
    parts, _ = build_sofa(sofa_spec("straight", seats=3, width=width_m, depth=0.95))
    boxes = place_sofa_boxes(parts, sofa_c, sofa_f)         # sofa de frente pra TV
    # mesa + tapete AGRUPADOS perto do sofa (nao esticados ate o rack); rack na parede-TV
    import math as _m
    fnx, fny = sofa_f
    _fn = _m.hypot(fnx, fny) or 1.0
    fnx, fny = fnx / _fn, fny / _fn
    M2IN = 39.3700787402

    def _ahead(dist_m):                                     # ponto 'dist_m' a frente do sofa
        return (sofa_c[0] + fnx * dist_m * M2IN, sofa_c[1] + fny * dist_m * M2IN)

    # GPT (ajuste fino do placement PASS): CENTRALIZAR o rack/TV no eixo do sofa —
    # projeta o rack no eixo de facing do sofa (sofa->mesa->tapete->rack colineares).
    dist_fwd = (rack_c[0] - sofa_c[0]) * fnx + (rack_c[1] - sofa_c[1]) * fny
    rack_c = (sofa_c[0] + fnx * dist_fwd, sofa_c[1] + fny * dist_fwd)
    boxes.append(_oriented_box("rack_tv", rack_c, rack_f, 1.80, 0.40, 0.0, 0.50, [120, 85, 55]))
    boxes.append(_oriented_box("tapete", _ahead(0.95), sofa_f, 2.40, 1.60, 0.0, 0.02, [165, 156, 140]))
    boxes.append(_oriented_box("mesa_centro", _ahead(1.15), sofa_f, 1.00, 0.55, 0.0, 0.40, [92, 72, 56]))
    out = {"result": "OK", "room_name": plan.get("room_name"), "n_placed": len(boxes),
           "placement": "common_sense_solver", "tv_wall": plan.get("tv_wall"),
           "sofa_wall": p["sofa"]["wall_id"], "view_dist_m": p["sofa"]["rule"]}
    return boxes, out


# dispatch por tipo de comodo (cresce conforme novos brains entram)
BRAINS = {BEDROOM: bedroom_designer_boxes, KITCHEN: kitchen_boxes, LIVING: living_room_boxes,
          BATHROOM: bath_boxes}


def collect_boxes(con):
    """Junta os boxes de TODOS os comodos com brain disponivel. Devolve
    (boxes, summary[(id,name,type,result,n_boxes)])."""
    rooms = classify_rooms(con)
    all_boxes, summary = [], []
    for r in rooms:
        brain = BRAINS.get(r["room_type"])
        if brain is None:
            summary.append((r["id"], r["name"], r["room_type"], "skip(sem brain)", 0))
            continue
        boxes, out = brain(con, r["id"])
        n = len(boxes) if boxes else 0
        all_boxes += boxes or []
        summary.append((r["id"], r["name"], r["room_type"], out.get("result"), n))
    return all_boxes, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, summary = collect_boxes(con)
    n_rooms = sum(1 for s in summary if s[4])
    print(f"[furnish-apt] {len(boxes)} placeholders em {n_rooms} comodo(s):")
    for rid, name, rt, res, n in summary:
        print(f"  {str(rid):5} {str(name)[:28]:28} {rt:9} {str(res):16} {n} boxes")
    if args.dry_run or not boxes:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skp_out = OUT_DIR / "planta_74_furnished.skp"
    before = OUT_DIR / "planta_74_furnished_before_top.png"
    after_top = OUT_DIR / "planta_74_furnished_after_top.png"
    after_iso = OUT_DIR / "planta_74_furnished_after_iso.png"
    log_path = OUT_DIR / "planta_74_furnished_log.txt"
    # mata o SketchUp ANTES de apagar os arquivos (senao o .skp fica travado)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    for p in (skp_out, before, after_top, after_iso, log_path):
        try:
            if p.exists():
                p.unlink()
        except PermissionError:
            pass

    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    env["LAYOUT_OUT"] = str(skp_out).replace("\\", "/")
    env["LAYOUT_BEFORE"] = str(before).replace("\\", "/")
    env["LAYOUT_AFTER_TOP"] = str(after_top).replace("\\", "/")
    env["LAYOUT_AFTER_ISO"] = str(after_iso).replace("\\", "/")
    env["LAYOUT_LOG"] = str(log_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(RB)]
    print("[furnish-apt] launching SU...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[furnish-apt] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[furnish-apt] TIMEOUT — SU nao produziu log")
        sys.exit(1)
    print(f"\n[furnish-apt] -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
