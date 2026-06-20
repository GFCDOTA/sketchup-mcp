# ARMCHAIR-CLASS — cycle 001 (2a classe do programa; template do sofa replicado)

- **Data:** 2026-06-12
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto"), matriz @9a4b663 via browsing.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- **Gates previos:** 6/6 derivados PASS, 6/6 sabotagens FAIL, matriz 9/9 PASS,
  suite 644 ✓. Geometria = build_sofa(seats=1) (gramatica congelada do sofa).

## VEREDITO_CLASSE: WARN — "boa replica do template; precisa SE EMANCIPAR do sofa"

> "A classe poltrona ja nasceu viavel. Passou no 'e poltrona?', ainda nao passou
> no 'e uma classe de poltrona madura?'. A classe ainda herda sofa demais na
> gramatica do volume — assento+bracos+base ainda 'sofa seat-1'."

- **IDENTIDADE:** sim, leem como POLTRONAS (nao cadeiras, nao mini-sofas).
- **ARQUETIPOS:** parcialmente — club gordo/fechado, standard equilibrada, lounge
  reclinada; "a diferenca ainda esta mais na ficha tecnica do que na personalidade
  visual; nao tao afastados quanto o sofa ficou no cycle 003".
- **PIOR_CELULA:** standard-slim-arm W=0.82 — "encosta no territorio de cadeira
  estofada robusta; braco fino demais pra escala; e' a celula que mais tensiona o
  DNA da classe" (nao esta errada).

## TOP3_FIXES_DE_CLASSE (cycle 002 da poltrona)

1. **Regra de identidade propria (anti-mini-sofa):** reforcar a "CAVIDADE" da
   poltrona — assento contido/acolhido, relacao braco+encosto mais INTEGRADA;
   "objeto unitario, menos 'modulo de sofa cortado'".
2. **Regra de presenca minima do braco na escala compacta:** slim-arm mostra o
   limite — nao so largura: altura, espessura percebida, topo, integracao com o
   encosto.
3. **Regra de linguagem mais forte por arquetipo:** club mais envolvente/contido;
   standard mais limpo/arquitetonico; lounge mais "nesting"; hoje compartilham
   demais a mesma espinha visual.

**OVERFIT_CHECK do juiz:** "o fix proibido seria engrossar so a standard-slim-arm
— o certo e' regra GERAL de presenca minima do braco pra toda a classe."

## Hipotese tecnica pro cycle 002 (emancipacao)

A "cavidade"/integracao braco+encosto provavelmente = braco que SOBE e ABRACA na
parte traseira (wraparound: a altura do braco cresce junto ao encosto em vez de
topo reto), assento embutido entre os bracos com overhang frontal, e encosto em
curva-de-abraco (3 segmentos angulados?). Isso e' GEOMETRIA NOVA de poltrona —
o ponto certo pra nascer um armchair_builder proprio (ou modo wrap no sofa_builder),
mantendo o contrato parts.

## Licao de teoria do cycle 001

`seat_util/width` e `arm_span_ratio` somam 1 — duas reguas redundantes com numeros
diferentes = gate inconsistente (pego pelo proprio gate). `arm_width max=0.26` e'
consequencia MATEMATICA de span<=0.50 com W<=1.05, nao gosto.
