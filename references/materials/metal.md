# Metal — puxadores, perfis, eletro, coifa, sóculo, esquadria, nichos

> Knowledge base de marcenaria planejada. Referência = LINGUAGEM; POSIÇÃO vem do
> PDF. RGB = cor base difusa aproximada; em metal o que MANDA na leitura é o
> REFLEXO (roughness/metalness no V-Ray), não só a cor difusa. Metal errado é o
> detalhe que mais facilmente "barateia" uma cozinha cara.

**Golden sample (cozinha planta_74):** geladeira INOX `rgb[216,220,227]`
(escovado, frio-neutro); cooktop PRETO; coifa slim; sóculo grafite `[40,41,45]`
(metal/laca escura fosca que "some"); LED quente 2700K. Regra do programa:
metal de planejado bom é CONTIDO — um acabamento dominante (ex. preto fosco OU
inox escovado), não um arco-íris de metais. Misturar 3 metais brilhantes
diferentes = leitura amadora.

`loose_object → planned_niche_system`: o eletro (geladeira, coifa) integra na
torre/nicho, não fica solto encostado. O metal "veste" o sistema.

---

## Inox escovado (brushed steel) — o do golden sample

- **Aparência:** cinza-prata frio com micro-riscos direcionais que difundem o
  reflexo. `rgb[216,220,227]` (golden sample, geladeira); mais neutro `[200,202,206]`.
  Reflexo SUAVE/anisotrópico, não espelhado.
- **Reflexo (render):** metalness alto, roughness MÉDIA (0.3–0.5), reflexo
  anisotrópico na direção da escovação. NÃO espelho.
- **Custo:** `$$` (acabamento padrão de eletro nacional).
- **Prós:** esconde digital muito melhor que polido; neutro, casa com tudo; o
  default seguro de geladeira/coifa/forno.
- **ONDE FALHA:** sem a micro-textura de escovação (reflexo liso demais em
  render) vira "plástico cinza". Inox FRIO `[216,220,227]` ao lado de madeira
  MUITO quente pode brigar — o sóculo grafite e o LED quente reconciliam.

## Inox polido / espelhado

- **Aparência:** prata espelho, reflete o ambiente nítido. `rgb[222,224,228]`
  base, mas a leitura é 90% reflexo.
- **Custo:** `$$`–`$$$`.
- **Prós:** brilho "joia"; pontual pode valorizar.
- **ONDE FALHA:** **MARCA DIGITAL violentamente** — em cozinha de uso lê sempre
  manchado. Em render, reflexo nítido + HDRI errado = "espelho de funhouse",
  reflete coisa estranha. Datado em frente grande. Evitar em superfície ampla.

## Grafite fosco / titânio fosco — o sóculo do golden sample

- **Aparência:** cinza-chumbo escuro, MATE, quase sem reflexo. `rgb[40,41,45]`
  (sóculo); puxador grafite `[58,60,64]`. Sofisticado, "some" na base e dá
  leveza ao volume.
- **Reflexo (render):** metalness médio, roughness ALTA (0.6–0.8); reflexo
  difuso quase nulo. É o oposto do gloss.
- **Custo:** `$$`–`$$$` (acabamento pintado/anodizado).
- **Prós:** o metal escuro contemporâneo premium; esconde digital; faz puxador/
  perfil/sóculo "desenharem" sem brilhar. Casa com fendi + madeira clara
  (golden sample).
- **ONDE FALHA:** grafite escovado/semi-brilho marca digital (perde a graça do
  fosco). Em cozinha muito escura some demais.

## Preto fosco (matte black)

- **Aparência:** preto profundo MATE. `rgb[26,26,28]`; puxador/perfil/torneira
  `[22,22,24]`. Contraste forte e gráfico.
- **Reflexo (render):** roughness alta, reflexo mínimo; quase corpo negro.
- **Custo:** `$$`–`$$$`.
- **Prós:** o acabamento "statement" do contemporâneo (puxador, torneira, perfil
  de nicho, esquadria preta). Gráfico, atemporal quando contido.
- **ONDE FALHA:** preto fosco PEGA POEIRA e marca de gordura perto do cooktop —
  em render fica "embaçado" se a roughness for alta demais sem sheen. Preto em
  TUDO (puxador+torneira+perfil+esquadria+eletro) pesa e vira "tendência 2021"
  saturada. Usar como linha de acento, não cobrir tudo.

## Latão / dourado / champagne (brass / gold)

- **Aparência:** dourado quente. Latão escovado `rgb[181,150,99]`; champagne/
  rosé-gold dessaturado `[198,178,150]`; dourado polido `[205,168,100]`.
- **Reflexo (render):** metalness alto; escovado roughness média (recomendado),
  polido roughness baixa.
- **Custo:** `$$$` (acabamento premium; bom latão é caro, o barato oxida/descasca).
- **Prós:** calor e luxo pontual; champagne dessaturado casa lindo com fendi +
  madeira clara (par natural do golden sample). Puxador/torneira/perfil de nicho.
- **ONDE FALHA:**
  - **Dourado POLIDO saturado** `[210,170,60]` = leitura "torneira de banheiro
    barato dos anos 80" / cafona. Ficar no escovado dessaturado.
  - Latão barato OXIDA/escurece irregular e o verniz DESCASCA → mancha.
  - Misturar dourado + inox + preto na mesma cozinha = amador. Escolher UM metal
    de acento.
  - Em render, dourado com IOR/cor errada vira "plástico amarelo" ou "ouro de
    videogame".

---

## Decisão rápida (para o gerador)

- **Default coerente com golden sample:** eletro INOX ESCOVADO `[216,220,227]`;
  sóculo GRAFITE FOSCO `[40,41,45]`; cooktop preto. LED quente 2700K reconcilia
  o inox frio com a madeira quente.
- **Metal de acento (puxador/torneira/perfil):** UM só — preto fosco `[22,22,24]`
  (gráfico, default seguro) OU latão escovado/champagne `[198,178,150]` (quente,
  premium, casa com fendi).
- **Regra dura:** no máximo DOIS acabamentos metálicos no ambiente (ex. inox eletro
  + preto acento). Três+ = amador.
- **Anti-padrões a barrar:** dourado polido saturado `[210,170,60]` (cafona);
  inox polido em superfície grande (digital, datado); preto fosco cobrindo tudo
  (pesado/datado); 3+ metais misturados; metal liso sem textura de escovação em
  render (lê plástico).
