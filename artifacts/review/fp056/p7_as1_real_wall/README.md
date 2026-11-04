# FP-056 — #442 (AS-1) × #488: churrasqueira, coifa e prateleira de serviço encostadas em parede REAL (2026-11-02)

Fecha a lacuna de evidência apontada na auditoria do p7 (`artifacts/review/fp056/p7/README.md`, seção #442): a variante
"churrasqueira 0,85 m" foi medida encostada na "alvenaria cega" do planejador, que **não existe** no consensus. Aqui cada
combinação largura × parede de apoio × posição foi medida **em memória** com o próprio planejador da A.S. e os mesmos gates do p7.

- **Commit sob prova:** `b556ca9f` (`origin/develop`; `code_dirty: false` em `tools/`, `core/`, `fixtures/` no JSON). `PT_TO_M=0.0259`.
- **Sem SketchUp, sem PIDs.** Gêmeo em caixas = L1. Aparência: `PENDING_HUMAN`.
- **Nada aplicado:** gerador, consensus, fixtures e `.skp` intactos (SHA-256 do consensus igual antes/depois, gravado no JSON).

## O que foi variado (em memória, `probe_as1_real_wall.py`)
| | Variação | Onde no planejador |
|---|---|---|
| V1 | largura única 1,00 / 0,85 / 0,70 m da churrasqueira e da coifa | `widths` dos itens, `tools/rooms/service/layout.py:249-255` |
| V2 | parede de apoio `m004` (lado norte do terraço), `m013` (lado leste da A.S.), `m001` (lado sul); zona de colocação = zona do planejador **menos a massa de parede** (`wall_mass_pt`), porque a borda do cell entra 5,6 cm sob `m004`/`m013` | `side`/`zone` dos itens; `_split_zones` (`layout.py:109`) |
| V3 | posição fixa ao longo da face, passo 0,05 m (o passo do `_slide`), toda a extensão da parede no consensus ∩ zona | `_slide(span=0)`, `layout.py:183`; demais checagens e `circulation_gate` do planejador **inalterados** |
| V4 | prateleira de serviço transladada em x até a face real da parede oeste (pós-processamento) | saída do planejador |
`m001` não estava no pedido: entrou porque o próprio `spatial_model` da A.S. lista `blind_wall_candidates = [m001, m013]`.

Critério "apoiado em parede real" = distância da pegada à massa de parede ≤ `EPS_DEPTH` = 0,5 mm (`tools/validation/penetration.py:38`),
a mesma regra do `WALL_MOUNTED` em `tools/validation/support_check.py:83-89`. Nenhum limiar novo.

## Resultado (203 variantes; `as1_real_wall_alternatives.json`)
| Alternativa | Churrasqueira/coifa: distância à parede real | Programa (bancada gourmet / cuba / banquetas / mesa externa / secadora) | Caixas | Pré-voo | Gêmeo novo/pior | Apoio (`support_check`) |
|---|---|---|---|---|---|---|
| atual (1,00 m, constante) | 0,7533 m (`m004`) | não / não / 0 / não / não | 390 | PASS | 0 / 0 | igual ao baseline `KNOWN_MODULES` |
| p7: 0,85 m na constante (= `const_0.85`) | **0,7782 m** (`m004`) | sim / sim / 1 / não / não | 393 | PASS | 0 / 0 | **Coifa PIOR: 0,7533 → 0,7782 m** (o teste `tests/test_fp056_p4_support_check.py:172` reprovaria; tolerância 0,5 mm) |
| 0,70 m na constante | 0,7533 m | não / não / 0 / não / não | 390 | PASS | 0 / 0 | igual |
| `m004` × 1,00/0,85/0,70 (120 posições) | **nunca encosta** | — | — | — | — | — |
| `m013` × 1,00/0,85/0,70 (54 posições) | **nunca entra** | — | — | — | — | — |
| `m001` × 1,00/0,85/0,70 (24 posições) | **nunca entra** | — | — | — | — | — |
| V4 prateleira na face da parede oeste (`m012`), sobre o atual | prateleira 0,3465 → **0,0 m** | inalterado | 390 | PASS | 0 / 0 | achado da Prateleira **some**; nenhum novo |

Por que nenhuma parede real recebe a churrasqueira (motivo medido pelas mesmas checagens do `_slide`, `layout.py:194-203`):
- **`m004`** (y = 13,246 m, x 3,235–6,141): 2,029 m dela é o vão `h_o011` (`glazed_balcony`, centro x = 4,533). A zona de circulação
  do `spatial_model` na frente do vão (x 3,448–5,617, 0,84 m de fundo) é invadida em 31–37 posições por largura
  (ex.: 0,52 m² com 0,85 m em x = 3,86, contra `_DOOR_TOL_M2` = 0,02, `layout.py:87`); as pontas cruzam a mureta construída `h_sb001`
  ou saem da zona. Os únicos trechos de alvenaria de `m004` (x 3,235–3,518 = 0,28 m e x 5,547–6,001 = 0,45 m) são menores que 0,70 m. As 2 posições por largura que
  "passam" caem na linha de corte da zona (y = `_AS_MIN_Y_M`), não em `m004` (0,67–0,71 m de `m001`).
- **`m013`** (x = 3,305 m, face útil y 13,315–14,959): a zona de giro da porta `h_o005` (y 14,177–15,015) ocupa o trecho sul; sobra
  0,86 m de face. 1,00 m não cabe; 0,85 m (1 posição) e 0,70 m (4 posições) passam no `_slide` mas o `circulation_gate` do cômodo
  reprova: `corredor_principal` `CORRIDOR_BLOCKED`, portal SECUNDÁRIO (o `h_o011`) **desconectado** (largura vazia 1,0 m → mobiliada 0,0 m;
  alvo secundário 0,80 m, `tools/validation/circulation_gate.py:17-24`). A churrasqueira fecha a faixa entre o tanque e `m013`.
- **`m001`** (face y = 10,55 m): o contorno sem fonte `sb002` (#484) ocupa o canto; sobra ~0,55 m de face (x 2,152–2,705). Toda
  posição sai da zona (o encosto cai na borda do recorte de `sb002`) e encosta em peça já colocada.

## Alternativas viáveis (tudo apoiado em parede real + pré-voo PASS + 0 defeito novo/pior)
- **Churrasqueira + coifa: nenhuma**, em nenhuma largura do planejador (0,70–1,00 m), em nenhuma das três paredes reais da zona.
  Tornar uma delas viável exige mudar algo que é decisão do Felipe: (i) mover/reduzir peça aprovada da A.S. (tanque) para abrir o
  corredor junto de `m013`; (ii) aceitar a churrasqueira diante do vão `h_o011` (contra o gate de circulação); (iii) decidir #484
  (construir `sb002` como massa daria um apoio real com fonte no canto de `m001`); ou (iv) manter o gap registrado (#488 alternativa d).
- **A variante 0,85 m do p7 não é "0 defeito pior"**: ela piora o apoio da Coifa em 2,49 cm além do baseline travado.
- **Prateleira de serviço: viável sozinha** (V4) e independente da AS-1: encostá-la na face da parede oeste zera o `NOT_IN_CONTACT`
  (0,3465 m), mantém pré-voo PASS e não cria defeito. A causa é o planejador alinhar a fita pela borda mais interna da zona
  (`_wall_line`, `layout.py:141-157`), que no trecho y ≥ 14,035 é recortada pelo contorno sem fonte `sb002`.

## O que isto NÃO é
Não é prova no SketchUp (L2), não é veredito visual, não altera `KNOWN_MODULES`, `known_gaps.json`, o planejador nem o consensus,
e não escolhe a alternativa da AS-1 (decisão do Felipe). V4 é translação de saída, não código do planejador.

## Reprodução (da raiz do repo)
```
PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_as1_real_wall/probe_as1_real_wall.py   # ~6 min, grava o JSON
PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_as1_real_wall/plot_as1_real_wall.py    # as1_real_wall_plan.png
```
`as1_real_wall_plan.png`: prancha com o PDF da planta por baixo (mesmas coordenadas do consensus), cada peça rotulada e o conflito
em vermelho com a medida. Colunas: atual · 0,85 m do p7 (coifa 75,33 → 77,82 cm) · melhor tentativa em `m013` (0,85 m; o planejador
a descarta: `CORRIDOR_BLOCKED`, passagem até o tanque 23,4 cm) · prateleira corrigida na parede oeste (`m012`).
