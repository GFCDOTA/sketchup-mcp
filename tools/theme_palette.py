"""theme_palette.py — o TEMA pinta os móveis no render SU-free do sweep.

Causa-raiz (ciclo de evolução 2026-07-12, notas 2/10 unânimes do GPT):
1. Os templates de layout (seeds L1/L2) herdam cores de DEBUG do
   place_layout_skp.KIND_RGB — sofa_3 azul puro (21,101,192), rack_tv roxo
   (106,27,154), mesa_centro laranja (239,108,0). O GPT flagra em todo card:
   "saturated primary (purple/orange/blue) placeholder colors".
2. O tema (black_wood_gold / dark_walnut / warm_compact) só afetava o caminho
   V-Ray da cozinha (kitchen_theme_env) — no su-free os 3 temas saíam com
   pixels IDÊNTICOS: "named palette is not reflected in pixels; material-name-
   to-color binding is not being applied".

Este módulo é o binding que faltava: paleta determinística por tema, aplicada
por KIND aos boxes ANTES do render. As paletas derivam dos presets curados em
artifacts/reference_lab/themes/*.json (ex.: cabinets "preto fosco ~[28,28,30]"
no BLACK_WOOD_GOLD). Não toca os builders (KIND_RGB deles fica; os testes que
os pinam continuam válidos) — o sweep é quem traduz intenção→pixel.

Regras:
- kind mapeado num grupo semântico → cor do grupo NO TEMA;
- kind NÃO mapeado mas com cor placeholder-saturada → neutro do tema (nunca
  deixa primário puro passar);
- whitelist (louça/colchão/vidro/inox/led/pedra) NUNCA recolore — identidade
  própria independe de tema;
- tema desconhecido → só a regra anti-placeholder (degrada honesto, sem crash).
Puro e determinístico: mesma entrada → mesma saída.
"""
from __future__ import annotations

# grupos semânticos por kind (vocabulário real do collect_boxes + templates)
UPHOLSTERY = {"sofa_3", "sofa_2", "seat", "seat_cushion", "back_cushion", "back",
              "arm", "cabeceira", "manta", "bench", "banheiro_cadeira_bar"}
WOOD_CASE = {"rack_tv", "mesa_centro", "corpo", "porta", "gaveta", "front", "top",
             "base", "tampo", "gabinete", "estrado", "niche", "rodape", "saia",
             "decor_board", "kc_niche_wood", "bed", "wardrobe", "nightstand",
             "dresser", "pe", "foot"}
KITCHEN_CABINETRY = {"kc_corpo", "kc_porta", "kc_gaveta", "kc_corpo_sup",
                     "kc_porta_sup", "kc_filler", "kc_soculo"}
METAL = {"puxador", "kc_puxador", "leg", "kc_torneira", "kc_gola"}
RUG = {"rug", "tapete"}
# identidade própria — nunca recolorir (louça, colchão, vidro, inox, LED, pedra)
KEEP = {"cuba", "vaso", "espelho", "colchao", "travesseiro", "kc_led",
        "kc_geladeira", "kc_inox", "kc_backsplash", "kc_tampo", "kc_cuba",
        "kc_vidro", "kc_ralo", "kc_boca", "bancada_banho", "decor_vaso", "filler"}

# paletas derivadas dos presets artifacts/reference_lab/themes/*.json
THEMES: dict[str, dict[str, list[int]]] = {
    # WARM_COMPACT_PREMIUM: greige + madeira média quente (o baseline neutro)
    "warm_compact": {
        "upholstery": [168, 158, 146],   # greige
        "wood": [122, 98, 70],           # madeira média quente
        "cabinetry": [195, 171, 141],    # como o kitchen builder já faz
        "metal": [64, 64, 68],           # grafite discreto
        "rug": [201, 185, 160],
        "neutral": [150, 142, 130],
    },
    # BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE: "preto fosco ~[28,28,30] + madeira
    # natural quente (acento) + dourado/bronze SUTIL"
    "black_wood_gold": {
        "upholstery": [48, 48, 52],      # charcoal
        "wood": [107, 74, 47],           # madeira quente (acento)
        "cabinetry": [28, 28, 30],       # preto fosco do preset
        "metal": [176, 141, 66],         # dourado discreto
        "rug": [56, 54, 52],
        "neutral": [40, 40, 43],
    },
    # DARK_WALNUT_MOODY_PREMIUM: nogueira escura rica + greige escuro + bronze
    "dark_walnut": {
        "upholstery": [110, 102, 92],    # greige escuro
        "wood": [72, 48, 33],            # nogueira
        "cabinetry": [82, 56, 38],
        "metal": [118, 88, 58],          # bronze
        "rug": [140, 128, 114],
        "neutral": [96, 84, 72],
    },
}


def _is_placeholder(rgb: list[int] | tuple[int, ...]) -> bool:
    """Cor de debug primária (o azul/roxo/laranja dos KIND_RGB antigos): spread
    alto E um canal dominando — nunca é material de interiores plausível."""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    spread = max(r, g, b) - min(r, g, b)
    return spread > 90


def _role_of(kind: str) -> str | None:
    if kind in KITCHEN_CABINETRY:
        return "cabinetry"
    if kind in UPHOLSTERY:
        return "upholstery"
    if kind in WOOD_CASE:
        return "wood"
    if kind in METAL:
        return "metal"
    if kind in RUG:
        return "rug"
    return None


def apply_theme_palette(boxes: list[dict], theme: str | None) -> list[dict]:
    """Devolve boxes com rgb re-mapeado pela paleta do tema (cópia rasa por box;
    a lista original não muta). Tema fora de THEMES → só anti-placeholder."""
    pal = THEMES.get(str(theme or ""))
    out: list[dict] = []
    for b in boxes:
        kind = str(b.get("kind", ""))
        rgb = list(b.get("rgb") or (120, 120, 120))
        nb = dict(b)
        if kind in KEEP:
            out.append(nb)
            continue
        role = _role_of(kind)
        if pal is not None and role is not None:
            nb["rgb"] = list(pal[role])
        elif _is_placeholder(rgb):
            nb["rgb"] = list((pal or THEMES["warm_compact"])["neutral"])
        out.append(nb)
    return out
