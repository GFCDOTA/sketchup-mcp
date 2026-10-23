# SKP Proof-of-Progress Summary — fp054-suite01-circulation (#381)

## Change

Na Suíte 01 (`r000`) da planta_74, a cadeira da escrivaninha fechava a passagem entre a porta do quarto e a da suíte (corredor
mobiliado 0,00 m; o pré-voo da FP-054 recusava materializar o apartamento). Decisão do Felipe (2026-10-23, no chat): tirar a
cadeira e subir só o criado-mudo de baixo 1 in (−y, afastando-o da escrivaninha). Registrada em
`tools/rooms/bedroom/layout_decisions.py` com origem `user_request`. Nenhuma parede, abertura ou cômodo muda.

## Canonical input

- **PDF**: `projects/planta_74/source/planta_74.pdf` (não lido nem alterado)
- **Consensus**: `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
  - SHA256 (LF): `69dbbf0394b5197321e511d5518cf6bb0ae6772879a6edfb285d4be36f3fe2be`
- **Builder commit before**: `92ff9d5` (develop antes desta PR)
- **Builder commit after**: `91aad4b` (commit sob prova, `dirty: false`)
- **SU version**: 26.0.429

## Artifacts

### Before

- **SKP**: não materializável no `develop` atual — o pré-voo (#386) recusa o layout original (`BLOCKED_LAYOUT_GATE`, `r000:circulation`).
  O `.skp` mobiliado canônico `artifacts/planta_74/furnished/planta_74_furnished.skp` é de agosto e ainda não tinha escrivaninha,
  então não é o "antes" desta decisão. O "antes" fiel é a planta das caixas do mesmo pipeline (painel esquerdo do side-by-side).

### After

- **SKP**: `artifacts/review/planta_74/fix-fp054-suite01-circulation/final/planta_74_after.skp`
  (sha256 `61002331aa754ea30c8e710454c34f01b963ca443f3747a0e213eb9e8f6463d4`, 3.355.264 bytes)
- **Top render**: `model_top_after.png` (apartamento) e `suite01_top_after.png` (foco na Suíte 01, `.skp` reaberto)
- **Iso render**: `model_iso_after.png`
- **Geometry report**: `artifacts/review/fp054/suite01_l2/inspect_summary.json` (88 grupos do modelo reaberto)

### Side-by-side

- **Composite**: `side_by_side_before_after.png` — planta das caixas antes × depois (mesmo pipeline, y para cima como no
  SketchUp, corredor medido pelo gate) + renders do `.skp` gerado no L2.

## Before / After comparison

| Eixo | Before | After | Verdict | Evidência específica |
|---|---|---|---|---|
| `wall_fidelity` | consensus inalterado | consensus inalterado | N/A | nenhuma parede tocada; SHA-256 do consensus e dos canônicos idêntico antes/depois (`summary.json`) |
| `door_fidelity` | 2 portais na Suíte 01 | 2 portais | N/A | aberturas inalteradas; `room_collisions` sem nenhum móvel no giro de porta |
| `furniture_layout` | corredor 0,00 m, gate FAIL | corredor 0,91 m, gate PASS | PASS | cadeira removida (8 peças), criado-mudo 1 −1 in em y; diff de snapshot FP-047: 13 deltas, todos na Suíte 01 — 8 peças da cadeira removidas + 5 peças do Criado-mudo 1 só em y; os outros 7 cômodos idênticos; snapshot `03140fb8…` → `5426c008…`, 402 → 394 peças |
| `wall_penetration` | 0 | 0 | PASS | pré-voo com `room_collisions`: nada dentro de parede; a 1ª variante (cama 2 in) punha 176 cm² e foi recusada |
| `materialization` | — | `.skp` salvo, reaberto em outro processo | PASS | 63/63 módulos planejados viraram grupos; 7 módulos da Suíte 01 batem com o plano em XY com erro máx. 0,05 mm |

## Veredito

**PASS (L1 + L2).** Visual: `PENDING_HUMAN` — o Felipe decide no chat.
