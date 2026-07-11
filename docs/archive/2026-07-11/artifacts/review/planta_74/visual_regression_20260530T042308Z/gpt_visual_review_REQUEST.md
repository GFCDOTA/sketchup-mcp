# GPT visual review — REQUEST (pending a connected browser)

## Status

`BLOCKED_VISUAL_REVIEW_CHROME_NOT_CONNECTED`

Visual render judgement must be done by GPT via **Chrome / Claude-in-Chrome /
ChatGPT web** on a connected browser. ChatGPT desktop via computer-use is
**prohibited** (steals the user's screen). The text-only bridge `/ask` is for
TEXTUAL technical decisions only — never for visual render judgement.

Claude must NOT self-declare IMPROVED / SAME / WORSE. This request waits for a
connected browser.

## Artifact to review (attach this image)

`artifacts/review/planta_74/visual_regression_20260530T042308Z/montage_pdf_before_after.png`
(3 columns: PDF ground truth | BEFORE | AFTER; top row = iso, bottom row = top view)

Supporting renders:
- PDF: `runs/planta_74/pdf_plan_region.png`
- BEFORE: `runs/planta_74/before_iso.png`, `runs/planta_74/before_top.png`
- AFTER: `runs/planta_74/model_iso.png`, `runs/planta_74/model_top.png`

## Question to send to GPT (ready)

Revisão visual de fidelidade — classifique IMPROVED, SAME ou WORSE.

Objetivo do patch: reduzir as portas que apareciam como painéis marrons
full-height no SKP (mudei DOOR_HEIGHT_M de 2.10 m para 0.02 m), pra ficar mais
parecido com os arcos de porta finos do PDF.

A imagem anexada é um montage com 3 colunas: PDF (ground truth) | BEFORE (antes
do patch) | AFTER (depois). Linha de cima = iso/3D, linha de baixo = topo.

Minha hipótese: remover os painéis full-height melhoraria a fidelidade ao PDF.

O que eu acho que piorou: as portas praticamente sumiram (viraram marcadores
planos quase invisíveis), os vãos ficaram menos legíveis, e a planta ficou menos
reconhecível. Paredes, floors e escala estão IGUAIS entre BEFORE e AFTER (só
mexi nas portas).

Dúvida: o AFTER está visualmente MAIS parecido com o PDF no CONJUNTO da planta,
ou as portas viraram linhas inúteis e ficou pior?

Pedido explícito: classifique como IMPROVED, SAME ou WORSE (AFTER vs BEFORE em
relação ao PDF, no conjunto) e diga se devo MANTER, AJUSTAR ou REVERTER o patch.
Seja rígido: se as portas ficaram ilegíveis, é WORSE.

## Expected classification criteria (what each verdict means)

- **IMPROVED**: AFTER is more PDF-like across the WHOLE plan — doors are legible
  (like the PDF's thin swing arcs), openings clear, walls/floors no worse, plan
  more recognizable. NO hard-FAIL item triggered.
- **SAME**: no meaningful whole-plan move toward the PDF (only a local metric
  changed; doors/walls/floors read equivalently).
- **WORSE**: ANY hard-FAIL item — doors vanish / become useless lines, gray
  blocks invade rooms, floors leak, openings less legible, more blocky, or plan
  less recognizable vs PDF. (My own read: WORSE — doors became invisible. GPT to
  confirm/override.)

## Current action

- Patch already REVERTED (`DOOR_HEIGHT_M` = 2.10). Nothing promoted.
- Awaiting a connected browser to run the visual review. No self-judgement.
