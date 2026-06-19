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

## Perfil do Felipe (briefing nativo)

Fonte de verdade estruturada: `artifacts/reference_lab/kitchen/specs/felipe_kitchen_preference_profile.json`
(prosa-fonte em `FELIPE_KITCHEN_PREFERENCES.md`). Trate como **RESTRIÇÃO, não sugestão**.
Apto ~74 m², Felipe + namorada, visitas eventuais, cozinha de uso **moderado** (ovo/frango/
bife/hambúrguer/frituras leves), flexível pro futuro. Prévia forte pra arquiteto/marceneiro/
empreiteira depois: **sonhar alto no conceito, mas durabilidade + manutenção viável na vida real.**

**USO (obrigatórios e desejados):** lava-louças, cooktop (vidro preto), forno embutido —
**obrigatórios**. Micro embutido em nicho escondido; airfryer em nicho com respiro; filtro/
purificador previsto. **Torre quente** (forno+micro+airfryer em coluna) agrada — estudar.
Muito armazenamento; **armário ATÉ O TETO** (anti-pó); **gavetões inferiores** pra panela.
Geladeira integrada em torre. Robô aspirador (prever circulação/docking). **SEM puxador
tradicional** — só cava/gola/perfil-J/embutido/push-amortecedor. Nichos só com propósito.

**ESTÉTICA:** **NÃO** gosta de branco puro → prefere **ESCURA ou meio-termo**. Gosta de
industrial preto+madeira, cimento queimado, madeira média/escura, moody/noturno, dourado/
bronze (sutil a presente), pedra com veio mais FORTE (se manutenção viável), reflecta/champagne
pontual com LED, luz quente 2700–3000K, hotel boutique / industrial premium. Direção aprovada
(DECISION 003): **BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE** — impacta mas continua usável/limpável.

**MANUTENÇÃO:** beleza **sem dor de cabeça**; manutenção viável **acima de** material delicado.
Cuba preta a considerar (estética) vs inox (durabilidade/seguro); reflecta marca dedo (aceita
se bonito = WARN, não free pass); piso mostra pouco pó/risco (default grafite médio acetinado).
LED frio, mármore na zona de trabalho e madeira em área molhada = fora.

**NUNCA:** mover pia/ponto hidráulico/parede/porta/shaft/área de serviço; inventar ilha;
mudar a planta por causa de uma foto; transformar linear em U/L; aplicar na cozinha real sem
spec antes; cravar PASS sozinho (veredito visual é do Felipe). Detalhe acionável por eixo:
`kitchen/rules/{material_maintenance,appliance_niche_rules,lighting_rules}.md` + guia
`HOW_TO_USE.md`.

## Estado
v0 validado (DECISION 001): 3 golden samples (warm/dark/boutique) GPT PASS, mesma geometria.
v1 acrescenta a camada de SISTEMA (medidas/ergonomia/manutenção/buildability) + os 4 gates.
