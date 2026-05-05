# sketchup-mcp — visão geral, arquitetura, setup em outra máquina

> Documento canônico de onboarding e handoff. Lê isso primeiro pra entender
> o repo de ponta a ponta antes de mergulhar nos diretórios. Atualizado em
> 2026-05-02.

---

## 1. O que essa aplicação faz

```
┌──────────────┐                      ┌──────────────┐                    ┌─────────┐
│ PDF da planta│ → Python pipeline →  │ JSON canônico│ → Ruby/SketchUp → │ .skp 3D │
└──────────────┘                      │ (consensus)  │                    └─────────┘
                                      └──────────────┘
                                              ↑
                                Validator + Dashboard observam
```

Pega um PDF de planta-baixa de imóvel, extrai geometria (paredes, cômodos,
portas, peitoris), produz um **modelo intermediário JSON honesto** (`consensus_model.json`
ou `observed_model.json`), e finalmente constrói um **modelo 3D no SketchUp 2026** (`.skp`).

Premissas inegociáveis (estão em [`AGENTS.md`](AGENTS.md) §2):

1. **Não inventar paredes ou cômodos.** Se o pipeline não encontra, output é vazio — não é "corrigido" silenciosamente.
2. **Não usar bounding box como substituto de room.**
3. **Não acoplar pipeline a um PDF específico.** Sem hardcode de threshold.
4. **Debug artifacts obrigatórios** (`debug_walls.svg`, `debug_junctions.svg`, `connectivity_report.json`).
5. **Ground truth nunca entra no output do extrator.** Scores são observacionais.

---

## 2. Arquitetura — o que cada peça faz

### 2.1 Pipeline Python (raster) — extrai geometria do PDF rasterizado

Cada pasta = um estágio do pipeline, isolado e testável:

| Pasta | Responsabilidade |
|---|---|
| **`ingest/`** | Lê o PDF e rasteriza com `pypdfium2` (vira imagem) |
| **`roi/`** | Detecta a região da planta dentro da página (ignora legendas, rodapé, chrome de brochura) |
| **`extract/`** | Acha segmentos de parede no raster via Hough + morfologia |
| **`classify/`** | Limpa duplicatas Hough, filtra texto/hachura, junta pares de paredes (face A + face B → centerline) |
| **`topology/`** | Constrói grafo, divide paredes em interseções, snap de endpoints, detecta junctions (cross/tee/end), gera rooms via `polygonize` (shapely) |
| **`openings/`** | Detecta portas/janelas (gap detection + arc confirm). Pruning de openings órfãs |
| **`model/`** | Orquestra os estágios e monta o `observed_model.json` final |
| **`debug/`** | **OBRIGATÓRIO**: gera SVGs (`debug_walls.svg`, `debug_junctions.svg`) e `connectivity_report.json` para auditar visualmente |

**Entry points:**
- CLI: `python main.py extract planta.pdf --out runs/planta`
- HTTP: `api/app.py` (FastAPI) — `POST /extract`

### 2.2 Pipeline vetorial (em `tools/`) — alternativa mais limpa pra PDFs vetoriais

Quando o PDF tem geometria vetorial limpa (caso comum de plantas comerciais brasileiras), pula o raster e lê os paths do PDF direto:

| Arquivo `tools/` | Função |
|---|---|
| `build_vector_consensus.py` | Lê paths preenchidos do PDF → walls + soft_barriers (peitoris) |
| `extract_room_labels.py` | Pega coords do texto (COZINHA, SUITE 01...) pra usar como seeds |
| `rooms_from_seeds.py` | Flood-fill a partir das seeds → polígonos de rooms com nome |
| `extract_openings_vector.py` | Acha arcos de porta (paths com curvas Bezier) → openings (`geometry_origin: "svg_arc"`) |
| `polygonize_rooms.py` | Alternativa: planta − walls = rooms via subtração shapely |

**Output:** `runs/vector/consensus_model.json` (schema 1.0.0)

### 2.3 Ruby/SketchUp consumer — JSON → .skp

