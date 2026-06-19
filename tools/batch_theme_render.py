"""batch_theme_render.py — BATCH_THEME_RENDER.

Aplica N theme presets na MESMA cozinha base (skin-swap, geometria CONGELADA), renderiza o hero
de cada, monta a biblioteca A/B/C/D e emite um relatório com os 4 gates + ranking
(mais vendável / autoral / seguro p/ manutenção / arriscado).

Pinterest = intenção visual (hipótese). PDF + gates = verdade espacial. Só pele/luz/câmera.

Uso:
  PT_TO_M=0.0259 .venv/Scripts/python.exe tools/batch_theme_render.py        # usa PNGs existentes
  BATCH_RENDER=1 PT_TO_M=0.0259 .venv/Scripts/python.exe tools/batch_theme_render.py  # re-renderiza
"""
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
FDIR = ROOT / "artifacts/planta_74/furnished/kitchen_angles"
RENDERS = ROOT / "artifacts/reference_lab/renders"
DRIVER = ROOT / ".claude/scratch/kitchen_vray.py"
VENV = ROOT / ".venv/Scripts/python.exe"

# câmera/crop/rig comuns (token hero_camera_compact_kitchen) — idênticos p/ todos os temas
CAM = {"VRAY_EYE": "189,634,52", "VRAY_TARGET": "72,651,45", "VRAY_FOV": "47",
       "CROP_X0": "0.09", "CROP_X1": "0.93", "CROP_Y0": "0.12", "CROP_Y1": "0.73",
       "VRAY_ISOLATE": "COZINHA", "VRAY_ALL_PORCELAIN": "1", "FNUM": "5.6", "SHUTTER": "110",
       "KEY_X": "186", "KEY_Y": "574", "KEY_Z": "114", "SUN_SIZE": "3", "NOISE": "0.013", "SHADE": "14"}

# registro dos temas: pele via KITCHEN_THEME + exposição própria + veredito dos gates (curado de GPT/Felipe)
THEMES = [
    {"id": "01_warm_compact_premium", "theme": "", "out": "cozinha_vray_hero.png",
     "role": "default seguro / vendável / amplo",
     "env": {"ISO": "78", "SKY": "0.07", "SUN": "0.18", "BURN": "0.72", "KEY_INT": "70", "FILL2_INT": "15", "LED_INT": "9"},
     "gpt": "PASS de pele", "gates": {"theme_fit": "PASS", "ergonomics": "PASS", "maintenance": "PASS", "buildability": "PASS"}},
    {"id": "03_hotel_boutique_warm_luxury", "theme": "hotel_boutique", "out": "cozinha_vray_hero_boutique.png",
     "role": "premium equilibrado / refinado",
     "env": {"ISO": "84", "SKY": "0.10", "SUN": "0.18", "BURN": "0.74", "KEY_INT": "72", "FILL2_INT": "16", "LED_INT": "15"},
     "gpt": "PASS", "gates": {"theme_fit": "PASS", "ergonomics": "PASS", "maintenance": "PASS", "buildability": "WARN (bronze/champagne custa)"}},
    {"id": "02_dark_walnut_moody", "theme": "dark_walnut", "out": "cozinha_vray_hero_dark.png",
     "role": "variante autoral / noturna / impacto",
     "env": {"ISO": "110", "SKY": "0.09", "SUN": "0.18", "BURN": "0.78", "KEY_INT": "86", "FILL2_INT": "18", "LED_INT": "30"},
     "gpt": "PASS variante", "gates": {"theme_fit": "PASS", "ergonomics": "PASS", "maintenance": "WARN (madeira na zona molhada)", "buildability": "PASS"}},
]

# rankings (curado dos vereditos GPT + gates)
RANKING = {
    "mais vendável": "01_warm_compact_premium",
    "mais autoral": "02_dark_walnut_moody",
    "mais seguro p/ manutenção": "01_warm_compact_premium",
    "mais arriscado": "02_dark_walnut_moody (madeira molhada + risco caverna)",
}


def render_theme(t):
    env = dict(os.environ)
    env.update(CAM)
    env.update(t["env"])
    env.setdefault("PT_TO_M", "0.0259")
    if t["theme"]:
        env["KITCHEN_THEME"] = t["theme"]
    else:
        env.pop("KITCHEN_THEME", None)
    subprocess.run([str(VENV), str(DRIVER), t["out"]], env=env, timeout=460, check=False)


def build_montage(present):
    pad, lbl, cw = 14, 32, 400
    ims = []
    for t in present:
        im = Image.open(FDIR / t["out"]).convert("RGB")
        im.thumbnail((cw, 360))
        ims.append((im, t["id"]))
    w = len(ims) * cw + (len(ims) + 1) * pad
    h = pad + max(i.height for i, _ in ims) + lbl + pad
    sh = Image.new("RGB", (w, h), (238, 239, 241))
    dr = ImageDraw.Draw(sh)
    x = pad
    for im, name in ims:
        dr.rectangle([x, pad, x + cw, pad + lbl], fill=(24, 26, 32))
        dr.text((x + 10, pad + 8), name, fill=(245, 246, 248))
        sh.paste(im, (x, pad + lbl))
        x += cw + pad
    RENDERS.mkdir(parents=True, exist_ok=True)
    out = RENDERS / "kitchen_themes_ABC.png"
    sh.save(out, quality=92)
    return out


def write_report(present, montage):
    lines = ["# BATCH_THEME_RENDER — relatório", "",
             "> Mesma geometria/planta/layout PDF. Skin-swap. Pinterest=hipótese, gates=verdade.", "",
             f"Montagem: `{montage.relative_to(ROOT)}`", "",
             "## Temas + 4 gates", "",
             "| tema | papel | GPT | theme_fit | ergonomics | maintenance | buildability |",
             "|---|---|---|---|---|---|---|"]
    for t in present:
        g = t["gates"]
        lines.append(f"| {t['id']} | {t['role']} | {t['gpt']} | {g['theme_fit']} | "
                     f"{g['ergonomics']} | {g['maintenance']} | {g['buildability']} |")
    lines += ["", "## Ranking", ""]
    for k, v in RANKING.items():
        lines.append(f"- **{k}:** {v}")
    out = RENDERS / "THEME_RANKING.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main():
    do_render = os.environ.get("BATCH_RENDER") == "1"
    present = []
    for t in THEMES:
        png = FDIR / t["out"]
        if do_render or not png.exists():
            print(f"render {t['id']} (theme={t['theme'] or 'clara'})")
            render_theme(t)
        if png.exists():
            present.append(t)
        else:
            print(f"SKIP {t['id']} (sem render)")
    montage = build_montage(present)
    report = write_report(present, montage)
    print(f"OK montagem={montage.name} relatorio={report.name} temas={len(present)}")


if __name__ == "__main__":
    main()
