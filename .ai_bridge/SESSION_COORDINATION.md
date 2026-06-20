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

## Claims ativos
| MT | descrição | dono (branch) | status |
|----|-----------|---------------|--------|
| MT-18 | driver kitchen_vray canônico | feat/living-room-golden-sample-propagation | DONE (459d9dc) |
| MT-01 | FILL3 luz lado direito | feat/living-room-golden-sample-propagation | DONE (459d9dc) |
| MT-09/10 | gates honestos (vent_gap, circulação) | **fix/kitchen-ergo-metric-gates** | em andamento (Sessão B) |