| Arquivo `tools/` | Função |
|---|---|
| `consume_consensus.rb` | Roda dentro do SU2026: lê o JSON, extruda walls a 2.70m, pinta floors com cores por room, cria parapets (peitoris) a 1.10m, salva o .skp |
| `skp_from_consensus.py` | Launcher Python: dispara SU2026 com bootstrap (passa um .skp positional pra pular o Welcome dialog do trial), espera o .skp aparecer |
| `inspect_walls_report.rb` | Auditor: roda dentro do SU, lista todos os groups/faces/materials/overlaps em JSON estruturado |
| `autorun_inspector_plugin.rb` / `autorun_consume.rb` | Plugins SU em `%APPDATA%/SketchUp/.../Plugins` que disparam os scripts acima na inicialização do SU |
| `su_boot.rb` | Bootstrap alternativo via `-RubyStartup` |

### 2.4 Renders — visualizadores em PNG

| Arquivo | Renderiza |
|---|---|
| `tools/render_axon.py` | Vista isométrica + topo a partir do consensus (matplotlib 3D) — desenha openings como swatches laranja nas paredes |
| `tools/render_openings_overlay.py` | PDF cropado com markers das openings detectadas |
| `render_debug.py`, `render_native.py`, `render_semantic.py`, `render_proto_overlays.py`, `render_with_openings.py`, `render_sidebyside.py` | Overlays variados para conferência visual |

Todos auto-registram seu PNG em `runs/png_history/manifest.jsonl` via `tools/png_history.py` — append-only com SHA256 de origem (.skp + consensus + PDF).

### 2.5 Validator (`validator/`) — qualidade automática

Microservice FastAPI na **porta 8770** que lê o manifest e dá nota a cada PNG gerado:

| Arquivo | Função |
|---|---|
| `validator/run.py` | CLI: `--once`, `--watch`, `--port`, `--vision`, `--show`, `--force` |
| `validator/service.py` | FastAPI: `/health`, `/metrics`, `/entries`, `/validate-pending` |
| `validator/pipeline.py` | Dispatcher: pega `kind` do entry → escolhe scorer |
| `validator/scorers/axon.py` | Confere fill density + canvas coverage + count de rooms |
| `validator/scorers/skp_view.py` | Cruza com `inspect_walls_report.rb` (overlaps + default-material faces + diversidade de cores) |
| `validator/scorers/sidebyside.py` | Coverage parity + SSIM contra PDF baseline |
| `validator/scorers/legacy.py` | Fallback básico |
| `validator/vision.py` | Crítica qualitativa via Ollama qwen2.5vl:7b (opcional) |

Contrato detalhado em [`docs/validator_protocol.md`](docs/validator_protocol.md).

### 2.6 MCP Server (`sketchup_mcp_server/`) — expõe o pipeline pra Claude

Protocolo MCP via stdio. Permite que outros agentes Claude rodem o pipeline como ferramenta.
- `server.py`: registra a tool `extract_plan(pdf_path, out_dir)`
- `tools.py`: implementação que chama `model.pipeline.run_pdf_pipeline`
- `.mcp.json`: declaração que o Claude Code carrega automaticamente quando abre o repo

### 2.7 Dashboard (`tools/dashboard/`) — observabilidade visual

HTML estático servido por `python -m http.server 8771 --directory tools`.
Abas: **Geral / Decisões / Aprendizados / Analítico / Plantas / Oráculo**.
A galeria de Plantas mostra renders + comparações. Oráculo lista runs com diagnóstico LLM.

### 2.8 Tools auxiliares

| Arquivo `tools/` | Função |
|---|---|
| `png_history.py` | Manifest append-only de todos os PNGs com hashes de origem |
| `extract_room_labels.py` | Extrai texto + coord do PDF |
| `polygonize_rooms.py` | Subtração de área via shapely |

### 2.9 Testes + Docs

