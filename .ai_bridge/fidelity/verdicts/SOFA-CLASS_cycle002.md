# SOFA-CLASS — cycle 002 (FASE 5: as 3 regras do juiz viraram REGRA de classe)

- **Data:** 2026-06-12
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto"), matriz ANTES (@aa686d3) vs DEPOIS
  (@0813659) via browsing, mesma conversa.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- **Gates previos:** 54/54 derivados PASS, 7/7 sabotagens FAIL (incl. nova "bunker"),
  matriz 9/9 class=PASS anatomia=PASS, suite 628 ✓ (exemplar default byte-identico).

## VEREDITO_CLASSE: WARN — **"melhora real, não cosmética"**

> "Cycle 002 prova que as regras novas mexeram na CLASSE, nao so na aparencia,
> principalmente na chaise."

- **FIX1_BUNKER: parcialmente resolvido.** Sapata recuada ajuda (lounge-2l-chunky-plinth
  deixou de ser bunker puro); braco chunky ainda domina em 3/4.
- **FIX2_CHAISE: "melhorou muito, mas nao fechou."** Deck em L ✓; mas a frente/lateral
  aberta criou "recorte escuro que parece buraco construtivo ou painel faltando".
- **FIX3_ARQUETIPOS: melhorou, ainda timido.** Formal crisp ✓, lounge overhang ✓; de
  longe ainda compartilham a mesma ossatura.
- **PIOR_CELULA:** standard-3l-chaiseR-plinth (ainda; "menos errada, mas a pior
  gramatica da classe").

## TOP3_RESTANTES (cycle 003, todos de classe)

1. **Regra de TERMINACAO da chaise:** frente/lateral com gramatica propria — base
   baixa continua OU perna/recuo coerente OU painel lateral reduzido; nunca "buraco".
2. **Reducao visual ADICIONAL do braco chunky:** alem da sapata — chanfro/bevel
   maior, sombra inferior ou taper/recuo vertical (nao virar parede lateral).
3. **Assinatura de SILHUETA por arquetipo mais forte:** formal mais ereto/crisp,
   lounge mais baixo/horizontal/fofo; a diferenca existe mas esta timida.

**OVERFIT_CHECK do juiz:** sem overfit nos fixes; proibido "arrumar so a celula
standard-3l-chaise-plinth" — a regra de terminacao vale pra qualquer arquetipo/tamanho.

## O que o cycle 002 entregou

- `SofaSpec`: + `arm_relief` / `arm_cap` / `seat_overhang` / `base_recess` (hardcode
  rec=0.06 PROMOVIDO) — defaults neutros (anti-regressao byte-identica).
- Builder: sapata recuada no braco (relief), tampo proud (cap), overhang do assento,
  chaise com frente aberta + vinco alinhado a seat_front + base com recess + pes sob
  o deck (pe orfao pego pelo gate sem_peca_solta — fix de classe).
- `sofa_class.py`: ARCHETYPES carregam linguagem; derive aplica relief automatico no
  chunky; constraint `compensacao_de_massa` + sabotagem "bunker".
