# Cozinha (`tools/rooms/kitchen/`)

Módulo de referência da convenção de cômodo ([mapa do repositório](../../../docs/architecture/repository_map.md), seção 4).
Descreve o que a cozinha **faz hoje**, onde está, com que prova e onde para. Nada aqui promove um estado: onde não há
prova, está escrito.

## Comece aqui

| Preciso de… | Arquivo |
|---|---|
| o **planner** (layout da cozinha) | [`layout.py`](layout.py) → `build_boxes(con, room_id)` |
| a **regra que protege a pia** (ponto hidráulico do PDF) | constantes `KITCHEN_SINK_ANCHOR` / `KITCHEN_SINK_SIDE` em `layout.py`; checagem em [`anchor_rules.py`](anchor_rules.py) → `validate`; trava fail-closed em [`validation/__init__.py`](validation/__init__.py) → `require_kitchen_anchor` |
| a medição ergonômica | [`validation/ergonomics.py`](validation/ergonomics.py) → `audit` (CLI: `python -m tools.rooms.kitchen.validation.ergonomics`) |
| o **especialista** (papel, fontes, ferramentas permitidas, limites) | [`specialist.md`](specialist.md), perfil [`specialist.v1.json`](specialist.v1.json), índice de conhecimento [`knowledge/index.v1.json`](knowledge/index.v1.json) |
| o **catálogo de capacidades** (fonte → recipe → capacidade → símbolo → teste → evidência) | `tools/rooms/capability_catalog.v1.json` (gate: `python -m tools.rooms.capability_catalog`; roteamento e plano fail-closed: `tools/rooms/specialists.py`) |
| quem chama a cozinha | `tools/furnish_apartment.py` (`collect_boxes`) via [`../dispatch.py`](../dispatch.py); manifesto em [`../manifest.v1.json`](../manifest.v1.json) |

As fachadas antigas em `tools/` (`kitchen_validation`, `kitchen_ergonomics`, `kitchen_vray`, `bake_theme_skp`,
`kitchen_wall_regression_gate`) saíram na FP-044/F6: a CLI de cada uma é `python -m` do dono acima (a do gate da pia é
`python -m tools.rooms.kitchen.anchor_rules`). `tools/kitchen_layout.py` também saiu; o planner é `layout.py`.

## Fluxo

```
consensus.json
  → tools/room_type.py            classifica o cômodo como KITCHEN pelo nome
  → tools/rooms/dispatch.py       get_brain(registry, KITCHEN) → layout.build_boxes
  → layout.build_boxes            segmenta a parede principal: geladeira → bancada (pia e cooktop embutidos) → torre;
                                  aéreo só sobre a bancada; 2ª parede livre ganha bancada extra
  → validation.require_kitchen_anchor   a pia tem de estar na parede OESTE do PDF; se não, o build ABORTA antes de renderizar
  → boxes (peças com módulo e cômodo) → tools/sketchup/furnish/place_layout_skp.rb   materializa como grupos no SketchUp
```

A pia é **ponto hidráulico fixo** do PDF (parede oeste). Mover de parede exige reforma hidráulica, não ajuste de layout.

## Dependências

- `core.scale`: `PT_TO_M`. A cozinha da `planta_74` roda com `0.0259`; `furnish_apartment` e o validador definem esse
  default antes do 1º import. Fixtures sintéticas usam a escala padrão: nunca no mesmo processo.
- `tools/rooms/shared/geometry.py` (`_fbox`, `_wall_setup`, `_window_zones`) e `tools/spatial_model.py`.
- `shapely` (interseções e módulos).

## Capacidades

Estados separados: **implementação**, **validação** e **visual** não se confundem
([spec FP-043 §5.2](../../../docs/specs/FP-043_repository_navigation_and_room_specialists.md)).

| Capacidade | Implementação | Validação | Visual |
|---|---|---|---|
| Layout linear (galley) em caixas/placeholders | implementada (`layout.build_boxes`) | L1: paleta/geometria dos boxes (`test_kitchen_layout_style`); L2 (SketchUp 26.0.429): as 76 peças do apê reabertas batem com o plano em 0,05 mm | pendente de revisão |
| Âncora da pia na parede oeste | implementada | L1 PASS; L2: pia, cooktop e coifa dentro da cozinha, sobre a bancada colada na parede oeste | n/a |
| Ergonomia (triângulo, folgas, aéreo) | implementada (`tools/kitchen_ergonomics.audit`) | L1 | n/a |
| Gabinete compartilhado (caixaria retangular + frentes lisas separadas) | implementado como **plano L1** em [`tools/rooms/shared/cabinet/plan.py`](../shared/cabinet/plan.py) → `plan_cabinet`; adapter da cozinha em [`capabilities/cabinet.py`](capabilities/cabinet.py) → `plan_kitchen_cabinet` | L1: `tests/test_cabinet_plan.py`, `tests/test_kitchen_cabinet_adapter.py`; L2 do construtor em micro-fixtures (P6b: 3 dimensões × 0°/90°/30°, reexecução, make_unique, edição local) **e na cozinha da planta_74** (P7: pedido inédito → `.skp` salvo/reaberto/inspecionado, `artifacts/review/fp043/p7_kitchen_cabinet/`); veio `NOT_SUPPORTED` | não revisado |
| Porta Shaker / frente rebaixada | **existe, mas NÃO está promovida**: plano puro e materialização com L2 sintético no módulo compartilhado ([`shared/cabinet/shaker/plan.py`](../shared/cabinet/shaker/plan.py), FP-046 P1–P3), adapter da cozinha com gates antes do job ([`capabilities/shaker.py`](capabilities/shaker.py), P4) e fluxo opt-in de pré-promoção ([`capabilities/shaker_flow.py`](capabilities/shaker_flow.py)). O binding `bind.kitchen.shaker` segue **sem capability** no catálogo (D46-09: a única fonte é descritiva) e a allowlist do perfil não inclui as ferramentas Shaker | `BLOCKED_CAPABILITY_MISSING` (o fluxo só roda com `prepromotion_ack=True`, argumento de código do operador) | L2 sintético: `artifacts/review/fp046/p3_shaker_l2/`; cozinha real: `artifacts/review/fp046/p4_kitchen_shaker_l2/` |
| Gavetas, ferragens, recorte de cuba em bancada | **ausentes** (recipes consultivas) | `BLOCKED_CAPABILITY_MISSING` | — |
| Lista de corte / fabricação | **ausente** | — | — |

