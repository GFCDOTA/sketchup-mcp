# Visual regression gate — planta_74 (shell-geometry-integrity)

Generated: 20260711T134556Z

Montage: `artifacts\review\planta_74\visual_regression_20260711T134556Z\montage_pdf_before_after.png`

## Verdict

VERDICT: IMPROVED
REASON: shell deixa de comer 2 features reais do consensus (~3-5cm, regiao A.S.) e de gerar 5 stubs fantasmas de junção; guarda-corpo da varanda com material correto (metal escuro, nao mais concreto). Nenhuma regressao.
ACTION: promote

## Evidência

- Painel :8765 /ask-vision: PASS todos os eixos, zero regressão; ressalva
  honesta = deltas sub-5cm abaixo da resolução da montage.
- Prova POSITIVA por dado (mais forte que pixel pra delta sub-5cm): o
  geometry_report do .skp promovido carrega total_shell_area_pts2 =
  11963.2201 (antes 11945.2422; +17.98 = exatamente as 2 features
  restauradas) e endpoints_free = 22 (antes 17; +5 = stubs mortos na
  origem pelo clamp).
- Prova visual do railing: runs/vision_check/railing_before_after.png —
  montantes/corrimão passam de cinza-concreto pra metal escuro.
- Testes: tests/test_shell_geometry_integrity.py 8/8 + suite 1327 passed.
- Origem: review clínico 2026-07-11 (3 revisores) — findings ALTA #1/#3
  (py) + MÉDIA #1 (rb, vivo) + hardening Hard Rule #2 e paridade
  origin-default Ruby×Python.
- Carimbo humano final (VISUAL_REVIEW): Felipe.
