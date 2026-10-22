# 📐 FP-048 — Núcleo Geométrico e Capabilities Compartilhadas
> SPEC SDD · SketchUp MCP · Python / Ruby / SketchUp Windows

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-048 — Operações geométricas e contratos cross-room"
  escopo_versao: "Padronizar geometria, quadros de referência e componentes reutilizáveis em dois cômodos sem duplicação nem quebra dos builders existentes."
  versao: "1.0.0"
  status: RASCUNHO
  classificacao:
    contexto_delimitado: "Ferramentas geométricas compartilhadas"
    dominio: "SketchUp MCP / arquitetura por cômodo"
    funcionalidade: "Geometria tipada, transformações, materiais, componente e reuse"
  baseline_develop: "029f9685a17bb720d6af426a25d8afe66f0472dc"
  spec_pai: "FP-045"
  dependencias: ["FP-046", "FP-047"]
  proxima_consumidora: "FP-049"
  data: "2026-10-21"
  branch_destino: "develop"
```

### Contexto verificado

O repositório possui `tools/rooms/shared/geometry.py`, `shared/cabinet/{model,assembly,plan,validation,sketchup}.py` e `shared/{wardrobe,bed,nightstand,anatomy,materials}.py`. O cabinet usa +X largura, +Y fundo-para-frente, +Z altura. O wardrobe usa X largura, frente em Y=0 e vetor frontal -Y. Essa diferença é real e impede reuso ingênuo por simples cópia das caixas. O `shared.wardrobe.build_wardrobe` produz peças e metadata, não prova de SKP editável. O especialista `closet` reutiliza bedroom com allowlist vazia. `tools.rooms.specialists.plan` planeja consultivamente. FP-046 e FP-047 ainda eram PRs draft no início desta especificação.

**Objetivo:** uma única implementação por operação reutilizável; adapters dos cômodos impõem restrições locais. Não criar framework vazio nem reimplementar a técnica Shaker (FP-046).

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Escopo e fases

Dentro: mapear primitivos atuais, modelo de parte semântica, contrato de transformada local/mundo, validações de definição/instância, 2 consumidores (kitchen + bedroom), catálogo, testes e execução Windows L2. Fora: arquitetura da planta, porta de correr, gaveta nova, mudança estética sem revisão, reescrita de sofa/bed/wardrobe e Ruby genérico.

| Fase | Entrega | Prova |
|---|---|---|
| F0 | grafo de operações existentes, donos, duplicações | relatório versionado; comparação de frames +Y/-Y |
| F1 | contratos `shared_geometry_part.v1` e `shared_transform.v1` | JSON Schema, exemplos e negativos |
| F2 | conversão determinística entre frames | 0°, 30°, 90°, 180°, ida/volta, handedness |
| F3 | operação shared pequena e estável | peça/painel/definição com IDs e assinatura |
| F4 | adapters cozinha/quarto independentes | mesmos símbolos shared, gates locais intactos |
| F5 | catalog/profiles/allowlist verificáveis | capability sem prova não executa |
| F6 | integração L2 Windows + FP-047 | SKP copiado, editável, reaberto, sem mudanças fora do escopo |
| F7 | rollout e relatório final | CA-19 completo, rollback por fatia |

### 2.2 Arquitetura

```text
registry + specialists.plan [consulta]
  -> recipe/source + capability_catalog.verify
  -> shared.geometry_contract [PROPOSTO]
  -> shared.operations [PROPOSTO; extrair só algo que já se repete]
  -> kitchen adapter | bedroom adapter
  -> gates do cômodo + FP-047
  -> materializador tipado e allowlisted
  -> cópia .skp -> reabrir/inspecionar -> prova L2
  -> revisão humana L3 se aparência mudar
