"""spatial_semantics.py — contrato semântico ÚNICO de geometria.

Origem (2026-08-12): depois de consertar 3 bugs da MESMA classe em 3 gates
diferentes no mesmo dia (LED marcado "degenerado" em geometry_sanity, vaso
arredondado marcado "eixo torto" em geometry_sanity, tapete de banho inflando
footprint de colisão em furniture_overlap_gate), consultei o GPT-Docker como
revisor de arquitetura. Diagnóstico dele: os 3 gates determinísticos
(circulation_gate.py, geometry_sanity.py, furniture_overlap_gate.py)
respondiam a MESMA pergunta ("essa geometria bloqueia passagem / colide /
pode ser não-retangular?") cada um com sua PRÓPRIA heurística — altura Z,
bool solto (decorative/smooth), substring de kind, substring de module — sem
compartilhar modelo. Cada bug corrigido isoladamente é a mesma classe de erro
reaparecendo em lugar diferente.

Princípio (ADR — ver docs/interview-study/architecture-lessons.md):
  Builders declaram intenção e relações. Gates canônicos avaliam a partir da
  intenção declarada. Nenhum gate deduz semântica por nome, dimensão ou forma
  quando ela pode ser declarada explicitamente.

Modelo (revisado pelo GPT-Docker — NÃO é o rascunho original do Felipe, que
tinha um único `collision_policy` SOLID|FOOTPRINT|IGNORE; o GPT apontou que
isso perde informação — ex. tapete precisa responder DIFERENTE pra circulação
["pisável"] vs overlap ["pode sobrepor"] vs geometry_sanity ["forma válida"].
Ver HANDOFF.md pra divergência documentada):

  geometry_intent: STRUCTURAL | FURNITURE | SOFT | DECORATIVE | FIXTURE
      O QUE a peça É (papel arquitetônico/funcional).

  shape_policy: {rotation_allowed, non_rectangular_allowed, curved_allowed}
      Forma esperada — separa "retângulo girado de propósito" (almofada 12°)
      de "polígono genuinamente não-retangular de propósito" (vaso arredondado).

  interaction_policy: {circulation: BLOCK|WALKABLE|OVERHEAD|IGNORE,
                        furniture_overlap: EXCLUSIVE|ALLOW|HOSTED|IGNORE}
      Como a peça se comporta em CADA domínio de checagem — substitui a
      heurística de altura Z do circulation_gate e o EXCLUDE/_FIX/_HOST/_TRIM
      por substring do furniture_overlap_gate.

  host: {host_id, relationship: NONE|MOUNTED_ON|EMBEDDED_IN|RESTS_ON|CONTAINED_IN}
      Substitui _is_embedded() por substring (cooktop "dentro" da bancada).

MIGRAÇÃO (fase 1-2 do plano, não big-bang): a maioria das peças do pipeline
ainda não declara os campos acima explicitamente no dict do builder. Este
módulo dá um DEFAULT via `KIND_REGISTRY`/`MODULE_REGISTRY` — que é uma
declaração CENTRAL e EXPLÍCITA por kind/module (não uma inferência por forma/
bbox: é uma tabela editada por humano, mesmo espírito de `_pp`'s tupla
`decorative` que já existia em bathroom_layout.py). Peça cujo kind/module não
bate em NADA da tabela cai no fallback FURNITURE + `_semantics_provenance:
"default_fallback"`, que o semantic_geometry_contract_gate reporta como
WARN_LEGACY_SEMANTICS — visível, não escondido.
"""
from __future__ import annotations

GEOMETRY_INTENTS = ("STRUCTURAL", "FURNITURE", "SOFT", "DECORATIVE", "FIXTURE")
CIRCULATION_POLICIES = ("BLOCK", "WALKABLE", "OVERHEAD", "IGNORE")
OVERLAP_POLICIES = ("EXCLUSIVE", "ALLOW", "HOSTED", "IGNORE")
HOST_RELATIONSHIPS = ("NONE", "MOUNTED_ON", "EMBEDDED_IN", "RESTS_ON", "CONTAINED_IN")

