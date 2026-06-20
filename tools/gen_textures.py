"""gen_textures.py — gera TEXTURAS procedurais (madeira com grao, tecido com trama) via
numpy/PIL, p/ os materiais V-Ray dos moveis. Auto-contido (sem assets externos/licenca).
Saida versionada em assets/textures/procedural/. Aplicadas no vray_export.rb (SU material.texture
-> V-Ray traduz com UV).

Uso: python tools/gen_textures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/textures/procedural"
SZ = 512


def _value_noise(h, w, scale, rng):
    """Noise suave (random upsample bilinear)."""
    sh, sw = max(2, h // scale), max(2, w // scale)
    small = (rng.random((sh, sw)) * 255).astype("uint8")
    return np.asarray(Image.fromarray(small).resize((w, h), Image.BILINEAR), dtype=float) / 255.0


def wood(c_base, c_dark, seed, rings=13):
    rng = np.random.default_rng(seed)
    warp = _value_noise(SZ, SZ, 48, rng) * 6.0 + _value_noise(SZ, SZ, 14, rng) * 1.6
    x = np.linspace(0, 1, SZ)[None, :].repeat(SZ, 0)
    grain = (np.sin((x * rings + warp) * np.pi) * 0.5 + 0.5) ** 1.4   # aneis/veios
    fine = _value_noise(SZ, SZ, 3, rng) * 0.18                        # grao fino
    t = np.clip(grain * 0.82 + fine, 0, 1)
    out = np.stack([c_dark[i] + (c_base[i] - c_dark[i]) * t for i in range(3)], -1)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def fabric(c_base, seed):
    rng = np.random.default_rng(seed)
    x = np.arange(SZ)[None, :].repeat(SZ, 0)
    y = np.arange(SZ)[:, None].repeat(SZ, 1)
    weave = np.sin(x * np.pi / 2.5) * np.sin(y * np.pi / 2.5)         # trama fina over/under
    n = rng.normal(0, 1, (SZ, SZ))
    n = np.asarray(Image.fromarray(((n - n.min()) / (np.ptp(n)) * 255).astype("uint8"))
                   .filter(ImageFilter.GaussianBlur(1)), dtype=float) / 255.0 - 0.5
    t = weave * 0.05 + n * 0.10
    out = np.stack([np.clip(c_base[i] + t * 42, 0, 255) for i in range(3)], -1)
    return Image.fromarray(out.astype("uint8"))


def linen(c_base, seed, period=3.2, amp=46):
    """Linho da ROUPA DE CAMA: trama FINA e SUTIL (GPT reprovou versao forte: 'grid/xadrez, procedural
    demais'). Weave MULTIPLICATIVO (ponto de tecido, nao listras cruzadas=grid) de baixa amplitude +
    slub dominante (irregularidade natural do fio) p/ quebrar a repeticao. Mais textura que o sofa,
    porem natural. Base levemente menos branca p/ segurar tom sob luz."""
    rng = np.random.default_rng(seed)
    x = np.arange(SZ)[None, :].repeat(SZ, 0)
    y = np.arange(SZ)[:, None].repeat(SZ, 1)
    weave = np.sin(x * np.pi / period) * np.sin(y * np.pi / period)   # ponto multiplicativo (sem grid)
    slub = _value_noise(SZ, SZ, 7, rng) - 0.5                         # fio irregular domina -> natural
    t = weave * 0.20 + slub * 0.45
    out = np.stack([np.clip(c_base[i] + t * amp, 0, 255) for i in range(3)], -1)
    return Image.fromarray(out.astype("uint8"))


def concrete(c_base, seed):
    """Concreto aparente: cinza FRIO com mottle multi-escala suave + manchas leves,
    fosco e SEM grao direcional. Tile grande (parede ~2-2.5m). Industrial feature wall."""
    rng = np.random.default_rng(seed)
    mottle = ((_value_noise(SZ, SZ, 64, rng) - 0.5) * 0.7
              + (_value_noise(SZ, SZ, 18, rng) - 0.5) * 0.4
              + (_value_noise(SZ, SZ, 5, rng) - 0.5) * 0.15)
    t = np.clip(mottle, -0.5, 0.5)
    out = np.stack([np.clip(c_base[i] + t * 32, 0, 255) for i in range(3)], -1)
    return Image.fromarray(out.astype("uint8"))


def brick(c_base, c_mortar, seed, rows=9, cols=4):
    """Tijolinho running-bond: tijolos + juntas de argamassa, leve variacao por tijolo
    (alternativa de parede de acento). Tile grande (parede)."""
    rng = np.random.default_rng(seed)
    img = np.empty((SZ, SZ, 3), dtype=float)
    img[:] = c_mortar
    bh = SZ / rows
    mortar = max(2, int(bh * 0.12))
    bw = SZ / cols
    for r in range(rows):
        y0, y1 = int(r * bh) + mortar, int((r + 1) * bh) - mortar
        offset = (bw / 2.0) if (r % 2) else 0.0
        x = -offset
        while x < SZ:
            x0, x1 = int(x) + mortar, int(x + bw) - mortar
            shade = 1.0 + (rng.random() - 0.5) * 0.18
            col = [min(255.0, max(0.0, c_base[i] * shade)) for i in range(3)]
            xa, xb, ya, yb = max(0, x0), min(SZ, x1), max(0, y0), min(SZ, y1)
            if xb > xa and yb > ya:
                img[ya:yb, xa:xb] = col
            x += bw
    n = (rng.random((SZ, SZ)) - 0.5)[..., None] * 10.0       # grao fino
    return Image.fromarray(np.clip(img + n, 0, 255).astype("uint8"))


def metal_matte(c_base, seed):
    """Metal preto FOSCO: quase preto, micro-grao baixo, sem brilho direcional
    (moldura/estrutura industrial; distinto do MAT_METAL escovado)."""
    rng = np.random.default_rng(seed)
    g = _value_noise(SZ, SZ, 4, rng) - 0.5
    out = np.stack([np.clip(c_base[i] + g * 16, 0, 255) for i in range(3)], -1)
    return Image.fromarray(out.astype("uint8"))


def porcelain(c_base, seed, tiles=2):
    """Porcelanato grande-formato: base clara quase uniforme + veias MARMORIZADAS
    suaves + junta de assentamento discreta (grade grande). Pratico p/ cozinha/banho
    (facil de limpar). Tile grande no V-Ray."""
    rng = np.random.default_rng(seed)
    warp = _value_noise(SZ, SZ, 70, rng) * 3.0
    veins = np.abs(np.sin((_value_noise(SZ, SZ, 28, rng) * 4 + warp) * np.pi)) ** 3
    micro = _value_noise(SZ, SZ, 2, rng) - 0.5
    t = -veins * 0.16 + micro * 0.05                      # veias levemente mais escuras
    out = np.stack([np.clip(c_base[i] + t * 46, 0, 255) for i in range(3)], -1)
    seam = SZ // tiles                                    # junta grande discreta
    mask = (np.arange(SZ) % seam) < 2
    out[mask] *= 0.93
    out[:, mask] *= 0.93
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def stone(c_base, seed):
    """Pedra/quartzo de bancada: base cinza media + GRAO fino (sal-e-pimenta) +
    veias suaves. Lisa, fosca-acetinada. Pratico (sem rejunte) p/ bancada de cozinha."""
    rng = np.random.default_rng(seed)
    speck = rng.random((SZ, SZ)) - 0.5                    # grao fino do quartzo
    vein = _value_noise(SZ, SZ, 55, rng) - 0.5
    t = speck * 0.10 + vein * 0.13
    out = np.stack([np.clip(c_base[i] + t * 48, 0, 255) for i in range(3)], -1)
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def wood_floor(c_base, c_dark, seed, planks=5, rings=7):
    """Piso de madeira: tabuas longas (veio vertical) + linhas de junta horizontais entre tabuas.
    Tom quente medio, escala grande (tile grande no V-Ray). Conserta a 'faixa cinza' do piso pastel
    chapado em TODO comodo (material floor_<room_id>). NAO afeta parede/movel (materiais distintos)."""
    rng = np.random.default_rng(seed)
    warp = _value_noise(SZ, SZ, 40, rng) * 5.0 + _value_noise(SZ, SZ, 12, rng) * 1.4
    y = np.linspace(0, 1, SZ)[:, None].repeat(SZ, 1)            # veio corre na vertical
    grain = (np.sin((y * rings + warp) * np.pi) * 0.5 + 0.5) ** 1.4
    fine = _value_noise(SZ, SZ, 3, rng) * 0.16
    t = np.clip(grain * 0.8 + fine, 0, 1)
    out = np.stack([c_dark[i] + (c_base[i] - c_dark[i]) * t for i in range(3)], -1)
    seam = (SZ // planks)                                       # juntas entre tabuas
    mask = (np.arange(SZ) % seam) < 2                           # 2px de junta (suave, nao preta)
    out[mask] *= 0.62
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


TEXTURES = {
    "wood_medium.png": lambda: wood((150, 108, 70), (96, 66, 42), 11),
    "wood_dark.png": lambda: wood((92, 66, 46), (52, 36, 24), 22),
    "fabric_light.png": lambda: fabric((192, 182, 164), 33),
    "fabric_accent.png": lambda: fabric((174, 144, 114), 44),
    "fabric_linen.png": lambda: linen((186, 178, 163), 55),   # roupa de cama (bedding-only)
    "wood_floor.png": lambda: wood_floor((194, 166, 124), (154, 126, 88), 77),   # piso carvalho CLARO (floor_*): reflete luz, nao escurece o render
    # ---- INDUSTRIAL (slice 1): concreto, tijolinho, tecido chumbo, metal preto fosco ----
    "concrete.png": lambda: concrete((165, 162, 158), 101),
    "brick.png": lambda: brick((150, 92, 70), (148, 144, 138), 102),
    "fabric_charcoal.png": lambda: fabric((60, 62, 66), 103),     # reusa fabric() parametrizada
    "metal_black_matte.png": lambda: metal_matte((30, 30, 32), 104),
    # ---- praticos (cozinha/banho): porcelanato claro + pedra de bancada ----
    "porcelain.png": lambda: porcelain((224, 222, 218), 105),
    "stone_counter.png": lambda: stone((176, 174, 170), 106),
}


# ---- override por TEXTURA PBR REAL (CC0 Poly Haven) quando presente em assets/textures/pbr/ ----
# (src jpg, png de saida, mult de cor|None). Mantém o procedural como fallback se o jpg sumir.
PBR = ROOT / "assets/textures/pbr"
PBR_MAP = [
    ("pbr_concrete.jpg", "concrete.png", None),                         # concreto board-formed (parede TV)
    ("pbr_wood_floor.jpg", "wood_floor.png", None),                     # piso madeira real
    ("pbr_wood_floor.jpg", "wood_medium.png", None),
    ("pbr_wood_floor.jpg", "wood_dark.png", (0.62, 0.58, 0.55)),        # madeira escura (rack/mesa)
    ("pbr_fabric.jpg", "fabric_charcoal.png", (0.34, 0.37, 0.40)),      # trama real escurecida p/ charcoal
    ("pbr_granite.jpg", "porcelain.png", None),                         # granito (piso area molhada)
]


def _apply_pbr_overrides():
    if not PBR.is_dir():
        return 0
    n = 0
    for src, dst, mult in PBR_MAP:
        p = PBR / src
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB").resize((SZ, SZ))
        if mult:
            a = np.clip(np.asarray(im, dtype=float) * np.asarray(mult), 0, 255)
            im = Image.fromarray(a.astype("uint8"))
        im.save(OUT / dst)
        n += 1
        print(f"  PBR: {dst} <- {src}{' (escurecido)' if mult else ''}")
    return n


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in TEXTURES.items():
        img = fn()
        img.save(OUT / name)
        print(f"  {name} {img.size}")
    n = _apply_pbr_overrides()
    print(f"-> {OUT.relative_to(ROOT)}  ({n} texturas PBR reais sobrepostas)")


if __name__ == "__main__":
    main()
    sys.exit(0)
