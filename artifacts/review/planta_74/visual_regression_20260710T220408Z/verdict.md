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
