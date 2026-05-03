# Content-Addressed Cache Design

> **Status:** proposta de design. Não implementar nesta etapa.
> Documenta a estratégia de cache antes de qualquer linha de código.

## Por que cachear

Hoje o pipeline reprocessa o mesmo PDF do zero a cada chamada:
1. Re-rasteriza (`pypdfium2` é o gargalo principal — 2-5s por PDF)
2. Re-extrai walls vetoriais
3. Re-faz flood-fill de rooms
4. Re-renderiza axon
5. Re-roda validator scoring (se manifest mudou)

Quando o input não mudou, isso é desperdício. Para iteração de
desenvolvimento (testar uma mudança em `consume_consensus.rb` sem
re-rodar o vector pipeline) o ganho potencial é **80-95%** do tempo
total.

## Por que content-addressed (não path-based)

Path-based cache ("cachear por nome de arquivo") quebra quando:
- Mesmo PDF é renomeado/copiado pra outro path
- PDF é editado mas mantém nome (cache stale invisível)
- Múltiplos devs em máquinas diferentes não compartilham cache

Content-addressed (chave = SHA256 do conteúdo + parâmetros relevantes)
resolve todos esses problemas. Trade-off: custo do hash (negligenciável
pra PDFs < 50 MB).

## Granularidade

Cachear em granularidade de **estágio do pipeline**, não monolítico:

| Estágio | Input | Output | Cache key |
|---|---|---|---|
| Rasterização | PDF + DPI | PNG bytes | `sha256(pdf) + dpi + page_idx` |
| Vector consensus | PDF + thresholds | walls + soft_barriers | `sha256(pdf) + sha256(thresholds_dict)` |
| Room labels | PDF | labels.json | `sha256(pdf)` |
| Rooms from seeds | walls + labels | rooms | `sha256(walls.json) + sha256(labels.json)` |
| Openings vector | PDF + walls | openings | `sha256(pdf) + sha256(walls.json)` |
| Render axon | consensus.json | PNG | `sha256(consensus.json) + view_mode + view_params` |
| SketchUp export | consensus.json | .skp | `sha256(consensus.json) + sha256(consume_consensus.rb)` |
| Validator scoring | PNG + manifest entry | score | `sha256(png) + sha256(scorer.py)` |

**Granularidade rasa demais** (cache só do PDF -> tudo): perde caso
de "consume_consensus.rb mudou, regenerar .skp mas não vector
consensus".

**Granularidade fina demais** (cada função): overhead de hash >
ganho. Mantenho no nível de estágio.

## Estrutura física do cache

```
runs/.cache/
├── raster/
│   └── <sha256[:16]>_dpi<N>_p<idx>.png
├── vector_consensus/
│   └── <sha256[:16]>_<params_hash[:8]>.json
├── room_labels/
│   └── <sha256[:16]>.json
├── rooms_from_seeds/
│   └── <walls_hash[:16]>_<labels_hash[:16]>.json
├── openings_vector/
│   └── <pdf_hash[:16]>_<walls_hash[:16]>.json
├── render_axon/
│   └── <consensus_hash[:16]>_<mode>_<params_hash[:8]>.png
├── sketchup_export/
│   └── <consensus_hash[:16]>_<rb_hash[:16]>.skp
├── validator/
│   └── <png_hash[:16]>_<scorer_hash[:16]>.json
└── _meta/
    └── cache_index.jsonl       # append-only log: timestamp, key, hit/miss, size
```

