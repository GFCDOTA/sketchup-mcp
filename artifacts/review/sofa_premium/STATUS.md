# FP-SOFA-PREMIUM — auditoria do programa (2026-07-11)

| alteration_id | hipotese | pre_verdict | post_verdict | kept/reverted | evidencias |
|---|---|---|---|---|---|
| run_000 | baseline 4 cams | — | FAIL blockiness=5 | baseline | run_000_baseline/ |
| alt_001 | bracos: perfil roundover r30 + recuo 70mm + -20mm alt + -10mm esp | APPROVE_CHANGE | IMPROVED | KEPT | alt_001_before_after.png |
| alt_002 | base: plinto 80mm recuado 60mm + riser oculto (pes eliminados) | REVISE_CHANGE (aplicada) | IMPROVED | KEPT | alt_002_before_after.png |
| alt_003 | encostos: almofada UNICA + coroamento r25 (rake baked) | APPROVE_CHANGE | IMPROVED | KEPT | alt_003_before_after.png |
| alt_004 | assentos: almofada UNICA + crown 15mm + raio frontal r25 | APPROVE_CHANGE | IMPROVED (blockiness 5->2) | KEPT | alt_004_before_after.png |
| alt_005 | travessa frontal: recuo 55mm + raio topo r20 | REVISE_CHANGE (aplicada) | IMPROVED (blockiness=2) | KEPT | alt_005_before_after.png |

Nenhuma alteracao executada sem APPROVE/REVISE previo; nenhuma SAME/WORSE mantida.

## Proximo ciclo (alt_006, ja definida pelo GPT)
Roundover real 25mm nas 2 arestas VERTICAIS frontais dos bracos — exige
primitivo com fillet em 2 eixos (mesh part) no render_parts_iso/sofa_builder.
Depois: criterio de parada = blockiness<=1 + harness .skp + integracao na
planta (planta_74_furnished_with_sofa_premium.skp) + relatorio final.

## Spec premium acumulada (harness)
derive_living_sofa(2.1) + arm_width=0.14 arm_height=0.56 arm_profile=rounded
arm_front_recess=0.07 arm_edge_radius=0.03 base_style=plinth
back_style=single_crowned seat_style=single_crowned base_rail=recessed_rounded

## PLANO DE PROXIMOS PASSOS (consulta GPT 2026-07-11, pos-ciclo-5)

1. CONGELAR o estagio procedural (NAO criar primitivo mesh no clay) —
   alt_001-005 congeladas; o clay ja cumpriu o papel de juiz barato.
   Risco de pular: sofisticar o juiz provisorio em vez do produto.
2. PROMOVER pro SketchUp real AGORA: sofa_premium_harness.skp com
   grupos/componentes por peca; alt_006 (roundover das arestas verticais
   frontais) NATIVA no SU (arcos/Follow Me + Soften) — sem reabrir 001-005.
3. GATE FINAL de silhueta no SKP (4 cams monocromaticas): blockiness<=1,
   sem linhas de segmentacao — ANTES de materiais/costuras.
4. INTEGRAR na sala/planta assim que passar: substituir o sofa em
   planta_74 -> planta_74_furnished_with_sofa_premium.skp (zero colisao,
   circulacao igual/melhor, cam eye-level de prova).
5. PARAR o polimento isolado apos integrar (costura/piping = fase
   upholstery futura compartilhada por todos os estofados).
6. TRANSFERIR a gramatica pro JANTAR como FAMILIA parametrica
   (DINING_PREMIUM_FAMILY: 1 cadeira + 1 mesa canonicas, regras
   extraidas das alt_001-005, max 2 ciclos de gate pra familia toda);
   depois camas/criados com os mesmos construtores.
