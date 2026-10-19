# Especialistas por cômodo

Comece pelo [README](../../README.md) e pelo [mapa do repositório](repository_map.md). Aqui está o **índice dos nove perfis**
da FP-043/P5: quem é o especialista de cada categoria, onde está a fonte (índice de conhecimento por ID), o limite (allowlist e
condições de parada em `specialist.md`) e a capacidade registrada. Um perfil **não autoriza execução**; o catálogo
([`capability_catalog.v1.json`](../../tools/rooms/capability_catalog.v1.json)) separa quatro dimensões de estado
(conhecimento, implementação, validação, visual) e o gate é `python -m tools.rooms.capability_catalog`.

| Categoria | Papel | Perfil · limite · fonte | Capacidades (implementação/validação) |
|---|---|---|---|
| `living` | planner | [`specialist.md`](../../tools/rooms/living/specialist.md) · [`specialist.v1.json`](../../tools/rooms/living/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/living/knowledge/index.v1.json) | `living.layout.boxes` (IMPLEMENTED/L1_PASS), `living.sofa.class` (IMPLEMENTED/L1_PASS), `living.sofa.gate` (IMPLEMENTED/L1_PASS) |
| `bedroom` | planner | [`specialist.md`](../../tools/rooms/bedroom/specialist.md) · [`specialist.v1.json`](../../tools/rooms/bedroom/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/bedroom/knowledge/index.v1.json) | `bedroom.layout.boxes` (IMPLEMENTED/L1_PASS), `bedroom.bed.build` (IMPLEMENTED/L1_PASS), `bedroom.wardrobe.build` (IMPLEMENTED/L1_PASS), `bedroom.wardrobe.gate` (IMPLEMENTED/L1_PASS) |
| `kitchen` | planner | [`specialist.md`](../../tools/rooms/kitchen/specialist.md) · [`specialist.v1.json`](../../tools/rooms/kitchen/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/kitchen/knowledge/index.v1.json) | `kitchen.layout.galley` (IMPLEMENTED/L2_PASS), `kitchen.sink-anchor-guard` (IMPLEMENTED/L1_PASS), `kitchen.ergonomics.audit` (IMPLEMENTED/UNTESTED), `kitchen.cabinet.plain-fronts` (IMPLEMENTED/L1_PASS), `shared.cabinet.parametric` (IMPLEMENTED/L2_PASS) |
| `bathroom` | planner | [`specialist.md`](../../tools/rooms/bathroom/specialist.md) · [`specialist.v1.json`](../../tools/rooms/bathroom/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/bathroom/knowledge/index.v1.json) | `bathroom.layout.boxes` (IMPLEMENTED/L1_PASS), `bathroom.wet-room.guard` (IMPLEMENTED/L1_PASS) |
| `service` | planner | [`specialist.md`](../../tools/rooms/service/specialist.md) · [`specialist.v1.json`](../../tools/rooms/service/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/service/knowledge/index.v1.json) | `service.layout.boxes` (IMPLEMENTED/L1_PASS) |
| `balcony` | advisory | [`specialist.md`](../../tools/rooms/balcony/specialist.md) · [`specialist.v1.json`](../../tools/rooms/balcony/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/balcony/knowledge/index.v1.json) | nenhuma (so conhecimento) |
| `closet` | reuse → bedroom | [`specialist.md`](../../tools/rooms/closet/specialist.md) · [`specialist.v1.json`](../../tools/rooms/closet/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/closet/knowledge/index.v1.json) | nenhuma (so conhecimento) |
| `home_office` | reuse → bedroom | [`specialist.md`](../../tools/rooms/home_office/specialist.md) · [`specialist.v1.json`](../../tools/rooms/home_office/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/home_office/knowledge/index.v1.json) | nenhuma (so conhecimento) |
| `circulation` | validation_only | [`specialist.md`](../../tools/rooms/circulation/specialist.md) · [`specialist.v1.json`](../../tools/rooms/circulation/specialist.v1.json) · [`knowledge/index.v1.json`](../../tools/rooms/circulation/knowledge/index.v1.json) | `circulation.gate` (IMPLEMENTED/L1_PASS) |

## Como o especialista decide

`tools/rooms/specialists.py` → `plan(request)`: resolve o cômodo pelo registry, escolhe a técnica pelo catálogo, resolve a
capacidade e confere allowlist, evidência e insumos (valor + unidade + origem). Sem capacidade `IMPLEMENTED` o resultado é
`BLOCKED_CAPABILITY_MISSING` com a lacuna específica; pedido que altera arquitetura, ferramenta fora da allowlist, insumo
incompleto e evidência velha também bloqueiam. O resultado de sucesso (`PLAN_READY_NOT_EXECUTED`) é um plano estruturado —
**não** executa nada e **não** substitui o veredito visual do Felipe.
