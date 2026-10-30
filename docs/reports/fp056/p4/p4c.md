# FP-056 P4c — CEILING e SUSPENDED_INTENTIONAL avaliados no gêmeo (2026-10-25)

Issue: #436. Complementa `p4b.md` (que ficou como retrato de 2026-10-24). Medido em `develop` com `PT_TO_M=0.0259`, gêmeo em caixas (L1); sem SketchUp.

## O que passou a ser medido
- **CEILING:** o topo do módulo encosta no teto a no máximo `EPS_DEPTH`. Teto = `CEILING_Z_M = 2,70 m`, a altura do shell (`WALL_HEIGHT_M` de
  `build_plan_shell_skp.rb`; um teste de contrato compara as duas constantes). Falha: `NOT_AT_CEILING` com a folga.
- **SUSPENDED_INTENTIONAL:** o módulo só é válido se alguma peça dele (cabo/haste) chega ao teto; senão `NOT_CONNECTED`.

## Medido na planta_74 (35 módulos julgados; 26 continuam sem modo declarado)
| Cômodo | Módulo | Modo | Resultado |
|---|---|---|---|
| Sala | Pendente | SUSPENDED_INTENTIONAL | **ok**: o cabo (`pend_cabo`) chega a 2,70 m |
| A.S. | Varal de teto | CEILING | `NOT_AT_CEILING`: topo a **62,0 cm** do teto (sem haste modelada) |
| Banho 01 / Banho 02 / Lavabo | PeleTeto | CEILING | `NOT_AT_CEILING`: **14,0 cm** (a pele de teto fica em 2,50–2,56 m) |

Os quatro achados entram no retrato travado de `tests/test_fp056_p4_support_check.py` (não podem piorar nem ganhar item novo).

## O que NÃO é
- Não corrige nada: a pele de teto a 14 cm pode ser um forro rebaixado **intencional** (aparência/projeto: decisão do proprietário) e o varal precisa de haste
  modelada ou de decisão. Nenhuma peça foi movida.
- Os 26 módulos sem modo declarado, a bandeja do Lavabo e o Criado-mudo (suspenso a 0,30 m) seguem dependendo do proprietário (ver comentário da #436).
- Medida no gêmeo; aparência `PENDING_HUMAN`.