# default shape/interaction policy POR geometry_intent — ponto de partida;
# peça individual pode dar override explícito (ex. sofá é FURNITURE mas raro
# ser rotation_allowed=False; vaso é FIXTURE mas precisa non_rectangular_allowed).
_DEFAULT_SHAPE_POLICY = {
    "STRUCTURAL": {"rotation_allowed": False, "non_rectangular_allowed": False, "curved_allowed": False},
    "FURNITURE": {"rotation_allowed": True, "non_rectangular_allowed": False, "curved_allowed": False},
    "FIXTURE": {"rotation_allowed": True, "non_rectangular_allowed": False, "curved_allowed": False},
    "SOFT": {"rotation_allowed": True, "non_rectangular_allowed": True, "curved_allowed": True},
    "DECORATIVE": {"rotation_allowed": True, "non_rectangular_allowed": True, "curved_allowed": True},
}
_DEFAULT_INTERACTION_POLICY = {
    "STRUCTURAL": {"circulation": "BLOCK", "furniture_overlap": "EXCLUSIVE"},
    "FURNITURE": {"circulation": "BLOCK", "furniture_overlap": "EXCLUSIVE"},
    "FIXTURE": {"circulation": "BLOCK", "furniture_overlap": "EXCLUSIVE"},
    "SOFT": {"circulation": "WALKABLE", "furniture_overlap": "ALLOW"},
    "DECORATIVE": {"circulation": "IGNORE", "furniture_overlap": "IGNORE"},
}

# ── registro central por KIND (match exato, depois prefixo) ────────────────
# Cada entrada é geometry_intent; shape/interaction herdam o default da
# intenção salvo override em _SHAPE_OVERRIDES/_INTERACTION_OVERRIDES/_HOST_MAP.
KIND_REGISTRY: dict[str, str] = {
    # estrutural (paredes/piso/teto/revestimento — todas as plantas)
    "parede": "STRUCTURAL", "piso": "STRUCTURAL", "teto": "STRUCTURAL",
    "kb_parede": "STRUCTURAL", "kb_parede_pedra": "STRUCTURAL",
    "kb_piso": "STRUCTURAL", "kb_piso_box": "STRUCTURAL", "kb_teto": "STRUCTURAL",
    "kb_folha": "STRUCTURAL", "kb_janela_fosco": "STRUCTURAL",
    "pele": "STRUCTURAL", "peleteto": "STRUCTURAL",
    # fixture (louça/metais/embutidos fixos — banheiro + cozinha)
    "vaso": "FIXTURE", "kb_tampa": "FIXTURE", "kb_botao": "FIXTURE",
    "box": "FIXTURE", "box_vidro": "FIXTURE", "bancada_banho": "FIXTURE",
    "kb_torneira": "FIXTURE", "kb_ducha": "FIXTURE", "kb_ducha_manual": "FIXTURE",
    "kb_misturador": "FIXTURE", "kb_ralo": "FIXTURE",
    "cooktop": "FIXTURE", "sink": "FIXTURE", "pia": "FIXTURE", "cuba": "FIXTURE",
    "kc_cuba": "FIXTURE", "kc_cuba_rim": "FIXTURE",
    # soft (pisável — nunca bloqueia circulação, nunca conta pra overlap sólido)
    "tapete": "SOFT", "rug": "SOFT", "rug_border": "SOFT", "rug_field": "SOFT",
    "kb_tapete": "SOFT",
    # decorativo (trim/hardware fino, luz, adorno — nunca bloqueia nada)
    "kb_moldura": "DECORATIVE", "kb_frasco": "DECORATIVE", "kb_toalha": "DECORATIVE",
    "kb_trilho": "DECORATIVE", "kb_puxador": "DECORATIVE", "kb_haste": "DECORATIVE",
    "kb_argola": "DECORATIVE", "kb_gancho": "DECORATIVE", "kb_papeleira": "DECORATIVE",
    "kb_escova": "DECORATIVE", "kb_toalheiro": "DECORATIVE", "kb_bandeja": "DECORATIVE",
    "kb_sabonete": "DECORATIVE", "kb_copo": "DECORATIVE", "kb_guia": "DECORATIVE",
    "kb_caixilho": "DECORATIVE", "kb_perfil": "DECORATIVE", "kb_slot_led": "DECORATIVE",
    "kb_led": "DECORATIVE", "kb_sombra": "DECORATIVE", "kb_gola": "DECORATIVE",
    "kb_lixeira": "DECORATIVE", "kb_nicho_box": "DECORATIVE",
    "kc_anel": "DECORATIVE", "kc_boca": "DECORATIVE", "kc_led": "DECORATIVE",
    "pend_cupula": "DECORATIVE", "pend_bronze": "DECORATIVE", "pend_cabo": "DECORATIVE",
    "almofada": "DECORATIVE", "lv_led": "DECORATIVE",
    "ks_gola": "DECORATIVE", "decor_board": "DECORATIVE", "decor_vaso": "DECORATIVE",
    # criado-mudo (quarto) — corpo/frente/tampo são o móvel de verdade
    "ks_criado_corpo": "FURNITURE", "ks_criado_frente": "FURNITURE", "ks_criado_tampo": "FURNITURE",
}
# prefixo/substring — só quando não bate exato (ordem importa: mais
# específico primeiro). Mantém DECORATIVE como fallback de "kb_*" não listado
# (maioria dos acessórios de banheiro é pequena/trim), mas NUNCA usado pra
# decidir sozinho — kinds estruturais/fixture relevantes estão no exact-match
# acima, que tem prioridade.
_PREFIX_FALLBACK: tuple[tuple[str, str], ...] = (
    ("led", "DECORATIVE"), ("pend_", "DECORATIVE"), ("kb_", "DECORATIVE"), ("kc_", "DECORATIVE"),
)

