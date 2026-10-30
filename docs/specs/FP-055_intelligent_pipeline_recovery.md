# FP-055 — Intelligent Pipeline Recovery & End-to-End Integration

```yaml
id: FP-055
versao: 1.0.0
status: EM_EXECUCAO        # P0-P4 entregues; P4 = infraestrutura de validacao do construido
prioridade: P0_CRITICAL
projeto_piloto: planta_74
dependencias: [FP-042, FP-043, FP-054, PR-394, PR-396]
politica:
  preservar_artefatos_oficiais: true
  preservar_provas_L1_L2: true
  proibir_fallback_silencioso: true
  aprovar_alteracao_visual_automaticamente: false
origem: pedido do Felipe no chat (2026-10-23), depois da auditoria de proveniencia do .skp renderizado
```

## Problema
A auditoria de 2026-10-23 mostrou que o modelo mostrado era antigo e que a geração atual não executa a maior parte da
inteligência entregue. Ela despacha por tipo de cômodo, sem especialistas, receitas, interfaces F1C, solver F2 nem gates
funcionais e de colisão. O checkout do MCP está 102 commits atrás. Detalhe e evidência em
[`docs/reports/fp055/p0/`](../reports/fp055/p0/README.md).

Causa-raiz (hipótese, confirmada no P0 por rastreio): o trabalho foi organizado por capacidade e módulo, não por fluxo de valor.
"Tem teste" virou "entregue" sem participar da geração.

## Decisões inegociáveis
| ID | Regra | Como se aplica aqui |
|---|---|---|
| D-001 | Fonte de verdade = PDF/consensus + decisões formais | `fixtures/planta_74/consensus_*.json`, `layout_decisions.py`; `.skp` antigo é baseline, nunca entrada |
| D-002 | Uma entrada canônica | novo orquestrador; `furnish_apartment.main` e `su_furnish` viram adaptadores do perfil `LEGACY_DIAGNOSTIC` |
| D-003 | Especialista = autoridade do cômodo | `tools/rooms/<cômodo>/specialist.v1.json` + `solver_policy.py`; não reimplementa o solver |
| D-004 | Matemática e construção comum em `shared` | `tools/rooms/shared/spatial_solver/`, `shared/cabinet/` |
| D-005 | Solver antes da construção | o builder recebe a proposta validada; adaptação explícita e revalidada |
| D-006 | Fail closed | dado obrigatório ausente ou violação rígida → sem rótulo de válido (diagnóstico continua permitido) |
| D-007 | Proveniência operacional | `RunManifest` por geração |
| D-008 | Estados de aprovação independentes | testes ≠ geração ≠ geometria ≠ função ≠ visual ≠ oficial |
| D-009 | Provas preservadas | R-18, catálogo, `capability-l2-proof` |
| D-010 | Incremental | uma fatia vertical por vez (Banho 02 primeiro) |

## Perfis (Strangler Fig)
`LEGACY_DIAGNOSTIC` (caminho atual; nunca publica como validado) · `INTELLIGENT_DRY_RUN` (propostas + evidência, sem SketchUp) ·
`INTELLIGENT_BUILD` (constrói em `runs/` só com as pré-condições). Escrita em `artifacts/` só com `allow_official_write: true`,
gates verdes **e** aprovação humana.

## Contratos (P2)
`GenerationRequest` · `RoomContext` · `SpecialistPlan` · `LayoutProposal` · `BuildResult` · `ValidationReport`
(`PASS/FAIL/BLOCKED/NOT_APPLICABLE/NOT_EXECUTED`) · `RunManifest` com os estados `AVAILABLE/SELECTED/INVOKED/CONSUMED/
REFLECTED_IN_MODEL/VALIDATED`. Cada contrato tem produtor, consumidor e teste de compatibilidade; campo obrigatório nunca é
descartado em silêncio (o descarte de `out["functional_interfaces"]` é o caso-teste).

