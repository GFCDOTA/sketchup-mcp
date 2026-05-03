# Target Repo Architecture

> **Status:** proposta arquitetural. Não implementar nesta etapa.
> Documenta o alvo pra que mudanças futuras tenham direção comum.

## Visão geral

Hoje o repo tem pastas Python soltas no root (pipeline raster) + `tools/`
misturando Python, Ruby e HTML + scripts de oracle dispersos + um
microservice FastAPI (`validator/`) + um MCP server. Funciona, mas
acoplamento implícito (sys.path shims, imports relativos hacky).

A arquitetura alvo separa **apps** (processos rodáveis com I/O ou
HTTP) de **packages** (bibliotecas reutilizáveis sem I/O), com
**scripts** (entry points one-shot), **agents** (especialistas
read-only), e **tools/dev** (utilidades só pra desenvolvedores).

## Estrutura alvo

```
apps/
├── api/                  # FastAPI HTTP service (POST /extract)
├── validator_service/    # validator/ atual com microservice :8770
├── mcp_server/           # MCP server stdio (sketchup-mcp-server)
├── dashboard/            # Static HTML/JS (tools/dashboard/ atual)
└── sketchup_bridge/      # subprocess launcher pro SU2026 + Ruby plugins

packages/
├── plan_core/            # schema (consensus_model, observed_model) + invariantes
├── raster_pipeline/      # ingest + roi + extract + classify + topology + openings
├── vector_pipeline/      # build_vector_consensus + extract_room_labels + rooms_from_seeds + extract_openings_vector
├── validation_core/      # validator/scorers + vision (lib, sem HTTP)
├── sketchup_export/      # consume_consensus.rb + autorun plugins + skp_from_consensus
└── renderers/            # render_axon + render_openings_overlay + scripts/preview/* + render_*.py

scripts/
├── benchmark/            # bench_pipeline.py + harness de timing/memória
├── smoke/                # smoke tests end-to-end com PDFs sintéticos
└── archive/              # one-shots já rodados, mantidos pra auditoria

tools/
└── dev/                  # validators de schema, generators de fixture, linters custom

agents/                   # ver docs/agents/* — read-only por default

docs/
tests/
runs/                     # outputs gerados, .gitignore'd
```

## O que vira processo (microsserviço de fato)

| Componente | Por quê |
|---|---|
| `apps/api/` | HTTP, multi-cliente, latência por request |
| `apps/validator_service/` | scoreio assíncrono de PNGs no manifest, métricas Prometheus-friendly |
| `apps/mcp_server/` | stdio MCP, vida curta por sessão Claude |
| `apps/dashboard/` | estático servido por `python -m http.server` (não precisa Python state) |
| `apps/sketchup_bridge/` | spawn-and-die do SU2026 (subprocess externo) |
| **Ollama** | externo, opcional (validator vision) |

5 processos diferentes quando tudo sobe. Todos comunicam por
HTTP/stdio/arquivos. Cada um pode ser deployado/escalado separado.

## O que continua biblioteca Python (não vira microsserviço)

| Package | Por quê |
|---|---|
| `packages/plan_core/` | schema validation, sem I/O — usado por todos |
| `packages/raster_pipeline/` | sequência rígida de estágios, baixa latência local melhor que HTTP |
| `packages/vector_pipeline/` | mesmo motivo |
| `packages/validation_core/` | scorers são funções puras de imagem → score |
| `packages/sketchup_export/` | wrapper Python de `consume_consensus.rb` |
| `packages/renderers/` | matplotlib/Blender headless |

**Regra:** se o componente tem estado de servidor, escalabilidade
independente, ou múltiplos clientes simultâneos → vira `apps/`. Se é
função pura de input → output → vira `packages/`.

## Por que NÃO transformar tudo em microsserviço

1. **Latência** — pipeline raster rodando em 4-5 estágios via HTTP
   adiciona overhead de serialização de imagens grandes (10-50 MB)
   por estágio. Local in-process é 100× mais rápido.
