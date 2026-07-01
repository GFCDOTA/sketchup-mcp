"""style_spec.py — gramatica de ESTILO de interior (tokens reusaveis): a camada que
FALTAVA. Mapeia `kind -> rgb` (e textura) por ESTILO e aplica nos boxes em tempo de
coleta, SEM reescrever builder. Espelha o programa de CLASSE de movel (dataclass +
tabela de tokens + gate). Slice 1 = "industrial" compacto (alvo: foto-referencia do
Felipe). Felipe 2026-06-18.

Cor entra por `apply_style` (reescreve b['rgb'] por kind = fonte UNICA do material SU
`ph_<kind>`, place_layout_skp.rb:113), rodando DENTRO da coleta antes do dump
LAYOUT_BOXES. Textura/BRDF entram no render (vray_export.rb / tweak_vrscene.py gated
por VRAY_STYLE). `texture_map_for` documenta o mapa que o .rb usa (mantido em sincronia).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StyleSpec:
    name: str
    kind_rgb: dict          # kind -> (r,g,b)   override de cor por papel
    kind_texture: dict      # kind -> textura png (espelha o tex_map gated do .rb)
    light_kelvin: int = 2700
    fill_color: tuple = (1.0, 0.82, 0.6)   # fill quente (~2700K)
    floor: str = "polished_concrete"
    must_style: tuple = ()  # kinds que TEM que ser recoloridos (checado no gate)
    # kind -> {finish,roughness,metalness,tile_in,cite}: leitura de REFLEXO por papel,
    # destilada de references/materials/*.md (cada entrada CITA a faixa da .md, sem inventar).
    # Contrato unico do BRDF: hoje alimenta o TILE do path interativo (place_layout_skp.rb via
    # LAYOUT_TILE_MAP) e documenta o reflexo p/ o V-Ray consumir sem numeros hardcoded no futuro
    # (refactor gated FORA desta FP p/ nao regredir o render PASS).
    kind_finish: dict = field(default_factory=dict)
    # (familia_de_modulo, kind) -> png / finish. FP-037: resolve material por MODULO quando o kind
    # e generico/sobrecarregado (base/top/front aparecem em rack E sofa). Chave-tupla so vive no
    # Python (nunca vai pro JSON); a resolucao anexa mat_name/tex_png/tile_in por box.
    module_kind_texture: dict = field(default_factory=dict)
    module_kind_finish: dict = field(default_factory=dict)


# ---- INDUSTRIAL compacto: sofa chumbo, rack baixo madeira escura, parede de concreto,
#      tapete cinza escuro, luz quente. (rack/mesa em peca unica aqui; black+wood
#      multi-part = slice 2 quando rack_class for wired). ----
_INDUSTRIAL_RGB = {
    "seat_cushion": (64, 66, 70), "back_cushion": (56, 58, 62), "arm": (60, 62, 66),
    "base": (34, 35, 38), "foot": (24, 24, 26),                 # sofa charcoal + base/pes escuros
    "rack_tv": (74, 56, 42),                                    # rack madeira escura (single-box)
    "mesa_centro": (60, 46, 34),                                # mesa de centro madeira escura
    "tapete": (54, 54, 58),                                     # tapete cinza escuro
    "parede_concreto": (165, 162, 158),                         # concreto aparente atras da TV
    "frame": (38, 38, 40),                                      # moldura do quadro = metal preto
}
_INDUSTRIAL_TEX = {
    "parede_concreto": "concrete.png",
    "rack_tv": "wood_dark.png", "mesa_centro": "wood_dark.png",
    "seat_cushion": "fabric_charcoal.png", "back_cushion": "fabric_charcoal.png",
    "arm": "fabric_charcoal.png", "tapete": "fabric_charcoal.png",
    "frame": "metal_black_matte.png",
}

# ---- MODERN_WARM: conecta a SALA à cozinha planejada (golden sample). Marcenaria em
#      nogueira clara, painel/TV-wall off-white, pernas/detalhes grafite, sofá tecido
#      bege claro. Espelha a paleta do _KC da cozinha. Felipe 2026-06-19. ----
_WALNUT = (156, 123, 86)         # nogueira clara (= base da cozinha)
_OFFWHITE = (228, 224, 214)      # off-white/fendi (= aéreo da cozinha)
_GRAPHITE = (44, 45, 50)         # grafite (= sóculo/puxador da cozinha)
_MODERN_WARM_RGB = {
    # sofá: tecido bege claro + base/pés grafite
    "seat_cushion": (184, 176, 162), "back_cushion": (178, 170, 156), "arm": (184, 176, 162),
    "base": _GRAPHITE, "foot": _GRAPHITE, "leg": _GRAPHITE, "saia": _GRAPHITE,
    "shelf_bracket": _GRAPHITE,
    # marcenaria (rack/mesas/prateleira/topos) = nogueira clara
    "rack_tv": _WALNUT, "mesa_centro": _WALNUT, "top": _WALNUT, "front": _WALNUT,
    "shelf_plank": _WALNUT, "niche": (120, 95, 66),
    # painel atrás da TV = off-white (ex-concreto)
    "parede_concreto": _OFFWHITE,
    # cadeiras grafite (detalhe preto) + moldura preta
    "seat": (70, 72, 78), "back": _GRAPHITE, "frame": (38, 38, 40),
    # tapete bege quente
    "tapete": (180, 172, 158),
}
_MODERN_WARM_TEX = {
    # nogueira clara -> wood_medium (wood.png/fabric.png NAO existem em assets/textures/procedural;
    # referencia-los deixava o path interativo cair no fallback chapado). painel off-white = LACA
    # LISA -> SEM textura (so cor+finish fosco); nao herda o wood_floor antigo (era incoerente).
    "rack_tv": "wood_medium.png", "mesa_centro": "wood_medium.png", "top": "wood_medium.png",
    "shelf_plank": "wood_medium.png",
    "seat_cushion": "fabric_light.png", "back_cushion": "fabric_light.png", "arm": "fabric_light.png",
}

# ---- FINISH / BRDF por PAPEL (destilado de references/materials/*.md; cada token CITA a .md).
# tile_in = tamanho fisico do tile (in) p/ o path interativo; parede ~2m pede tile grande (80).
# fabric NAO ganha token: e o mais fosco/difuso da lista, cor+trama bastam (sem reflexo p/ ler).
_FIN_WOOD_MATTE = {"finish": "matte", "roughness": 0.60, "metalness": 0.0, "tile_in": 40,
                   "cite": "wood.md: manter fosco/acetinado; verniz brilhante data (sem gloss)"}
_FIN_GRAPHITE = {"finish": "matte", "roughness": 0.70, "metalness": 0.40, "tile_in": 40,
                 "cite": "metal.md: grafite fosco roughness 0.6-0.8, metalness medio"}
_FIN_BLACK_MATTE = {"finish": "matte", "roughness": 0.80, "metalness": 0.30, "tile_in": 40,
                    "cite": "metal.md: preto fosco roughness alta, reflexo minimo"}
_FIN_CONCRETE = {"finish": "matte", "roughness": 0.85, "metalness": 0.0, "tile_in": 80,
                 "cite": "stone.md: mineral fosco, roughness alta, reflexo baixo (parede ~2m)"}
_FIN_LACQUER_MATTE = {"finish": "matte", "roughness": 0.60, "metalness": 0.0, "tile_in": 80,
                      "cite": "lacquer.md: laca fosca ZERO brilho, absorve luz"}

_INDUSTRIAL_FIN = {
    "rack_tv": _FIN_WOOD_MATTE, "mesa_centro": _FIN_WOOD_MATTE,   # madeira escura fosca
    "base": _FIN_GRAPHITE, "foot": _FIN_GRAPHITE,                 # base/pes = grafite fosco
    "frame": _FIN_BLACK_MATTE,                                    # moldura = metal preto fosco
    "parede_concreto": _FIN_CONCRETE,                             # concreto aparente (tile 80)
}
_MODERN_WARM_FIN = {
    "rack_tv": _FIN_WOOD_MATTE, "mesa_centro": _FIN_WOOD_MATTE, "top": _FIN_WOOD_MATTE,
    "shelf_plank": _FIN_WOOD_MATTE, "niche": _FIN_WOOD_MATTE,
    "base": _FIN_GRAPHITE, "foot": _FIN_GRAPHITE, "leg": _FIN_GRAPHITE, "saia": _FIN_GRAPHITE,
    "shelf_bracket": _FIN_GRAPHITE, "back": _FIN_GRAPHITE, "frame": _FIN_BLACK_MATTE,
    "parede_concreto": _FIN_LACQUER_MATTE,                        # painel off-white = laca fosca
}

# ---- FP-037: material por (FAMILIA_DE_MODULO, kind). Destrava MADEIRA no rack/mesa-de-centro/mesa-
# de-jantar, cujos kinds (base/top/front/niche/leg) sao GENERICOS e compartilhados com o sofa. A
# regra de ouro: (sofa, base) e (sofa, foot) NAO tem entrada aqui -> resolvem por kind/flat (grafite),
# entao a madeira do rack NUNCA vaza pro sofa. Wood = mesmo png do kind-level do estilo (sem inventar).
# rack emite foot/base/top/front/niche (rack_class.build_rack); coffee_table emite top/leg;
# dining_table emite top/saia/foot (_dining_table_square). Pes/saia ficam grafite (nao entram).
_WOOD_IND = "wood_dark.png"
_INDUSTRIAL_MOD_TEX = {
    ("rack", "base"): _WOOD_IND, ("rack", "top"): _WOOD_IND,
    ("rack", "front"): _WOOD_IND, ("rack", "niche"): _WOOD_IND,
    ("coffee_table", "top"): _WOOD_IND,
    ("dining_table", "top"): _WOOD_IND,
}
_WOOD_MW = "wood_medium.png"
_MODERN_WARM_MOD_TEX = {
    ("rack", "base"): _WOOD_MW, ("rack", "top"): _WOOD_MW,
    ("rack", "front"): _WOOD_MW, ("rack", "niche"): _WOOD_MW,
    ("coffee_table", "top"): _WOOD_MW,
    ("dining_table", "top"): _WOOD_MW,
}
_INDUSTRIAL_MOD_FIN = {k: _FIN_WOOD_MATTE for k in _INDUSTRIAL_MOD_TEX}
_MODERN_WARM_MOD_FIN = {k: _FIN_WOOD_MATTE for k in _MODERN_WARM_MOD_TEX}

STYLE_TOKENS = {
    "industrial": StyleSpec(
        name="industrial", kind_rgb=_INDUSTRIAL_RGB, kind_texture=_INDUSTRIAL_TEX,
        kind_finish=_INDUSTRIAL_FIN,
        module_kind_texture=_INDUSTRIAL_MOD_TEX, module_kind_finish=_INDUSTRIAL_MOD_FIN,
        light_kelvin=2700, fill_color=(1.0, 0.82, 0.6), floor="polished_concrete",
        must_style=("seat_cushion", "back_cushion", "arm", "tapete"),
    ),
    "modern_warm": StyleSpec(
        name="modern_warm", kind_rgb=_MODERN_WARM_RGB, kind_texture=_MODERN_WARM_TEX,
        kind_finish=_MODERN_WARM_FIN,
        module_kind_texture=_MODERN_WARM_MOD_TEX, module_kind_finish=_MODERN_WARM_MOD_FIN,
        light_kelvin=3000, fill_color=(1.0, 0.86, 0.68), floor="light_wood",
        must_style=("seat_cushion", "back_cushion", "arm", "rack_tv", "mesa_centro", "tapete"),
    ),
}

# ---- FP-037: familia de modulo (normaliza o rotulo humano de b["module"]) + resolucao de material.
# ORDEM importa (checar 'cadeira' antes de 'jantar'; 'criado' antes de 'cama'). Primeiro match vence.
_FAMILY_RULES = (
    ("cadeira", "dining_chair"), ("mesa de jantar", "dining_table"),
    ("mesa de centro", "coffee_table"), ("rack", "rack"), ("sofa", "sofa"),
    ("criado", "nightstand"), ("guarda", "wardrobe"), ("cama", "bed"),
    ("tapete", "rug"), ("rug", "rug"),
    ("parede", "wall_panel"), ("concreto", "wall_panel"),
    ("bancada", "bathroom_vanity"), ("espelho", "bathroom_vanity"),
    ("vaso", "bathroom_vanity"), ("gabinete", "bathroom_vanity"),
    ("cabinet", "kitchen_cabinet"), ("cooktop", "kitchen_cabinet"),
    ("countertop", "kitchen_cabinet"), ("backsplash", "kitchen_cabinet"),
    ("sink", "kitchen_cabinet"), ("fridge", "kitchen_cabinet"),
    ("hood", "kitchen_cabinet"), ("filler", "kitchen_cabinet"),
    ("planta", "decor"), ("quadro", "decor"), ("prateleira", "decor"), ("trilho", "decor"),
)


def module_family(module_str) -> str:
    """Rotulo humano de b["module"] -> familia canonica (rack/coffee_table/sofa/...). Desconhecido
    -> "" (cai no fallback por kind). Determinístico, case-insensitive."""
    m = str(module_str or "").lower()
    for kw, fam in _FAMILY_RULES:
        if kw in m:
            return fam
    return ""


def resolve_material(style_name, family, kind) -> dict:
    """Resolve o material de UMA peca por HIERARQUIA: (familia,kind) -> kind -> flat.
    Devolve {mat_name, tex_png, tile_in}. mat_name = ph_{familia}_{kind} SO quando o override de
    modulo casa (senao ph_{kind}, compat com o V-Ray). Sem estilo/entrada -> cor chapada (FP-036)."""
    st = STYLE_TOKENS.get(style_name)
    if not st:
        return {"mat_name": f"ph_{kind}", "tex_png": None, "tile_in": 40}
    key = (family, kind)
    if key in st.module_kind_texture:                       # NIVEL 1: override por modulo
        fin = st.module_kind_finish.get(key, {})
        return {"mat_name": f"ph_{family}_{kind}", "tex_png": st.module_kind_texture[key],
                "tile_in": fin.get("tile_in", 40)}
    if kind in st.kind_texture:                             # NIVEL 2: mapa por kind (FP-036)
        return {"mat_name": f"ph_{kind}", "tex_png": st.kind_texture[kind],
                "tile_in": st.kind_finish.get(kind, {}).get("tile_in", 40)}
    return {"mat_name": f"ph_{kind}", "tex_png": None, "tile_in": 40}   # NIVEL 3: flat


def attach_materials(boxes, style_name):
    """Anexa mat_name/tex_png/tile_in a cada box (IN-PLACE), resolvendo por (familia,kind). Roda
    DEPOIS do apply_style, ANTES do dump LAYOUT_BOXES. O place_layout_skp.rb prefere esses campos
    (senao cai no fallback FP-036 por kind). Sem estilo -> no-op. Devolve nº com textura resolvida."""
    st = STYLE_TOKENS.get(style_name)
    if not st:
        return 0
    n = 0
    for b in boxes:
        fam = module_family(b.get("module"))
        r = resolve_material(style_name, fam, b.get("kind"))
        b["mat_name"], b["tex_png"], b["tile_in"] = r["mat_name"], r["tex_png"], r["tile_in"]
        if r["tex_png"]:
            n += 1
    return n


def get_style(name):
    return STYLE_TOKENS.get(name)


def apply_style(boxes, style_name):
    """Reescreve b['rgb'] por kind conforme o estilo (IN-PLACE). Fonte UNICA da cor do
    material SU ph_<kind>. Roda DENTRO da coleta, ANTES do dump LAYOUT_BOXES. Kinds fora
    do mapa (ex. foliage/pot da planta, ja industrial) ficam intactos. Devolve nº recolorido."""
    st = STYLE_TOKENS.get(style_name)
    if not st:
        return 0
    n = 0
    for b in boxes:
        rgb = st.kind_rgb.get(b.get("kind"))
        if rgb is not None:
            b["rgb"] = list(rgb)
            n += 1
    return n


def texture_map_for(style_name):
    """kind -> textura png (espelha o tex_map gated do vray_export.rb). Fonte consumida
    tanto pelo V-Ray quanto AGORA pelo path interativo (place_layout_skp.rb via LAYOUT_TEX_MAP)."""
    st = STYLE_TOKENS.get(style_name)
    return dict(st.kind_texture) if st else {}


def finish_map_for(style_name):
    """kind -> {finish,roughness,metalness,tile_in,cite}. Reflexo por papel, .md-citado."""
    st = STYLE_TOKENS.get(style_name)
    return dict(st.kind_finish) if st else {}


def tile_map_for(style_name):
    """kind -> tile_in (destilado do finish token). O path interativo dimensiona o tile da
    textura SU por kind; sem entrada o .rb cai no default (40 in). Parede pede tile grande."""
    st = STYLE_TOKENS.get(style_name)
    if not st:
        return {}
    return {k: fin.get("tile_in", 40) for k, fin in st.kind_finish.items()}


def texture_env(style_name, tex_dir):
    """Vars de ENV que o place_layout_skp.rb le p/ texturizar o path interativo por kind.
    Fonte UNICA (texture_map_for/tile_map_for) -> serializada UMA vez aqui p/ furnish + slice r002.
    Estilo desconhecido -> {} (o .rb cai no default '{}' = cor chapada, comportamento anterior)."""
    import json
    tm = texture_map_for(style_name)
    if not tm:
        return {}
    return {
        "LAYOUT_TEX_MAP": json.dumps(tm),
        "LAYOUT_TILE_MAP": json.dumps(tile_map_for(style_name)),
        "LAYOUT_TEX_DIR": str(tex_dir),
    }


if __name__ == "__main__":
    for name, st in STYLE_TOKENS.items():
        print(f"STYLE {name}: {len(st.kind_rgb)} kinds, must_style={st.must_style}, "
              f"kelvin={st.light_kelvin}, tex={len(st.kind_texture)}, finish={len(st.kind_finish)}")
