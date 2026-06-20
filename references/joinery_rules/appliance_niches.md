# Appliance niches — `loose_object -> planned_niche_system`

> O salto de qualidade nº 1 da marcenaria planejada: nenhum eletrodoméstico fica
> **solto** ao lado do armário. Cada um ganha um **nicho planejado** — recorte com
> painel lateral, frente flush, filler, respiro, material coordenado e integração com o
> conjunto. O golden-sample da planta_74 já faz isso com a torre da geladeira
> (`tools/kitchen_layout.py`, módulo `aereo_fridge` + filler/gable).

## A anatomia de qualquer nicho planejado

Todo nicho é a mesma receita de 6 partes; muda só a dimensão:

1. **Painel lateral (gable/torre)** — chapa vertical do mesmo material do conjunto que
   "abraça" o eletro e o transforma de objeto solto em parte do armário. É o que cria a
   leitura de COLUNA. Espessura de chapa ~1.8 cm (`PANEL_THICKNESS_MDF`).
2. **Frente flush** — a face do eletro alinha com a frente dos módulos vizinhos (mesmo
   plano da porta). Nada de geladeira "pra fora" estourando a linha da bancada.
3. **Filler / painel de acabamento** — fecha a folga entre o nicho e a parede/coluna
   (15–18 cm, proj. 16). Na planta_74 o filler de 16 cm é o gable lateral da torre.
4. **Respiro / ventilação** — folga calculada pra calor + abertura de porta. Cada eletro
   tem o seu (tabela abaixo). Respiro some quando o nicho é justo demais → defeito.
5. **Material** — o nicho usa o MESMO material/cor do conjunto (corpo/aéreo), não uma
   cor "de eletro". Inox/preto é só o eletro em si; a moldura é marcenaria.
6. **Integração vertical** — acima do eletro entra **aéreo de fechamento** (não vão
   aberto): o `aereo_fridge` da planta_74 fecha o topo da geladeira até a linha do aéreo
   (`aereo_top = AEREO_Z0 + AEREO_H`). Isso é o que faz a torre ir do piso ao teto.

> Regra de ouro: se você consegue **puxar o eletro pra fora sem mexer em marcenaria**,
> ele está solto (`loose_object`) e ainda NÃO é um nicho planejado.

---

## Geladeira / torre (o caso resolvido na planta_74)

- **Largura do nicho:** 55–75 cm (corpo ~60–70 + respiro). Proj. `GEL_W = 0.70`.
- **Profundidade:** `GEL_D = 0.66`; corpo da geladeira é fundo, o nicho acompanha.
- **Altura:** torre **piso-teto** — corpo `GEL_H = 1.80` + módulo de fechamento
  `aereo_fridge` por cima até `aereo_top` (≈2.10). Sem vão morto em cima.
- **Respiro:** 2–6 cm lateral total (nicho `GEL_W` − corpo inset). Mais alguns cm atrás
  pro compressor. Topo precisa de folga de exaustão de calor.
- **Painel lateral / filler:** gable de 16 cm (`filler`) faz a junção torre↔bancada e
  esconde a lateral crua da geladeira.
- **Material:** painel/torre = material do conjunto. A geladeira é inox `[216,220,227]`;
  o nicho ao redor é marcenaria (aéreo fendi / corpo carvalho).
- **Erro comum:** geladeira encostada no fim da bancada sem painel/torre (`loose_object`),
  ou nicho justo (porta raspa, sem ventilação), ou vão aberto acima (acumula pó, lê
  inacabado).

## Forno (embutido / coluna)

- **Nicho:** ~60 cm de largura útil (forno padrão 60 cm), recorte na altura confortável
  — forno de embutir em coluna costuma ficar com a porta na faixa de 80–100 cm do piso
  (não se abaixa pra abrir). Profundidade da coluna 55–60 cm.