Capacidades exclusivas da cozinha ficam em [`capabilities/`](capabilities/) (V-Ray, bake de tema, os `.rb` de recolor/ângulos e o adapter do gabinete). O adapter só planeja: o gabinete é aceito **depois** de `hydraulic_anchor` (pia na parede oeste), `architecture` (cabe na célula, sem tocar parede), `furniture_overlap` (sem sobrepor a mobília planejada) e `circulation` (zonas de porta livres + `circulation_gate` PASS), nesta ordem; o primeiro que falha para os demais. Ferragem, gaveta, porta Shaker, recorte de bancada/cuba e fabricação **não existem** e seguem `BLOCKED_CAPABILITY_MISSING`.

O percurso completo do pedido ao `.skp` é [`capabilities/cabinet_flow.py`](capabilities/cabinet_flow.py) → `run_request`: resolve cômodo e capacidade, exige insumos com unidade e origem, roda os 4 gates, confere a allowlist, materializa numa **cópia** da base, reabre o salvo em outro processo, verifica plano × geometria e devolve um trace (`kitchen_cabinet_trace.v1`) com hashes, commit e versão do SketchUp. Qualquer bloqueio (Shaker sem builder, ferramenta fora da allowlist, geometria impossível, insumo sem unidade/origem, alteração de arquitetura) volta **antes** de subir o SketchUp e deixa a entrada intacta; job interrompido não deixa resultado. O job Ruby que cria o grupo é [`tools/rooms/shared/cabinet/ruby/cabinet_build.rb`](../shared/cabinet/ruby/cabinet_build.rb); a evidência L2 (trace, negativos, job interrompido e o `.skp`) está em [`artifacts/review/fp043/p7_kitchen_cabinet/README.md`](../../../artifacts/review/fp043/p7_kitchen_cabinet/README.md).

O plano consultivo `cabinet_plan` ([`tools/sketchup/knowledge.py`](../../sketchup/knowledge.py)) devolve BOM proposta e
caixas de um caso sintético com `plan_state = BLOCKED_CAPABILITY_MISSING` e `execution_authorized = false`: **não é
plano de operação** e não gera Ruby nem `.skp`. As recipes de cozinha estão em
[`references/sketchup/knowledge/video_recipes.v1.json`](../../../references/sketchup/knowledge/video_recipes.v1.json) e
[`environment_recipes.v1.json`](../../../references/sketchup/knowledge/environment_recipes.v1.json)
(`room.kitchen.cabinet-assemblies`), todas `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`.

## Testes

| Teste | Cobre |
|---|---|
| `tests/test_fp042_kitchen_anchor_ownership.py` | a regra da pia mora em `anchor_rules` (que também expõe a CLI do gate) |
| `tests/test_fp042_kitchen_validation_boundary.py` | `validation.py` chama o validador uma vez e é fail-closed |
| `tests/test_fp042_kitchen_bathroom_builder_ownership.py` | dono único do layout de cozinha/banheiro e entradas legadas estáveis |
| `tests/test_kitchen_layout_style.py` | contratos determinísticos de paleta e geometria dos boxes (sem branco, pia lida de cima, cooktop fino); não julga beleza |
| `tests/test_kitchen_wall_regression_gate.py` | `kitchen_wall_regression_gate`: passagem preservada passa, parede sólida nova que a fecha falha |
| `tests/test_sketchup_knowledge.py` | plano consultivo do gabinete (`cabinet_plan`) |
| `tests/test_kitchen_cabinet_flow.py` | o fluxo vertical com SketchUp dublê: ordem do trace, idempotência, 8 bloqueios/negativos, job interrompido, verificação reprovada, PIDs fechados só por PID |
| `tests/test_cabinet_plan.py` | plano L1 do gabinete: 3 dimensões válidas (uma reservada, fixada por hash), geometria impossível, entrada incompleta, pose 0°/90°/30°, assinatura, `require_valid` |
| `tests/test_kitchen_cabinet_adapter.py` | os quatro gates da cozinha, ordem e curto-circuito; consensus/fixture canônicos intactos (escala da planta_74) |

## Provas

- L2 no SketchUp real, com o que passou, o que falhou e o que ficou pendente:
  [`artifacts/review/l2_fp042_20261019/README.md`](../../../artifacts/review/l2_fp042_20261019/README.md) (seção «Cozinha»).
- Entregável mobiliado canônico: `artifacts/planta_74/furnished/`.

## Limites

- Peças são **placeholders** (caixas e perfis), não marcenaria: sem caixaria desmontável, gavetas, ferragens ou lista de corte.
- Aparência (materiais, proporções) não é aprovada por este módulo: revisão visual é do Felipe.
- O corpo da geladeira nasce com `z0 = 2 cm` por desenho do layout (sem peça de pé); registrado, não corrigido.
- `kitchen_ergonomics`, `kitchen_wall_regression_gate`, `kitchen_vray` e os `.rb` de render/tema da cozinha ainda moram em `tools/` até P4.