- `tests/` — pytest com fixtures sintéticas (sem PDF real); valida invariantes
- `tests/fixtures/` — modelos sintéticos canônicos
- `docs/` — análises arquiteturais (`ANALYSIS.md`, `CAUSA-RAIZ.md`, `SOLUTION.md`, `validator_protocol.md`, `openings_vector_v0.md`, `png_history_protocol.md`, etc.)
- `patches/` — propostas de melhoria não-aplicadas (LSD, CubiCasa5K DL oracle)
- `scripts/oracle/` — integração com LLM-as-architect e CubiCasa5K
- `scripts/preview/` — renderers Blender headless

---

## 3. O que é "microsserviço de verdade" e o que é só pasta Python

**Honestidade total:** a maior parte é **organização de código** (separation of concerns), não microsserviços de runtime.

### Roda como processo separado (microsserviço de fato)

| Componente | Processo | Porta/Protocol |
|---|---|---|
| `api/app.py` | Python | HTTP (configurável) |
| `validator/` | Python | HTTP :8770 |
| `sketchup_mcp_server/` | Python | stdio (MCP) |
| `tools/dashboard/` | `http.server` | HTTP :8771 (estático) |
| **SketchUp 2026** | `SketchUp.exe` | Subprocess spawn-and-die (externo) |
| **Ollama** (validator vision) | Externo | HTTP :11434 (opcional) |

São **5 processos** diferentes se você sobe tudo. Conversam por HTTP/stdio/arquivos.

### Não é microsserviço — só pasta Python

`ingest/`, `extract/`, `classify/`, `topology/`, `openings/`, `model/`, `roi/`, `debug/` rodam **no MESMO processo** quando chamados via `main.py`, `api/app.py` ou MCP server. Cada um é módulo Python que `import`-a o anterior. Sem rede, sem fila, sem container, sem isolamento de falha.

**Vantagens disso:** simples, rápido, fácil de testar e debugar, latência zero entre estágios, deploy é `pip install -e .`.
**Custo:** se `extract/` crasha, derruba o request inteiro. Não escala estágios independentemente.

Pra um sistema single-tenant que processa 1 PDF por vez, o trade-off vale a pena.

---

## 4. Setup em outra máquina (zero a executando)

### 4.1 Pré-requisitos

- **Python ≥ 3.11** (testado em 3.12.13) — recomendo `pyenv`/`uv` ou Python.org direto
- **Git**
- **(opcional, pra gerar .skp)** SketchUp 2026 instalado em `C:\Program Files\SketchUp\SketchUp 2026\` (Windows)
- **(opcional, pra critique vision)** Ollama com modelo `qwen2.5vl:7b` rodando em `localhost:11434`

### 4.2 Clone e instala

```bash
# clone
git clone https://github.com/GFCDOTA/sketchup-mcp.git
cd sketchup-mcp

# venv (recomendado)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# instala como package editable
pip install -e .             # core: pipeline + FastAPI + MCP server
pip install -e ".[dl]"       # extras: torch + CubiCasa5K oracle (opcional, pesado)
pip install -e ".[dev]"      # extras: pytest + ruff
```

`pip install -e .` instala automaticamente o console script `sketchup-mcp-server` (entry point pro MCP).

### 4.3 Smoke test

```bash
# rodar pipeline raster numa planta exemplo
python main.py extract planta_74.pdf --out runs/smoke_test

# verifica saídas
ls runs/smoke_test/
# observed_model.json + debug_walls.svg + debug_junctions.svg + connectivity_report.json
```

### 4.4 Pipeline vetorial completo (planta_74)

```bash
# 1. walls + soft_barriers do PDF
python -m tools.build_vector_consensus planta_74.pdf \
       --out runs/vector/consensus_model.json

# 2. text labels (Cozinha, Suíte 01, ...)
python -m tools.extract_room_labels planta_74.pdf \
       --out runs/vector/labels.json

# 3. rooms por flood-fill
python -m tools.rooms_from_seeds runs/vector/consensus_model.json \
       runs/vector/labels.json

