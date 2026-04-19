# AGENTS

## 1. Missão do serviço

PDF de planta -> observed_model honesto.

Não é responsabilidade deste serviço lidar com Ruby/SketchUp, mobiliário, closed-loop com LLM, nem remendar comportamento em cima de legado.

## 2. Invariantes do sistema

- Não inventar dados
- Não mascarar falhas (rooms=0 é informação, não erro)
- Não usar bounding box como substituto de room
- Não acoplar pipeline a um PDF específico
- Cada estágio do pipeline deve ser isolado e testável
- Artefatos de debug (debug_walls.svg, debug_junctions.svg, connectivity_report.json) são SEMPRE emitidos — sem eles o run é inválido
- Se um estágio falhar, ele reporta — não corrige em silêncio
- Ground truth nunca é usado como saída do extrator

## 3. Pipeline

`PDF -> ingest -> extract -> classify -> topology -> model -> debug`

- `api/`: expõe a interface do serviço e recebe requisições de extração sem incorporar lógica central do pipeline
- `ingest/`: lê o PDF de entrada e o transforma em representação utilizável pelas etapas seguintes
- `extract/`: extrai geometria observada bruta a partir da entrada processada em ingest
- `classify/`: consolida e classifica candidatos geométricos em entidades de parede observadas
- `topology/`: constrói junctions, conectividade, relações espaciais e rooms reais sem fallback de bounding box
- `model/`: monta o `observed_model.json` final a partir das saídas observadas do pipeline
- `debug/`: emite artefatos obrigatórios de inspeção e diagnóstico do run
- `tests/`: valida cada estágio isoladamente e o comportamento do pipeline sem esconder falhas

## 4. Contrato de saída (observed_model.json)

Schema mínimo obrigatório:

- `schema_version`
- `walls`
- `junctions`
- `rooms`
- `scores`
- `metadata`

Campos mínimos esperados:

- `scores.geometry`
- `scores.topology`
- `scores.rooms`
- `metadata.rooms_detected`
- `metadata.topology_quality`
- `metadata.warnings`

Regras do contrato:

- `rooms` pode ser `[]` — isso é observação válida
- O arquivo representa observação do pipeline, não preenchimento especulativo
- Scores são indicadores observacionais e não licença para mascarar ausência de estrutura

## 5. Regras de trabalho para agentes

- Toda mudança começa com um git checkpoint (ou branch) antes de alterar código
- Commits pequenos, semânticos, com prefixo convencional (`feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`)
- Um commit = uma ideia
- Nunca misturar refactor com feature no mesmo commit
- Sempre atualizar testes junto com mudança de comportamento
- Sempre atualizar `README.md` e/ou `AGENTS.md` se a arquitetura mudar
- Se faltar input essencial (ex.: PDF real para teste), o agente PARA e declara o bloqueio — não inventa fixture que mascare a falta

## 6. O que é proibido

- Reaproveitar heurística específica de uma planta
- Corrigir sintoma sem entender causa
- Inflar score artificialmente
- Declarar "sucesso" sem artefatos de debug válidos
- Instalar dependências nesta máquina sem autorização (Python não está instalado aqui)

## 7. Como rodar (resumo curto)

O `README.md` é a fonte canônica dos comandos de execução e teste.

## 8. Decision hierarchy and conflict resolution

Decision hierarchy:

1. Automated tests are the source of truth.
2. Codex is authoritative for code correctness and test validity.
3. Claude is authoritative for architecture, planning, and execution flow.
4. The user is only consulted for irreversible or high-cost decisions (push, destructive FS ops, global config, credentials).

Conflict rule:

- If tests fail -> Codex is correct.
- If tests pass but the design is questionable -> Claude decides.
- If both are uncertain -> create a minimal reproducible test; the test outcome decides.

## 9. Histórico de decisões arquiteturais

### Decisões

- 2026-04-19: Scaffold inicial via Codex, pipeline em estágios isolados, sem reaproveitar código legado.
- 2026-04-19: Ingest raster-first usando `pypdfium2`.
- 2026-04-19: Topology via grafo + polygonize — sem fallback de bounding box para rooms.
