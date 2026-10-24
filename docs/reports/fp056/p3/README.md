# FP-056 P3a — barreiras como limite do espaço utilizável (#434) (2026-10-24)

## Defeito reproduzido
`room_collisions.audit` e o pré-voo (`layout_preflight`) só olhavam a massa de parede e o giro de porta. **Móvel sobre
guarda-corpo, peitoril ou mureta passava** em todo gate de proposta (o R2a da spec foi corrigido por sorte, via RC-B, não por
contrato). Medição no apartamento gerado, com a barreira na espessura construída (1,5 pol): a Jardineira da A.S. entrava
**5 mm** (61 cm²) na mureta `h_sb001`; antes do ajuste de espessura a Condensadora também aparecia contra o peitoril `h_sb000`
(4,3 cm contra a massa de meia parede, falso positivo do modelo errado de espessura).

## Correção (na origem, sem exceção no validador)
- `tools/rooms/shared/clearance.py`: `soft_barrier_masses_pt` (massa de cada barreira **com fonte**, na espessura que o shell
  constrói; `SOFT_BARRIER_THICKNESS_IN` com teste de contrato contra o Ruby) e `barrier_is_sourced` (mesma regra do
  `barrier_source` do shell).
- `tools/validation/room_collisions.py`: nova lista `barrier_penetration` (mobiliário/louça cuja base fica abaixo do topo da
  barreira e cuja pegada a cruza além de `EPS_DEPTH`). Barreira sem altura declarada bloqueia qualquer altura (lado seguro; a
  altura não é inventada). `layout_preflight` passa a recusar (FAIL) com `barrier_penetration`.
- `tools/rooms/service/layout.py`: a zona de mobiliar da A.S. perde a massa das barreiras construídas. Causa: a laje entra
  `FLOOR_UNDER_FRAC` sob a barreira (RC-A) e a peça encostada no limite do `cell` entrava na barreira.
- Resultado medido (gêmeo em caixas): **só a A.S. mudou** (`fp044_baseline`: `CAIXAS_MUDARAM: A.S.`); snapshot
  `a4fa928927d11a0f` → `f8e4dbe406eab2282a16`, 390 peças; nenhuma peça perdida; 0 `barrier_penetration` no apartamento.
  Baseline novo em `artifacts/review/fp056/p3/fp044_baseline.json` (os anteriores ficam como retrato histórico).

## Achado novo (decisão do Felipe, não aplicado) — traços sem fonte `sb000`–`sb007`
Os 8 traços do consensus sem `barrier_type`/fonte **não são construídos** pelo shell (Hard Rule 1) mas
`compute_room_floors` os usa para fechar o envelope e **recortar a laje e o `cell` de todos os cômodos**: a laje de cada
cômodo é de 0,26 a 1,97 m² menor do que sem eles (Suíte 01 −0,99; A.S. −1,97; Sala −0,94; Suíte 02 −0,49; Cozinha −0,26;
Banho 01 −0,62; Banho 02 −0,64; Lavabo −0,72). Eles contornam paredes e retângulos fechados dentro dos cômodos (prováveis
prumadas/pilares). Isso muda a laje construída e o espaço dos planejadores de todos os cômodos, inclusive layouts aprovados;
portanto **não foi alterado**. Alternativas e impacto estão na Issue de decisão (ver backlog). Também invalida a leitura
do experimento da FP-056 P2 (a "região utilizável" subtraía esses traços).

## Prova
`tests/test_fp056_p3_barriers.py` (6 `planta74_scale` + 1 contrato Ruby × Python); suítes `not planta74_scale` e
`planta74_scale` verdes. Não substitui o L2: a validação no SketchUp real entra com a geração completa (P6).
