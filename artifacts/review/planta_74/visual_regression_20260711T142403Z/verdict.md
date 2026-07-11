# Visual regression gate — planta_74 (terraco-tecnico-mureta)

Generated: 20260711T142403Z

## Verdict

VERDICT: IMPROVED
REASON: MURETA H=0,70M do terraco tecnico (nomeada pelo PDF, ausente do .skp desde sempre) agora existe como low wall de 0.70m; peitoril leste confirmado ja coberto pelo h_sb000. Zero regressao.
ACTION: promote

## Evidência

- pdf_height_labels_audit => PASS (3/3 MATCH; antes 1 MATCH + 2 UNRENDERED).
- Curadoria: banda vetorial do PDF x[223.1..230.9] y[408.0..500.2] promovida
  como h_sb001 (mureta, 0.70m, pdf_vector provenance). Overlays:
  runs/vision_check/terraco_overlay.png + mureta_extent_zoom.png +
  mureta_before_after.png. Descoberta colateral: a orfa sb004 DUPLICA a
  borda leste ja coberta pelo h_sb000 (tiebreak sourced no audit).
- Builder: low_wall honra height_m do consensus (0.70 real, nao 1.10 fixo);
  source gate aceita origem pdf_vector/pdf_text_label alem de
  human_annotation (predicado unificado).
- geometry_report: h_sb001 rendered length_m=2.388 ✓; h_sb000 agora grava
  render_as='railing' consistente com a geometria.
- Painel /ask-vision: 5 eixos ESTRUTURA PASS, mureta visivel e mais baixa
  que o railing, sem regressao; WARNs = render flat sem sombra (by design).
- Suite: 1331 passed. Carimbo humano final (VISUAL_REVIEW): Felipe —
  task despachada por ele (chip task_820ccf6e).
