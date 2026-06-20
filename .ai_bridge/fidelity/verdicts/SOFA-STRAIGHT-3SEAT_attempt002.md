# SOFA-STRAIGHT-3SEAT — veredito GPT, tentativa 002 (após o fix)

- **Data:** 2026-06-08
- **Juiz:** GPT (ChatGPT Plus, via Chrome) — mesmo chat do attempt 1 (lembra a crítica)
- **Mudança aplicada** (branch `feat/sofa-cushion-bevel`, worktree isolado — sem colidir com a sessão V-Ray paralela):
  `cushion_bevel` ligado no `sofa_builder._seat_row` (topo inset ~4cm nas 6 almofadas) + `arm_width` 0.22→0.18
- **Render:** Python iso determinístico (`tools/render_parts_iso.py`, SEM SketchUp) — before/after no MESMO estilo
- **Veredito:** **WARN** (melhorou de verdade, ainda não PASS) · gate determinístico do sofá: **PASS** (19 peças, bbox exato)

## VEREDITO: WARN — melhorou de verdade, mas ainda não virou PASS.

## O_QUE_MELHOROU
O bevel nas almofadas quebrou bastante o efeito de "caixa chapada"; agora assento e encosto têm leitura mais clara de peças separadas. Os braços em 0,18m melhoraram a proporção lateral e deixaram o volume menos pesado. Comparado ao attempt 1, o sofá ficou menos bruto e mais próximo de um produto.

## O_QUE_AINDA_FALTA
O principal problema agora são os **encostos**, que continuam parecendo **placas verticais rígidas**, não almofadas. Ainda falta: inclinação/recuo do encosto (~8–12°), espessura visual mais acolchoada (~10–14cm, volume mais "fofo"), e uma base menos monolítica (o bloco escuro da base segue alto e pesado).

## PROXIMA_ACAO
Inclinar os encostos para trás ~10° (criar parâmetro `backrest_rake = 8–12°`). É o ajuste único mais impactante agora — tira a leitura de "painel reto" e aproxima do alvo industrial/clean realista. **(cycle 3)**
