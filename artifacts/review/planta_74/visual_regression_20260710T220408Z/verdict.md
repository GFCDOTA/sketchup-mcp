# Visual regression gate — planta_74 (furnish-2026-07-10-industrial)

Generated: 20260710T220408Z

Montage: `artifacts\review\planta_74\visual_regression_20260710T220408Z\montage_pdf_before_after.png`

## Hard FAIL checklist (any True => WORSE)

- [ ] doors disappear or become useless lines
- [ ] gray walls/blocks invade rooms
- [ ] colored floors leak / do not respect walls
- [ ] openings become less legible
- [ ] model is more blocky than the baseline
- [ ] plan is less recognizable vs the PDF

## Verdict (fill by LOOKING — not pytest/counts/exit-0)

VERDICT: SAME
REASON: re-geração 2026-07-10 (estilo industrial, pipeline pós FP-032..040) é estruturalmente indistinguível do baseline FP-037 de 2026-07-01 e segue reconhecível vs o PDF — nenhum hard-FAIL do checklist disparou.
ACTION: promote

## Contexto

- Esta run NÃO era uma mudança de fidelidade/aparência: foi uma re-geração de
  demonstração no pipeline novo (RAG/visão/carteiro). SAME = estabilidade =
  resultado desejado; não há mudança a reverter (o "SAME => revert" do scaffold
  aplica a mudanças que PROMETEM melhora visual).
- Veredito emitido pelo painel de 3 juízes do `:8765 /ask-vision`
  (visual_findings.v1, top_level=WARN, confidence=medium): todos os eixos
  estruturais PASS; WARNs são caps de honestidade (resolução da montage
  insuficiente pra confirmar porta/janela individualmente), não defeito visto.
  Recomendação dos juízes se um check estrito for necessário: crops por vista
  em alta resolução.
- Gates determinísticos da run: kitchen_validation PASS, overlap_gate PASS
  (8/8 cômodos, incl. COZINHA 12 móveis), flat_white_check PASS.
- 7 design_patterns_observed extraídos pelo painel (6 works / 1 neutral)
  alimentam o corpus do RAG automaticamente.
- Carimbo humano final (VISUAL_REVIEW) segue sendo do Felipe.

## Check estrito porta/janela (follow-up, 2026-07-10)

Re-despacho do painel com PDF 300dpi + renders em resolução nativa
(o path-guard do bridge bloqueia o scratchpad do Claude — usar path do repo):

- Paredes / cômodos (9/9) / escala / orientação: **PASS**.
- Posições de TODAS as portas e janelas resolvíveis: **MATCH** com o PDF.
- **FINDING REAL — porta de ENTRADA com swing INVERTIDO** (vf_004,
  confirmado por crop manual PDF vs SKP): no PDF a folha abre PRA DENTRO
  da SALA DE JANTAR (dobradiça à esquerda, arco interno); no SKP a folha
  renderiza PRA FORA da unidade. Investigar: lado do arc no
  consensus_model vs offset do leaf no build_plan_shell_skp.
- FAIL de material_light do painel = categoria (cobrou V-Ray de render
  interativo flat) — não se aplica a este artefato; a própria síntese
  reconhece que seria WARN.
- Janelas de COZINHA/BANHOS/A.S.: UNRESOLVABLE por oclusão de mobília
  no top view (não é defeito; conferir com render sem mobília se preciso).