# módulos (grupo .skp) cujo geometry_intent é conhecido independente do kind —
# usado quando o kind individual (ex. "seat", "back", "frame", "foot" de uma
# cadeira) não tem entrada própria em KIND_REGISTRY.
MODULE_REGISTRY: dict[str, str] = {
    "sofa": "FURNITURE", "mesa de jantar": "FURNITURE", "cadeira jantar": "FURNITURE",
    "mesa de centro": "FURNITURE", "rack tv": "FURNITURE", "painel tv": "FURNITURE",
    "tv": "FURNITURE", "cama": "FURNITURE", "painel cabeceira": "FURNITURE",
    "guarda-roupa": "FURNITURE", "criado-mudo": "FURNITURE", "bancada": "FURNITURE",
    "tapete": "SOFT", "pendente": "DECORATIVE", "vaso": "FIXTURE", "enxoval": "DECORATIVE",
    "espelho": "FIXTURE", "parede concreto": "STRUCTURAL",
}

# host relationship conhecido — substitui _FIX/_HOST/_TRIM do furniture_overlap_gate.
HOST_RELATIONSHIP_BY_KIND: dict[str, tuple[str, str]] = {
    # kind -> (relationship, host_kind_hint) — host_id real é resolvido pelo
    # chamador (não dá pra saber o id da instância aqui, só o PADRÃO esperado).
    "cooktop": ("EMBEDDED_IN", "bancada"), "sink": ("EMBEDDED_IN", "bancada"),
    "pia": ("EMBEDDED_IN", "bancada"), "cuba": ("EMBEDDED_IN", "bancada"),
    "kb_tampa": ("MOUNTED_ON", "vaso"), "kb_botao": ("MOUNTED_ON", "vaso"),
}


def resolve_geometry_intent(kind: str | None, module: str | None) -> tuple[str, str]:
    """(geometry_intent, provenance). provenance in {'kind_exact','kind_prefix',
    'module','default_fallback'} — só os 3 primeiros contam como 'explícito'
    pro semantic_geometry_contract_gate; o último é legado a migrar."""
    k = str(kind or "").lower()
    if k in KIND_REGISTRY:
        return KIND_REGISTRY[k], "kind_exact"
    for prefix, intent in _PREFIX_FALLBACK:
        if prefix in k:
            return intent, "kind_prefix"
    m = str(module or "").lower()
    if m in MODULE_REGISTRY:
        return MODULE_REGISTRY[m], "module"
    return "FURNITURE", "default_fallback"


def resolve_shape_policy(intent: str, overrides: dict | None = None) -> dict:
    base = dict(_DEFAULT_SHAPE_POLICY.get(intent, _DEFAULT_SHAPE_POLICY["FURNITURE"]))
    if overrides:
        base.update(overrides)
    return base


def resolve_interaction_policy(intent: str, overrides: dict | None = None) -> dict:
    base = {k: dict(v) if isinstance(v, dict) else v
            for k, v in _DEFAULT_INTERACTION_POLICY.get(intent, _DEFAULT_INTERACTION_POLICY["FURNITURE"]).items()}
    if overrides:
        base.update(overrides)
    return base


def resolve_host(kind: str | None) -> dict:
    k = str(kind or "").lower()
    if k in HOST_RELATIONSHIP_BY_KIND:
        rel, host_kind_hint = HOST_RELATIONSHIP_BY_KIND[k]
        return {"host_id": None, "host_kind_hint": host_kind_hint, "relationship": rel}
    return {"host_id": None, "host_kind_hint": None, "relationship": "NONE"}


def annotate(box: dict) -> dict:
    """Preenche geometry_intent/shape_policy/interaction_policy/host NO box se
    ainda não declarados explicitamente (builder pode ter setado geometry_intent
    direto — nesse caso não sobrescreve). Idempotente. Não muta geometria."""
    if "geometry_intent" in box:
        intent, provenance = box["geometry_intent"], "explicit"
    else:
        intent, provenance = resolve_geometry_intent(box.get("kind"), box.get("module"))
        box["geometry_intent"] = intent
    box["_semantics_provenance"] = provenance
    box.setdefault("shape_policy", resolve_shape_policy(intent, box.get("shape_policy")))
    box.setdefault("interaction_policy", resolve_interaction_policy(intent, box.get("interaction_policy")))
    box.setdefault("host", resolve_host(box.get("kind")))
    return box


def annotate_all(boxes: list[dict]) -> list[dict]:
    for b in boxes:
        annotate(b)
    return boxes
