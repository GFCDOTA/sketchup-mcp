# FP-054 — Suíte 01 (#381): decisão do Felipe aplicada e provada no SketchUp real (L2)

**Defeito:** na Suíte 01 (`r000`) a cadeira da escrivaninha fechava a passagem entre a porta do quarto e a da suíte (corredor
mobiliado 0,00 m; sem a cadeira 0,89 m para alvo 0,90). Desde #386 o pré-voo recusava materializar o apartamento.

**Decisão (Felipe, chat, 2026-10-23):** sem a cadeira da escrivaninha e só o criado-mudo de baixo (`criado_mudo_dir`, módulo
"Criado-mudo 1") 1 in em −y, afastando-o da escrivaninha. A 1ª escolha (conjunto da cama 2 in) foi recusada com medidas: o
criado-mudo de cima já encosta na parede norte e entrava até 176 cm² nela. Registro: `tools/rooms/bedroom/layout_decisions.py`
(origem `user_request`, issue #381).

**Também nesta PR:** o pré-voo (`tools/validation/layout_preflight.py`) passa a rodar `room_collisions` (móvel dentro de parede e
no giro de porta) — a 1ª variante tinha passado nele.

| | |
|---|---|
| Código sob prova | commit `91aad4b`, árvore **limpa** (`dirty: false`) |
| SketchUp | 26.0.429 (Windows 11), `interactive`; PIDs 34092 (furnish) e 31660 (reabertura/inspeção) fechados por PID; renders do antes/depois em 2 PIDs próprios (18792, 3396), também fechados por PID; nenhum SketchUp alheio tocado |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp054/suite01_l2/l2_suite01.py <saida em runs/>` |
| Entrega SKP (Constituição #8) | `artifacts/review/planta_74/fix-fp054-suite01-circulation/final/` (`.skp`, renders, side-by-side, `regression_summary.md`) |

## Resultado — 10 verificações, 10 PASS (`summary.json`)

- pré-voo do apartamento: `PASS` (circulação, sobreposição e colisões em todos os cômodos mobiliados);
- **negativo:** com o layout original (sem a decisão) o `su_furnish` recusa **antes** do SketchUp (`BLOCKED_LAYOUT_GATE`,
  `r000/circulation`), 0 PIDs, sem diretório;
- furnish no SketchUp real: `.skp` salvo (3.355.264 bytes, sha256 `61002331…`);
- **reaberto em outro processo e inspecionado** (88 grupos): os 7 módulos da Suíte 01 batem com o plano em XY com erro máximo
  0,05 mm (`suite01_plan_vs_model.json`); a cadeira não existe no modelo; escrivaninha e Criado-mudo 1 existem; os 63 módulos
  planejados do apartamento viraram grupos;
- canônicos byte a byte idênticos; nenhum scratch em `artifacts/`; nenhum PID próprio vivo no fim.

Regressão por cômodo (FP-047, diff de snapshot): 13 deltas, todos na Suíte 01 (8 peças da cadeira removidas, 5 do Criado-mudo 1
só em y). Corredor 0,00 → 0,91 m; criado-mudo a ≥ 1 cm da cama; nada em parede.

## O que NÃO é

- Não é veredito visual: `PENDING_HUMAN` até o Felipe olhar `side_by_side_before_after.png`.
- Não promove nada a canônico: `artifacts/planta_74/furnished/planta_74_furnished.skp` segue o de agosto (anterior à escrivaninha);
  promover é passo separado (`promote_canonical`) depois do veredito.
- O "antes" no `.skp` não pôde ser materializado (o pré-voo recusa, de propósito); o antes fiel é a planta das caixas do mesmo
  pipeline no side-by-side.
