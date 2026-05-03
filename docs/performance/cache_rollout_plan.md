# Cache Rollout Plan

> Companheiro de [`cache_design.md`](cache_design.md) e
> [`cache_keys.md`](cache_keys.md). Define a sequência de PRs pra
> introduzir o cache sem quebrar nada.

## Princípios do rollout

1. **Estágio por estágio** — cada PR habilita cache de um estágio só
2. **Opt-in primeiro** — flag `--cache` por default desligado, ativa
   manual; depois flag `--no-cache` por default ligado
3. **Warn-only intermediate** — modo "would have hit" pra observar
   sem servir cache
4. **Validação empírica obrigatória** — bench antes/depois, hit rate
   mínimo aceitável
5. **Rollback fácil** — env var `SKM_NO_CACHE=1` desliga tudo;
   `git revert <commit>` reverte 1 estágio

## Sequência (cada item = 1 PR dedicado)

### PR 1 — Infraestrutura base de cache (sem nenhum estágio cachear)

Cria `packages/cache/` (ou `tools/cache/` se preferir), com:
- `cache.py` — funções `cache_key()`, `cache_get()`, `cache_set()`,
  `cache_clear()`, `cache_stats()`
- `__init__.py` exporta API pública
- `tests/test_cache_infra.py` — testa serialização, hash determinístico,
  read/write, atomic rename, missing key behavior

**O que NÃO faz:** ainda não usa em nenhum estágio. Pure library.

**Validação:**
- pytest passa (novos testes verdes, baseline inalterado)
- ruff check sem novos erros
- `python -c "from packages.cache import cache_key; print(cache_key({'a':1}))"`

**Mensagem:** `feat(cache): add content-addressed cache infrastructure (no callers yet)`

### PR 2 — Cache do estágio `raster` (warn-only)

Adiciona uso em `ingest/service.py` (ou onde quer que `pypdfium2`
seja chamado):

```python
key = cache_key({"stage": "raster", "pdf_sha256": ..., "dpi": ..., "page_idx": ..., "pypdfium2_version": ...})
hit = cache_get("raster", key)
if cache_warn_only:
    log.info(f"[cache] raster {'hit' if hit else 'miss'} key={key}")
    # NÃO usa o hit ainda — só loga
return _do_raster_actual(pdf, dpi, page_idx)
```

**Modo warn-only por 1 PR pra validar que keys são estáveis** —
log mostrar 100% miss na primeira run, 100% hit na segunda.

**Validação:**
- bench cold + warm (mesmo PDF) — log esperado: miss + hit
- Nenhum byte do output muda (pixel-by-pixel diff)

**Mensagem:** `perf(cache): instrument raster stage in warn-only mode`

### PR 3 — Cache do estágio `raster` (enabled, opt-in)

Mesmo código, mas agora **usa** o hit:

```python
hit = cache_get("raster", key)
if hit and not cache_disabled():
    return hit
result = _do_raster_actual(pdf, dpi, page_idx)
cache_set("raster", key, result)
return result
```

`cache_disabled()` lê `SKM_NO_CACHE` env var (default False).

**Validação:**
- bench warm: tempo do raster cai pra ~50ms (load) vs ~2-5s (compute)
- Output bytes idênticos
- pytest verde
- Adicionar teste `tests/test_cache_raster.py` que confirma:
  hit retorna mesmo bytes, miss invalida quando código muda

**Mensagem:** `perf(cache): enable raster cache (opt-in via SKM_NO_CACHE=1 to disable)`

### PR 4 — Cache do estágio `vector_consensus` (warn-only)

Análogo ao PR 2 pra `tools/build_vector_consensus.py`.

### PR 5 — Cache do estágio `vector_consensus` (enabled)

Análogo ao PR 3.

### PR 6 — Cache do estágio `room_labels`

Mesmo padrão (warn-only e enabled podem ser combinados em 1 PR
porque o estágio é determinístico simples).

### PR 7 — Cache do estágio `rooms_from_seeds`

### PR 8 — Cache do estágio `openings_vector`

### PR 9 — Cache do estágio `render_axon`

