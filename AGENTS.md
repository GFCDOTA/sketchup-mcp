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

## 10. Hardening 2026-04

Ciclo de 13 fases (F1–F13) sobre a branch `fix/dedup-colinear-planta74`
para levar a app de "fix colinear isolado" (`a11724a`) ao estado
estável publicável. F1–F5 já eram fundamentação pré-existente; F6–F13
são a onda de hardening.

| Fase | Entrega | Nota |
| --- | --- | --- |
| F1–F5 | fix colinear + audit log + room check + sliver + strip merge | pré-existente |
| F6 | room dedup final — planta_74 31 -> 18 rooms + 8 testes | `03581fb` |
| F7 | openings adaptive gate + locus dedup + room-membership filter | `dcc5b07` |
| F8 | Python CLI para o bridge Ruby (`skp_export.__main__`) + schema v2 | paralelo |
| F9 | Ruby robustness — coords unify, thickness, hinge, floors | paralelo |
| F10 | +33 testes (transport openings_arc + snapshot p12/planta_74) | `4814e81` |
| F11 | multiplant validation via `scripts/validate_multiplant.py` | `3663cce` |
| F12 | semantic furniture filter — walls 230 -> 149 | `a9367b2` |
| F13 | CI gating — GitHub Actions + Makefile + AGENTS sync | este commit |

Gate estável p12 `snapshot_sha256 = 39b4138f4fd5613e...` (preservado
através de toda a onda). pytest suite: **149 pass / 15 pre-existing
fail / 7 skip** — os 15 fails listados são anteriores à branch e estão
rastreados, não regressão desta onda.

Contribuição: Claude Opus 4.7 (1M ctx) como agent principal, consultas
pontuais ao GPT-4 via bridge local (UIAutomation + sessão Plus) em
bifurcações de design.

### Como rodar a regressão completa

```bash
make all       # lint + pytest + validate + skp-dryrun + smoke
make validate  # só a suite multiplant F11 contra os JSON fixtures
make test      # só pytest (gate primário de regressão)
```

CI replicado em `.github/workflows/ci.yml` (jobs: pytest, lint,
schema-validate, skp-dryrun). PR de referência:
<https://github.com/GFCDOTA/sketchup-mcp/pull/1>.
