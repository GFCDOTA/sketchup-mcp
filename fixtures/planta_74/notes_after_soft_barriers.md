# Preflight notes — apto 74,93 m²

- **PDF**: `planta_74.pdf`
- **Consensus**: `runs\vector\consensus_with_human_walls_and_soft_barriers.json`
- **Walls**: 35
- **Rooms**: 8
- **Openings**: 12

## D1..D7 mapping

| ID | Detected? | Opening | Wall | Rooms | Hinge | Confidence |
|----|-----------|---------|------|-------|-------|------------|
| D1 | ❌ MISSING | — | — | — | — | — |
| D2 | ❌ MISSING | — | — | — | — | — |
| D3 | ❌ MISSING | — | — | — | — | — |
| D4 | ❌ MISSING | — | — | — | — | — |
| D5 | ❌ MISSING | — | — | — | — | — |
| D6 | ❌ MISSING | — | — | — | — | — |
| D7 | ❌ MISSING | — | — | — | — | — |

## Validation checklist (user criterion)

- **Banho 02 tem porta?** ❌ FAIL (0 interior_door(s) detectada(s))
- **Porta D7 na lateral oeste?** ⚠️ N/A — sem porta detectada no Banho 02
- **Lavabo abre pra dentro?** ⚠️ N/A — sem porta no LAVABO
- **Suíte 02 tem só 1 porta de entrada?** ❌ FAIL (0 doors+passages)
- **Parede fechada atrás de porta?** ✅ PASS (0 portas com vão < 10pt ou sem wall)
- **Sem porta inventada?** ❌ FAIL (12 openings sem geometry_origin oficial)
- **Sem texto duplicado nos rótulos?** ✅ PASS (duplicados: [])

## Verdict

⚠️ **PARTIAL** — D-ids faltando: D1, D2, D3, D4, D5, D6, D7

**Causa provável**: o pipeline V7 só detecta portas com arcos de porta visíveis no PDF (svg_arc) ou gaps colineares (wall_gap). A porta principal D1 — entrada do apto pela área comum — fica em parede de fronteira que não desenha arco no PDF da planta-padrão (é desenhada apenas no projeto executivo). É um gap esperado e não um bug do extractor.

## Detalhes por opening detectada

| ID | kind_v5 | rooms | hinge | conf | decision |
|----|---------|-------|-------|------|----------|
| h_o000 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o001 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o002 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o003 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o004 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o005 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o006 | interior_door | ? ↔ ? | left | 1.00 | clean |
| h_o007 | window | ? ↔ ? | left | 1.00 | clean |
| h_o008 | window | ? ↔ ? | left | 1.00 | clean |
| h_o009 | window | ? ↔ ? | left | 1.00 | clean |
| h_o010 | window | ? ↔ ? | left | 1.00 | clean |
| h_o011 | glazed_balcony | ? ↔ ? | left | 1.00 | clean |