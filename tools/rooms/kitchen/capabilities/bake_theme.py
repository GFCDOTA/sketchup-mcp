"""bake_theme_skp.py — gera um .skp da planta com a cozinha BAKEADA num tema (cor+textura).
Copia o furnished base, abre no SketchUp headless, roda recolor_kitchen_theme.rb, salva o
.skp tematizado em artifacts/planta_74/furnished/. NAO toca o base (cozinha clara aprovada).
Uso: KITCHEN_THEME=black_wood_gold .venv/Scripts/python.exe .claude/scratch/bake_theme_skp.py
"""
import hashlib
import os
import shutil
import time
from pathlib import Path
from tools.sketchup.legacy_process import launch_owned, close_owned

ROOT = Path(__file__).resolve().parents[4]   # raiz do repo (o original usava parents[2] = apps/, caminho morto)
SU = Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe")
RB = ROOT / "tools/rooms/kitchen/capabilities/ruby/recolor_kitchen_theme.rb"
TEX = ROOT / "assets/textures/procedural"
BASE = ROOT / "artifacts/planta_74/furnished/planta_74_furnished.skp"
SCRATCH = ROOT / ".claude/scratch"

def main() -> None:
    theme = os.environ.get("KITCHEN_THEME", "black_wood_gold")
    out = ROOT / f"artifacts/planta_74/furnished/planta_74_furnished_{theme}.skp"
    copy = SCRATCH / "bake_copy.skp"
    log = SCRATCH / "bake_log.txt"
    for p in (copy, log):
        if p.exists():
            p.unlink()
    shutil.copy2(BASE, copy)
    base_hash = hashlib.sha256(BASE.read_bytes()).hexdigest()

    env = dict(os.environ)
    env.update({
        "KITCHEN_THEME": theme,
        "THEME_OUT": str(out).replace("\\", "/"),
        "VRAY_TEX_DIR": str(TEX),
        "RECOLOR_LOG": str(log).replace("\\", "/"),
    })
    pid = launch_owned(SU, copy, RB, env=env)
    deadline = time.time() + 150
    while time.time() < deadline:
        if log.exists():
            time.sleep(2)
            break
        time.sleep(2)
    close_owned(pid)
    time.sleep(1)
    intact = hashlib.sha256(BASE.read_bytes()).hexdigest() == base_hash
    print(log.read_text("utf-8", "ignore") if log.exists() else "(no log)")
    print(f"base_intact={intact}  OUT_exists={out.exists()}  size={out.stat().st_size if out.exists() else 0}")
    print(out)


if __name__ == "__main__":
    main()
