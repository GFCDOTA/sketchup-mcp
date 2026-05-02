# Repo Hardening Plan

> **Este commit não altera lógica funcional.** Adiciona apenas tooling
> (ruff config, pytest-xdist), CI (GitHub Actions) e este documento.
> Nenhum arquivo de algoritmo foi tocado. Nenhum threshold foi
> alterado. Nenhum teste foi modificado. Nenhum arquivo foi movido.

## Context

Repo `GFCDOTA/sketchup-mcp` (local: `D:/Claude/microservices/plan-extract-v2/`)
recebeu 32 commits desde 2026-04-29 — pipeline vetorial novo (`tools/`),
validator microservice (`validator/`), MCP server (`sketchup_mcp_server/`),
Ruby/SketchUp consumer, dashboard estático, e múltiplos render scripts.
Total: 8 entry points HTTP/CLI/MCP + 4 scripts Ruby. Não havia CI, ruff
não estava configurado, `pytest-xdist` não declarado, e `requirements.txt`
estava paralelo a `pyproject.toml` (drift risk).

Este commit (Phase 1 do plano em ondas) instala o piso mínimo de
tooling e CI pra que mudanças futuras sejam guardadas por verificação
automática — sem tocar em nada que afete o pipeline.

---

## Current State (baseline em main, 2026-05-02, working tree limpo)

| Item | Valor |
|---|---|
| Branch base | `main` |
| Branch deste commit | `chore/repo-hardening` |
| Python | 3.12.10 |
| pyproject.toml | existe, sem `[tool.ruff]` |
| requirements.txt | existe, paralelo a pyproject |
| .github/workflows/ | inexistente |
| tests/ | 29 arquivos, 218 tests collected, 0 collection errors |
| pytest (run completo) | **200 passed, 16 failed, 2 skipped** em ~5s |
| ruff | não instalado, sem config |

### 16 falhas conhecidas (BASELINE_KNOWN_FAILURES)

| Arquivo | Falhas | Causa raiz |
|---|---|---|
| `tests/test_text_filter.py` | 6 | Gate `len(strokes) > 200` em `classify/service.py` |
| `tests/test_orientation_balance.py` | 5 | Mesma origem |
| `tests/test_pair_merge.py` | 3 | Mesma origem |
| `tests/test_planta_74_regression.py` | 2 | Métricas locked em `planta_74.pdf`; não no CI |
| `tests/test_f1_regression.py::test_raster_byte_identical_on_planta_74` | 1 | Mesma origem |

**Por que NÃO corrigir agora:** corrigir o gate `len(strokes) > 200`
exige threshold sweep + medição empírica em planta_74 + p10 + p12
(documentado em sessão 2026-04-29 que tentar sem isso quebra o
pipeline em 75% das walls). Esse trabalho é Commit 6+ na sequência
abaixo.

### 2 skips (esperados)

- `tests/test_cubicasa_oracle.py` — sem CubiCasa weights nem `torch`
- `tests/test_oracle.py` — `compare_oracles` sem helper centroid-match

---

### Ruff baseline (144 violations)

Após instalar `[dev]` e rodar `ruff check . --statistics` na branch
`chore/repo-hardening`:

| Count | Code | Rule | Fixable |
|---:|---|---|---|
| 64 | I001 | unsorted-imports | ✅ |
| 34 | F401 | unused-import | ⚠️ unsafe |
| 13 | E702 | multiple-statements-on-one-line-semicolon | ❌ |
| 9 | E741 | ambiguous-variable-name | ❌ |
| 8 | F841 | unused-variable | ❌ |
| 5 | E401 | multiple-imports-on-one-line | ✅ |
| **5** | **F821** | **undefined-name** | ❌ ⚠️ **investigar — pode ser bug real** |
| 3 | E701 | multiple-statements-on-one-line-colon | ❌ |
| 1 | E402 | module-import-not-at-top-of-file | ❌ |
| 1 | E731 | lambda-assignment | ❌ |
| 1 | F541 | f-string-missing-placeholders | ✅ |
| **144** | | **TOTAL** | |

**Por que NÃO rodar `ruff --fix` agora:** user vetou explicitamente
autoformat em massa. Cleanup deve ser por onda dedicada (Commit
adicional, separado da movimentação de arquivos), pra que cada
mudança seja revisável.

**No CI:** ruff roda em modo `continue-on-error: true` (informativo,
não bloqueante) por enquanto. Vira bloqueante quando os 144 forem
zerados.

**5 F821 (undefined-name) merecem investigação** — podem ser bugs
reais (nomes que não existem no escopo). Investigar em commit
dedicado, sem autofix.

---

## CI scope — explicitamente "subset verde inicial"

`.github/workflows/ci.yml` roda `ruff check .` + `pytest` deselectando
**dois grupos** de testes:

