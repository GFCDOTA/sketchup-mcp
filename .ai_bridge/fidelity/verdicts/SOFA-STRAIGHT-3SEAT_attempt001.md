# SOFA-STRAIGHT-3SEAT — veredito GPT, tentativa 001

- **Data:** 2026-06-08
- **Juiz:** GPT (ChatGPT Plus, via Chrome) — fronteira dura: a máquina não autojulga
- **Render avaliado:** `sketchup-mcp-mobiliar/artifacts/review/furniture/sofa/sofa_arms_iso.png`
- **Veredito:** **WARN**

## VEREDITO: WARN
Reconhece como sofá 3 lugares, mas ainda está mais "bloco CG parametrizado" do que produto realista.

## PROPORCAO_ESCALA
Assento coerente em largura para 3 lugares, mas almofadas muito "chapadas" e baixas; encostos altos e retos demais, quase placas verticais; braços grossos e altos, com cara de caixa; pés pequenos ok p/ industrial. Altura ~80cm plausível, mas encosto deveria parecer mais macio e menos monolítico.

## ANATOMIA
3 assentos, 3 encostos, braços, base e pés identificáveis. Mas almofadas parecem peças rígidas empilhadas, não volumes acolchoados. Falta separação anatômica entre estrutura rígida e partes macias: assento/encosto com mais espessura visual, bordas arredondadas e leve abaulamento.

## REALISMO_FORMA
Ainda parece bloco CG. Arestas duras demais, sem chanfro/raio; encostos parecem painéis de madeira/caixa, não almofadas; base escura funciona p/ industrial mas está muito contínua e pesada. Precisa de bevels, folgas menores e proporção mais refinada dos braços.

## TOP_3_PROBLEMAS
1. Arestas 100% retas/quebradas: mata o realismo de tecido/estofado.
2. Encostos muito verticais, altos e rígidos, parecendo blocos estruturais.
3. Braços/base grossos demais em relação às almofadas → sofá pesado e pouco confortável.

## PROXIMA_ACAO
Aplicar raio/chanfro nas almofadas de 4–6 cm: **`cushion_edge_radius = 0.04–0.06m`**. É o ajuste mais importante antes de mexer em textura — muda imediatamente de "caixa" para "estofado".

## ALVO_IDEAL (referência p/ as próximas tentativas)
Sofá reto 3 lugares: **largura ~2,10–2,30m**, **profundidade ~0,85–0,95m**, **altura total ~0,78–0,85m**, **assento ~0,42–0,45m** do piso. Braços **16–22cm** de largura, encosto levemente inclinado/recuado, almofadas grossas com bordas arredondadas e separações visíveis mas não exageradas.