- **Respiro:** forno gera muito calor — exige folga de ventilação especificada pelo
  fabricante (tipicamente vão atrás + grelha de exaustão; nunca selar a caixa).
- **Integração:** forno + micro empilhados na MESMA coluna (ver micro) é o arranjo
  premium; alinhar frentes flush.
- **Erro comum:** forno embaixo do cooktop "porque sempre foi assim" quando o projeto
  pede coluna (perde-se a ergonomia de não abaixar) — escolha é de layout, mas a coluna
  lê mais planejada e poupa a coluna.

## Micro-ondas (sempre em nicho, nunca na bancada)

- **Nicho:** recorte dedicado, tipicamente empilhado com o forno na coluna, ou em nicho
  alto no aéreo. Largura ~musculatura do micro + folga; frente flush com a coluna.
- **Respiro:** grelhas laterais/traseiras do micro precisam de folga — caixa selada
  superaquece.
- **Porquê:** micro **na bancada** é o `loose_object` clássico que come área de trabalho
  e quebra a linha limpa. Sobe pro nicho.
- **Erro comum:** micro pousado no tampo (rouba bancada, parece provisório) ou enfiado
  num vão sem respiro.

## Cooktop (embutido no tampo)

- **Nicho:** recorte NO tampo. O cooktop fica quase flush com a pedra — vidro fino só uns
  mm acima do tampo. Proj. `COOK_W=0.46, COOK_D=0.50, COOK_Z0=0.885` (logo abaixo de
  `COUNTER_H=0.90`, embutido).
- **Embaixo:** módulo base (forno ou gaveteiro) — nunca vão aberto.
- **Material/cor:** vidro preto `[44,44,48]`. A moldura é o tampo de pedra.
- **Erro comum:** cooktop de sobrepor com borda alta saliente (degrau que junta gordura),
  ou cooktop longe da coifa fora da faixa de exaustão (ver cooktop→coifa em
  `kitchen_ergonomics.md`).

## Coifa / depurador (under-cabinet, slim)

- **Nicho:** embutida no aéreo, slim, alinhada sobre o cooktop. Proj. coifa
  `COOK_W + 0.06` de largura, profundidade `AEREO_DEPTH - 0.01`, espessura 5,5 cm,
  pendurada em `AEREO_Z0 - 0.055` (sob o aéreo). Cor torre/grafite `[69,90,100]` com
  grelha embutida.
- **Distância ao cooktop:** 45–65 cm (under-cabinet). Chaminé aberta subiria 70–80.
- **Integração:** a coifa vira PARTE do aéreo (caixa contínua), não um objeto pendurado.
  Acima dela, aéreo de fechamento esconde o duto.
- **Erro comum:** coifa-objeto pendurada por hastes longe do aéreo (`loose_object`),
  desalinhada do cooktop, ou com duto aparente. Embutir slim no aéreo resolve.

## Lava-louças / cooktop de piso / adega (mesma receita)

Qualquer eletro de embutir segue a anatomia: recorte do módulo na medida do aparelho +
frente flush (porta-painel do mesmo material cobrindo a face, no caso de integrados) +
respiro do fabricante + alinhamento. **Integrado** = frente coberta por painel de
marcenaria (some o eletro); **de embutir aparente** = frente do próprio eletro flush com
as portas. Os dois são nicho planejado; nenhum fica solto.

---

## Checklist de nicho (antes de mostrar)
- [ ] Tem painel lateral/torre (não dá pra puxar o eletro sem mexer em marcenaria)?
- [ ] Frente flush com os módulos vizinhos?
- [ ] Filler fechando a folga com parede/coluna (15–18 cm)?
- [ ] Respiro dentro da faixa (geladeira 2–6 cm lateral; forno/micro com ventilação)?
- [ ] Material do nicho = material do conjunto (não cor de eletro)?
- [ ] Topo fechado por aéreo (sem vão morto sobre o eletro)?

Falhou qualquer item → ainda é `loose_object`, não nicho.
