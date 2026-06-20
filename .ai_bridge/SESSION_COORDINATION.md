# SESSION_COORDINATION — cozinha planta_74 (multi-sessão)

> Fio de coordenação entre sessões paralelas trabalhando a cozinha. Ler ANTES de
> reivindicar qualquer microtarefa do `artifacts/reference_lab/kitchen/spec/KITCHEN_TO_100.md`.

## ⚠️ Colisão registrada — 2026-06-20 (MT-09/10 gates)
Duas sessões fizeram a MESMA microtarefa (endurecer `fridge_vent_gap` + circulação) em paralelo:
- **Sessão B** (worktree `E:/Claude/worktrees/kitchen-ergo-gates`, branch `fix/kitchen-ergo-metric-gates`):
  commit `9917c2d` — vent_gap (2,6)→(6,12) + `work_triangle_fridge_cooktop_m` (≥1,2 m). **Dona oficial do MT-09/10.**
- **Sessão A** (branch `feat/living-room-golden-sample-propagation`): commit `27267a6` — mesma coisa +
  `cooktop_fridge_sep` (separação térmica ≥60 cm). **REVERTIDO em `6b47bac`** (defiro pra Sessão B; era scope-creep).

**Oferta da Sessão A pra Sessão B (opcional):** considerar adicionar `cooktop_fridge_sep`
(geladeira↔cooktop ≥60 cm, "frio longe do calor", spec §0.3) ao gate — complementa o work-triangle de vocês.

## Regra de coordenação (pra não atropelar de novo)
1. **`KITCHEN_TO_100.md` é o ÚNICO backlog.** Toda microtarefa tem **UM dono** = **UMA branch**.
2. **Antes de pegar uma microtarefa:** `git worktree list` + `git fetch --all` + ler esta nota.
   Se outra sessão já está numa MT, NÃO pegar a mesma.
3. **Fase GEO** (MT-23..MT-32, mexe geometria congelada do GOLDEN_SAMPLE_004): **só com OK explícito do Felipe.**
4. **Anunciar aqui** ao reivindicar/soltar uma MT (data + branch + MT#).

## Estado do develop (2026-06-20, atualizado)
`origin/develop @ f7f2f95`. A **Sessão B (handoff/integradora)** landou a lane de MEDIDORES inteira:
- `48a1ebd` (#230) = MT-09/10 · `f7f2f95` = MT-11/13/14 (clearances de uso; achado real
  `faucet_to_upper_clearance=0.32m WARN`). Worktree `kitchen-ergo-gates` já removida.

## Divisão de LANES (pra não atropelar — acordado pela Sessão A)
- **Sessão B (integradora):** MEDIDORES + PIPELINE + git (kitchen_ergonomics, **MT-15** wire dos gates,
  landa em develop, cleanup). É a dona da geometria-de-medição e do runner.
- **Sessão A (esta, `feat/living-room-golden-sample-propagation`):** STUDIO + DESIGN + RENDER PELE
  (dashboard :8782, agentes, `interior-designer` directives, material/luz: MT-02 parede, MT-04/05/06).
  NÃO toca `kitchen_ergonomics.py` nem o runner (lane da B).
- **Ops/limpeza** (portas, NOC, dirs mortos) = lane separada; Sessão A audita, **NÃO deleta o NOC
  :8765** (load-bearing: build_plan_shell_skp + ask_gpt_gate + noc_dispatcher dependem).

## Claims ativos
| MT | descrição | dono (branch) | status |
|----|-----------|---------------|--------|
| MT-18 | driver kitchen_vray canônico | feat/living-room-golden-sample-propagation (A) | DONE (459d9dc) |
| MT-01 | FILL3 luz lado direito | feat/living-room-golden-sample-propagation (A) | DONE (459d9dc) |
| MT-09/10 | gates honestos (vent_gap, circulação) | develop via #230 (B) | **DONE/landed** |
| MT-11/13/14 | clearances de uso | develop @f7f2f95 (B) | **DONE/landed** |
| MT-15 | wire dos gates no pipeline | **Sessão B** (reivindicou) | em andamento (B) — A NÃO pega |
| MT-02 | parede anti-caverna (diretriz do designer pronta) | feat/living-room-golden-sample-propagation (A) | próxima (A) |
| Studio F0 | agentes+reference_db+dashboard | feat/living-room-golden-sample-propagation (A) | DONE |