```

**Separação:** operação geométrica (painel, perfil, extrusão, recorte) ≠ capability (porta Shaker, gabinete, gaveta) ≠ especialista (regras de cozinha/quarto). Um especialista só pode selecionar capability implementada e comprovada. Função no shared não concede automaticamente permissão de execução.

#### 2.2.1 Fluxo obrigatório

1. Resolver projeto, room id e recipe com fontes e evidência. Fonte/recipe inválida → bloquear.
2. Consultar catalog e profiles; sem capability validada/allowlist: `BLOCKED_CAPABILITY_MISSING`.
3. Validar todas as medidas com `value/unit/origin`; converter para metros, sem valores de fabricante inventados.
4. Resolver frame explicitamente, incluindo normal frontal, handedness, eixos e matriz de pose.
5. Converter gabinete +Y para wardrobe -Y sem inverter face/puxador silenciosamente; aplicar roundtrip e determinant check.
6. Gerar peças com IDs semânticos, parent, roles, envelopes, material, grain e transformada.
7. Validar volumes, contato permitido vs interseção indevida, definição compartilhada e `make_unique`.
8. Assinar plano, validar assinatura antes de materializar, proibir esquema estranho.
9. Adaptar o plano aos gates específicos: cozinha (pia oeste/arquitetura/colisões/circulação); quarto (paredes/aberturas/circulação).
10. Executar job SketchUp somente em cópia de trabalho nova via allowlist e PID próprio.
11. Reabrir e provar componentes, geometria, materiais, hierarquia e isolamento entre instâncias.
12. Vincular evidências a commit, symbols, source, fixture, SHA e versão real do SketchUp. L3 só decisão humana.

#### 2.2.2 Regras numeradas

| Regra | Condição | Resultado |
|---|---|---|
| R-01 | operação necessária em dois cômodos | implementação canônica no shared |
| R-02 | shared importa bedroom/kitchen | ownership FAIL |
| R-03 | capability ausente | bloquear, sem Ruby improvisado |
| R-04 | medidas sem unit/origin | recusar antes de abrir SketchUp |
| R-05 | frame desconhecido | `FRAME_AMBIGUOUS` proposto |
| R-06 | +Y gabinete / -Y wardrobe | converter com teste de normal frontal |
| R-07 | rot 30 graus | preservar geometria e handedness |
| R-08 | reflection implícita | negar sem ADR e prova |
| R-09 | mm e m equivalentes | geometria normalizada equivalente |
| R-10 | peça com volume zero | REFUSED com campo/causa |
| R-11 | solicitação de recorte não implementado | BLOCKED, não textura falsa |
| R-12 | definição compartilhada | papel, dimensões, material, grão e geometria equivalentes |
| R-13 | editar uma instância | make_unique sem alterar as demais |
| R-14 | mesmo pedido | IDs/assinatura determinísticos |
| R-15 | assinatura adulterada | materializador rejeita |
| R-16 | regra hidráulica dentro do shared | erro de ownership |
| R-17 | adapter cozinha | quatro gates intactos |
| R-18 | adapter quarto | parede/janela/porta livres |
| R-19 | closet sem executor | consultivo, não simular L2 |
| R-20 | FP-046 draft/sem prova | Shaker continua bloqueado |
| R-21 | código pós-evidência alterado | marcar stale |
| R-22 | CI Linux verde | L1, não L2 |
| R-23 | mudança de aparência | PENDING_HUMAN |
| R-24 | canônico muda | FAIL e rollback |
| R-25 | API antiga usada | preservar saída legada |
| R-26 | job falha | base intacta e manifesto FAILED |
| R-27 | alias de cômodo não resolvido | recusar |
| R-28 | teste/fixture faltando no catalog | impedir promoção |

### 2.3 Componentes

| Caminho | Ação |
|---|---|
| `tools/rooms/shared/geometry.py` | aproveitar boxes e coordenadas existentes |
| `tools/rooms/shared/sofa.py` | mapear `_p`, `parts_to_boxes`, `place_sofa_boxes`; não clonar |
| `tools/rooms/shared/cabinet/{model,assembly,plan,validation,sketchup}.py` | preservar assinatura e saída v1 |
| `tools/rooms/shared/{wardrobe,nightstand,bed,anatomy,materials}.py` | consumers e anatomia |
| `tools/rooms/{registry,specialists,capability_catalog}.py` | routing, provas e binding |
| `tools/rooms/ownership_audit.py` | guardas arquiteturais |
| **PROPOSTO** `tools/rooms/shared/geometry_contract.py` | frame, part, transform tipados |
| **PROPOSTO** `tools/rooms/shared/operations.py` | apenas operadores comprovadamente comuns |
| **PROPOSTO** `core/schemas/shared_geometry_part.v1.schema.json` | validação das partes |
| **PROPOSTO** `tests/test_fp048_frames.py` | roundtrip, rotação e reflexões |
| **PROPOSTO** `tests/test_fp048_cross_room.py` | mesma operação, duas consumers reais |
| `docs/specs/fp042_inventory.v1.json` | ownership de cada novo arquivo |

### 2.4 API/Schema propostos (não existentes)

```json
{
  "schema_version": "shared_geometry_part.v1",
  "part_id": "pilot/painel",
  "parent_id": "pilot/assembly",
  "role": "front_panel",
  "geometry": {"kind": "box", "min_m": [0.0, 0.0, 0.0], "max_m": [0.6, 0.018, 0.72]},
  "frame": {
    "width_axis": "+X", "front_normal": [0, -1, 0], "up_axis": "+Z",
    "handedness": "right", "pose_origin": "user_request"
  },
  "material": {"id": "mdf_sintetico", "origin": "user_request"},
  "grain": {"direction": "none", "support": "NOT_SUPPORTED"},
  "edit_policy": "MAKE_UNIQUE_ON_LOCAL_CHANGE",
  "recipe_id": "cabinet.reusable-components",
  "geometry_signature": null,
  "execution_authorized": false
}
```

Valores do exemplo são sintéticos, **não defaults**. `geometry_signature=null` é falta de prova, nunca autorização. `shared_transform.v1` deverá declarar source/target frame, pose com valor/unidade/origem, matriz rígida, inversa e determinant; refletir pede operação distinta e ADR. APIs reais atuais: `shared.wardrobe.build_wardrobe(spec)`, `shared.cabinet.assembly.build_parts(params)`, `shared.cabinet.plan.plan_cabinet(request)`, `require_valid(plan)` e `shared.cabinet.sketchup.materialize/inspect/verify`. Não fingir que esses tipos já são interoperáveis.

### 2.5 Eventos e mensagens

Kafka, SQS, Avro, DLQ, HTTP e ACK manual: **N/A**. Processo local com trace JSON e manifesto, no modelo de idempotência de cabinet_flow. Retry nunca duplica raiz e não deixa falso PASS se SketchUp falhar.

### 2.6 Dados, observabilidade e RNFs

`Part` (ID, role, material, frame, bounds), `Assembly` (parts, definitions, assinatura), `Frame` (bases, normal frontal, transform/inversa), `Proof` (recipe, symbol digests, tests, L1/L2/L3), `RunManifest` (commit, hash, job próprio, versão SketchUp, output).

RNFs: determinismo, retrocompatibilidade, ausência de import cross-room, sem modificar PDF/fixtures/SKP canônicos, editabilidade em SketchUp real, logging por request/part/frame/source e separação honesta de L1/L2/L3. L2 só em Windows real; L3 depende de Felipe.

### 2.7 Testes e critérios de aceite

**L1:** micro-fixture de um painel nas duas convenções; transformar 0, 30, 90, 180 graus; testar normal/handedness (bbox sozinho insuficiente). Testar origens, units e adulteração de assinatura; confirmar duas consumers importam o mesmo símbolo shared, não cópia de código.

**L2:** job real em SketchUp Windows, salvar/reabrir dois modelos de trabalho, comparar IDs, vértices, instâncias e materiais; testar `make_unique`. Sem Windows, evidência pendente. L3: revisão humana se afetar apartamento.

| CA | Given | When | Then |
|---|---|---|---|
| CA-01 | operações existentes | auditar F0 | mapa/ownership documentados |
| CA-02 | shared importa room | rodar gate | FAIL |
| CA-03 | origem ausente | planejar | REFUSED |
| CA-04 | frame desconhecido | converter | BLOCKED |
| CA-05 | gabinete +Y e wardrobe -Y | transformar | normal frontal correta |
| CA-06 | rot 30 graus | aplicar e inverter | posições/normais conservadas |
| CA-07 | reflection não declarada | validar | FAIL |
| CA-08 | mm vs m | converter | geometria equivalente |
| CA-09 | material diferente | compartilhar definition | bloqueado |
| CA-10 | parts equivalentes | compartilhar definition | permitido |
| CA-11 | editar A | make_unique | B permanece igual |
| CA-12 | request repetido | criar plano | mesmos IDs/hash |
| CA-13 | assinatura adulterada | job | não executa |
| CA-14 | recipe sem builder | routing | bloqueio explícito |
| CA-15 | símbolo alterado | verificar catálogo | stale |
| CA-16 | kitchen usa shared | validar | âncora e quatro gates preservados |
| CA-17 | bedroom usa shared | validar | parede/aberturas preservadas |
| CA-18 | dois consumers | analisar imports | mesmo símbolo shared |
| **CA-19** | fases implementadas | rodar E2E | 4 checks CI + dois consumidores + L2 real reaberto + SHA intacto + L3 se necessário; senão PARTIAL |
| CA-20 | closet allowlist vazia | executar | BLOCKED |
| CA-21 | Shaker não mergeado | pedir porta | não duplicar, aguardar |
| CA-22 | recorte ainda inexistente | planejar | BLOCKED |
| CA-23 | API legada | regressão | sem mudança indevida |
| CA-24 | CI só Linux | publicar relatório | L2 PENDING_SKETCHUP |
| CA-25 | fonte canônica diferente | gate | FAIL |

**Comandos base:** `python -m tools.rooms.inventory_gate --strict`, `python -m tools.rooms.ownership_audit`, `python -m tools.rooms.capability_catalog`, `python -m tools.mcp_server.smoke`, `python -m tools.mcp_server.stdio_check`, `pytest -m "not planta74_scale"` e `PT_TO_M=0.0259 pytest -m planta74_scale` em processos separados. Para `quadrado` e `planta_74` consultar o entrypoint atual em `.github/workflows/ci.yml`: o alias `tools/run_deterministic_gates.py` foi removido na FP-045/F2, não ressuscitar.

### 2.8 Lançamento, rollback e ADRs

F0/F1 PR documentação/esquema → F2 transform testes → F3 primitive shared → F4 dois adapters → F5 catálogo → F6 L2/FP-047 → F7 relatório. Não alterar nenhum canônico; refatoração `strict_identity`, mudança funcional `scoped_change` conforme FP-047. Cada PR com testes, inventário FP-042 atualizado e quatro checks verdes.

ADRs propostas: ADR-048-01 convenções +Y/-Y e handedness; ADR-048-02 equivalência de definitions e `make_unique`; ADR-048-03 limites de primitive vs capability e permissão. Rollback por `git revert`, hashes dos originais mantidos; invalidar provas stale após mudança.

## 🔄 BLOCO 3 — Governança

| Decisão | Estado |
|---|---|
| D48-01 ferramenta ≠ capability ≠ especialista | RESOLVIDA |
| D48-02 shared nunca importa código de cômodo | RESOLVIDA |
| D48-03 piloto usa kitchen + bedroom | RESOLVIDA |
| D48-04 ADR matemática +Y/-Y | PENDENTE TÉCNICA |
| D48-05 definição/instance edit compatível | PENDENTE TÉCNICA |
| D48-06 depender de FP-046/047 somente após merge/prova | PENDENTE DEPENDÊNCIA |
| D48-07 resultado visual do apartamento | PENDENTE FELIPE |

**Handoff:** confirmar HEAD e PRs novos; começar por F0 e negativos F1/F2, não mover builders antes das provas; fazer uma primitive shared real e dois consumidores, testar CI e Windows quando necessário; respeitar `PENDING_HUMAN`; publicar evidência do CA-19, digests e rollback.

**Checklist:** [x] metadata, arquitetura, fases, ownership, 28 regras, schema proposto, testes negativos, 25 CAs e CA-19, L1/L2/L3, rollback e handoff. [ ] Implementação F0–F7: pendente. **Criar a SPEC não significa implementar ou aprovar aparência.**