**HARD_EXTERNAL_DEPS** (4 testes — não rodáveis em CI ubuntu padrão):
- `tests/test_planta_74_regression.py` (precisa `planta_74.pdf`)
- `tests/test_cubicasa_oracle.py` (precisa weights + GPU)
- `tests/test_oracle.py` (precisa `ANTHROPIC_API_KEY`)
- `tests/test_f1_regression.py::test_raster_byte_identical_on_planta_74` (precisa PDF)

**BASELINE_KNOWN_FAILURES** (3 arquivos — quebrados em main, dívida documentada):
- `tests/test_text_filter.py`
- `tests/test_orientation_balance.py`
- `tests/test_pair_merge.py`

**Não é CI completo.** É um portão verde inicial. Quando o gate
`len(strokes) > 200` for endereçado (Commit 6+), os deselects do
grupo BASELINE_KNOWN_FAILURES devem ser removidos.

CI **não depende de**: SketchUp, Windows GUI, Ollama, GPU, weights
externos, internet (além de instalar dependências), ou `planta_74.pdf`.

---

## Risks identificados

1. **runs/ race condition** — vários scripts e tests escrevem em `runs/`.
   `pytest -n auto` pode quebrar até `tmp_path` fixture ser introduzido.
   Razão pela qual `pytest-xdist` foi instalado mas não habilitado por
   default no CI.
2. **requirements.txt drift** — paralelo a `pyproject.toml`. Marcado
   como "legacy compatibility" no comentário do topo do arquivo.
3. **Hardcoded local paths** — `proto_colored.py:2`, `proto_red.py:2`,
   `render_sidebyside.py:4` referenciam `C:/Users/felip_local/Documents/paredes.png`.
   Adicionados ao `extend-exclude` do ruff por enquanto. Devem virar
   CLI args ou fixtures.
4. **sys.path shims** — 14+ arquivos usam `sys.path.insert(0, ...)`
   ad-hoc. Funciona mas frágil. Listado em "Tech debt" abaixo.
5. **Ruby/SketchUp paths** — `tools/su_boot.rb` referencia
   `E:/Claude/sketchup-mcp/...` (outra máquina). Não bloqueia CI
   mas é não-portável.

---

## Tech debt registrada

| Item | Onde | Phase do plano |
|---|---|---|
| `proto_*.py` + `render_sidebyside.py` com paths locais | root | Commit 4 (mover) ou commit dedicado |
| `requirements.txt` paralelo | root | Commit 5 (consolidar em pyproject + drop) |
| 14+ sys.path shims | scripts/, tools/, render_*.py | Commit 4 (após mover renders) |
| 14 cycles experimentais em runs/ | runs/cycle*/ | Commit 5 (arquivar em runs/_archive/) |
| `len(strokes) > 200` hardcoded threshold | classify/service.py | Commit 6+ (root cause) |
| `inspect_walls_report.rb` sem SHA256 do .skp | tools/ | fora do escopo de hardening |

---

## Sequência de ondas (commits)

| Commit | Escopo | Risco | Toca lógica? |
|---|---|---|---|
| **1 (este)** | tooling/CI/docs | baixo | ❌ não |
| **2** | benchmark + performance baseline (timing por estágio do pipeline, sem mudar código) | baixo | ❌ não |
| **3** | cache por hash (PDF SHA256 → raster cache em `runs/.cache/`) | médio | só I/O |
| **4** | mover render_*.py do root → `scripts/render/` ou `tools/render/` com wrappers retrocompatíveis | médio | só import paths |
| **5** | subdividir `tools/` por categoria (vector/sketchup/dashboard/render/util) + arquivar runs/cycle* obsoletos + arquivar patches aplicados | médio | só estrutura |
| **6** | introduzir agentes especialistas read-only (auditor, geometry, openings, sketchup, performance, validator, docs, ci-guardian) | baixo | ❌ não |
| **7** | auditor recorrente em workflow agendado (.github/workflows/repo-auditor.yml) → emite reports/repo_audit.md → cria PR (nunca merge automático) | baixo | ❌ não |
| **8+** | destravar BASELINE_KNOWN_FAILURES via root-cause fix em `classify/service.py` (gate `len(strokes) > 200`) | **alto** | ✅ sim |

---

## Validation commands

```bash
# Antes (capturar baseline)
git status -s
python --version
python -m pytest --collect-only -q
python -m pytest -q --tb=line | tail -5    # documenta 200/16/2

# Após edits (este commit)
python -m pip install -e ".[dev]"          # instala ruff + pytest-xdist
python -m ruff check .                     # baseline N violations — não fixar
python -m pytest -q --tb=short \
  --deselect tests/test_text_filter.py \
  --deselect tests/test_orientation_balance.py \
  --deselect tests/test_pair_merge.py \
  --deselect tests/test_planta_74_regression.py \
  --deselect "tests/test_f1_regression.py::test_raster_byte_identical_on_planta_74" \
  --deselect tests/test_cubicasa_oracle.py \
  --deselect tests/test_oracle.py
# Esperado: VERDE (todos os passing tests do baseline + 0 falhas novas)

git diff --stat                            # 4 arquivos
git status -s                              # limpo após commit
```