### PR 10 — Cache do estágio `sketchup_export`

⚠️ **CUIDADO ESPECIAL:** key inclui hash de `consume_consensus.rb` E
versão do SU. Se SU2026 atualizar (build 26.0.491 → 26.0.492),
cache invalida automaticamente. Bom — evita .skp stale por bug do
SU.

### PR 11 — Cache do estágio `validator`

Cache por (PNG hash, scorer hash, vision_enabled). Vision response
do Ollama pode demorar 30s — cache aqui é big win.

### PR 12 — Cache GC + observability

Adiciona:
- `agents/cache_keeper/run_gc.py` — script standalone que lê
  `_meta/cache_index.jsonl`, calcula least-recently-used, deleta
  entries não usadas em N dias OU se cache > X GB
- Seção "Cache health" no `agents/auditor/run_audit.py`
- Documentação `docs/performance/cache_observability.md`

### PR 13 — Default cache ON

Após 2 semanas de uso opt-in sem incidentes:
- Inverter default: `SKM_USE_CACHE=1` por default; `SKM_NO_CACHE=1`
  pra desabilitar
- Atualizar README/OVERVIEW
- Bench em CI confirma economia consistente

## Critérios pra avançar de PR pra PR

Cada PR só é mergeado se:
1. ✅ pytest baseline mantido (nenhuma regressão funcional)
2. ✅ Output byte-identical pra inputs idênticos (validado em test)
3. ✅ Performance Specialist aprova (ganho > esperado, sem regressão
   em output)
4. ✅ Geometry Specialist aprova (se PR toca raster/vector/openings)
5. ✅ SketchUp Specialist aprova (PR 10)
6. ✅ Hit rate observado em runs reais (warn-only logs) > 80% após
   warmup

Se algum critério falha, PR fica em discussão; não força.

## Métricas de sucesso

Após PR 13, bench warm vs cold no mesmo PDF deve mostrar:

| Estágio | Cold (s) | Warm (s) | Economia |
|---|---|---|---|
| raster | 2.5 | 0.05 | -98% |
| vector_consensus | 0.6 | 0.05 | -92% |
| room_labels | 0.2 | 0.02 | -90% |
| rooms_from_seeds | 1.8 | 0.05 | -97% |
| openings_vector | 0.5 | 0.03 | -94% |
| render_axon | 1.2 | 0.05 | -96% |
| sketchup_export | 65.0 (SU spawn) | 0.10 | -99% |
| validation | 2.5 | 0.05 | -98% |
| **TOTAL** | ~74s | ~0.4s | **-99%** |

Esses são targets — valores reais virão dos benches.

## Rollback strategies

### Rollback de 1 estágio
```bash
git revert <commit-do-pr>
```
Outros estágios continuam cacheando normalmente.

### Rollback global temporário
```bash
export SKM_NO_CACHE=1
# todo cache desligado, sem reverter código
```

### Rollback completo
```bash
git revert <pr-1>..<pr-13>
rm -rf runs/.cache
```

### Cache corruption isolada
```bash
# limpar 1 estágio
rm -rf runs/.cache/raster/
# próxima run reconstrói esse estágio do zero
```

## O que esta fase NÃO faz

- ❌ Não implementa nenhum cache (nem mesmo o PR 1 da infraestrutura
  é parte deste commit)
- ❌ Não cria `packages/cache/`
- ❌ Não modifica nenhum estágio do pipeline
- ❌ Não adiciona dependências

A implementação real começa em PR dedicado quando humano decidir
priorizar cache vs outras frentes (ver Commit 4 do roadmap em
`docs/repo_hardening_plan.md`).

## Decisão pendente: cache compartilhado entre máquinas?

**Hoje (default proposto):** local-only em `runs/.cache/`. Cada
máquina tem seu cache. Simples.

**Futuro possível:** S3/GCS bucket com prefix por máquina + plataforma.
Útil pra CI: build na ubuntu-latest cacheia em S3, próxima run no
mesmo SHA pega cache. Adiciona complexidade (auth, cost, eviction
policy).

Decisão fica pra discussão humana — não ditar em design doc.
