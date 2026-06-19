# Madeira — frentes, painéis, nichos, ripados

> Knowledge base de marcenaria planejada. Referência = LINGUAGEM; POSIÇÃO vem do
> PDF. RGB = cor base difusa aproximada do material SketchUp/V-Ray.

**Golden sample (cozinha planta_74):** inferiores em CARVALHO/FREIJÓ CLARO
coordenado `rgb[191,167,137]` — madeira clara, quente, dessaturada, com veio
visível mas calmo. Nicho de madeira mais escura/mel `[138,104,66]` como ponto
de acento. Regra de ouro do programa: madeira de planejado bom é CLARA e
DESSATURADA. Quanto mais saturado/alaranjado/avermelhado, mais "builder-grade"
(marcenaria de loja, mogno fake anos 90).

`loose_object → planned_niche_system`: a madeira é a pele do sistema (frente de
gaveta/porta, painel ripado de fundo, nicho integrado), não um móvel solto.

---

## Carvalho (oak) — o default do golden sample

- **Aparência:** claro, quente-neutro, veio reto e legível. Carvalho natural
  `rgb[191,167,137]` (golden sample); carvalho mais branqueado/nórdico
  `[205,186,158]`; rústico (knotty) com nós. Veio direcional dá ritmo às frentes.
- **Custo:** `$$`–`$$$` (lâmina natural `$$$`; "carvalho" em MDF foil/melamina `$$`).
- **Prós:** é o oak do planejado contemporâneo — casa com qualquer pedra clara,
  com fendi, com preto. Veio o suficiente pra ter alma, calmo o suficiente pra
  não brigar. Difícil errar.
- **Contras:** virou onipresente (risco de "genérico de Pinterest"); foil barato
  imita mal o veio (repetição visível).
- **ONDE FALHA:** RGB saturado demais → `[200,150,90]` já lê "carvalho mel de
  loja". Manter dessaturado. Foil com veio repetindo a cada 60 cm denuncia
  material barato em render — randomizar/variar o mapa.

## Freijó

- **Aparência:** marrom-mel quente brasileiro, veio mais marcado e levemente mais
  escuro que carvalho. `rgb[176,138,96]`; pode chegar a `[160,120,80]`. O
  "carvalho tropical" — é a alma quente do planejado nacional.
- **Custo:** `$$$` (madeira nobre nacional; lâmina).
- **Prós:** quente sem ser alaranjado-fake; casa lindo com pedra clara e off-white;
  identidade BR (o golden sample cita carvalho/freijó como par coordenado).
- **Contras:** mais escuro/quente que carvalho → puxa o ambiente; em cozinha
  pequena pode pesar.
- **ONDE FALHA:** se a paleta toda já é quente (parede bege + piso amadeirado),
  freijó some/embola — precisa de contraste claro (pedra/fendi). Verniz brilhante
  sobre freijó vira "móvel envernizado de sala de jantar da vovó".

## Nogueira (walnut)

- **Aparência:** marrom escuro chocolate, veio rico e ondulado. `rgb[92,64,46]`;
  mais claro `[110,78,56]`. Madeira "cara de olhar", sofisticada e escura.
- **Custo:** `$$$$`.
- **Prós:** luxo e profundidade; faz contraste premium com pedra branca e laca
  off-white. Ponto-herói (uma parede de nogueira numa cozinha clara).
- **Contras:** ESCURECE o ambiente — usar como acento, não como cozinha inteira
  em espaço pequeno.
- **ONDE FALHA:** nogueira em tudo + cozinha pequena + pouca luz = caverna. Em
  render escuro engole detalhe (precisa de luz quente rebatida). Imitação barata
  de nogueira fica vermelho-arroxeada (`[110,60,55]`) → cara de fake; manter
  no marrom-neutro.

## MDF amadeirado (foil / melamina / lâmina sobre MDF)

- **Aparência:** o substrato real de 90% do planejado. Reproduz qualquer madeira
  acima; qualidade = qualidade do mapa/veio. Bom carvalho foil ≈ `[191,167,137]`.
- **Custo:** `$`–`$$` (melamina/foil `$`; lâmina natural sobre MDF `$$$`).
- **Prós:** barato, estável, plano, sem empenar; chapa grande sem emenda.
  Viabiliza o sistema inteiro.
- **Contras:** é a fonte do "builder-grade" quando o veio é ruim/saturado.
- **ONDE FALHA (anti-padrão central):**
  - **Veio saturado/alaranjado** = leitura imediata de "marcenaria de loja".
    Dessaturar.
  - **Padrão de veio REPETINDO** (foil tileado) — em render, mesmo nó/risca a
    cada porta denuncia foil barato. Variar o offset do mapa por peça.
  - Borda com fita de PVC de cor diferente lê "móvel de montar".

## Ripado (painel ripado / réguas verticais)

- **Aparência:** réguas de madeira paralelas com sulco/sombra entre elas. Mesma
  paleta da madeira-base (carvalho `[191,167,137]`, nogueira `[92,64,46]`). O
  sulco cria ritmo e sombra — recurso de PAREDE/painel/fundo de nicho, não de
  frente de gaveta.
- **Custo:** `$$$` (trabalho de marcenaria; mais caro que liso).
- **Prós:** textura e verticalidade; transforma painel chapado em peça de design;
  ótimo em fundo de nicho, painel de TV, lateral de torre/geladeira.
- **Contras:** acumula poeira no sulco; data se usado em excesso.
- **ONDE FALHA:**
  - **Ripado em TUDO** = tendência saturada, data rápido (o "boiserie 2022").
    Usar pontual.
  - **Render:** sulco sem profundidade real (só textura plana) = falso; precisa
    de geometria/normal map pra sombra entre réguas. Espaçamento de régua
    irregular lê amador.

---

## Decisão rápida (para o gerador)

- **Default coerente com golden sample:** carvalho/freijó CLARO dessaturado
  `[191,167,137]`; nicho de acento `[138,104,66]`.
- **Quer acento premium/escuro:** nogueira `[92,64,46]` em UMA peça-herói, resto
  claro.
- **Quer textura/parede de design:** ripado na paleta da madeira-base, pontual.
- **Substrato real:** MDF amadeirado — a cor manda, não o nome.
- **Anti-padrões a barrar:** RGB saturado/alaranjado (`>` ~`[200,150,90]`) →
  builder-grade; veio repetindo tileado; verniz brilhante (data); ripado em
  excesso; nogueira+espaço pequeno+pouca luz (caverna).
