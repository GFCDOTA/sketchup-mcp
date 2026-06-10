# Analise de referencia — ref_mdg

**Hipotese:** desconhecido (confianca baixa) — variante **straight**
**Unidade do modelo:** mm  |  **single block?** NAO (17 componentes)

## Bounding box
- 1.336 x 0.447 x 0.394 m (largura x profundidade x altura)

## Anatomia detectada
- overall: 1.336 x 0.447 x 0.394 m
- altura do assento ~ 0.29 m
- assentos: 17 (cada ~0.5x0.5x0.143 m)
- encostos: 0 (cada ~NonexNonexNone m)
- bracos: 0 (cada ~NonexNonexNone m)
- pes: 10

## Materiais
- principal: **IMG_0197** rgb=[8, 8, 3] textura=IMG_0197.jpg
- todos: Blue & Gray, IMG_0197, [0135_DarkGray], myBlack, daisy-black-plain-colour-31000, wallpaper-65713

## Eixo / orientacao
- -Y (assumido: frente = lado dos assentos/encosto)

## Renders
- top / front / iso (ver PNGs nesta pasta)

## Conclusao p/ o builder
- NAO e bloco unico: tem 17 pecas semanticas separadas.
- o SofaBuilder deve reproduzir: base/plataforma + assentos SEPARADOS + encostos SEPARADOS + bracos + pes
- material principal = tecido escuro (Dansbo-like); pes escuros.