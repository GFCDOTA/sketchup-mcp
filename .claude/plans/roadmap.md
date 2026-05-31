# Roadmap — sketchup-mcp

Macro milestones. Não é backlog infinito — só os blocos que
destravam o produto final.

> **Cuidado:** este arquivo é heurístico baseado em estado
> público do repo (PRs mergeadas). Verificar com humano se há
> direção estratégica diferente.

## M0 — pipeline mínimo (concluído)

- Status: ✅ feito (PR #184)
- Critério de saída: repo podado, `consensus.json →
  build_plan_shell_skp → .skp` funciona end-to-end

## M1 — fidelidade canônica em planta_74 (em progresso)

- Status: 🟡 baseline OK, refinamento em curso
- Critério de saída: `artifacts/planta_74/` carrega SKP
  fidelidade-WARN justificada, com side-by-side + report + 6
  contract tests verdes
- Blockers conhecidos: room_fidelity WARN por open-plan cells
  (planta_74 r001/r002) — backlog `semantic_zones` overlay

## M2 — segundo apartamento real

- Status: ⚪ não iniciado
- Critério de saída: segunda planta (e.g. `planta_<X>`) com
  artifact canônico no mesmo padrão de `planta_74`
- Pré-requisito: M1 estável

## M3 — semantic zones overlay

- Status: ⚪ não iniciado
- Critério de saída: cells open-plan (r001/r002 em planta_74)
  ganham split semântico sem forjar wall geometry. Spec +
  fixture + teste + aplicação em planta_74
- Pré-requisito: PDF anotação humana ou heurística confiável (ver
  `specs/perfect_reference_strategy.md`)

## M4 — vector PDF extractor canônico

- Status: ⚪ não iniciado / pré-requisito incerto
- Critério de saída: `tools/build_vector_consensus.py` (ou
  equivalente) produzindo `observed_model.json` honesto pra um
  PDF vetorial novo, sem fabricar paredes
- Pré-requisito: clareza sobre tier de verdade (ver
  `specs/perfect_reference_strategy.md`)

## Não-roadmap

- Dashboard / UI visual: foi podado em PR #184. Não voltar sem
  decisão de produto explícita.
- Real-time editing: fora de escopo.
- Conversão end-to-end qualquer PDF qualquer: fora de escopo (PDFs
  raster sem escala continuam exigindo anotação humana).

## TODO — validar contra repo

- [ ] Confirmar com humano se M2/M3/M4 batem com direção real
- [ ] Adicionar dates targets se houver acordo
