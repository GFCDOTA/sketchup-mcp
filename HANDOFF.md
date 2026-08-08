# HANDOFF — Estúdio Banheiro (2026-08-05, fim da sessão 1)

## Retomada em 1 linha
Loop YOLO no BANHO 01 da planta_74 até o GPT dar APROVADO_DESIGN=SIM.
Estado: **p17 = 8.6/10, AINDA_NÃO**. Próximo passo: p18 (TOP3 abaixo).

## Onde está tudo
- Worktree: `E:\Claude\worktrees\estudio-banheiro` (branch `feat/estudio-banheiro`, pushed).
- Placar + gotchas: `artifacts/estudio_banheiro/ITERATIONS.md` (LER PRIMEIRO).
- Backlog de defeitos: `artifacts/estudio_banheiro/AUDITORIA_P12.md`.
- Renders: `artifacts/estudio_banheiro/iterations/planta_iter_*.png`.
- Memória persistente: `project_estudio_banheiro.md` (fases 1-6 completas).
- Juiz: chat fixo GPT "Estúdio Banheiro — Claude ⇄ GPT" via bridge :8899
  (Docker Desktop precisa estar de pé; /health primeiro).

## Ciclo padrão (por iteração)
1. Editar `tools/bathroom_layout.py` (geometria) e/ou `tools/tweak_vrscene.py`
   (theme estudio_banho) e/ou texturas em `assets/textures/procedural/`.
2. `pytest tests/test_bathrooms_style.py` (25 travas) → `python -m tools.furnish_apartment`.
3. Render:
   python -m tools.render_banho_vray --eye "518,631,63" --target "536,567,46"
     --fov 60 --iso 160 --shutter 80 --fnum 5.6 --sky 0.16 --sun 0.05
     --burn 0.5 --hide "porta,door"
     --fill "534,585,72,30,10;525,546,68,36,8;528,588,88,18,10;520,610,72,12,10;523,584,55,22,9;523,596,76,22,9"
     --rect "521,545,93,22,16,52,0,0,-1"
     --out artifacts/planta_74/furnished/kitchen_angles/banho01_stone_iNN.png
4. cp pra `artifacts/estudio_banheiro/iterations/planta_iter_NN.png` → commit → push.
5. /ask no bridge (formato do prompt do Felipe, pedir NOTA + APROVADO_DESIGN +
   TOP3). Timeout ou resposta <20s idêntica = STALE → ler no Chrome.

## TOP3 da p18
1. Espelho: reflexo 30-40% (borda esquerda enquadrada com intenção).
2. Box: fixo×folha inequívocos; vidro alpha ~0.16; nicho/chuveiro/misturador revelados.
3. Câmera 2-4cm trás/esquerda — 1ª leitura = espelho+bancada+box.

## Regras vivas (não esquecer)
- SKP navegável = mesma pele do render (tex/alpha por peça); PeleTeto oculto.
- Posição vem do PDF; shaft SE intocável; top view validada com o Felipe.
- Fills ≥50cm de parede; rect no teto DENTRO do box; STONE_MONOLITH (dourado 0).
