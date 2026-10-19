# FP-041 — auditoria e modularização incremental por cômodo

## Diagnóstico do repositório

Snapshot do tree remoto (2.034 entradas, 1.723 blobs; ponto de partida #253).
Módulos existentes identificados por leitura de imports, pontos de entrada e símbolos:

- `tools/furnish_apartment.py`: orquestrador com cerca de 974 linhas; `BRAINS` despacha
  BEDROOM, KITCHEN, LIVING, BATHROOM, SERVICE e aplica estilos/materiais.
- `tools/bedroom_layout.py`: helpers de geometria consumidos por cozinha, banho,
  planejador da sala e bedroom_designer, acoplamento indevido.
- `tools/service_layout.py`: dependência cíclica tardia de
  `tools.furnish_apartment._oriented_box`.
- `tools/room_type.py`: tipos extraídos por regex de nomes de cômodos;
  `core/domain/room_registry.py`: ids/aliases canônicos específicos de planta_74.
- `tools/service_layout.py` modela uma unidade composta de A.S. e terraços
  porque o próprio consensus não os separa em paredes (não inventar 3 rooms).

## Critério de propriedade dos módulos

Uma função com consumidores de mais de um cômodo pertence a `shared`.
Uma capacidade cujo único dono é uma espécie de cômodo pertence a essa espécie.
Um executor que agrega resultados de todos os cômodos fica em `orchestrator`,
não no módulo de um cômodo.
A fonte de verdade de medidas é `consensus`/spec aprovada, não a receita.

```text
tools/rooms/
  shared/geometry.py    ← implementação real comum (extraída)
  registry.py            ← roteamento de conhecimento e provider metadata
  manifest.v1.json       ← capabilities declarativas, NUNCA autorização
  living/                ← provider legado: place_layout_skp, sofas
  bedroom/               ← provider legado: bedroom_designer, builders
  kitchen/               ← provider legado: kitchen_layout, validação hidráulica
  bathroom/              ← provider legado: bathroom_layout
  service/               ← service_layout (A.S. + terraço social/técnico)
  balcony/               ← perfil consultivo, sem brain independente
  closet/                ← perfil consultivo reutiliza marcenaria de bedroom
  home_office/           ← perfil consultivo, sem brain próprio
  circulation/           ← validação/gates
```

### Alterações funcionais implementadas nesta fatia

- Extrai para `shared.geometry`: `_fbox`, `_wall_setup`, `_perp_depth`,
  `_window_zones`, `_door_zones`, `_oriented_box`.
- Redireciona imports diretos de cozinha, banho, sala e bedroom designer.
- Preserva re-exports na origem legada para compatibilidade de clientes externos.
- Remove ciclo explícito `service_layout → furnish_apartment` apenas para
  obter `_oriented_box`.
- Cria módulos por cômodo como pacotes de roteamento (sem mover ainda todos
  os builders legados nem duplicar código-fonte).
- `registry.resolve_module()` e `resolve_project_room()` retornam metadados
  estáticos, não instanciam executor nem importam todos os providers.

### Decisões de não migração por enquanto

- Manter `tools/furnish_apartment.py` como orquestrador público para não romper
  scripts, CLI e fluxos de renderização.
- Não renomear room ids, reclassificar r001, alterar escala, shapes, materiais,
  gates geométricos, scripts Ruby nem caminhos SKP.
- `balcony` não ganha brain se o terrace pertence à A.S. no consensus.
- `closet` e `home_office` são categorias de conhecimento; não quartos novos.

### Verificações obrigatórias antes do merge

1. `python -m pytest tests/test_room_module_architecture.py -q`.
2. `python -m pytest tests/ -q` (com ressalvas do conftest e testes planta74
   que exigem PT_TO_M separado).
3. `python -m pytest -m planta74_scale -q` em processo próprio se aplicável.
4. `python -m ruff check tools/rooms/ tools/bedroom_layout.py
   tools/bathroom_layout.py tools/kitchen_layout.py
   tools/service_layout.py tools/furnish_apartment.py
   interior/planners/living_room_planner.py tools/bedroom_designer.py`.
5. `python -m tools.run_deterministic_gates --fixture planta_74` e quadrado
   conforme matriz do repo. No-code SketchUp L2 pendente nesta mudança.

**Status:** apenas auditoria estática remota e comparação de fonte; a suíte não
foi executada neste ambiente. Não afirmar equivalência dinâmica antes dos testes.
