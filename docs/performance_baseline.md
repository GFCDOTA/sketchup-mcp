# Performance Baseline

> Como medir performance do pipeline e estabelecer baseline pra
> detectar regressões em PRs futuros.

## Por que medir

Sem baseline, regressões silenciosas (10-30% mais lento) passam
despercebidas até alguém reclamar. Com baseline, o `Performance
Specialist` (read-only agent definido em
[`docs/agents/performance_specialist.md`](agents/performance_specialist.md))
pode detectar e bloquear regressões > 20% em qualquer estágio.

## Ferramenta

[`scripts/benchmark/bench_pipeline.py`](../scripts/benchmark/bench_pipeline.py)
mede tempo + memória por estágio. Não modifica código.

Documentação: [`scripts/benchmark/README.md`](../scripts/benchmark/README.md).

## Workflow recomendado

### 1. Capturar baseline em main

```bash
git checkout main
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out reports/perf_baseline.json \
    --runs 3 --warmup 1 \
    --label "main-$(git rev-parse --short HEAD)"
```

Commitar `reports/perf_baseline.json` em PR dedicado quando ele
mudar significativamente (não a cada commit — só quando há mudança
de baseline real).

### 2. Comparar antes de PR

```bash
# Antes (na main)
git checkout main
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out /tmp/perf_before.json \
    --runs 3 --warmup 1

# Depois (na branch)
git checkout feature/x
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out /tmp/perf_after.json \
    --runs 3 --warmup 1

# Comparar
diff <(jq '.summary' /tmp/perf_before.json) \
     <(jq '.summary' /tmp/perf_after.json)
```

### 3. Diff esperado

| Métrica | Antes | Depois | Aceitável | Decisão |
|---|---|---|---|---|
| `vector_consensus.elapsed_s_median` | 0.612s | 0.638s | +4.2% | ✅ ok |
| `rooms_from_seeds.elapsed_s_median` | 1.847s | 2.301s | +24.6% | 🟡 discuss |
| `extract_openings_vector.elapsed_s_median` | 0.493s | 0.812s | +64.7% | 🔴 block |

Tolerâncias do `Performance Specialist`:
- ≤ 20% por estágio: ok
- 20-50%: discuss (precisa justificativa no PR)
- > 50%: block

## PDFs canônicos pra benchmark

| PDF | Onde | Características |
|---|---|---|
| `planta_74.pdf` | repo root | vetorial complexo, principal test case (33 walls / 11 rooms / 12 openings) |
| `tests/fixtures/svg/minimal_room.svg` | tests/ | sintético rápido, determinístico |

PDFs sintéticos adicionais ficam em `tests/fixtures/` quando
adicionados em commits dedicados.

## Estabilidade

### Coeficiente de Variação (CV)

CV = stdev / mean por estágio. Reportado por `bench_pipeline.py`.

- **CV < 5%**: medição confiável
- **CV 5-10%**: aceitável, mas considerar mais runs
- **CV > 10%**: ambiente ruidoso — rodar em máquina idle ou aumentar
  `--runs` pra 5-10

### Warmup

`--warmup 1` é o mínimo recomendado. Primeira run paga custo de:
- Filesystem cache do PDF
- Import de bibliotecas Python
- JIT/compile inicial

## Limitações conhecidas

1. **Não isola CPU vs wall-clock** — ruído de outros processos no
   sistema afeta resultado
2. **Não captura GPU** — CubiCasa oracle desligado por default
3. **Pico de RSS em Windows** depende de `psutil` (opcional)
4. **SU2026 spawn é assíncrono** — CV alto pra `sketchup_export` é
   esperado; rodar em isolamento se quiser dados confiáveis dele
5. **Validation depende de manifest** — se `runs/png_history/manifest.jsonl`
   não existir, validation skipa

## Sequência futura

| Commit | Escopo |
|---|---|
| ~~Atual~~ | Add `bench_pipeline.py` + README + example output (este commit) |
| Futuro 1 | `reports/perf_baseline.json` real (após executar contra main) |
| Futuro 2 | `.github/workflows/perf-baseline.yml` (cron weekly em main) |
| Futuro 3 | Performance Specialist agent ativando o bench em PRs (FASE 6+) |
| Futuro 4 | Cache de rasterização (FASE 4 do roadmap) — bench valida ganho |

## Não-objetivo

Este baseline **não é budget**. Não falha o CI quando algo extrapola
limite. É observação. Decisão de aceitar regressão fica com humano
revisor do PR.