## Fases e gates
| Fase | Entrega | Gate |
|---|---|---|
| P0 | inventário, runtime, grafo de execução, lacunas, baseline (**esta PR**) | entrypoints classificados; nada crítico com estado desconhecido |
| P1 | identidade de runtime (commit esperado × checkout do MCP), versão do SketchUp/bridge; bloquear geração inteligente com runtime divergente | divergência bloqueada ou autorizada como dev, de forma verificável |
| P2 | DTOs/schemas + testes de contrato | todo contrato com produtor, consumidor e teste |
| P3 | orquestrador: contexto → especialista → receitas → requisitos → solver → proposta → builder → comparação → gates → manifesto | fixture: mudar uma restrição do especialista muda ou bloqueia a proposta, com rastro |
| P4 | Banho 02 vertical no SketchUp real | solução na fixture controlada + resultado real (válido, INFEASIBLE comprovado ou UNKNOWN justificado) |
| P5 | receitas → operação → implementação → prova; separar regra funcional / receita construtiva / referência estética | uma técnica de marcenaria compartilhada usada por 2 componentes |
| P6 | expansão por cômodo (Banho 01, Lavabo, Cozinha, Suítes, Sala, Serviço, …) | todo cômodo com estado final explícito |
| P7 | gates de CI + qualificação SketchUp real + relatório de não consumidos + mutação de integração | pipeline que descarta interface ou roda código velho falha de forma demonstrável |
| P8 | geração limpa integrada + manifesto + renders e overlays novos | reproduzível pelo manifesto, com equivalência semântica |
| P9 | reconciliação final, estado por capacidade | nenhuma lacuna escondida; 0 PR aberta |

### Estado em 2026-10-24 (backlog: GitHub Project #1)
| Fase | Estado | Evidência / Issue |
|---|---|---|
| P0–P3 | feitas | `docs/reports/fp055/p0..p3/` |
| P4 | validação do construído feita; vertical Banho 02 real a reconciliar | #421, #422 |
| Caminho legado | endurecido: saída segura, pré-voo obrigatório, guard de banheiro bloqueante, interfaces expostas | #423, #424, #425, #427; #490 (demais escritores) |
| P5 receitas → operação | parcial: resolução receita→capacidade→operação→símbolo→prova (`tools/rooms/recipe_resolution.py`, somente leitura); falta técnica compartilhada em 2 componentes (medida hoje: nenhuma) e ligar ao `plan_room` | #416 |
| P6 expansão por cômodo | não iniciada | #417 |
| P7 gates | parcial: gate de consumo e relatório de não consumidos; falta qualificação SU como pré-condição e mutação do orquestrador integrado | #418, #479; `docs/reports/fp055/p7/` |
| P8/P9 | dependem de P5–P7 e da FP-056 P6 | #419, #420 |

## Regressão obrigatória
Os 8 defeitos (baseline em `docs/reports/fp055/p0/baseline_manifest.json`) ficam medidos antes e depois. Nunca se corrige
mexendo em limiar ou tirando validação. A F2 já mostrou que, no grau de liberdade declarado, os três banheiros são INFEASIBLE:
integrar não os conserta. A saída real é uma decisão do Felipe (vão do box no builder, parede ou louça do vaso). Até lá, o
resultado honesto é `INFEASIBLE` com o motivo.

## Risco arquitetural prioritário — R-ARCH-01 (FP-043 P3a-03 / D-007)
A validação sobre a geometria construída (P4) confirmou na planta real o defeito conhecido da FP-043. O espaço de mobiliar
dos planejadores é a laje construtiva, que entra `FLOOR_UNDER_FRAC = 0,4 × espessura` sob a parede
(`tools/sketchup/shell/build_plan_shell_skp.py:664`). Resultado: móveis dentro da parede (11 ocorrências R1), além de
peças sobre área sem laje (R2b) e atravessando barreira de varanda (R2a). Registro completo, por causa-raiz e por cômodo:
`artifacts/review/fp055/p4/`. Tratamento:
- correção **na origem**, pela FP-056 (`docs/specs/FP-056_usable_space_support_barriers.md`), começando pela separação
  `ConstructedFloorGeometry` × `UsablePlacementRegion`. É prioritária sobre P5/P6;
- o validador não ganha exceção, e nenhum limiar muda para esconder ocorrência;
- vigente desde já: gate de não regressão contra `artifacts/review/fp055/p4/defect_baseline.json` (defeito novo ou pior
  reprova).

## Fora do escopo
Reescrever o projeto; mudar dimensões estruturais; inventar dado ausente do PDF; promover blog a norma; aplicar mudança no `.skp`
oficial sem aprovação; aprovar aparência.

## Definição de concluído
Os 16 itens do Bloco 14 do pedido original. Requisito pendente → `PARTIALLY_COMPLETED` ou `BLOCKED`, nunca "concluído".
