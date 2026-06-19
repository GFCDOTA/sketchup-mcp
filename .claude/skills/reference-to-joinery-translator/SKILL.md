---
name: reference-to-joinery-translator
description: >
  v1 — REFERENCE_TO_KITCHEN_SYSTEM_TRANSLATOR. Compila referência visual CURADA em SISTEMA de
  cozinha implementável: não só TEMA (cor/material/luz), mas INTELIGÊNCIA DE USO (medidas,
  ergonomia, manutenção, buildability). Produz analysis (10 saídas) + theme preset + roda 4
  gates. NÃO é scraper. Regra de ouro: Pinterest = intenção visual (hipótese), PDF/gates =
  verdade espacial. Use quando o Felipe colar referência de cozinha/planejado, ou pra rodar
  BATCH_THEME_RENDER de presets na planta_74.
---

# REFERENCE_TO_KITCHEN_SYSTEM_TRANSLATOR (v1)

> **Medida de Pinterest não é verdade. É hipótese.** PDF + ergonomia + gate validam.
> Pinterest manda na **intenção visual**. PDF/gates mandam na **verdade espacial**.
> Felipe manda no **PASS**.

Evolução do reference-to-joinery-translator v0 (que já separava FORMA×PELE e virou tema). Agora
extrai também a **inteligência de uso** — porque o Pinterest tem muita mentira de foto: cozinha
linda que na vida real é ruim de limpar, escura demais, coifa inútil, armário alto demais, vão
pegando poeira, bancada sem apoio.

## Duas camadas que o agente aprende (separadas)
1. **TEMA** — preto/madeira/pedra/LED, industrial/japandi/hotel… (a PELE, a vibe).
2. **INTELIGÊNCIA DE USO** — altura, vão, limpeza, poeira, ergonomia, coifa, rodapé, torre,
   circulação, manutenção, buildability (o SISTEMA).

## Para cada referência, produza 10 saídas (analysis)
```
1.  Theme extraction        — cor/material/luz/sensação
2.  Form/skin separation    — o que é FORMA (joinery) vs PELE (material/luz/câmera)
3.  Dimension hints         — medidas aparentes/anotadas (HIPÓTESE, nunca verdade)
4.  Ergonomics notes        — altura/alcance/uso diário/circulação/bancada
5.  Maintenance notes       — poeira/limpeza/mancha/vão inútil
6.  Buildability notes      — marcenaria executa ou é só foto?
7.  What to copy            — tema/paleta/textura/iluminação/sensação
8.  What to adapt           — medidas/proporções/materiais/intensidade de luz
9.  What to reject          — layout de mansão/ilha impossível/coifa gigante/vão de poeira
10. Theme preset            — JSON aplicável na planta_74 (KITCHEN_THEME)
```
Template: `artifacts/reference_lab/templates/reference_analysis_template.md`.

## 4 gates novos (além dos gates de fidelidade)
- **theme_fit_gate** — o tema combina com a planta COMPACTA linear da planta_74?
- **ergonomics_gate** — altura/alcance/uso/circulação/bancada fazem sentido?
  (`tools/kitchen_ergonomics.py` = as 12 medidas; falha = WARN/FAIL.)
- **maintenance_gate** — vai juntar poeira / ruim de limpar / manchar / vão inútil?
- **buildability_gate** — dá pra marcenaria executar, ou é só imagem de Pinterest?

Definição: `artifacts/reference_lab/gates/reference_system_gates.md`.

## Hierarquia absoluta
PDF na **posição** · gates na **circulação/segurança/manutenção** · referência na **linguagem
visual** · Felipe/GPT no **PASS**. Tema muda skin/material/luz/câmera; **NUNCA** âncora do PDF
ou geometria aprovada sem autorização (DECISION 001).

## Fluxo de lote (BATCH_THEME_RENDER)
```
Felipe cola 5–10 refs curadas (inbox/)
  → extrai temas (analyzed/*.analysis.md) → agrupa por linguagem → cria 3–N presets (themes/)
  → aplica na MESMA geometria da planta_74 (skin-swap) → renderiza A/B/C/D (renders/)
  → roda os 4 gates → GPT/Felipe julga → congela os melhores (GOLDEN_SAMPLES.md)
```
Driver: `tools/batch_theme_render.py`. Saída: hero por tema + montagem + ranking (mais vendável /
autoral / seguro p/ manutenção / arriscado).

## NUNCA
- tratar Pinterest como verdade técnica (medida = hipótese, valida no PDF/ergonomia);
- copiar layout/ilha/coifa-gigante/vão-de-poeira da referência;
- scraping em massa; copiar imagem literalmente;
- mover âncora do PDF; cravar PASS sozinho (GPT checkpoint, Felipe juiz).

## Estado
v0 validado (DECISION 001): 3 golden samples (warm/dark/boutique) GPT PASS, mesma geometria.
v1 acrescenta a camada de SISTEMA (medidas/ergonomia/manutenção/buildability) + os 4 gates.