# 3-opt-in. Mesmo step com canonicalização de polígonos (V1 fix —
# elimina a "mordida diagonal" da SALA DE ESTAR documentada em
# docs/tour/matterport_visual_findings_74m2.md). Default OFF; ative
# explicitamente quando quiser o fix V1 no consensus_model.json:
python -m tools.rooms_from_seeds runs/vector/consensus_model.json \
       runs/vector/labels.json \
       --canonicalize-rooms --room-canonicalization-tol 8

# 4. openings (door arcs)
python -m tools.extract_openings_vector planta_74.pdf \
       --consensus runs/vector/consensus_model.json --mode replace
```

Output esperado: `runs/vector/consensus_model.json` com **33 walls + 11 rooms + 12 openings** para `planta_74.pdf`.

### 4.5 Gerar o .skp 3D (precisa SU2026)

```bash
python -m tools.skp_from_consensus runs/vector/consensus_model.json \
       --out runs/vector/planta_74.skp --timeout 180
```

Esse comando dispara SU2026, executa o `consume_consensus.rb` plugin que está em `%APPDATA%/SketchUp/SketchUp 2026/SketchUp/Plugins/`, salva o .skp e fecha. ~60-90s.

⚠️ **Pré-requisito:** copiar o conteúdo de `tools/autorun_consume.rb` e `tools/autorun_inspector_plugin.rb` pra `%APPDATA%/SketchUp/SketchUp 2026/SketchUp/Plugins/` na primeira vez. O launcher `skp_from_consensus.py` escreve um `autorun_control.txt` lá apontando pro consensus + script.

### 4.6 Renderizar visualizações

```bash
# axon iso + top com openings em laranja
python -m tools.render_axon runs/vector/consensus_model.json \
       --out runs/vector/axon_iso.png --mode axon \
       --skp runs/vector/planta_74.skp --pdf planta_74.pdf

python -m tools.render_axon runs/vector/consensus_model.json \
       --out runs/vector/axon_top.png --mode top \
       --skp runs/vector/planta_74.skp --pdf planta_74.pdf

# overlay das openings sobre o PDF
python -m tools.render_openings_overlay planta_74.pdf \
       --consensus runs/vector/consensus_model.json \
       --out runs/vector/openings_overlay.png --scale 4
```

Todos os PNGs ficam registrados em `runs/png_history/manifest.jsonl`.

### 4.7 Subir os serviços

```bash
# validator microservice (porta 8770)
python -m validator.run --port 8770 &

# dashboard estático (porta 8771)
python -m http.server 8771 --directory tools &

# rodar validador uma vez (sem subir API)
python -m validator.run --once

# com critique visual via Ollama
python -m validator.run --once --vision
```

Depois abre:
- **Dashboard:** http://localhost:8771/dashboard/index.html#plantas
- **Validator health:** http://localhost:8770/health
- **Validator metrics:** http://localhost:8770/metrics

### 4.8 MCP server

Já registrado em `.mcp.json`. Quando você abrir o repo no Claude Code, ele detecta e disponibiliza a tool `extract_plan`. Pra testar manual:

```bash
sketchup-mcp-server  # entry point instalado por pip install -e .
```

### 4.9 Testes

```bash
pytest                       # roda tudo
pytest -v -k "topology"      # só os de topology
pytest -v --tb=short         # tracebacks curtos
```

---

## 5. Fluxo end-to-end pra planta_74.pdf

```
planta_74.pdf
   ↓
[tools.build_vector_consensus]  → 33 walls + 8 soft_barriers
[tools.extract_room_labels]     → 11 labels (Cozinha, Suite 01, ...)
[tools.rooms_from_seeds]        → 11 rooms (com nomes)
[tools.extract_openings_vector] → 12 openings (svg_arc)
   ↓
runs/vector/consensus_model.json  (schema 1.0.0)
   ↓
[tools.skp_from_consensus]
   → lança SU2026 com bootstrap .skp positional
   → autorun_consume.rb dispara
   → consume_consensus.rb lê JSON, extruda walls 2.70m, pinta floors, parapets 1.10m
   → salva runs/vector/planta_74.skp
   ↓
[tools.inspect_walls_report.rb] → runs/vector/inspect_report_post_fix.json (audit)
   ↓
