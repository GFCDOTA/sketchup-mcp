# Analise de referencia — Group_60_ref

**Hipotese:** sofa (confianca alta) — variante **chaise** chaise_left
**Unidade do modelo:** in  |  **single block?** NAO (11 componentes)

## Bounding box
- 1.656 x 2.839 x 0.927 m (largura x profundidade x altura)
- footprint preenchido 73% do bbox (<80% => L/chaise)

## Anatomia detectada
- overall: 2.839 x 1.656 x 0.927 m
- altura do assento ~ 0.28 m
- assentos: 2 (cada ~0.9x0.7x0.15 m)
- encostos: 2 (cada ~0.15x0.9x0.825 m)
- bracos: 4 (cada ~0.7x0.493x0.511 m)
- pes: 4

## Materiais
- principal: **Material4** rgb=[37, 38, 33] textura=kivik-bezug-fur-hocker-mit-aufb__0152869_PE311149_S4.jpg
- todos: Dansbo Dark Gray, Carpet, Fabrics, Leathers, Textiles and Wallpaper-1, [Color_009], Material25, Material4

## Eixo / orientacao
- -Y (assumido: frente = lado dos assentos/encosto)

## Renders
- top / front / iso (ver PNGs nesta pasta)

## Conclusao p/ o builder
- NAO e bloco unico: tem 11 pecas semanticas separadas.
- o SofaBuilder deve reproduzir: base/plataforma + assentos SEPARADOS + encostos SEPARADOS + bracos + pes + CHAISE
- material principal = tecido escuro (Dansbo-like); pes escuros.