# FP-043 — reconciliação do relatório final com a `develop` (2026-10-24)

**Issue:** #459. **Base:** `develop@4fb7f1d`. Este documento **não substitui** [FP-043_final_validation.md](FP-043_final_validation.md)
(retrato de 2026-10-19, `develop@e67f86c`, que continua como foi publicado): registra, ao lado dele, o que mudou e o que continua
aberto. **Estado global mantido: `PARTIAL_BLOCKED`**; FP-043 **não** está encerrada. Não é `VISUAL_REVIEW` nem prova L2 nova.

## 1. Matriz de gates reexecutada (local, Windows, venv do repo, 2026-10-24)
Todos `exit=0`: `tools.rooms.inventory_gate --strict`, `tools.navigation.p0_map --check`, `tools.navigation.docs_check`,
`tools.rooms.ownership_audit`, `tools.rooms.capability_catalog` (errors `{}`), `tools.mcp_server.smoke`, `tools.mcp_server.stdio_check`,
`tools.validation.run_deterministic_gates --fixture quadrado` e `--fixture planta_74` (`PT_TO_M=0.0259`, `overall=PASS`),
`tools.validation.scale_anchor_gate` (planta_74). **Correção de caminho:** o relatório antigo cita `python -m tools.run_deterministic_gates`;
o módulo vive em `tools.validation.run_deterministic_gates` desde a reorganização da raiz (FP-044 F6).

## 2. Status por subfase hoje
| Fase | Estado em 2026-10-19 | Estado hoje | Evidência / Issue |
|---|---|---|---|
| P0–P2, P3a-01/05, P4, P5, P6a/b, P7 | DONE (L1/L2 conforme o relatório) | **sem mudança** | relatório de 2026-10-19; catálogo íntegro hoje |
| P3a-02 / D-007 (laje sob a parede) | PARTIAL, `xfail(strict)` | **PARTIAL**: a origem está sendo tratada pela FP-056 (região utilizável, barreiras, varredura real da folha); o `FLOOR_UNDER_FRAC` segue como está porque mudar o shell muda laje/cell de tudo | FP-056 (#410), #484 (traços sem fonte: decisão do proprietário) |
| P3a-03 (colisões) | DONE_L2 (402/402 peças, 0 na parede) | **superado por medição mais fina**: o gêmeo e o validador v2 registram defeitos persistentes (baseline FP-055 P4: 34 registrados, 29 persistem na geração completa da FP-056 P6) com gate de não regressão e agora trava contra edição do baseline | `artifacts/review/fp055/p4/`, #440, PR 531 |
| P3a-04 (quadrado, D-001) | BLOCKED_DECISION | **sem mudança** (decisão A/B/C do proprietário) | `artifacts/review/fp043/p3a04_quadrado_d001/` |
| P3b (processo/MCP/render/escala) | DONE_L2 para #311 | **parcial**: Windows L2 ok; o smoke estrito `su_*` pelo cliente MCP real depende de reiniciar o servidor (processo velho) e a qualificação SketchUp 26 versionada foi refeita em 2026-10-24 | #457 (aberta), #430, #479 (fechada), `artifacts/review/fp055/p7/qualification_2026-10-24/` |
| P8 (navegação/auditoria/relatório) | DONE_COM_PENDÊNCIAS | **DONE_COM_PENDÊNCIAS**, agora com esta reconciliação | este documento |

## 3. Pendências que continuam reais
1. **Visual (proprietário)**: nenhum `VISUAL_REVIEW` foi atribuído por agente; aparência segue `PENDING_HUMAN`.
2. **D-001 e D-002–D-005**: decisões do proprietário (sem mudança).
3. **D-007**: ver acima (traços sem fonte #484 e região utilizável #431 aguardam o proprietário).
4. **Perda de programa registrada** (Bancada gourmet, Banqueta) em `docs/governance/known_gaps.json`: decisão do proprietário.
5. **Limites de prova**: o CI Linux não substitui o SketchUp; nenhuma prova de hoje aprova aparência.

## 4. O que NÃO é
Não reabre fases DONE, não altera o relatório de 2026-10-19, não toca fixtures/PDF/`.skp` canônicos e não promove nenhum estado de
`PARTIAL_BLOCKED` para `COMPLETE` (as condições da FP-043 §11 seguem não atendidas).