[tools.render_axon] → axon_iso.png + axon_top.png
   → auto-registrados em runs/png_history/manifest.jsonl
   ↓
[validator.run --once] → score cada PNG, escreve `validation` no manifest
   ↓
[dashboard 8771] mostra galeria; [validator 8770] expõe métricas
```

---

## 6. Como dividir trabalho entre pessoas

| Peça | Linguagem | Perfil |
|---|---|---|
| **Pipeline raster** (`ingest`/`extract`/`classify`/`topology`) | Python + OpenCV + shapely | Visão computacional |
| **Pipeline vetorial** (`tools/build_vector_consensus`, `extract_openings_vector`) | Python + pypdfium2 | PDF/geometria |
| **Ruby SketchUp consumer** (`consume_consensus.rb` + plugins) | Ruby + SketchUp API | Especialista SU |
| **Renders e visualizações** (`render_*.py`, `png_history`) | Python + matplotlib + PIL | Frontend/QA visual |
| **Validator microservice** (`validator/`) | Python + FastAPI | Backend observability |
| **MCP server** (`sketchup_mcp_server/`) | Python + MCP protocol | Quem trabalha com agentes Claude |
| **Dashboard** (`tools/dashboard/`) | HTML + JS + Chart.js | Frontend |
| **Testes/CI** (`tests/`, `pyproject.toml`) | pytest + ruff | DevOps/QA |
| **Docs/diagnóstico** (`docs/`, `patches/`) | Markdown | Tech lead/arquiteto |

A divisão natural é **por camada do pipeline**. Cada camada conversa pelo schema (`observed_model.json` schema 2.x ou `consensus_model.json` schema 1.0.0) — então dá pra trabalhar em paralelo sem pisar no pé.

---

## 7. Estado atual e gotchas conhecidos

### O que funciona

- ✅ Pipeline raster end-to-end em planta_74 (94 walls, 14 rooms na config padrão)
- ✅ Pipeline vetorial completo em planta_74 (33 walls, 11 rooms, 12 openings)
- ✅ Geração do .skp com walls extrudadas, floors coloridos, parapets cinza-concreto
- ✅ Validator scorer pra axon/skp_view/sidebyside/legacy
- ✅ MCP server com tool `extract_plan`
- ✅ Dashboard estático
- ✅ Testes sintéticos passando

### O que NÃO funciona ainda

- ❌ **`consume_consensus.rb` não carve openings** — as portas detectadas no consensus aparecem no JSON mas não viram cortes nos walls do .skp. Walls ficam full-height através das portas. Próximo trabalho: adicionar `add_opening` que faz pushpull negativo nas walls com `wall_id`.
- ❌ **SU2026 trial dialog** — sem admin no `C:\Program Files\…`, o launcher precisa do bootstrap fix (passar .skp positional) — já implementado em `skp_from_consensus.py`.
- ❌ **Sem regression alerting** — validator scoreia mas não diffa contra histórico.
- ❌ **Janelas não detectadas** — `extract_openings_vector.py` só pega arcos de porta, não pares de linhas paralelas de janela.
- ❌ **Pipeline raster despedaça plantas complexas** — ver [`docs/CAUSA-RAIZ.md`](docs/CAUSA-RAIZ.md).
- Patches 03 (`b798881`) and 04 (`7fb1d80`) APPLIED. Patch 02 (density-trigger) PENDING empirical sweep. Patches 07-09 in `patches/archive/` are HIGH risk and require explicit human approval per CLAUDE.md §1 hard rule #5.

### Limitações

- `inspect_walls_report.rb` não embute SHA256 do .skp inspecionado, então o validator faz match por basename + mtime (frágil pra .skps renomeados).
- PDF baseline pra SSIM é page 1 only.
- Vision LLM é local-only (Ollama). Sem GPT-4V porque o `chatgpt-bridge` em `E:/chatgpt-bridge/` (memory `reference_chatgpt_bridge`) é só texto.

---

## 8. Onde achar o que

| Procura | Onde |
|---|---|
| Como o pipeline roda end-to-end | [`README.md`](README.md) §2 + este doc §5 |
| Por que o pipeline despedaça plantas | [`docs/CAUSA-RAIZ.md`](docs/CAUSA-RAIZ.md) |
| Roadmap de melhorias propostas | [`docs/ROADMAP.md`](docs/ROADMAP.md), [`docs/SOLUTION-FINAL.md`](docs/SOLUTION-FINAL.md) |
| Schema do `observed_model.json` v2.x | [`docs/SCHEMA-V2.md`](docs/SCHEMA-V2.md) |
| Schema do `consensus_model.json` 1.0.0 | inline em `tools/build_vector_consensus.py` + memory `project_consensus_model_schema` |
| Validator (scorers, REST API) | [`docs/validator_protocol.md`](docs/validator_protocol.md) |
| Vector openings (algoritmo + limitações) | [`docs/openings_vector_v0.md`](docs/openings_vector_v0.md) |
| PNG history manifest | [`docs/png_history_protocol.md`](docs/png_history_protocol.md) |
| Inspeção do .skp planta_74 | [`docs/diagnostics/2026-05-02_planta_74_skp_inspection.md`](docs/diagnostics/2026-05-02_planta_74_skp_inspection.md) |
| Invariantes inegociáveis | [`AGENTS.md`](AGENTS.md) §2, [`CLAUDE.md`](CLAUDE.md) §2 |
| Protocolo git pra Claude | [`CLAUDE.md`](CLAUDE.md) §0 |

---

## 9. Quick reference de comandos

```bash
# pipeline raster
python main.py extract <pdf> --out runs/<name>

