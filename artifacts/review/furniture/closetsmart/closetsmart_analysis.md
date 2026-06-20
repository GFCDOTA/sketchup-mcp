# Analise de referencia — ref_closetsmart

**Hipotese:** desconhecido (confianca baixa) — variante **straight**
**Unidade do modelo:** m  |  **single block?** NAO (59 componentes)

## Bounding box
- 3.1 x 2.3 x 2.955 m (largura x profundidade x altura)

## Anatomia detectada
- overall: 3.1 x 2.3 x 2.955 m
- altura do assento ~ 0.3 m
- assentos: 1 (cada ~0.75x0.56x0.08 m)
- encostos: 14 (cada ~0.683x0.43x2.179 m)
- bracos: 0 (cada ~NonexNonexNone m)
- pes: 0

## Materiais
- principal: **<auto>3** rgb=[0, 0, 0]
- todos: <auto>, <auto>1, <auto>2, <auto>3, [Translucent Glass Gray]

## Eixo / orientacao
- -Y (assumido: frente = lado dos assentos/encosto)

## Renders
- top / front / iso (ver PNGs nesta pasta)

## Conclusao p/ o builder
- NAO e bloco unico: tem 59 pecas semanticas separadas.
- o SofaBuilder deve reproduzir: base/plataforma + assentos SEPARADOS + encostos SEPARADOS + bracos + pes
- material principal = tecido escuro (Dansbo-like); pes escuros.