---

## Future Architecture and Specialist Agents

> **Esta seção é proposta, não implementação.** Não cria pastas,
> não move arquivos, não introduz workflows agendados. Documenta o
> alvo arquitetural e transforma em commits subsequentes.

### A) Separação futura do repo

Estrutura alvo, em ondas posteriores:

```
apps/
├── api/                  # FastAPI HTTP service (api/app.py atual)
├── validator_service/    # validator/ atual com microservice :8770
├── mcp_server/           # sketchup_mcp_server/ atual
├── dashboard/            # tools/dashboard/ atual (HTML/JS estático)
└── sketchup_bridge/      # tools/skp_from_consensus.py + Ruby plugins

packages/
├── plan_core/            # schema do consensus_model + observed_model + invariantes
├── raster_pipeline/      # ingest + roi + extract + classify + topology + openings (raster)
├── vector_pipeline/      # tools/build_vector_consensus + extract_room_labels + rooms_from_seeds + extract_openings_vector
├── validation_core/      # validator/scorers + validator/vision (lib, sem HTTP)
├── sketchup_export/      # consume_consensus.rb + autorun plugins + skp_from_consensus.py
└── renderers/            # render_axon + render_openings_overlay + scripts/preview/* + render_*.py do root

scripts/
├── benchmark/            # timing por estágio, baseline de performance
├── smoke/                # smoke tests end-to-end com PDFs sintéticos
└── archive/              # scripts one-shot já rodados, mantidos pra auditoria

tools/
└── dev/                  # ferramentas de desenvolvimento (linters custom, validators de schema)

agents/                   # agentes especialistas (ver seção B)

docs/
tests/
runs/
```

**Critério de move:** cada pasta vira um package Python com seu próprio
`__init__.py` + entry points. Imports passam a ser absolutos
(`from plan_core.schema import ConsensusModel`). Os 14+ sys.path shims
podem ser deletados.

### B) Agentes especialistas futuros

Cada agente tem escopo restrito + arquivos permitidos + arquivos
proibidos + checks obrigatórios. Devem ser invocáveis manualmente
(`agents/<name>/run.py`) e via workflow (Phase 7).

#### 1. Repo Auditor (`agents/auditor/`)
- **Responsabilidade:** rodar checks gerais sobre o repo (ruff, mypy se introduzido, dependências obsoletas, arquivos órfãos, paths quebrados)
- **Arquivos permitidos:** `reports/repo_audit.md` (escrever)
- **Arquivos proibidos:** todo o resto (read-only sobre o repo)
- **Checks obrigatórios:** `ruff check .`, `pytest --collect-only`, `git ls-files`, comparação com previous report
- **Quando pode editar:** apenas `reports/repo_audit.md`
- **Quando só pode sugerir:** sempre que detectar dívida ou regressão (output em PR comment)
- **Output:** `reports/repo_audit.md` + opcionalmente PR draft

#### 2. Geometry Specialist (`agents/geometry/`)
- **Responsabilidade:** revisar mudanças em `packages/raster_pipeline/extract` + `topology` + `model`
- **Arquivos permitidos:** comments em PR + `reports/geometry_review.md`
- **Arquivos proibidos:** qualquer .py ou .rb (read-only)
- **Checks obrigatórios:** rodar pytest dos módulos afetados, comparar métricas (walls/rooms/orphans) antes/depois em planta_74, verificar invariantes do AGENTS.md §2
- **Quando pode editar:** nunca
- **Quando só pode sugerir:** sempre, em PR comments
- **Output:** review summary + diff de métricas

#### 3. Openings Specialist (`agents/openings/`)
- **Responsabilidade:** revisar mudanças em `packages/vector_pipeline/openings` + `tools/extract_openings_vector.py`
- **Arquivos permitidos:** `reports/openings_review.md`
- **Arquivos proibidos:** qualquer código
- **Checks obrigatórios:** comparar count + tipo + hinge_side + swing_deg de openings em planta_74 antes/depois
- **Quando pode editar:** nunca
- **Quando só pode sugerir:** em PR comments
- **Output:** opening diff table

