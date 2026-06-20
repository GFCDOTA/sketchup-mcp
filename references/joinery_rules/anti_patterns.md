# Anti-patterns de marcenaria — sintoma → correção

> Os defeitos que fazem uma cozinha/armário planejado parecer móvel de loja, render de
> game ou builder-grade. Cada um: **como reconhecer (sintoma)** → **como consertar
> (correção)**. Estes são exatamente os FAILs que os gates e o veredito visual do GPT
> pegam antes de mostrar pro Felipe. Princípio que mata a maioria deles:
> `loose_object -> planned_niche_system`.

---

## 1. Objeto solto (`loose_object`)
- **Sintoma:** geladeira, micro, coifa, lava-louças pousados ao lado/sobre o armário
  sem painel, torre ou recorte. Dá pra "puxar o eletro pra fora" sem mexer em marcenaria.
  A linha da bancada quebra onde o objeto entra.
- **Correção:** envolver em **nicho planejado** — painel lateral + frente flush + filler
  + respiro + aéreo de fechamento por cima (ver `appliance_niches.md`). O eletro vira
  COLUNA/torre integrada. É o defeito-raiz; quase todos os outros descendem dele.

## 2. Branco puro chapado
- **Sintoma:** tudo `[255,255,255]` sem variação, plano, sem sombra de profundidade —
  lê plástico/render barato, "cozinha de catálogo de banco de imagens". Sem reveal, sem
  textura, sem temperatura de cor.
- **Correção:** usar **off-white QUENTE / fendi** (`[224,215,199]` no aéreo do golden
  sample), não branco puro. Quebrar o monocromático com madeira na base
  (`[191,167,137]`) e pedra no tampo (`[222,219,212]`). Adicionar reveal/shadow-gap pra
  criar sombra (ver `premium_details.md`). Branco SÓ funciona com textura + sombra
  + um material quente de contraponto.

## 3. Madeira saturada builder-grade
- **Sintoma:** madeira laranja/marrom-mel super-saturada, brilho de verniz plástico,
  veio fake repetido — cara de MDF revestido genérico anos 2000. Cor "madeira" do
  default do renderer.
- **Correção:** **carvalho/freijó CLARO dessaturado e coordenado** (`[191,167,137]`,
  base do golden sample) casado com o aéreo fendi pra matar o bicolor. Veios sutis via
  textura V-Ray, acabamento fosco/acetinado. Se precisa de madeira mais escura pra
  contraste, reserve pra **nicho/decoração** (`niche_wood [138,104,66]`), não pro corpo
  inteiro.

## 4. Coifa solta
- **Sintoma:** coifa pendurada por hastes longe do aéreo, desalinhada do cooktop, duto
  aparente — objeto flutuante que não pertence ao conjunto.
- **Correção:** **coifa slim embutida no aéreo**, alinhada sobre o cooktop, na faixa
  45–65 cm (under-cabinet), com aéreo de fechamento escondendo o duto. Vira parte da
  caixa do aéreo, não um pendente. (Caso particular do anti-padrão nº 1.)

## 5. Cuba rasa
- **Sintoma:** bojo raso que não esconde a louça, água respinga pra fora, lê acessório
  de banheiro num plano de cozinha. Bojo claro/uniforme que não lê profundidade.
- **Correção:** cuba profunda, **borda flush com o tampo** a 90 cm (`PIA_Z0=0.90`),
  bojo em tom **escuro** pra ler profundidade (`cuba [92,96,103]`) contra o tampo claro.
  Undermount/flush, sem borda saliente que junta sujeira.

## 6. Pia fora do ponto hidráulico
- **Sintoma:** cuba/torneira posicionada por estética numa parede sem prumada — viola a
  realidade da instalação. Reprova no gate `sink_anchor_pdf` / `kitchen_validation`.
- **Correção:** a pia é **POSIÇÃO**, vem do PDF (`KITCHEN_SINK_ANCHOR`,
  `KITCHEN_SINK_SIDE="W"`). A referência influencia material/linguagem, **nunca** move a
  pia. Layout se organiza EM TORNO do ponto hidráulico, não o contrário. Mesma regra
  vale pra ramal de gás (cooktop) e exaustão (coifa).

## 7. Módulos sem junta / reveal
- **Sintoma:** frente de armário como uma chapa lisa única, sem nenhuma linha de junta —
  ou uma "porta" gigante de 1,2 m cobrindo o módulo inteiro. Lê como bloco maciço, não
  como marcenaria modulada. Fake.
- **Correção:** **modular em portas de 35–65 cm** (40/50/60 reais) com **reveal /
  shadow-gap** entre frentes (2–4 mm). A junta é o que prova que é marcenaria de
  verdade. Sobra de vão → vira **filler** (15–18 cm), não porta de medida estranha.

## 8. Bicolor agressivo
- **Sintoma:** dois materiais que brigam — madeira saturada embaixo + branco puro em
  cima, ou contraste alto sem transição, "tabuleiro de xadrez". Lê barato e datado.
- **Correção:** paleta **coordenada e quente** — base carvalho claro `[191,167,137]` +
  aéreo fendi `[224,215,199]` + tampo pedra `[222,219,212]` + sóculo grafite
  `[40,41,45]` como âncora escura pontual. Os tons conversam (todos quentes,
  dessaturados); o contraste é sutil e o grafite aparece só em sóculo/puxador/cooktop.
  Bicolor PODE existir, mas precisa ser **harmônico**, não competitivo.

---

## Tabela-resumo

| Anti-padrão | Sintoma rápido | Correção rápida |
|---|---|---|
| Objeto solto | eletro sai sem mexer no armário | nicho planejado (painel+flush+filler+respiro) |
| Branco chapado | `[255,255,255]` plano sem sombra | fendi quente + madeira + reveal |
| Madeira saturada | laranja-mel brilhante | carvalho claro dessaturado coordenado |
| Coifa solta | pendente desalinhado, duto à vista | coifa slim embutida no aéreo |
| Cuba rasa | bojo raso, borda saliente | cuba funda, flush a 90 cm, bojo escuro |
| Pia fora do ponto | cuba onde não tem prumada | pia = POSIÇÃO do PDF, layout em torno |
| Sem junta/reveal | frente lisa / porta gigante | módulos 35–65 cm + shadow-gap; sobra=filler |
| Bicolor agressivo | madeira saturada + branco puro | paleta quente coordenada, grafite pontual |
