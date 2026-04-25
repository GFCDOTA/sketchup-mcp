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

Schema atual: `2.1.0`.

Top-level obrigatórios:

- `schema_version`
- `run_id` (uuid4 hex por run)
- `source` (filename, source_type in {pdf, raster}, page_count, sha256; sha256/filename podem ser null no path raster)
- `bounds` (pages[] com per-page AABB; pages=[] quando nenhuma wall foi detectada)
- `roi` (per-page; cada item: applied bool, bbox or null, fallback_reason, component_pixel_count, component_bbox_area, component_count). Imagens < 500 px do menor lado retornam applied=true com bbox = página inteira (skip semântico, não fallback).
- `walls` (saída pós-merge: segmentos colineares recombinados — geometria limpa para consumo)
- `junctions` (extraídos do SPLIT graph antes do merge — preservam cross/tee em pontos onde o output `walls` agora passa por dentro sem quebrar)
- `rooms`
- `scores`
- `metadata`
- `warnings` (lista de strings; `roi_fallback_used` aparece quando qualquer página do PDF caiu em fallback)

Campos mínimos esperados:

- `scores.geometry`, `scores.topology`, `scores.rooms` (todos em [0, 1])
- `metadata.rooms_detected`, `metadata.topology_quality` (good/fair/poor), `metadata.connectivity`
- `metadata.warnings` (mirror do top-level `warnings` durante 2.x; remoção prevista num major bump)
- `metadata.connectivity.*` (computado do SPLIT graph: node_count e component_sizes podem ser maiores que `len(walls)` porque cada intersection topológica é nó. Honest reporting: se você divide o número de junctions pelo número de walls, NÃO é uma métrica direta — junctions descrevem topologia, walls descrevem geometria observada)

Regras do contrato:

- `rooms` pode ser `[]` — isso é observação válida
- `bounds.pages` pode ser `[]` — quando não há walls, mantenha a lista vazia em vez de `null`
- O arquivo representa observação do pipeline, não preenchimento especulativo
- Scores são indicadores observacionais e não licença para mascarar ausência de estrutura
- Mudança de contrato backward-incompatível exige major bump (3.x) e atualização desta seção + README

## 5. Regras de trabalho para agentes

- **Session start protocol** — toda nova sessão começa com `git fetch --all` + `git pull --ff-only` em cada repo ativo (`sketchup-mcp` e `sketchup-mcp-exp-dedup`). Working tree dirty da sessão anterior é committado em commits temáticos antes de mexer em código novo. No final da sessão: commits do trabalho desta sessão + `git push` na branch corrente. Sem `--force`, sem `--no-verify` sem autorização explícita.
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
- 2026-04-21: Promovidos protos `proto_red.py` / `proto_colored*.py` / `proto_skel.py` / `preprocess_walls.py` para o pacote `preprocess/`. Os scripts originais foram movidos para `preprocess/legacy/` (preservados, não removidos).

## 10. Apêndice — Preprocess opcional (`preprocess/`)

O pacote `preprocess/` adiciona uma etapa **opcional** entre `ingest` e `extract`. Ele transforma o raster da página antes da extração — tipicamente isolando paredes desenhadas em uma cor específica (vermelho, preto, grey31, ...) — quando o PDF cru não rende geometria limpa o suficiente para o pipeline.

### Regras

- **Off por default.** Sem `preprocess=`, o pipeline opera exatamente como antes.
- **Genérico.** Os presets descrevem famílias de paleta (`red`, `black`, `grey31`, ...), nunca um PDF específico. Não acoplar heurística a `planta_74.pdf` ou similar — isso violaria a invariante §2.
- **Nunca silencioso.** Toda aplicação de preprocess injeta um warning explícito no `observed_model.warnings` (ex: `preprocess_color_mask_applied`). Se o pipeline rodar com input alterado, o consumidor downstream tem como saber. Sem warning = bug.
- **Sem fallback automático.** O pipeline NÃO escolhe sozinho ativar preprocess "se o PDF parecer ruim". A decisão é do caller (CLI/API/teste). Fallback silencioso mascararia falha de extração.
- **Não substitui o extrator.** Preprocess é uma muleta para paletas onde a alvenaria é desenhada em cor sólida. Casos onde extract precisa melhorar (Hough, ROI, classify) continuam sendo problema do extractor.

### API

```python
from model.pipeline import run_pdf_pipeline

result = run_pdf_pipeline(
    pdf_bytes,
    filename="planta.pdf",
    output_dir=Path("artifacts/run-001"),
    preprocess={"mode": "color_mask", "color": "auto"},
)
assert "preprocess_color_mask_applied" in result.observed_model["warnings"]
```

### Modos suportados

- `{"mode": "color_mask", "color": "auto"|"red"|"black"|"grey31"|...}` — extrai canal cromático dominante.
- `{"mode": "color_mask", ..., "skeleton": true}` — adicionalmente esqueletoniza para 1px e re-dilata.

### Legado

Scripts originais `proto_red.py`, `proto_colored*.py`, `proto_skel.py`, `proto_v2.py`, `proto_runner.py`, `preprocess_walls.py` foram movidos para `preprocess/legacy/` (não deletados). Ver `preprocess/legacy/README.md` para mapeamento proto -> produção.