#### 4. SketchUp Specialist (`agents/sketchup/`)
- **Responsabilidade:** revisar `consume_consensus.rb`, `inspect_walls_report.rb`, autorun plugins, `skp_from_consensus.py`
- **Arquivos permitidos:** `reports/sketchup_review.md`
- **Arquivos proibidos:** qualquer código
- **Checks obrigatórios:** ler diagnostic mais recente em `docs/diagnostics/`, validar coerência com `inspect_walls_report` esperado, conferir invariantes (sem `wall_dark1/2`, sem `Sree`, layers corretas)
- **Quando pode editar:** nunca
- **Quando só pode sugerir:** em PR comments + alertas em diagnostics
- **Output:** review + checklist de invariantes SU

#### 5. Performance Specialist (`agents/performance/`)
- **Responsabilidade:** rodar benchmarks (`scripts/benchmark/`) e detectar regressões de timing/memória
- **Arquivos permitidos:** `reports/perf_baseline.json`, `reports/perf_diff.md`
- **Arquivos proibidos:** qualquer código
- **Checks obrigatórios:** medir tempo por estágio (ingest/roi/extract/classify/topology/openings/model) em PDFs canônicos (planta_74, synth_*), comparar com baseline
- **Quando pode editar:** apenas reports/
- **Quando só pode sugerir:** em PR comment + alerta se regressão > 20%
- **Output:** perf diff table

#### 6. Validator Specialist (`agents/validator/`)
- **Responsabilidade:** rodar `validator/run.py --once` em PRs que tocam pipeline e detectar queda de score
- **Arquivos permitidos:** `reports/validator_diff.md`
- **Arquivos proibidos:** qualquer código
- **Checks obrigatórios:** scoreio antes/depois com mesmos inputs, diff por kind (axon, sidebyside, skp_view)
- **Quando pode editar:** apenas reports/
- **Quando só pode sugerir:** em PR comment
- **Output:** score diff por entrada do manifest

#### 7. Docs Maintainer (`agents/docs/`)
- **Responsabilidade:** manter `OVERVIEW.md`, `CLAUDE.md`, `AGENTS.md`, `README.md` em sincronia com mudanças do repo
- **Arquivos permitidos:** `OVERVIEW.md`, `README.md`, arquivos em `docs/` (exceto `docs/diagnostics/` que é histórico)
- **Arquivos proibidos:** qualquer código, `CLAUDE.md` (precisa autorização do user), `AGENTS.md` (idem)
- **Checks obrigatórios:** detectar entry points novos sem doc, listas desatualizadas (commits/tasks), broken markdown links
- **Quando pode editar:** docs/ + README/OVERVIEW
- **Quando só pode sugerir:** mudanças em CLAUDE.md/AGENTS.md (PR draft + ping user)
- **Output:** PR draft com diff de docs

#### 8. CI Guardian (`agents/ci_guardian/`)
- **Responsabilidade:** monitorar CI flakiness, sugerir aumento/diminuição de timeout, identificar testes lentos, propor habilitar `pytest -n auto` quando seguro
- **Arquivos permitidos:** `reports/ci_health.md`, `.github/workflows/ci.yml` (somente após PR aprovado pelo user)
- **Arquivos proibidos:** test files, código de produção
- **Checks obrigatórios:** ler últimas 30 runs do CI via `gh run list`, calcular flakiness rate por job, identificar regressões de tempo
- **Quando pode editar:** apenas reports/, e ci.yml com PR draft (não merge automático)
- **Quando só pode sugerir:** sempre via PR comment ou draft
- **Output:** ci_health report + propostas em PR drafts

### C) Auditor recorrente futuro

Proposta para o Phase 7 (não implementar agora):

```
agents/auditor/
├── __init__.py
├── run_audit.py              # entry point: rodar todos os checks + escrever report
├── checks/
│   ├── ruff_check.py
│   ├── pytest_collect.py
│   ├── deps_check.py
│   ├── orphan_files.py
│   ├── broken_paths.py
│   └── invariants.py         # checks dos invariantes do AGENTS.md
└── README.md

reports/
└── repo_audit.md             # output, sobrescrito a cada run

.github/workflows/repo-auditor.yml   # cron weekly + workflow_dispatch
```

**Regras inegociáveis do auditor:**
- Nunca merge automático
- Nunca commit direto em `main`
- Sempre PR draft com label `audit`
- Sempre incluir comparação com previous report
- Sempre listar new findings + resolved findings
- Output é apenas markdown — não muda código

---

## Recomendação final

**Próximo commit (Commit 1, este) é seguro.** Toca apenas:
- `pyproject.toml` (add `[tool.ruff]`, atualiza `[dev]`)
- `requirements.txt` (comentário + 1 linha)
- `.github/workflows/ci.yml` (novo)
- `docs/repo_hardening_plan.md` (novo, este arquivo)

Zero risco de regressão funcional. Reversível com `git revert HEAD`.
Habilita ferramentas usadas nos commits seguintes.
