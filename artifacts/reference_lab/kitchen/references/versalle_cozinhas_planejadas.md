# Referencia curada — Versalle "Cozinhas Planejadas" (board Pinterest)

> **Board:** https://br.pinterest.com/versallemoveis/cozinhas-planejadas/
> **Tipo:** INSPIRACAO curada pelo Felipe, NAO reproducao. Esta nota registra a
> GRAMATICA a extrair; nenhuma imagem e baixada/copiada nem pixel reproduzido.
> O agente le isto como LINGUAGEM, nunca como POSICAO.

```
referencia = LINGUAGEM   ·   PDF = POSICAO   ·   gates = SEGURANCA   ·   Felipe = PASS
```

## Por que este board entrou
Board comercial de marcenaria planejada (movelaria Versalle). Util como vocabulario
de cozinha de planejado bem-resolvida: como modulos, torres, aereos ate o teto,
iluminacao embutida e acabamentos coordenados sao tratados por quem vende planejado.
Casa com a direcao aprovada do Felipe (BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE) e com o
golden sample da `planta_74` — por isso vira fonte de gramatica, nao de copia.

## O QUE EXTRAIR (gramatica — vai para tokens/material/luz, nunca para layout)
- **Paleta coordenada** — combinacoes de madeira quente + neutro escuro/fendi + pedra;
  ler como `material_token`/`palettes/`, mapear para RGB, NUNCA importar a cor "no olho".
- **Marcenaria** — frentes flush, modulacao limpa, sistema handle-less (cava/gola/perfil),
  reveal/shadow gap entre modulos, soculo recuado, fechamento ate o teto (anti-po).
- **Torre / coluna** — geladeira e forno/micro/airfryer integrados em torre planejada
  (`loose_object -> planned_niche_system`); confirma a preferencia de torre quente.
- **Iluminacao** — LED linear sob aereo / em nicho, quente, embutido; nada de spot bolinha.
- **Acentos** — bronze/champagne SUTIL, vidro reflecta pontual com LED interno, backsplash
  de pedra protagonista atras da area da torneira.

Destino dessa extracao: `references/tokens/*.json`, `references/materials/*.md`,
`references/palettes/*.json` e os `cards/*.json` — sempre com RGB aproximado, faixa de
medida e ONDE FALHA. A nota nao cria token novo sozinha; aponta para onde codificar.

## O QUE NAO COPIAR (POSICAO e estrutura — sao do PDF, nao da foto)
- **Layout** — muitas fotos do board sao cozinha em U/L, ilha, peninsula ou ambiente
  amplo de casa/mansao. A `planta_74` e **linear FIXO do PDF**. Nao transformar em U/L.
- **Ilha** — proibido inventar ilha por causa de foto.
- **Escala de mansao** — vaos largos, pe-direito alto, dupla bancada: nao existem no
  apto de 74 m2. Ler a forma, descartar a metragem.
- **Pia / ponto hidraulico / parede / porta / janela / shaft / area de servico** —
  IMUTAVEIS. Nenhuma referencia move a pia. A marcenaria se organiza EM TORNO do PDF.
- **Cor/material "no olho"** — toda escolha passa por `material_token` + RGB + maintenance
  gate, nunca "ficou parecido com a foto".

## Como casa com o perfil do Felipe
Ver `specs/felipe_kitchen_preference_profile.json` (fonte de verdade do gosto/uso).
- **Bate forte:** escura/meio-termo, industrial preto+madeira, ate-o-teto anti-po,
  handle-less, LED quente embutido, torre integrada, bronze sutil, reflecta pontual.
- **Cuidar (marcar WARN):** veio dourado/reflecta exagerado = "mansao fake"; tudo preto
  sem reflexo = caverna; madeira em area molhada = fake; coifa fora de escala; LED frio.
- **Manutencao real:** cuba preta vs inox, piso grafite medio (nao preto), pedra a
  pesquisar (quartzo/porcelanato/granito) — decisao so no maintenance gate, com trade-off.

## Uso pelo agente (regra de processo)
A referencia influencia LINGUAGEM e MEDIDA, depois o PDF fixa a POSICAO, os gates dao a
SEGURANCA e o Felipe da o PASS. Fluxo: extrair gramatica deste board -> gerar 3 variacoes
reais sobre a geometria CONGELADA da `planta_74` -> Felipe julga A/B/C -> so depois descer
para material/cuba/manutencao/custo. **Nao** gerar dezenas de imagens no olhometro; **nao**
escolher material definitivo antes do A/B/C; **nao** aplicar na cozinha real sem spec.

## Status
- Registro de referencia: **curado** (Felipe escolheu o board).
- Extracao de tokens novos a partir dele: **a fazer** quando houver design move concreto
  (cada novo token nasce em `references/tokens/` com `gate_refs` + `applies_to_kinds`).
- Veredito visual: **do Felipe** (nunca auto).