2. **Complexidade operacional** — 11 microsserviços pra processar 1 PDF
   é overkill pra single-tenant. Deploy, monitoring, fault tolerance
   custam tempo de engenharia.
3. **Testabilidade** — função pura é trivial de testar; serviço HTTP
   precisa de mock + fixtures + conftest mais elaborado.
4. **Custo de container** — cada microsserviço vira imagem Docker,
   pipeline CI mais lento, registry mais cheio.

A regra clássica: **monolithic-first até dor real de escala**. Hoje
não há dor — single-tenant, 1 PDF por vez, latência aceitável.

## Riscos de mover entrypoints de alto risco

### `main.py` (CLI extract/serve)
- **Risco:** scripts externos (CI, integração, devs) chamam por nome.
- **Mitigação:** manter `main.py` no root como wrapper que importa de
  `apps/api/cli.py`. Wrapper pode emitir `DeprecationWarning` apontando
  pro novo path.

### `sketchup_mcp_server/`
- **Risco:** `.mcp.json` aponta pro module path; Claude Code carrega
  automaticamente. Mudança quebra todas as sessões abertas.
- **Mitigação:** manter `sketchup_mcp_server/server.py` como
  re-export de `apps/mcp_server/server.py`. Atualizar `.mcp.json` em
  PR separado, com comunicação clara aos usuários.

### `consume_consensus.rb` + autorun plugins
- **Risco:** autorun plugins ficam em `%APPDATA%/SketchUp/.../Plugins/`.
  Eles dão `load 'consume_consensus.rb'` por path absoluto. Mudar
  path no repo quebra a integração SU.
- **Mitigação:** atualizar autorun plugins junto, fornecer script de
  reinstalação. **NÃO mover sem atualizar `%APPDATA%` do dev.**

### Console script `sketchup-mcp-server` (pyproject)
- **Risco:** instalado via `pip install -e .` em ambientes de produção.
- **Mitigação:** atualizar `[project.scripts]` no mesmo commit que move
  o módulo. Re-executar `pip install -e .` invalida o velho.

## Estratégia de wrappers de compatibilidade

Pra cada arquivo movido, deixar no path antigo um stub:

```python
# render_debug.py (root, after move)
"""Compatibility shim. Real implementation in packages.renderers.debug.
This wrapper will be removed in version 0.3.0 (target 2026-08-XX)."""
import warnings
from packages.renderers.debug import *  # noqa
warnings.warn(
    "render_debug.py at repo root is deprecated; "
    "import from packages.renderers.debug instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

Mantém retrocompatibilidade durante transição. Stub é deletado em
release marcado.

**Quando deletar o stub:** quando `git log --grep="render_debug"`
não mostrar uso ativo + `grep -r "import render_debug"` não retornar
nada + 1 release de aviso passou.

## Sequência sugerida de migração (NÃO executar sem PR humano)

1. Criar `packages/` vazios com `__init__.py` (commit dedicado)
2. Mover `plan_core` (schema + invariantes) — menor risco, package puro
3. Mover `validation_core` (scorers — funções puras)
4. Mover `vector_pipeline` (tools/build_*, extract_*, rooms_from_seeds)
5. Mover `renderers` com wrappers root
6. Mover `raster_pipeline` (ingest/roi/extract/classify/topology/openings)
7. Criar `apps/api/` extraindo `api/app.py`
8. Criar `apps/validator_service/` extraindo `validator/`
9. Criar `apps/mcp_server/` extraindo `sketchup_mcp_server/`
10. Criar `apps/dashboard/` extraindo `tools/dashboard/`
11. Criar `apps/sketchup_bridge/` extraindo `tools/skp_from_consensus.py` +
    Ruby plugins (com atualização do `%APPDATA%`)
12. Limpar wrappers de compatibilidade (release marcado)

Cada passo = 1 PR dedicado, com testes verdes antes/depois, e métricas
do pipeline iguais antes/depois. Nada disso nesta fase.
