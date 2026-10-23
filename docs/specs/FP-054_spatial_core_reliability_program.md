# 📐 FP-045 — Programa de Confiabilidade do Núcleo Espacial, Algoritmos e SketchUp MCP

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 abaixo. Evidências em `docs/reports/fp054/`.


## §0 — Validação contra o código e reconciliação (Claude, 2026-10-23, `develop@45e50ea`)

Registro: recebida como **FP-045 MASTER** + F0–F5 + kickoff; arquivos do pacote preservados como `FP-054*`. Esta seção NÃO
muda a intenção da spec — só ancora no que existe e corrige o que divergiu.

| # | Ponto | Situação real | Ajuste |
|---|---|---|---|
| 1 | Numeração | FP-045…FP-053 já existem; a FP-045 do repo é especialistas/modularização (mergeada) | esta spec = **FP-054**; evidências em `docs/reports/fp054/` (não `docs/reports/FP-045/`) |
| 2 | Leituras obrigatórias (BLOCO 12) | todas existem em `develop@45e50ea`, inclusive `docs/architecture/specialists.md` | — |
| 3 | `harness-app` | `GFCDOTA/harness-app`, branch canônica `develop` @ `5ca598b`, sincronizada, 0 PRs abertos | F0 registra o SHA no baseline |
| 4 | Vocabulário de estado | o catálogo já tem `UNTESTED/L1_PASS/L2_PASS/FAILED/BLOCKED` e visual `NOT_REVIEWED/APPROVED/CHANGES_REQUESTED/NOT_APPLICABLE` | F4 reaproveita: `VISUAL_REVIEWED` = visual `APPROVED`/`CHANGES_REQUESTED`; `BLOCKED_L2` = `BLOCKED` + motivo. Os status de `ConstraintResult` (BLOCO 4) são novos e só valem para gates |
| 5 | Dependências da F2 | `scipy` e OR-Tools/CP-SAT **não** estão no `pyproject.toml` (hoje: shapely, numpy, pypdfium2, Pillow, matplotlib; dev: pytest, ruff, hypothesis) | adotar só com benchmark contra a referência enumerativa e ADR (BLOCO 7.4: "não adotar por hype") |
| 6 | "Relato não reproduzido" (BLOCO 1) | reproduzido e versionado: 28 candidatos da grade + 9 de refino = 37 checagens, ~0,1 s (`artifacts/review/perf/dining_search_2026-10-23/`, `docs/reports/construction_core/geometry_hot_paths.md`, trava `tests/test_layout_search_pruning.py` ≤ 40) | F0 mede de novo em benchmark versionado com seeds, p50/p95 e memória |
| 7 | Especialistas | 9 perfis + **20 fragmentos** (`tools/rooms/<cômodo>/fragments/`, #366) + catálogo com 18 capacidades (5 L2) | F3 parte daí; os 27 papéis seguem só como taxonomia |
| 8 | CI | hoje 4 checks obrigatórios (pytest 3.11, pytest 3.12, deterministic fidelity gates, mcp smoke+stdio) | os jobs do BLOCO 9 são **alvo**; L2 Windows não existe no CI → `BLOCKED_L2` fora da estação local |
| 9 | Hipótese para a F1 (não é fato) | `circulation_gate` com < 2 portais deixa `corredor_principal` = PASS (só anota `"erro"` no detalhe) | primeiro candidato a falso PASS: provar com fixture negativa na F1 antes de mexer |
| 10 | Precedência | FP-051/052/053 têm trilhas de aprendizado/tutorial | congeladas pela FP-054 até a F5 liberar (BLOCO 2); itens de núcleo do mapa de microfases (T0.x) seguem como insumo da F1–F3 |

> SPEC-mãe SDD · sketchup-mcp + harness-app · versão 1.0.0 · status PROPOSTA PARA EXECUÇÃO

## BLOCO 1 — Metadata e decisão
```yaml
spec:
  feature: "FP-045 Spatial Core Reliability & Quality Program"
  escopo_versão: "Auditar, corrigir e provar o núcleo de modelagem/planejamento/validação antes de expandir tutoriais ou capacidade estética"
  versao: "1.0.0"
  status: "PROPOSTA_PARA_EXECUCAO"
  prioridade: "P0: confiabilidade"
  repositorios: ["GFCDOTA/sketchup-mcp", "harness-app (confirmar remote e branch)"]
  branch_base: develop
  preservacao: ["PDF como fonte", "SKP canônico", "fixtures protegidas", "hashes", "evidências anteriores", "compatibilidade MCP"]
  politica_de_release: "fail-closed e evidência por capacidade; nenhuma aprovação por mera ausência de exceções"
```

### Contexto verificado x hipótese
- **Verificado por leitura de código/documentos em `develop` em 2026-10-23:** `tools/validation/circulation_gate.py`, `tools/rooms/shared/spatial_model.py`, `README.md`, `tools/rooms/README.md`, `docs/architecture/repository_map.md`, `docs/reports/FP-043_final_validation.md`. A aplicação usa Python/Shapely e Ruby/SketchUp; existe catálogo de 9 perfis, módulos por cômodo e níveis L1/L2. FP-043 já contém evidências e pendências expressas.
- **Relato operacional ainda não reproduzido nesta SPEC:** grade de 15 cm, 28 candidatos, 9 refinamentos e ~0,1 s. Esses números são observações a verificar em benchmark versionado, não requisitos de implementação.
- **Hipóteses que exigem prova:** aceitação inadequada de portas/cadeiras, falso positivo em circulação, excessiva sensibilidade a nomes, limiares, e busca espacial insuficiente. Nenhum diagnóstico está automaticamente provado sem fixture negativa.
- **Não há auditoria exaustiva ainda:** o inventário e a execução das suítes fazem parte das fases. Não afirmar “todos os arquivos auditados”, “27 agentes já existem” ou “SketchUp L2 aprovado” sem evidência atual.

## BLOCO 2 — Visão, objetivos e não objetivos
**Objetivo principal:** produzir layouts **fisicamente viáveis, funcionalmente utilizáveis, arquitetonicamente coerentes e explicáveis**, com validação automatizada confiável, repetível e independente da opinião visual do usuário.

**Objetivos verificáveis:**
1. Identificar 100% dos caminhos ativos/versionados e associá-los a owners; classificar rotas críticas e dependências entre `core`, `interior`, `tools/rooms`, `tools/validation`, `tools/orchestration`, `tools/sketchup`, `tools/mcp_server`, `ops`, `tests` e `harness-app`.
2. Cada gate crítico possuir ao menos um teste positivo, um negativo, casos-limite e teste de entrada incompleta (fail-closed/UNKNOWN_BLOCKED).
3. Corrigir primeiro violações de invariantes, antes de desempenho ou estética; preservar e registrar contraprovocação de bugs.
4. Determinar se existe solução, por que existe/não existe, quais restrições a tornam impossível e quais alternativas são melhores.
5. Separar validade física, ergonomia, funcionalidade, qualidade de layout, qualidade estética e evidência de materialização, com estados independentes.
6. Tornar benchmarks reproduzíveis (hardware, commit, sementes, entrada, número de objetos, p50/p95, memória e complexidade).
7. Provar no SketchUp real as classes de mudança que afetam modelagem/materialização (não apenas Python).

**Não objetivos até a liberação do core:** novas receitas RAG, vídeos/transcrições, novos estilos, expansão massiva de móveis, alteração silenciosa da planta ou substituição geral da linguagem. Preservar tudo já realizado; congelar expansão, não apagar artefatos.

## BLOCO 3 — Princípios inegociáveis
- **Correctness > performance > features**; um algoritmo rápido errado continua errado.
- **Fail closed:** ausência de portal, semântica, unidade, dimensões ou geometria válida não pode virar PASS. Definir `PASS`, `FAIL`, `BLOCKED_MISSING_INPUT`, `NOT_APPLICABLE`, `WARN` com tipagem forte.
- **Severidade não é decisão visual:** gates determinísticos medem regras; julgamentos estéticos exigem métricas explícitas ou revisão humana; não inventar selo de “bonito”.
- **Fonte de verdade única:** unidade/escala/ID/semântica projetual definidos em `core`; política de projeto separada de algoritmos.
- **Um dono por capacidade:** especialistas de ambientes compõem serviços shared, sem clonar geometrias ou validadores.
- **Controle de regressão:** baseline imutável e comparação por SHA; nunca alterar fixture de referência para fazer teste passar sem decisão formal.
- **Mudanças graduais:** preservar MCP público e resultados de outros cômodos; migração estranguladora com adapters temporários e data de remoção.
- **Condição de saída baseada em evidências:** CI verde não significa SKP correto; L1, integração, L2 SketchUp e qualidade funcional são diferentes.
- **Prova adversarial:** cada mudança de gate deve trazer contraprova de falso PASS ou falso FAIL e teste metamórfico.
- **Sem PR abandonado:** PR integrar após checks e revisão, ou fechar com motivo registrado; jamais mergear testes quebrados só para esvaziar fila.

## BLOCO 4 — Arquitetura-alvo (proposta, sujeita ao inventário)
```
user goal / planner policy
  -> room capability contracts (living, kitchen, bedroom, bathroom, service, balcony, closet, office, circulation)
  -> shared spatial services [geometry model, topology, clearance, doors, obstacle semantics,
                              constraint engine, candidate generation, solver, objective ranking]
  -> independent validation [contract checks, geometry invariants, circulation, ergonomics,
                             quality scores, diagnostics]
  -> SketchUp executor [MCP -> jobs -> Ruby -> SKP]
  -> independent inspection / evidence [SKP reopen, entities/bbox/transforms, snapshots,
                                        reports, consistency comparisons]
```

### Interfaces sugeridas (nomes orientativos)
```python
@dataclass(frozen=True)
class PlacementProblem:
    scene: SceneSnapshot
    movable: tuple[FurnitureSpec, ...]
    immovable: tuple[Obstacle, ...]
    rules: tuple[Constraint, ...]
    preferences: tuple[Objective, ...]
    policy_version: str
    seed: int

@dataclass(frozen=True)
class ConstraintResult:
    rule_id: str
    status: Literal['PASS','FAIL','BLOCKED_MISSING_INPUT','NOT_APPLICABLE','WARN']
    measured: float | None
    threshold: float | None
    units: str | None
    witness_geometry: object | None
    evidence: dict

@dataclass(frozen=True)
class PlacementDecision:
    status: Literal['FEASIBLE','INFEASIBLE','UNKNOWN']
    candidates_evaluated: int
    selected: object | None
    alternatives: tuple[object, ...]
    constraints: tuple[ConstraintResult, ...]
    scores: dict[str, float]
    reason_codes: tuple[str, ...]
```
**Importante:** o solver nunca pode mudar regra hard para obter solução; pode sugerir relaxamento com aprovação explícita, sem executar silenciosamente. Preferências são soft, restrições físicas hard.

## BLOCO 5 — Programa faseado: dependências e gates
| Fase | SPEC-filha | Trabalho | Gate obrigatório |
|---|---|---|---|
| F0 | FP-045-F0 | congelamento, inventário, métricas e baseline | inventário reconciliado; baseline reproduzível |
| F1 | FP-045-F1 | contratos, semântica e gates de geometria/circulação | teste negativo falha antes, passa após correção, sem falso PASS |
| F2 | FP-045-F2 | algoritmo de posicionamento e ranking | solução viável ou prova de inviabilidade; qualidade >= baseline nos cenários-alvo |
| F3 | FP-045-F3 | micropartições, DSA, benchmark e arquitetura | comportamento preservado + ganho medido; sem duplicidade de owner |
| F4 | FP-045-F4 | testes end-to-end e SketchUp real | round-trip e medição independente no SKP real |
| F5 | FP-045-F5 | escala para todos ambientes, governança e liberação | matriz de capacidades e lacunas assinadas com evidência |

**Ordem:** F0 -> F1 -> F2 -> F3 -> F4 -> F5. Patches urgentes de F1 podem ocorrer antes de F0 completo somente com fixture de reprodução, risco documentado e rebase na matriz. F4 executa microchecks em cada PR que afete Ruby, além de sua campanha global.

## BLOCO 6 — Matriz de testes (obrigatória)
| Camada | Casos exemplares | Frequência |
|---|---|---|
| Unitária | unidades/escala, normais, rotação, invalid polygons, naming/ID, missing portal, roles, hierarquia de objetos, clearance | cada PR |
| Property-based | invariância translação/rotação, monotonicidade de adição de obstáculo, determinismo, simetria e limites de epsilon | cada PR relevante |
| Contraprovas | polígono desconectado, porta parcialmente bloqueada, cadeira puxada contra parede, corredor aparente, falsa folga | cada alteração geométrica |
| Integração | PDF/consensus -> scene -> planner -> gates -> JSON -> materialização | cada PR crítico |
| Regressão | cenas reais canônicas + sintéticas com resultados esperados e hashes | cada PR |
| Differential | referência independente: algoritmo simples lento/outra implementação/manual exato para casos pequenos | antes de mudar solver |
| Performance | n=10,100,1000 móveis; dimensões 3x; seeds; p50/p95, peak RSS, número de operações; sem esconder outliers | F0 e alterações de hot paths |
| SketchUp L2 | abrir, construir, salvar, reabrir, inspecionar entity IDs, transform, unidade, colisões e percurso | alterações de execução e campanha F4 |
| Visual assistida | imagens top/isométrica, diffs, critérios objetivos mensuráveis; revisão do usuário somente para gosto | mudanças relevantes |

### Invariantes de aceitação
- Porta com arco de abertura e envelope operacional não pode colidir com mobiliário proibido; recortes/espessuras validados no mesmo sistema de coordenadas.
- Circulação entre portais obrigatórios deve existir em toda a largura aplicável, não apenas perto do ponto de entrada; portas/portais ausentes => BLOCKED, não PASS.
- Cada cadeira deve caber em uso e recolhida conforme contrato e orientação real, não conforme nome textual opcional.
- Móvel inteiro dentro da área permitida; footprint 2D, altura/sobreposição 3D e obstáculos suspensos avaliados conforme semântica.
- Aumento de obstáculo não pode aumentar incorretamente a área transitável; mover/rotacionar a cena rigidamente preserva verdicts dentro de epsilon.
- Um layout com violações hard não pode vencer o ranking de um válido, independentemente da estética.
- A ausência de solução deve retornar diagnóstico de restrições conflitantes, sem forçar mesa junto à porta.
- Score sempre explica critérios, pesos, unidades, política e top N alternativas; sem scoring mágico não auditável.

## BLOCO 7 — Estratégia de DSA, Big O e desempenho
1. Medir chamadas e tempo inclusivo/exclusivo usando `cProfile`/`pyinstrument` opcional, contagens de operações e memory profiler; não supor gargalo sem profiling.
2. Anotar complexidade por tamanho relevante: `F` móveis, `C` candidatos, `P` vértices, `E` arestas de grafo, `R` regiões transitáveis. Evitar um único `n` descontextualizado.
3. Avaliar **prepared geometry**, `STRtree` com gestão de invalidação, índices espaciais, geometria estática congelada, poda segura e buffers pré-computados; verificar diferenças em resultados.
4. Implementar solver em duas camadas: geração adaptativa/regiões plausíveis + refinamento contínuo (e.g. scipy.optimize) **só quando as restrições permitirem**, com múltiplos starts e orçamento explícito. Alternativas: CSP/CP-SAT para escolhas discretas e posições parametrizadas; não adotar por hype.
5. Benchmark com **igual qualidade e igual conjunto de restrições**; ganho de 2x que muda resposta correta é regressão.
6. Não deixar cache mutável entre projetos; chave com hash do conteúdo, versão de política, escala e geometria; teste de invalidação.

## BLOCO 8 — Especialistas: papéis, não 27 processos de IA
- A cifra anterior de **27** é uma taxonomia inicial (10 núcleo + 9 ambientes + 8 validação/operação). NÃO impor 27 agentes em execução ou contratos separados sem análise de responsabilidades e custos.
- F0 deve reconciliar os **9 perfis documentados** com contratos reais e definir se um especialista agrupa várias capacidades ou se precisa dividir.
- Modelo recomendado de execução: **orquestrador + especialista implementador + revisor adversarial independente + executor/prover L2**; agentes adicionais só para especialidade necessária.
- Responsabilidades críticas: DSA/performance, geometria, solver, circulação, semântica/schema, ergonomia, arquitetura por cômodo, instrumentação, fixtures/testes, SketchUp Ruby e revisão de evidência.
- Cada agente recebe apenas paths de ownership, entradas, saídas, dependências, evidência e limites. Revisão independente nunca altera baseline silenciosamente.
- **Orçamento de tokens:** preferir documentação versionada (`docs/specs/`, contratos/ADR, relatórios) e tarefas curtas; nenhuma dependência de uma sessão longa de modelo caro.

## BLOCO 9 — Estratégia CI, PR e rollback
- Jobs separados: `lint-type-contract`, `unit-property`, `geometry-adversarial`, `integration`, `determinism`, `benchmark-report`, `MCP-contract`, `Windows-SketchUp-L2` (runner/estação com licença e acesso reais), `artifact-integrity`.
- Build Linux não simula o Windows/SketchUp. Quando L2 não estiver disponível marcar `BLOCKED_L2`, jamais `PASS_L2`.
- Cada PR vincula microcapacidade, issue, caso de falha, teste antes/depois, métricas e impacto por cômodo.
- Merge apenas quando os gates aplicáveis estão verdes e evidência requerida anexada; se bloqueado, fechar com motivo ou estacionar fora de PR aberto conforme política do usuário.
- Rollback por feature flag/adapters, commit/tag base e snapshots imutáveis; um rollback não altera PDF/.skp de referência.

## BLOCO 10 — Critérios de conclusão da FP-045
1. Inventário atualizado: arquivos e caminhos ativos com ownership rastreável; exceções justificadas.
2. Zero falso PASS conhecido nos gates críticos; casos incompletos produzem estado explícito bloqueado.
3. Suite adversarial e property-based automatizada, estável e auditável; suíte integral verde nas escalas suportadas.
4. Critérios espaciais objetivos mensurados nos cenários canônicos; para cada layout inviável há diagnóstico e alternativas sem forçar posição errada.
5. L2 recente de fluxos alterados no SketchUp real; diff e inspector reportados, com limitações.
6. Benchmarks com hardware/versão/dados e sem regressão injustificada de qualidade, tempo ou memória.
7. Não há regressão de cozinha, sala, dormitórios, banheiro, serviço, varanda e demais perfis cobertos; perfis sem capacidade ficam como `NOT_IMPLEMENTED`, nunca aprovados implicitamente.
8. Relatório final de riscos residuais, pendências, evidência, aprovação e próximos trabalhos. Só então retomar expansão de tutoriais.

## BLOCO 11 — Definição de pronto por microtarefa
`Issue -> reproducer red -> contrato/invariante -> solução mínima -> unit/property/integration -> adversarial -> benchmark (se relevante) -> prova L2 (se relevante) -> review independente -> CI -> merge/close -> atualizar matriz e handoff`.

## BLOCO 12 — Links e leitura mandatória antes de implementar
`README.md`, `docs/architecture/repository_map.md`, `tools/rooms/README.md`, `docs/reports/FP-043_final_validation.md`, `docs/architecture/specialists.md`, `CLAUDE.md`, catálogo de capacidades, manifests, `tools/validation/circulation_gate.py`, `tools/rooms/living/planning/layout_candidates.py`, `core/project_policy.py`. Conferir quais caminhos existem no `develop` atual e ajustar a SPEC em PR se mudaram; não confiar em snapshots antigos.

## BLOCO 13 — Kickoff executável para Claude
> Atue no `develop` de `GFCDOTA/sketchup-mcp` e identifique a branch canônica do harness-app. Implemente a FP-045 **por ordem F0 a F5**, iniciando exclusivamente pelo inventário e pela bateria de testes que reproduzem defeitos, sem desenvolver novos tutoriais. Leia todos os arquivos listados em BLOCO 12 e reconcilie as specs existentes. Gere matriz completa arquivo -> responsabilidade -> especialista -> testes -> riscos e análise de hotspots com medidas. Em seguida trate primeiro gates que podem aprovar geometrias incorretas; cada correção deve incluir teste adversarial que falhava antes, testes positivos, property-based e regressão. Não altere política de medidas para forçar PASS. Não declare qualidade com base em CI verde; mudanças na materialização exigem SketchUp real. Execute em micro-PRs que integrem em `develop` apenas com gates verdes; nenhum PR deve ficar aberto ao concluir a sessão, feche com motivo se não puder mergear. Proteja PDF, SKP, hashes e fixtures. Atualize specs/relatórios por fase, com prova, complexidade temporal/espacial e limitações. Se a sessão acabar, produza handoff completo com próximo comando inequívoco e o status de cada gate.
