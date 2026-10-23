# FP-054 F2B — geometria compartilhada e motor de restrições rígidas (2026-10-23)

## Geometria consolidada
As medições (espaço livre, trecho usável da interface, folga, vão, alcance, gargalo) saíram de
`tools/validation/functional_clearance.py` para `tools/rooms/shared/spatial_solver/geometry.py` (uma implementação; o
validador re-exporta). Prova de equivalência: o relatório da F1C regenerado depois da mudança é **byte a byte idêntico** ao de
antes.

## Motor (`tools/rooms/shared/spatial_solver/engine.py`)
Rígido = INVALID funcional (modo SOLVER), entrada inválida, colisão (núcleo canônico `furniture_overlap_gate`, nível FAIL, com Z e
embutidos), peça fora do cômodo, invasão de parede e de giro de porta (`room_collisions`), corredor do cômodo reprovado.
Cada violação traz **culpado** (parede, outra peça, a entrada declarada, gargalo) e medida.

Correções feitas antes de aceitar números: a 1ª versão acusava colisão bancada×cuba (embutida) e bancada×espelho (na parede,
acima) por ignorar Z e hospedagem — trocado pelo núcleo canônico de sobreposição.

## Defeitos conhecidos reproduzidos (planta_74) — exatamente os 8 da F1C
| Cômodo | Violação | Peça | Medido / mínimo | Culpado |
|---|---|---|---|---|
| Banho 01 | largura do vão do box | Box | 0,327 / 0,60 m (0,411 declarado) | WALL — o trecho declarado começa dentro do revestimento |
| Banho 02 | frente da entrada do box | Box | 0,00 / 0,60 m | WALL — a frente do box está contra a parede oeste |
| Banho 02 | largura do vão do box | Box | 0,00 / 0,60 m | WALL |
| Banho 02 | alcance do box | Box | 0,00 / 0,60 m | INTERFACE_OBSTRUCTED |
| Banho 02 | frente do vaso | Vaso | 0,523 / 0,60 m | WALL (parede oposta) |
| Lavabo | frente do lavatório | Bancada | 0,044 / 0,55 m | Vaso |
| Lavabo | frente do vaso | Vaso | 0,032 / 0,60 m | Bancada |
| Lavabo | alcance do vaso | Vaso | 0,00 / 0,60 m | PATH_DISCONNECTED |

Cozinha: **viável**, sem violação; margem mínima 0,19 m (frente 1,09 m; alcance 1,34 m, gargalo na entrada).

## Cenários sintéticos (testes)
Sala limpa viável; box com a frente contra a parede; vão insuficiente com frente sobrando (profundidade não compensa); porta do
cômodo bloqueada (corredor reprovado + peça no giro da porta); peça com espaço na frente mas cercada (alcance desconectado); duas
peças sem colisão com zonas de uso incompatíveis (culpam uma à outra); gargalo na entrada da cozinha localizado; interface
semântica ausente = violação de entrada.
