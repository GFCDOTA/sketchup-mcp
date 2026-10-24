# Qualificação SketchUp 26 real — matriz abrir/construir/salvar/reabrir/inspecionar (2026-10-24)

Issue: #479 (FP-055 P7). Retrato datado; não reescrever (nova prova vai numa pasta nova).

## Identidade
| Item | Valor |
|---|---|
| Commit sob prova | `5a4262438d33cba9e719bb07ed29abc2d17ad113` (`origin/develop`, worktree limpa: `dirty: false`) |
| SketchUp | 26.0.429 (`SketchUp 2026`), modo interativo |
| PIDs abertos e fechados pelo script | 8880, 27700, 32060 (build, `inspect_model`, `inspect_geometry`; todos fechados, conferido por `tasklist`) |
| Escala | `PT_TO_M=0.0259`; cadeia de escala do contrato OK |
| Script | `artifacts/review/fp056/p6/run_p6.py` (inalterado) |

## Matriz
| Etapa | Resultado |
|---|---|
| pré-voo obrigatório (circulação, sobreposição, parede/barreira/giro) | PASS |
| construir + salvar (cópia do shell canônico → mobiliado em `runs/`) | PASS |
| reabrir em **outro processo** + inspecionar modelo + extrair geometria | PASS |
| todo módulo planejado existe como grupo dentro de 5 mm | PASS |
| paredes construídas = consensus | PASS |
| sem defeito novo/pior vs baseline FP-055 P4 | PASS |
| canônicos byte-idênticos (SHA-256 antes/depois) | PASS |
| PIDs próprios fechados | PASS |
| sem perda de programa sem decisão registrada | **FAIL esperado**: `r001|PROGRAM|Bancada gourmet` e `r001|PROGRAM|Banqueta`, as **duas** lacunas já registradas em `docs/governance/known_gaps.json` (decisões do proprietário). O `run_p6` não consulta o registro; o gate do CI (`quality_geometry_gate`) consulta e dá `KNOWN`. |

## O que é e o que NÃO é
- É prova **L2 de execução** (SketchUp real, reabertura em outro processo). A aparência continua **`PENDING_HUMAN`**: nenhum veredito visual aqui.
- O ambiente construído ainda tem defeitos persistentes do baseline (6 dos 8 cômodos com status FAIL no validador v2: defeitos conhecidos e travados, nenhum novo). Isto **não** declara o apartamento correto.
- Não prova capacidades individuais do catálogo (R-18) nem substitui revisão independente.

## Reprodução
`PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p6/run_p6.py runs/fp055/p7_qualification` (commit limpo; saída em `runs/`).
Arquivos aqui: `summary.json` (casos, PIDs, versões, SHA-256), `regression.json` (comparação com o baseline).
