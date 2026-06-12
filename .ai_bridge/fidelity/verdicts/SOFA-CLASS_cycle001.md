# SOFA-CLASS — cycle 001 (programa "arquiteto de classe", FASES 0-4)

- **Data:** 2026-06-12
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto") — julgou a MATRIZ de generalizacao
  (9 variantes derivadas pela classe, zero ajuste manual) via browsing.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- **Imagem:** artifacts/review/furniture/sofa_class/sofa_class_matrix.png (@aa686d3)
- **Gates deterministicos previos:** sofa_class_gate 54/54 derivados PASS + 6/6
  sabotagens FAIL; matriz 9/9 class=PASS anatomia=PASS; suite 628 ✓.

## VEREDITO_CLASSE: WARN

> "A classe ja existe e generaliza, mas ainda nao e' PASS limpo porque os extremos
> comecam a virar bloco/plinto com almofadas. A teoria esta boa; a anatomia ainda
> precisa de 3 regras de contencao."

- **IDENTIDADE:** sim — as 9 leem como a mesma familia ("talvez ate demais": os
  arquetipos mudam DIMENSAO mas ainda nao mudam LINGUAGEM o suficiente).
- **ESCALA:** correta — "o corpo humano parece preservado"; largura escala, alturas nao.
- **EXTREMOS:** degrada em lounge-2l-chunky-plinth e formal-4l-chunky-legs (pesados
  mas legiveis); **PIOR_CELULA: standard-3l-chaiseR-plinth** — chaise = "caixote
  anexado", braco-muralha, plinth pesado, sem continuidade assento->chaise.

## TOP3_FIXES_DE_CLASSE (cycle 002 = FASE 5, refino da classe)

1. **Regra de proporcao braco/massa:** chunky nao escala livre — se arm_width/height
   sobe, a classe COMPENSA peso visual (chanfro, recuo inferior, pe aparente ou base
   mais leve). "Hoje chunky + plinth vira bunker."
2. **Regra de chaise integrada:** chaise herda alinhamento do assento, continuidade
   de almofada, frente mais leve, braco lateral menos dominante. Constraint: "chaise
   deve parecer extensao do seat deck, nao modulo colado."
3. **Regra de diferenciacao por arquetipo:** mudar LINGUAGEM, nao so medidas —
   formal: bracos mais verticais, assento contido; lounge: base visualmente mais
   horizontal, encosto mais relaxado. "Hoje os tres ainda parecem variacoes
   dimensionais da mesma caixa."

**OVERFIT_CHECK do juiz:** nenhum fix e' remendo de exemplar; o unico remendo a
evitar e' "ajeitar so a chaise dessa celula" — o problema e' a GRAMATICA de chaise
da classe.

## O que o cycle 001 entregou (ja em develop apos merge)

- `interior/class_specs/SOFA_CLASS_SPEC.md` (teoria: faixas/relacoes/arquetipos/
  anti-patterns/escala/anti-regressao)
- `tools/sofa_class.py` (teoria executavel + derive_spec + gate; 6 sabotagens)
- `tools/sofa_class_matrix.py` (prova de generalizacao em grid)
- Furo de contrato corrigido: `SofaSpec.bbox_m()` agora preve o overhang do rake
  (todo sofa com rake dava WARN falso de bbox)
- 65 testes novos (suite 628 ✓)
