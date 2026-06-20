"""furnish_plan.py — gera plantas mobiliadas (planta_74_vN.skp) inserindo
moveis (.skp do 3D Warehouse) numa planta-base ja pronta, posicionados no
comodo certo. Felipe 2026-06-04.

Uso:
    python tools/furnish_plan.py            # gera as variantes definidas em JOBS

Cada job: {component, out, room, rot, scale, name}. A posicao = ponto interno
do comodo `room` (do consensus), convertido pra SU inches.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import polylabel

ROOT = Path(r"E:\Claude\sketchup-mcp")
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
from core.scale import PT_TO_IN  # noqa: E402  (fonte unica de escala; nao redefinir)
CONSENSUS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
BASE_SKP = ROOT / "artifacts/planta_74/planta_74.skp"
FURNITURE = ROOT / "runs/planta_74/_furniture"
OUT_DIR = ROOT / "runs/planta_74"


def room_center_su(room_id: str) -> tuple[float, float]:
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rm = next(r for r in con["rooms"] if r["id"] == room_id)
    pts = [(float(p[0]), float(p[1])) for p in rm["polygon_pts"]]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    poly = Polygon(pts)
    try:
        c = polylabel(poly, tolerance=1.0)   # ponto mais central (longe das bordas)
    except Exception:
        c = poly.representative_point()
    return c.x * PT_TO_IN, c.y * PT_TO_IN


def orient_gate(iso_path: Path, model: str = "qwen2.5vl:7b") -> str:
    """Oracle de visao (Ollama) sobre o render iso: o movel esta na orientacao/
    posicao certa? Veredito AUXILIAR (modelo 7B) — pega erro grosseiro (tombado/
    afundado/atravessando parede); o olho do humano e o juiz final."""
    import base64
    import urllib.request
    if not iso_path.exists():
        return "(sem render pra validar)"
    img = base64.b64encode(iso_path.read_bytes()).decode()
    prompt = (
        "Render isometrico de um apartamento (paredes cinza-escuro). Na sala "
        "(area azul-clara, lado esquerdo) ha um SOFA cinza-escuro. Avalie SO o "
        "sofa, curto:\n"
        "1) VERTICAL: em pe na pose natural (assento pra cima, pes no chao) ou "
        "tombado/de cabeca pra baixo/de lado?\n"
        "2) APOIO: no chao dentro do comodo, ou flutuando/afundado/atravessando "
        "parede?\n3) DIRECAO: pra que lado a frente aponta?\n"
        "Termine com: VEREDITO=OK ou VEREDITO=PROBLEMA."
    )
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps({"model": model, "prompt": prompt, "images": [img],
                         "stream": False, "options": {"temperature": 0.1}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read()).get("response", "(vazio)").strip()
    except Exception as e:
        return f"(gate de visao offline: {e})"


def main():
    # variantes a gerar (uma planta por sofa). cx,cy resolvidos por comodo.
    sofas = [
        {"file": "kivik_sofa.skp", "out": "planta_74_v2.skp", "name": "sofa_kivik",
         "room": "r002", "rot": 0, "scale": 1.0},
        {"file": "tufted_sofa.skp", "out": "planta_74_v3.skp", "name": "sofa_tufted",
         "room": "r002", "rot": 0, "scale": 1.0},
    ]
    cx, cy = room_center_su("r002")
    print(f"[furnish] sala r002 centro -> SU ({cx:.1f}, {cy:.1f}) in")

    jobs = []
    for s in sofas:
        jobs.append({
            "component": str(FURNITURE / s["file"]).replace("\\", "/"),
            "out": str(OUT_DIR / s["out"]).replace("\\", "/"),
            "cx": cx, "cy": cy, "rot": s["rot"], "scale": s["scale"], "name": s["name"],
        })
        outp = OUT_DIR / s["out"]
        if outp.exists():
            outp.unlink()

    log_path = OUT_DIR / "furnish_log.txt"
    if log_path.exists():
        log_path.unlink()

    placements_path = OUT_DIR / "furnish_placements.json"
    if placements_path.exists():
        placements_path.unlink()

    env = os.environ.copy()
    env["FURNISH_JOBS"] = json.dumps(jobs)
    env["FURNISH_LOG"] = str(log_path).replace("\\", "/")
    env["FURNISH_PLACEMENTS"] = str(placements_path).replace("\\", "/")

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"],
                   capture_output=True)
    time.sleep(1)

    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(ROOT / "tools/furnish_plan.rb")]
    print(f"[furnish] launching SU with {len(jobs)} job(s)...")
    subprocess.Popen(cmd, env=env,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))

    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)

    subprocess.run(["taskkill", "/F", "/IM", "SketchUp.exe"], capture_output=True)

    if log_path.exists():
        print("[furnish] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[furnish] TIMEOUT — no log produced (SU may not have run the script)")
        sys.exit(1)

    # === GATE DETERMINISTICO de dimensoes (confiavel) ===
    # faixas plausiveis pra SOFA (m): maior horizontal = largura, menor = prof.
    print("\n[furnish] === DIMENSION GATE (deterministico) ===")
    if placements_path.exists():
        placements = json.loads(placements_path.read_text("utf-8"))
        for p in placements:
            horiz = sorted([p["w_m"], p["d_m"]], reverse=True)
            largura, prof, alt = horiz[0], horiz[1], p["h_m"]
            checks = {
                "largura 1.2-3.6m": 1.2 <= largura <= 3.6,
                "prof 0.7-1.8m": 0.7 <= prof <= 1.8,
                "altura 0.55-1.15m": 0.55 <= alt <= 1.15,
            }
            ok = all(checks.values())
            sc = f" (auto-scaled x{p['scale']})" if p.get("autoscaled") else ""
            print(f"  {p['out']:20} {largura:.2f}x{prof:.2f}x{alt:.2f}m{sc} -> "
                  f"{'PASS' if ok else 'FAIL'}")
            if not ok:
                for k, v in checks.items():
                    if not v:
                        print(f"       ✗ {k}")
    else:
        print("  (sem placements json)")

    # === GATE DE VISAO (auxiliar — qwen2.5vl; pega orientacao grosseira) ===
    print("\n[furnish] === ORIENTATION GATE (visao qwen2.5vl, AUXILIAR) ===")
    for s in sofas:
        iso = OUT_DIR / s["out"].replace(".skp", "_iso.png")
        verdict = orient_gate(iso)
        last = [ln for ln in verdict.splitlines() if "VEREDITO" in ln.upper()]
        print(f"  {s['out']:20} {last[0].strip() if last else verdict[:60]}")


if __name__ == "__main__":
    main()
