"""material_review.py — FP-038: imagens de REVISAO por AMBIENTE do .skp mobiliado, boas o bastante
pro Felipe dar veredito visual (IMPROVED/SAME/WORSE) SEM abrir o SketchUp.

O iso do ape inteiro nao mostra textura (movel pequeno, sofa atras do vidro da sacada). Esta tool
abre o .skp JA gerado (FP-036), isola cada comodo (esconde oclusores/vidro), frameia a mobilia e
renderiza um proof por ambiente + um close do sofa. NAO julga estetica (isso e do Felipe / FP-039);
so PRODUZ as imagens. NAO altera o .skp (renderiza uma COPIA, nunca salva por cima).

Fatia 0 (esta): bbox por comodo (Python puro) + config declarativa de cameras + dry-run.
Fatias 1-3 (proximas): tools/material_review.rb (isola+frameia+render) + launch do SU + smoke.

Uso:
  python tools/material_review.py --dry-run      # imprime bbox por camera (sem SU)
  python tools/material_review.py [--skp <path>] # (fatia 2+) renderiza os proofs
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
RB = ROOT / "tools/material_review.rb"
DEFAULT_SKP = ROOT / "artifacts/planta_74/furnished/planta_74_furnished.skp"
OUT_DIR = ROOT / "artifacts/planta_74/furnished/material_review"

# Config declarativa de cameras por ambiente. `match` = substring testada contra o NOME DO GRUPO do
# .rb ("#{room} · #{module}", place_layout_skp.rb:82) — mesma semantica no Python (bbox) e no .rb.
# O .rb esconde TODO o shell (parede/piso/vidro) p/ o material aparecer SEM oclusao (proof de
# material, nao de arquitetura). `exclude` = substrings de MODULOS a tirar do frame (movel alto/
# distante que encolhe o alvo: trilho de luz, jantar, decor). `mode`: "iso" | "closeup" (mais perto).
ROOM_CAMERAS = [
    {"name": "living", "match": "SALA", "out": "living_material_proof.png", "mode": "iso",
     "exclude": ["Trilho de luz", "Mesa de jantar", "Cadeira jantar", "Planta", "Quadro", "Prateleira"]},
    {"name": "kitchen", "match": "COZINHA", "out": "kitchen_material_proof.png",
     "mode": "iso", "exclude": []},
    {"name": "bedroom", "match": "SUITE 01", "out": "bedroom_material_proof.png",
     "mode": "iso", "exclude": []},
    {"name": "living_sofa_closeup", "match": "· Sofa", "out": "living_sofa_closeup.png",
     "mode": "closeup", "exclude": []},
]


def group_name(b) -> str:
    """Nome do grupo top-level do movel, IGUAL ao place_layout_skp.rb:82 ("#{room} · #{module}")."""
    room = str(b.get("room") or "Apto")
    mod = str(b.get("module") or b.get("kind") or "Movel")
    return f"{room} · {mod}"


def room_bbox(boxes, match):
    """bbox (x0,y0,x1,y1) em SU inches dos boxes cujo NOME DE GRUPO contem `match` (case-insensitive),
    via corners (ou x0..x1 no fallback). None se nenhum box casar. Determinístico."""
    m = match.upper()
    xs, ys = [], []
    for b in boxes:
        if m not in group_name(b).upper():
            continue
        corners = b.get("corners") or []
        if corners:
            for c in corners:
                xs.append(float(c[0]))
                ys.append(float(c[1]))
        elif all(k in b for k in ("x0", "y0", "x1", "y1")):
            xs += [float(b["x0"]), float(b["x1"])]
            ys += [float(b["y0"]), float(b["y1"])]
    if not xs:
        return None
    return (round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2))


def output_path(cam) -> Path:
    return OUT_DIR / cam["out"]


def validate_cameras(cams=ROOM_CAMERAS) -> list[str]:
    """Erros de config (vazio = ok). Nomes de saida previsiveis, modes conhecidos, sem colisao."""
    errs, seen = [], set()
    for c in cams:
        for k in ("name", "match", "out", "mode", "exclude"):
            if k not in c:
                errs.append(f"{c.get('name','?')}: falta '{k}'")
        if c.get("mode") not in ("iso", "closeup"):
            errs.append(f"{c.get('name','?')}: mode invalido {c.get('mode')!r}")
        if not str(c.get("out", "")).endswith(".png"):
            errs.append(f"{c.get('name','?')}: out nao e .png")
        if c.get("out") in seen:
            errs.append(f"saida duplicada: {c.get('out')}")
        seen.add(c.get("out"))
    return errs


def _dry_run():
    """Constroi os boxes reais da planta_74 (como o furnish) e imprime o bbox de cada camera."""
    os.environ.setdefault("PT_TO_M", "0.0259")
    os.environ.setdefault("FURNISH_STYLE", "industrial")
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    con = json.loads(Path(CONSENSUS).read_text("utf-8"))
    boxes, _ = collect_boxes(con)
    print(f"[material-review] {len(boxes)} boxes; config: {len(ROOM_CAMERAS)} cameras")
    errs = validate_cameras()
    print(f"[material-review] config valida: {'OK' if not errs else errs}")
    for cam in ROOM_CAMERAS:
        bb = room_bbox(boxes, cam["match"])
        n = sum(1 for b in boxes if cam["match"].upper() in group_name(b).upper())
        print(f"  {cam['name']:22} match={cam['match']!r:26} boxes={n:3} bbox={bb} -> {cam['out']}")


def build_cameras_env(cams=ROOM_CAMERAS, out_dir=OUT_DIR):
    """MR_CAMERAS: cada camera com o `out` resolvido pra path absoluto (forward slashes)."""
    payload = []
    for c in cams:
        payload.append({"name": c["name"], "match": c["match"], "mode": c["mode"],
                        "exclude": c.get("exclude", []),
                        "out": str((out_dir / c["out"]).resolve()).replace("\\", "/")})
    return json.dumps(payload)


def render_proofs(skp_path):
    """Abre uma COPIA do .skp mobiliado e renderiza os proofs por ambiente (nunca salva o original)."""
    skp = Path(skp_path).resolve()
    if not skp.exists():
        print(f"[material-review] .skp nao encontrado: {skp}")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # COPIA de trabalho (o .rb nao salva, mas abrir a copia protege 100% o original)
    work = OUT_DIR / "_review_copy.skp"
    shutil.copyfile(skp, work)
    log_path = OUT_DIR / "material_review_log.txt"
    for c in ROOM_CAMERAS:
        p = OUT_DIR / c["out"]
        if p.exists():
            try:
                p.unlink()
            except PermissionError:
                pass
    if log_path.exists():
        log_path.unlink()

    env = os.environ.copy()
    env["MR_CAMERAS"] = build_cameras_env()
    env["MR_LOG"] = str(log_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)
    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(work), "-RubyStartup", str(RB)]
    print(f"[material-review] launching SU (base={skp.name}, {len(ROOM_CAMERAS)} cameras)...")
    subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if not log_path.exists():
        print("[material-review] TIMEOUT — SU nao produziu log")
        sys.exit(1)
    print("[material-review] LOG:")
    print(log_path.read_text("utf-8"))
    print(f"\n[material-review] -> {OUT_DIR}/")
    for c in ROOM_CAMERAS:
        p = OUT_DIR / c["out"]
        print(f"  {'OK ' if p.exists() else 'MISS'} {c['out']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skp", default=str(DEFAULT_SKP), help="skp mobiliado a revisar")
    ap.add_argument("--dry-run", action="store_true", help="so imprime bbox por camera (sem SU)")
    args = ap.parse_args()
    if args.dry_run:
        _dry_run()
        return
    render_proofs(args.skp)


if __name__ == "__main__":
    main()
