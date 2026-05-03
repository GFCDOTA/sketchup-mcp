# scripts/benchmark/

Pipeline performance benchmarks. Read-only over the pipeline — measure
without changing.

## bench_pipeline.py

Mede tempo + memória por estágio do pipeline vetorial (e opcionalmente
SketchUp export + validation).

### Uso básico

```bash
# Single run com PDF canônico
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out reports/perf_baseline.json

# Mediana de 3 runs com 1 warmup (recomendado pra baseline)
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out reports/perf_baseline.json \
    --runs 3 --warmup 1 \
    --label "baseline-2026-05-02"
```

### Estágios medidos

Vector pipeline (sempre rodam):
- `vector_consensus` — `tools/build_vector_consensus.py`
- `extract_room_labels` — `tools/extract_room_labels.py`
- `rooms_from_seeds` — `tools/rooms_from_seeds.py`
- `extract_openings_vector` — `tools/extract_openings_vector.py`
- `render_axon_top` — `tools/render_axon.py` (matplotlib)

Optional (skipped if dependency missing):
- `sketchup_export` — só roda se `C:/Program Files/SketchUp/SketchUp 2026/SketchUp/SketchUp.exe` existe
- `validation` — chama `validator/run.py --once`

### Output

JSON com:
- `timestamp`, `git_commit`, `git_branch`, `python_version`, `platform`
- `input.pdf_sha256` — pra detectar quando benchmark trocou de input
- `command` — comando exato pra reproduzir
- `summary` — mediana/min/max/CV por estágio
- `runs_raw` — todas as runs individuais pra inspeção

### O que NÃO faz

- ❌ Não modifica código do pipeline
- ❌ Não modifica `consensus_model.json` produzido (escreve em scratch dir)
- ❌ Não exige `planta_74.pdf` no repo — aceita qualquer PDF via `--pdf`
- ❌ Não requer SketchUp — pula se não instalado
- ❌ Não requer Ollama — pula se não disponível
- ❌ Não falha se um estágio quebrar — marca `failed` e segue
  pros próximos

### Workflow típico de uso

```bash
# 1. Capturar baseline na main
git checkout main
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out reports/perf_main.json \
    --runs 3 --warmup 1

# 2. Trocar pra branch de teste
git checkout feature/some-optimization
python scripts/benchmark/bench_pipeline.py \
    --pdf planta_74.pdf \
    --out reports/perf_feature.json \
    --runs 3 --warmup 1

# 3. Comparar (manual ou via diff de jq)
diff <(jq '.summary' reports/perf_main.json) \
     <(jq '.summary' reports/perf_feature.json)
```

### Estabilidade da medição

- Coeficiente de variação (CV) reportado por estágio
- Se CV > 10% em estágios curtos (< 1s), ambiente é ruidoso —
  rodar em máquina idle ou aumentar `--runs`
- Warmup de 1 run recomendado pra estabilizar caches do filesystem

### Consumido por

- `docs/agents/performance_specialist.md` — agent que compara reports
- Future: `.github/workflows/perf-baseline.yml` (FASE 5+ do roadmap)

### Limitações conhecidas

- Não mede CPU time vs wall-clock separadamente
- Não captura GPU usage (CubiCasa oracle desligado por default)
- Pico de memória em Windows depende de `psutil`; sem `psutil` retorna 0
- SU2026 spawn é assíncrono (60-90s); CV pode ser alto pra sketchup_export