**runs/.cache/** porque:
- runs/ já está em `.gitignore` (linha 19)
- Cache local, não compartilhado em git
- Co-localizado com outros artefatos efêmeros

**Por que SHA256[:16]:** suficiente pra evitar colisão prática, nome
legível, prefix-friendly pra ls.

## Invalidação

A chave de cache deve incluir TUDO que afeta o output:
- Hash do input principal (PDF, JSON anterior)
- Hash dos parâmetros (dict ordenado e serializado)
- Hash do código que produz (versão do estágio) — opcional, mas
  recomendado pra evitar stale cache após bugfix

**Não usar mtime do arquivo** — frágil (cópia, git checkout,
filesystems sem subseg precision).

**TTL?** Não por default — cache é content-addressed, então só fica
stale se o conteúdo mudar (que muda a chave). Garbage collection é
manual:

```bash
# Limpar entries mais antigas que 30 dias (acesso, não criação)
find runs/.cache -type f -atime +30 -delete
# Limpar tudo
rm -rf runs/.cache
```

## Disable / opt-out

Cache **opt-in por default** durante rollout. Cada estágio tem flag
de bypass:

```python
# CLI
python -m tools.build_vector_consensus planta.pdf --no-cache
# ou via env
SKM_NO_CACHE=1 python main.py extract planta.pdf
# ou seletivo
SKM_NO_CACHE=raster,render python -m tools.render_axon ...
```

Default mode: **warn-only** (loga "would have hit/missed", roda como
hoje). Após 1 semana de validação, vira **enabled**. Após mais 1
semana, fica **default-on**.

## Observabilidade

Cada hit/miss vai pra `runs/.cache/_meta/cache_index.jsonl`:

```jsonl
{"ts":"2026-05-02T19:00:00Z","stage":"raster","key":"abc123...","status":"miss","compute_s":2.4,"output_bytes":1024000}
{"ts":"2026-05-02T19:00:30Z","stage":"raster","key":"abc123...","status":"hit","load_s":0.05,"output_bytes":1024000}
```

`scripts/benchmark/bench_pipeline.py` (FASE 2 do roadmap) deve
respeitar `SKM_NO_CACHE=1` por default — bench mede pipeline cold.

Cache hit rate visível em:
- `agents/auditor/run_audit.py` (FASE 3, próxima versão) — adiciona
  seção "Cache health"
- Dashboard (Phase futura) — gráfico hit rate por estágio

## Como medir ganho

1. Capturar baseline cold em `reports/perf_baseline.json`
   (`SKM_NO_CACHE=1`)
2. Capturar baseline warm (segunda run sem flag)
3. Diff por estágio:
   - hit rate por estágio
   - tempo médio por hit
   - tempo médio por miss
   - economia total (warm vs cold)

Esperado em PDF que não mudou:
- raster: 0 ms (hit) vs 2-5s (miss) — 100% economia
- vector consensus: 0.05s (hit) vs 0.6s (miss) — ~92%
- render: 0.05s (hit) vs 1.2s (miss) — ~96%
- Total pipeline: 30s -> 1s (97% economia)

## Risks

1. **Stale cache hidden** — chave incompleta libera output errado.
   Mitigação: incluir hash do código no key (versionado), validar com
   hash da output (sanity check).
2. **Filesystem race** — duas runs simultâneas escrevem mesma chave.
   Mitigação: write to temp + atomic rename.
3. **Disk fill** — runs/.cache cresce sem limite. Mitigação: doc de
   GC manual + alerta no auditor quando > 1 GB.
4. **Cache corruption** — file truncado por crash. Mitigação:
   validação de integridade (size + sample bytes) antes de servir hit.
5. **Multi-machine consistency** — se cache for compartilhado (não é
   por default), hash de Python version / OS pode importar pra
   estágios que usam binding nativo (cv2, shapely). Mitigação:
   cache local-only por default, prefix de plataforma no path se
   compartilhado.

## Rollback

Implementação faseada (ver [`cache_rollout_plan.md`](cache_rollout_plan.md))
permite rollback estágio por estágio:

```bash
# Desligar tudo
rm -rf runs/.cache
export SKM_NO_CACHE=1
# Desligar um estágio
export SKM_NO_CACHE=render
```

Reverter código:
```bash
git revert <commit-hash-do-estágio>
```

Cada estágio é commit dedicado, então rollback é cirúrgico.

## O que esta fase NÃO faz

- ❌ Não implementa nenhum cache (só design)
- ❌ Não cria `runs/.cache/`
- ❌ Não modifica nenhum estágio do pipeline
- ❌ Não adiciona dependência (no `diskcache`, `joblib`, etc. ainda)

A implementação real é decisão humana, vai em PR dedicado por estágio,
sequência em `cache_rollout_plan.md`.