# pipeline vetorial completo
python -m tools.build_vector_consensus <pdf> --out runs/vector/consensus_model.json
python -m tools.extract_room_labels <pdf> --out runs/vector/labels.json
python -m tools.rooms_from_seeds runs/vector/consensus_model.json runs/vector/labels.json
python -m tools.extract_openings_vector <pdf> --consensus runs/vector/consensus_model.json

# .skp
python -m tools.skp_from_consensus runs/vector/consensus_model.json --out runs/vector/planta_74.skp

# renders
python -m tools.render_axon runs/vector/consensus_model.json --out runs/vector/axon_iso.png --mode axon
python -m tools.render_openings_overlay <pdf> --consensus runs/vector/consensus_model.json --out runs/vector/openings_overlay.png

# observabilidade
python -m validator.run --once                # valida tudo pendente
python -m validator.run --port 8770           # API
python -m http.server 8771 --directory tools  # dashboard

# MCP
sketchup-mcp-server                            # stdio MCP server

# testes
pytest -v
```

---

## 10. Como me chamar (Claude) pra continuar trabalhando

1. Abre o repo no Claude Code
2. O `.mcp.json` carrega automaticamente o MCP server
3. O `CLAUDE.md` é lido a cada sessão
4. Diz pro Claude: *"Continue de onde parou — sync git primeiro"* (memory `feedback_session_start_git_protocol`)
5. Pra autonomia total: *"Modo AUTONOMIA TOTAL. Aplique fixes, gere PNGs, commite e pushe sem pedir confirmação"* (memory `feedback_autonomia_total_sketchup_mcp`)

Próximos targets prioritários, em ordem:

1. **`consume_consensus.rb` carve openings** — adicionar `add_opening(wall_group, opening)` que recebe `wall_id` + `center` + `opening_width_pts` e faz pushpull negativo de altura ~2.10m. Necessário pra portas aparecerem no .skp.
2. **Detector de janelas vetoriais** — pares de linhas paralelas stroked-only ao longo das walls (atualmente só portas).
3. **Regression alerting no validator** — diff de score histórico por kind, dispara alerta quando cair > X%.
4. **`inspect_walls_report.rb` embute SHA256 do .skp** — pra matcher do validator ser robusto contra rename.
5. **Pipeline raster reconnect** — aplicar patch 09 (AFPlan multi-scale + CCA) de [`patches/`](patches/).
