# HANDOFF — Estúdio Banheiro (2026-08-08 — 🏆 APROVADO_DESIGN)

## Estado em 1 linha
Loop CONCLUÍDO: **p20 = 9.2/10 com APROVADO_DESIGN: SIM** (critério de parada
do Felipe: "faz sentido pra um designer de interiores"). Placar completo e
lições em `artifacts/estudio_banheiro/ITERATIONS.md`.

## Deliverables
- Heroes de portfólio (1500×1875):
  `artifacts/planta_74/furnished/kitchen_angles/banho01_stone_HERO.png` e
  `banho01_stone_HERO_lavatorio.png`.
- Renders do loop: `artifacts/estudio_banheiro/iterations/planta_iter_01..20.png`.
- `.skp` navegável com a MESMA pele (alpha 0.16 no vidro): rebuild via
  `python -m tools.furnish_apartment` (venv canônico).

## O que mudou nesta retomada (p18→p20)
- `bathroom_layout.py`: montante preto no bordo da folha (correr inequívoco);
  `_KIND_ALPHA` vidro 0.16.
- `tweak_vrscene.py` (theme estudio_banho): kb_folha no glass INCOLOR (a cor SU
  esverdeada era o "leitoso"); espelho diffuse 0.010; shadow gap void matte;
  cuba com reflexo leve; metais pretos com glint; halo LED −20%.
- Câmera final: eye 520,634,64 → target 533.5,567,45 (cmd completo no
  ITERATIONS.md).

## Se retomar (polish opcional, TOP3 residual do juiz)
1. Espelho: 20-30% de reflexo útil sem perder o mood escuro.
2. Bancada: veio mais suave; antracite da direita menos massa contínua.
3. (Feito) hero em alta resolução.

## Pendências de repo (NÃO do estúdio)
- Branch `feat/estudio-banheiro` está off `fix/planta74-furnished-fidelity`
  (20+ commits pendentes de PR pra develop) — decisão de merge é outra frente.

## Gotchas vivos do bridge :8899
- /ask 504 "streaming não começou" ≠ falha: a msg POSTA e o GPT responde —
  ler o chat fixo pelo Chrome real (get_page_text) antes de reenviar.
- Resposta <20s idêntica à anterior = STALE; conferir no Chrome.
- Docker Desktop precisa estar de pé (container gpt-chrome-bridge sobe junto).
