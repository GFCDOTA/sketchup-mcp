# CARD: Matar branco chapado (fendi)

**Problema:** branco puro em flat/V-Ray parece MDF barato ou bloco sem profundidade —
o "brancão". Some sob a luz, sem temperatura.

**Solução:** trocar branco puro por **off-white quente / fendi acetinado** + shadow gaps
+ LED. O acabamento é **satin** (acetinado), nunca ultra-gloss (marca digital, data) nem
fosco-papel (lê barato).

**Aplicável em:** aéreo, torre, painel superior, filler.

**Gate:**
- não usar branco puro (> ~[244,244,244] = anti-padrão "branco-papel").
- não ultra-gloss (reflexo plástico/marca digital).

**Valores (golden sample):** fendi [224,215,199] (corpo_sup/porta_sup/filler);
BRDF V-Ray satin = `reflect AColor(0.05) / reflect_glossiness 0.58 / fresnel_ior 1.4 /
metalness 0`. Contraste com a base carvalho [191,167,137] aquecido p/ coordenar (matar
o bicolor builder-grade).

**Token:** `references/tokens/warm_fendi_upper.json`

**Evidência:** GPT — *"o V-Ray resolveu o brancão: o fendi ficou mais quente/acetinado"*.
Ver [hero](../../planta_74/furnished/kitchen_angles/cozinha_vray_hero.png).
