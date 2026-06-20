"""reference_grammar.py — núcleo do "especialista Pinterest".

Traduz uma REFERÊNCIA VISUAL (Pinterest / print / foto) em uma
``DesignGrammarSpec`` estruturada que os builders/gates consomem — **sem copiar
a imagem**.

Regra-mãe (skill ``planned-joinery-translator``):

    A REFERÊNCIA manda na LINGUAGEM  (paleta, tokens de marcenaria, assinatura).
    O PDF/consensus manda na POSIÇÃO (pia, parede, porta, janela, circulação =
    IMUTÁVEL).

O Claude (que JÁ é um modelo de visão) lê a imagem e preenche os campos de
linguagem seguindo o CONTRATO devolvido por :func:`grammar_contract`. Este
módulo **não vê pixels** — ele:

  (a) entrega o contrato + vocabulário canônico ancorado na amostra-ouro da
      cozinha (``artifacts/kitchen_research/joinery_tokens.json``);
  (b) normaliza tokens soltos pro vocabulário canônico (:func:`normalize_grammar`);
  (c) valida a spec cruzando com as âncoras do PDF (:func:`validate_grammar_spec`),
      reprovando qualquer tentativa da referência de mexer na POSIÇÃO.

Determinístico, sem rede, sem clock/random — testável e auditável.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Vocabulário canônico — ancorado na amostra-ouro (joinery_tokens.json, cozinha
# r004 da planta_74). NÃO inventar: estes são os tokens que JÁ têm builder/ergo
# provados. O vocabulário cresce por cômodo conforme novas classes são provadas.
# ---------------------------------------------------------------------------

# token canônico -> resumo de intenção + a que builder/cômodo serve.
CANON_TOKENS: dict[str, dict[str, Any]] = {
    "fridge_tower": {
        "intent": "Geladeira inox vira COLUNA integrada full-height (não bloco solto).",
        "builder_kind": "geladeira + aereo_fridge + filler",
        "rooms": ["kitchen"],
    },
    "upper_niche": {
        "intent": "1 bay ABERTA de madeira na linha de aéreos = nicho de assinatura.",
        "builder_kind": "aereo (niche bay)",
        "rooms": ["kitchen", "living"],
    },
    "shadow_gap_reveal": {
        "intent": "Junta/cava planejada entre módulos = marcenaria fina sem puxador dominando.",
        "builder_kind": "panel inset (reveal) entre módulos",
        "rooms": ["kitchen", "bedroom", "living"],
    },
    "led_strip": {
        "intent": "Fita LED quente sob o aéreo lava a pedra; em massa básica lê como linha clara.",
        "builder_kind": "aereo (led + valance)",
        "rooms": ["kitchen", "living", "bedroom"],
    },
    "stone_backsplash_veined": {
        "intent": "Tampo de pedra clara sobe como backsplash contínuo (mesmo material = leitura premium).",
        "builder_kind": "bancada (tampo + backpanel)",
        "rooms": ["kitchen", "bathroom"],
    },
    "gola_reveal": {
        "intent": "Sistema handle-less por gola: sombra fina recuada no pé da porta.",
        "builder_kind": "aereo (gola panel)",
        "rooms": ["kitchen", "bedroom"],
    },
    "slim_integrated_hood": {
        "intent": "Coifa SLIM embutida sob o aéreo, caixa na cor da marcenaria (não bloco preto solto).",
        "builder_kind": "coifa (slim)",
        "rooms": ["kitchen"],
    },
    "plinth_graphite": {
        "intent": "Sóculo/toe-kick recuado grafite -> marcenaria parece flutuar.",
        "builder_kind": "bancada (sóculo body)",
        "rooms": ["kitchen", "bedroom", "bathroom"],
    },
    "warm_fendi_uppers": {
        "intent": "Aéreos em fendi/off-white quente -> dois-tons suave com a base de madeira.",
        "builder_kind": "aereo / filler / coifa (corpo_sup)",
        "rooms": ["kitchen"],
    },
    "oak_lowers": {
        "intent": "Módulos inferiores em carvalho/freijó quente -> ancora o ambiente.",
        "builder_kind": "bancada (corpo/porta/gaveta)",
        "rooms": ["kitchen", "living"],
    },
}

# Sinônimos vindos do design_grammar_spec.template.json (naming alternativo) ->
# token canônico da amostra-ouro. Normalize colapsa duplicatas por aqui.
TOKEN_SYNONYMS: dict[str, str] = {
    "integrated_fridge_tower": "fridge_tower",
    "recessed_toe_kick": "plinth_graphite",
    "open_niche": "upper_niche",
    "flush_upper_cabinet": "warm_fendi_uppers",
    "continuous_thin_countertop": "stone_backsplash_veined",
    "backsplash": "stone_backsplash_veined",
}

# Tokens "conhecidos mas sem builder de assinatura próprio" — válidos no
# vocabulário (não geram WARN), mas marcados como atributo/eletrodoméstico.
KNOWN_ATTRIBUTE_TOKENS: set[str] = {
    "slab_doors",
    "side_filler_panel",
    "slim_black_cooktop",
    "deep_dark_sink",
    "gooseneck_faucet",
}

# Papéis de paleta válidos por cômodo (do template; cresce por cômodo).
PALETTE_ROLES: dict[str, set[str]] = {
    "kitchen": {
        "base_cabinets", "upper_cabinets", "countertop", "toe_kick",
        "appliances", "cooktop", "accent", "backsplash",
    },
    "bedroom": {"headboard", "wardrobe", "nightstand", "bedframe", "accent", "wall"},
    "living": {"sofa", "rack", "coffee_table", "wall", "rug", "accent"},
    "bathroom": {"vanity", "countertop", "stone", "fixtures", "accent", "wall"},
}

# Chaves que pertencem ao PDF/consensus — IMUTÁVEIS pela referência.
# A referência NUNCA preenche posição; estas vêm do extrator do PDF.
FIXED_ANCHOR_KEYS: tuple[str, ...] = ("sink", "doors", "windows", "walls", "circulation")

# Top-level obrigatórios da DesignGrammarSpec (do template).
REQUIRED_SPEC_KEYS: tuple[str, ...] = (
    "room", "room_id", "style", "reference", "palette",
    "joinery_tokens", "fixed_anchors", "gates_required", "acceptance",
)

_RULE = (
    "A REFERÊNCIA manda na LINGUAGEM (paleta/tokens/assinatura). "
    "O PDF/consensus manda na POSIÇÃO (pia/parede/porta/janela/circulação = IMUTÁVEL). "
    "O agente traduz os dois; nunca move geometria por causa de uma foto."
)

_DEFAULT_GATES = [
    "pdf_anchor", "circulation_free", "no_overlap", "editability",
    "language_coherence", "realistic_proportion", "visual_verdict_human_or_gpt",
]

_ACCEPTANCE = (
    "Parece planejado real em material básico ANTES do V-Ray; "
    "se parece cubo/Minecraft, reprova."
)


def _canon(token: str) -> str:
    """Colapsa um token solto pro nome canônico (via sinônimo) se houver."""
    t = token.strip()
    return TOKEN_SYNONYMS.get(t, t)


def known_tokens_for(room_type: str) -> list[dict[str, Any]]:
    """Lista os tokens canônicos relevantes pro cômodo (com intenção/builder)."""
    out = []
    for name, meta in CANON_TOKENS.items():
        if room_type in meta.get("rooms", []):
            out.append({"token": name, **{k: meta[k] for k in ("intent", "builder_kind")}})
    return out


# ---------------------------------------------------------------------------
# (a) CONTRATO — a "ficha do especialista" que o Claude usa pra ler a imagem.
# ---------------------------------------------------------------------------

def grammar_contract(room_type: str = "kitchen") -> dict[str, Any]:
    """Devolve o briefing de extração: o que olhar na referência e em que
    formato responder. O Claude lê a imagem + este contrato, monta o ``draft``
    e chama ``reference_to_grammar(draft=...)`` pra normalizar.
    """
    rt = room_type.strip().lower()
    return {
        "rule": _RULE,
        "room_type": rt,
        "how_to": [
            "1. Olhe a referência e extraia LINGUAGEM, nunca pixels nem posição.",
            "2. Nomeie a PALETA por PAPEL (não 'a cor X', e sim 'base_cabinets=warm_wood').",
            "3. Liste os joinery_tokens visíveis (use os canônicos abaixo quando casar).",
            "4. Descreva a ASSINATURA em 1 frase (o que faz a peça 'ler' como planejada).",
            "5. NÃO preencha fixed_anchors — eles vêm do PDF; o validador os injeta.",
            "6. Devolva o draft via reference_to_grammar(draft=...) pra normalizar e validar.",
        ],
        "palette_roles": sorted(PALETTE_ROLES.get(rt, set())),
        "known_joinery_tokens": known_tokens_for(rt),
        "attribute_tokens_ok": sorted(KNOWN_ATTRIBUTE_TOKENS),
        "fixed_anchor_keys": list(FIXED_ANCHOR_KEYS),
        "fixed_anchor_note": "Estes vêm do PDF/consensus e são IMUTÁVEIS — não preencher a partir da imagem.",
        "draft_shape": {
            "reference": {"source": "pinterest|print|foto|url", "note": "o que foi visto, sem copiar"},
            "style": "ex.: modern_compact_planned",
            "palette": {"<role>": "<material/cor nomeada>"},
            "joinery_tokens": ["<token>", "..."],
            "signature": "1 frase: o que faz ler como planejado",
            "loose_to_system": {"<loose_object>": ["<system_part>", "..."]},
            "modules": [{"name": "...", "type": "...", "selectable": True}],
        },
        "spec_keys": list(REQUIRED_SPEC_KEYS),
        "acceptance": _ACCEPTANCE,
    }


# ---------------------------------------------------------------------------
# (b) NORMALIZADOR — draft do agente -> DesignGrammarSpec canônica.
# ---------------------------------------------------------------------------

def normalize_grammar(
    draft: dict[str, Any],
    room_type: str = "kitchen",
    plant: str | None = None,
    room_id: str | None = None,
) -> dict[str, Any]:
    """Converte o ``draft`` (linguagem extraída pelo agente) numa
    DesignGrammarSpec conforme o template, colapsando sinônimos de token e
    injetando os ``fixed_anchors`` como referências ao PDF (autoridade do PDF
    por CONSTRUÇÃO — a referência nunca define posição).

    Retorna ``{"spec": <DesignGrammarSpec>, "vocab_report": {...}}``.
    """
    draft = draft or {}
    rt = room_type.strip().lower()

    raw_tokens = list(draft.get("joinery_tokens", []) or [])
    canonical, synonyms_applied, unknown = [], {}, []
    for tok in raw_tokens:
        c = _canon(tok)
        if c != tok:
            synonyms_applied[tok] = c
        if c in CANON_TOKENS or c in KNOWN_ATTRIBUTE_TOKENS:
            if c not in canonical:
                canonical.append(c)
        else:
            unknown.append(c)
            if c not in canonical:
                canonical.append(c)  # mantém (vocab cresce); só sinaliza

    spec: dict[str, Any] = {
        "_doc": "DesignGrammarSpec — referência_visual -> componentes SketchUp. "
                "Linguagem da referência; POSIÇÃO do PDF (fixed_anchors).",
        "room": rt,
        "plant": plant or draft.get("plant") or "unknown",
        "room_id": room_id or draft.get("room_id") or "unknown",
        "style": draft.get("style") or "modern_compact_planned",
        "reference": draft.get("reference") or {"source": "pinterest", "note": ""},
        "palette": dict(draft.get("palette") or {}),
        "joinery_tokens": canonical,
        "signature": draft.get("signature", ""),
        "loose_to_system": draft.get("loose_to_system") or {
            "_rule": "todo objeto solto vira sistema de nicho planejado",
        },
        # POSIÇÃO = PDF. Injetado por construção; NÃO vem do draft.
        "fixed_anchors": {
            "_rule": "do PDF/consensus — IMUTÁVEL pela referência",
            **{k: f"pdf_{k}" for k in FIXED_ANCHOR_KEYS},
        },
        "modules": draft.get("modules") or [],
        "gates_required": list(_DEFAULT_GATES),
        "acceptance": _ACCEPTANCE,
    }

    return {
        "spec": spec,
        "vocab_report": {
            "canonical": [t for t in canonical if t not in unknown],
            "synonyms_applied": synonyms_applied,
            "unknown": unknown,
            "palette_roles_unknown": sorted(
                set(spec["palette"]) - PALETTE_ROLES.get(rt, set())
            ),
        },
    }


# ---------------------------------------------------------------------------
# (c) VALIDADOR — DesignGrammarSpec vs autoridade do PDF.
# ---------------------------------------------------------------------------

def _load_consensus(consensus_path: str | Path | None) -> dict[str, Any] | None:
    if not consensus_path:
        return None
    p = Path(consensus_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _room_ids(consensus: dict[str, Any]) -> set[str]:
    rooms = consensus.get("rooms") or []
    ids = set()
    for r in rooms:
        if isinstance(r, dict):
            rid = r.get("id") or r.get("room_id") or r.get("name")
            if rid:
                ids.add(str(rid))
    return ids


def validate_grammar_spec(
    spec: dict[str, Any],
    consensus_path: str | Path | None = None,
    room_id: str | None = None,
) -> dict[str, Any]:
    """Valida a DesignGrammarSpec. Reprova (FAIL) o que feriria a autoridade
    do PDF; sinaliza (WARN) vocabulário fora do canônico.

    Cruza com o consensus do PDF quando ``consensus_path`` é dado: o ``room_id``
    da spec precisa existir como cômodo real no PDF.
    """
    errors: list[str] = []
    warnings: list[str] = []
    spec = spec or {}
    rt = str(spec.get("room", "")).strip().lower()

    # 1. Estrutura mínima.
    for key in REQUIRED_SPEC_KEYS:
        if key not in spec or spec[key] in (None, "", [], {}):
            errors.append(f"campo obrigatório ausente/vazio: '{key}'")

    # 2. Autoridade do PDF: fixed_anchors devem ser referências ao PDF, nunca
    #    posições inventadas pela referência.
    fa = spec.get("fixed_anchors") or {}
    if not isinstance(fa, dict) or not fa:
        errors.append("fixed_anchors ausente — a POSIÇÃO precisa vir do PDF.")
    else:
        for k in FIXED_ANCHOR_KEYS:
            v = fa.get(k)
            if v is None:
                warnings.append(f"fixed_anchor '{k}' não declarado (esperado do PDF).")
                continue
            sval = str(v).lower()
            looks_pdf = any(s in sval for s in ("pdf", "consensus", "hydraulic", "wall", "anchor"))
            if not looks_pdf:
                errors.append(
                    f"fixed_anchor '{k}'='{v}' não parece vir do PDF — "
                    "a referência NÃO pode definir POSIÇÃO."
                )

    # 3. Vocabulário de tokens.
    for tok in spec.get("joinery_tokens", []) or []:
        c = _canon(tok)
        if c not in CANON_TOKENS and c not in KNOWN_ATTRIBUTE_TOKENS:
            warnings.append(f"joinery_token fora do canônico (vocab cresce): '{tok}'")

    # 4. Papéis de paleta.
    roles = PALETTE_ROLES.get(rt)
    if roles is not None:
        for role in (spec.get("palette") or {}):
            if role not in roles:
                warnings.append(f"papel de paleta desconhecido p/ {rt}: '{role}'")

    # 5. Cruzamento com o PDF (consensus).
    consensus = _load_consensus(consensus_path)
    rid = room_id or spec.get("room_id")
    if consensus is not None:
        ids = _room_ids(consensus)
        if rid and rid not in ids and rid != "unknown":
            errors.append(
                f"room_id '{rid}' não existe no consensus do PDF "
                f"(cômodos: {sorted(ids)}) — a referência não cria cômodo."
            )
    elif consensus_path:
        warnings.append(f"consensus não carregado de '{consensus_path}' — cruzamento PDF pulado.")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {
        "result": result,
        "errors": errors,
        "warnings": warnings,
        "room": rt,
        "room_id": rid,
        "n_tokens": len(spec.get("joinery_tokens", []) or []),
    }
