# Laca — frentes lisas pintadas (aéreos, torres, fillers, ilha)

> Knowledge base de marcenaria planejada. Referência = LINGUAGEM; POSIÇÃO vem do
> PDF. RGB = cor base difusa aproximada do material SketchUp/V-Ray. Laca =
> superfície lisa SEM veio; o acabamento (fosco/acetinado/gloss) e a TEMPERATURA
> da cor é que decidem se lê caro ou barato.

**Golden sample (cozinha planta_74):** aéreos + torre da geladeira + filler em
FENDI QUENTE `rgb[224,215,199]` — off-white levemente bege/cinza, NÃO branco
puro. O sóculo é grafite `[40,41,45]` (laca escura fosca, base que "some" e dá
leveza). A lição central: **branco quente/fendi lê caro; branco puro chapado lê
MDF barato.** A temperatura salva a laca.

`loose_object → planned_niche_system`: a laca é a pele lisa do sistema superior
(aéreos contínuos, torre integrada da geladeira, filler que fecha o vão até o
teto) — não uma porta avulsa.

---

## Laca fosca (mate) — o acabamento do golden sample

- **Aparência:** superfície lisa, ZERO brilho, aveludada. Absorve luz, esconde
  marca. Fendi `rgb[224,215,199]`; off-white quente `[230,224,212]`; grafite
  (sóculo) `[40,41,45]`; verde-oliva/sage dessaturado `[150,156,138]` para acento.
- **Custo:** `$$$` (laca de verdade é processo de pintura caro; "laca fake" =
  melamina/foil liso `$`).
- **Prós:** o look contemporâneo premium; esconde digital e poeira; fendi fosco
  é o que faz o golden sample funcionar. Cor sólida grande sem o ruído do veio.
- **Contras:** risca/lasca exige retoque profissional; superfície grande fosca
  pode parecer "chapada" se a cor for fria/sem vida.
- **ONDE FALHA:** fosco em cor FRIA + superfície grande = leitura de "parede de
  drywall"/MDF cru. A vida vem da temperatura quente + leve variação de luz.

## Laca acetinada (satin / semi-fosco)

- **Aparência:** brilho suave, reflexo difuso (não espelha). Fendi acetinado
  `rgb[224,215,199]` com leve sheen; cinza-pérola `[200,200,196]`.
- **Custo:** `$$$`.
- **Prós:** meio-termo — mais "vivo"/limpável que fosco, sem o problema de digital
  do gloss. Reflexo difuso dá leve profundidade em render.
- **Contras:** mostra ondulação da chapa sob luz rasante se o substrato for ruim.
- **ONDE FALHA:** luz rasante de janela revela qualquer imperfeição do MDF
  embaixo. Em render, specular médio sem controle vira "plástico molhado".

## Laca ultra-gloss (alto brilho / espelhado)

- **Aparência:** espelha o ambiente, reflexo nítido. Branco gloss `rgb[238,238,236]`;
  preto piano `[24,24,26]`; vermelho/cores fortes (data fácil).
- **Custo:** `$$$$` (processo + cuidado).
- **Prós:** amplia ambiente pequeno (reflexo); dramático em peça-herói; preto
  piano em ilha pode ser lindo.
- **Contras:** o acabamento mais problemático no uso real.
- **ONDE FALHA (o clássico):**
  - **MARCA DIGITAL e risca** brutalmente — em cozinha de uso lê "sempre sujo".
  - **RISCA** com qualquer atrito; impossível disfarçar.
  - Mostra TODA ondulação do substrato sob reflexo.
  - **Render:** reflexo nítido demais + HDRI errado = parece plástico de brinquedo
    ou "cozinha de catálogo dos anos 2000". Tende a datar. Usar com muita parcimônia.

## Fendi / off-white quente VS branco puro (a decisão que mais importa)

- **Branco puro** `rgb[244,244,242]`–`[250,250,248]`: frio, chapado. **ONDE
  FALHA:** em superfície grande lisa lê **MDF branco barato / móvel de montar**.
  É o anti-padrão #1 da laca. Sem veio + sem temperatura + sem reflexo = morto.
- **Fendi / off-white quente** `rgb[224,215,199]`–`[230,224,212]`: a mesma forma,
  +temperatura = leitura PREMIUM. É a diferença entre "planejado caro" e "loja de
  móveis". O golden sample escolheu fendi de propósito.
- **Regra do gerador:** NUNCA cravar branco puro `>[244,…]` em frente de laca
  grande. Puxar pro fendi quente. Se o brief pede "branco", entregar branco
  QUENTE, não papel.

---

## Decisão rápida (para o gerador)

- **Default coerente com golden sample:** laca FOSCA fendi quente `[224,215,199]`
  nos aéreos/torre/filler; sóculo grafite fosco `[40,41,45]`.
- **Quer mais limpável/vivo:** acetinada na mesma cor.
- **Quer drama/ampliar pequeno:** ultra-gloss em UMA peça-herói (ilha), ciente do
  digital/risco — nunca na cozinha toda.
- **Acento de cor:** sage/oliva dessaturado fosco `[150,156,138]` ou verde-petróleo;
  fugir de cores saturadas (datam).
- **Anti-padrões a barrar:** branco puro chapado `>[244,…]` (lê MDF barato);
  ultra-gloss em superfície de uso (digital/risca); cor fria fosca em painel
  grande (parede de drywall); reflexo gloss nítido sem HDRI (plástico).
