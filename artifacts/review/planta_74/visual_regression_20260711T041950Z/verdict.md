# Visual regression gate — planta_74 (fix-entry-door-swing)

Generated: 20260711T041950Z

Montage: `artifacts\review\planta_74\visual_regression_20260711T041950Z\montage_pdf_before_after.png`

## Hard FAIL checklist (any True => WORSE)

- [ ] doors disappear or become useless lines
- [ ] gray walls/blocks invade rooms
- [ ] colored floors leak / do not respect walls
- [ ] openings become less legible
- [ ] model is more blocky than the baseline
- [ ] plan is less recognizable vs the PDF

## Verdict (fill by LOOKING — not pytest/counts/exit-0)

VERDICT: IMPROVED
REASON: porta de ENTRADA agora abre PRA DENTRO da sala como o PDF (vf_004 corrigido); demais folhas seguem o arco medido; zero regressão fora das portas.
ACTION: promote

## Evidência

- Painel :8765 /ask-vision (3 juízes, tier deep): door_fidelity PASS
  ("AFTER entry leaf swings inward into the sala... correcting the vf_004
  outward-into-exterior bug"), walls/rooms/scale PASS, "both judges vote
  IMPROVED/promote". WARNs restantes = janelas fora do zoom de inspeção e
  shading interativo flat (by design, não é regressão).
- Medida determinística: tools/door_swing_audit.py => PASS 7/7 (swing+hinge
  da fixture == arcos bezier do PDF; endpoints em espaço de página).
- Testes: tests/test_door_swing_contract.py 4/4 (red→green) + suite completa
  1315 passed.
- Fixture emendada com aprovação humana: task vf_004 despachada pelo Felipe
  (2×, 2026-07-10/11). h_o004/h_o005/h_o006 tinham hinge_side errado ("left"
  uniforme); 5/7 portas renderizavam com swing invertido.
- Carimbo final de aparência (VISUAL_REVIEW humano): Felipe.
