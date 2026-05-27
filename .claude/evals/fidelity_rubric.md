# Fidelity rubric — sketchup-mcp

Rubric pra Camada 3 (julgamento humano). Cada dimensão tem
critérios OK / WARN / FAIL, com justificativa exigida pra WARN/FAIL.

> Camada 3 é qualitativa por design — não há campo
> machine-readable hoje. Esta rubric existe pra que reviewers
> humanos avaliem com critério consistente, não com gosto.

## Como usar

1. Após build SKP + render + side-by-side, abrir
   `artifacts/<plant>/README.md`
2. Preencher seção `## Status` com OK/WARN/FAIL por dimensão +
   justificativa
3. Se houver WARN ou FAIL, citar critério desta rubric (e.g.
   "FAIL: dimensão A1 — wall não extrudada")
4. PR review humano valida que o status está honesto

## Dimensão A — Walls (paredes)

### A1 — Walls da consensus aparecem como mass extrudada

- **OK**: 100% das walls em `consensus.walls[]` viraram
  geometria extrudada visível
- **WARN**: 1+ wall presente mas com geometria degenerada
  (comprimento <ε, sliver)
- **FAIL**: 1+ wall em `consensus.walls[]` sumiu do SKP

Evidência: comparar `shell_stats_from_python.input_walls` com
walls visíveis no render top + count de groups `Floor_Group_*` /
`PlanShell_Group` no `geometry_report.json`.

### A2 — Sem stubs residuais

- **OK**: nenhum stub residual (PR #192 / FP-026 #193)
- **WARN**: stub <X.X cm (TODO: definir threshold)
- **FAIL**: stub >X.X cm visível no render

Evidência: render top com overlay debug. Ferramenta:
`tools/diagnose_wall_stubs.py`.

### A3 — Sem notches / slivers no shell polygon

- **OK**: `shell_stats_from_python.slivers_removed == 0` E sem
  notches visíveis
- **FAIL**: slivers > 0 OU notch visível no render top

## Dimensão B — Rooms (ambientes)

### B1 — Closed cells emergem do polygonize

- **OK**: `floor_groups.count` == número de ambientes semânticos
  esperados pelo PDF
- **WARN**: `floor_groups.count` < ambientes esperados POR cells
  fundidos open-plan no PDF (sem parede dividindo). Justificar
  cada cell fundido com lista de labels.
- **FAIL**: cell esperado pelo wall geometry não fecha (há
  parede no PDF mas o polygonize não fechou)

Exemplo planta_74 (snapshot 2026-05-27): WARN — 8 cells vs 11
ambientes, com r001 = `A.S. | TERRACO SOCIAL | TERRACO TECNICO`
e r002 = `SALA DE JANTAR | SALA DE ESTAR`. Justificativa: no PDF
não há parede entre esses ambientes (open-plan).

### B2 — Labels semânticos preservados

- **OK**: cells fundidos carregam todos os labels separados por
  `|` no SKP
- **WARN**: labels truncados ou normalizados
- **FAIL**: cell sem label

## Dimensão C — Openings (portas / janelas)

### C1 — `kind_v5` routing correto

- **OK**: window → 3D aperture com peitoril+verga; door /
  passage / porta-vidro → 2D full-height
- **FAIL**: window routed como 2D OU door routed como 3D

Evidência: contar `WindowGlass_Group_*` vs `DoorLeaf_Group_*` vs
`GlazedBalcony_Group_*` em `groups_diagnostic[]`.

### C2 — Soft barriers não viram parede cheia

- **OK**: `soft_barrier_groups` presente com `height_m ≈ 1.1`
  (peitoril/grade)
- **FAIL**: peitoril extrudado até teto (`height_m == 2.7`)

### C3 — `geometry_origin = wall_gap` não foi carved

- **OK**: openings com `geometry_origin: wall_gap` aparecem como
  vão (sem carve adicional)
- **FAIL**: wall_gap foi tratado como carve, gerando dupla-perda
  de mass

## Dimensão D — Visual / dimensional global

### D1 — Side-by-side bate visualmente

- **OK**: reviewer humano confirma que o SKP top render
  sobreposto ao PDF tem walls / openings nos mesmos locais
- **WARN**: discrepância < 5% em uma área isolada
- **FAIL**: discrepância > 5% OU >1 área com discrepância
  visível

### D2 — Dimensões batem com PDF

- **OK**: dimensões críticas (largura total, comprimento total,
  ambientes principais) batem com PDF measure em ±2%
- **FAIL**: discrepância >2%

Evidência: `groups_diagnostic[].bbox_m` vs medidas do PDF.

## Veredito

Para promover pra `artifacts/<plant>/`:

- Toda dimensão A em **OK**
- Toda dimensão B em **OK** ou **WARN justificado**
- Toda dimensão C em **OK**
- Toda dimensão D em **OK** ou **WARN justificado**

Qualquer **FAIL** = não promove. Bloqueia PR.

## TODO

- [ ] Definir threshold exato pra A2 (stub) em cm
- [ ] Definir tolerância exata pra D1 (% discrepância visual) e
      D2 (% discrepância dimensional)
- [ ] Considerar automatizar D2 via comparação dimensional
      automática
