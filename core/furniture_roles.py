"""furniture_roles.py — papel funcional DECLARADO de um movel (FP-054 F1-02, #382).

Os gates que medem um conjunto (mesa + cadeiras de jantar) precisam saber QUAL caixa e mesa de jantar e qual e cadeira de
jantar. Antes isso saia de prefixo de texto (`module.startswith("Cadeira")`): a mesma cadeira rotulada `Chair` nao era medida
e o gate passava; uma cadeira de escrivaninha (`Cadeira escrivaninha`) contava como cadeira de jantar.

Agora o papel vem, nesta ordem, de:
  1. `box["furniture_role"]` declarado pelo builder (tem que estar em `ROLES`);
  2. `MODULE_ROLE`: tabela CENTRAL e explicita por nome exato de modulo (editada por humano, mesmo espirito do
     `MODULE_REGISTRY` de `core/spatial_semantics.py`) — nunca prefixo, substring ou forma;
  3. senao, `None` ("undeclared"). Um ASSENTO (kind `seat`) sem papel e entrada faltante: o gate bloqueia em vez de ignorar.

Modulo separado de `core/spatial_semantics.py` de proposito: acrescentar papeis aqui nao muda o fecho (R-18) de capacidades
que alcancam aquele modulo.
"""
from __future__ import annotations

ROLES: tuple[str, ...] = ("dining_table", "dining_chair", "desk_chair", "sofa", "armchair", "coffee_table", "desk", "bed")
SEAT_KINDS: tuple[str, ...] = ("seat",)

MODULE_ROLE: dict[str, str] = {
    "mesa de jantar": "dining_table",
    "cadeira jantar": "dining_chair",
    "cadeira escrivaninha": "desk_chair",
    "escrivaninha": "desk",
    "sofa": "sofa",
    "mesa de centro": "coffee_table",
    "cama": "bed",
}


def resolve_role(box: dict) -> tuple[str | None, str]:
    """(papel, proveniencia) com proveniencia em {'explicit', 'module_registry', 'invalid_explicit', 'undeclared'}."""
    explicit = box.get("furniture_role")
    if explicit is not None:
        return (explicit, "explicit") if explicit in ROLES else (None, "invalid_explicit")
    module = str(box.get("module") or "").strip().lower()
    if module in MODULE_ROLE:
        return MODULE_ROLE[module], "module_registry"
    return None, "undeclared"


def is_seat(box: dict) -> bool:
    return str(box.get("kind") or "") in SEAT_KINDS
