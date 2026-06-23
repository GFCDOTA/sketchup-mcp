# Felipe Style DNA

> **Identidade de estilo CANÔNICA e room-agnostic** do Felipe (cozinha · sala · lavabo · quarto · área).
> Consolidação (não duplicação) das fontes que já existiam, todas específicas de cozinha:
> [FELIPE_KITCHEN_PREFERENCES.md](../../artifacts/reference_lab/FELIPE_KITCHEN_PREFERENCES.md) (prosa GOSTOU/NÃO-GOSTOU) +
> [felipe_kitchen_preference_profile.json](../../artifacts/reference_lab/kitchen/specs/felipe_kitchen_preference_profile.json) (machine-readable) +
> [theme BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE.json](../../artifacts/reference_lab/themes/BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE.json) (preset executável, GOLDEN_SAMPLE_004 aprovado).
> O Arquiteto carrega este arquivo ANTES de gerar qualquer cômodo. É RESTRIÇÃO, não sugestão.

## Estilo principal
**BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE** — industrial boutique premium, escuro, quente e sofisticado.
"Casa de gente rica", não oficina. Não é industrial bruto, não é showroom genérico, não é luxo fake.

## Regra de ouro (não negociável)
**Referência = LINGUAGEM · PDF = POSIÇÃO · Gates = SEGURANÇA · Felipe = PASS final.**
O PDF/planta manda na posição (parede/porta/janela/pia/hidráulica/circulação = imutável). A referência só
influencia a linguagem (cor/material/luz/marcenaria). O veredito visual IMPROVED/SAME/WORSE é do Felipe,
nunca auto.

## Materiais (a paleta da assinatura)
- **Base** preto fosco / grafite (nos volumes certos) — `[24,24,24]` a `[38,39,40]`.
- **Equilíbrio** madeira natural quente (nogueira/freijó/carvalho mais quente) **como ACENTO**, nunca massa fria — `~[126,82,48]`.
- **Protagonista** pedra escura com veio dourado **SUTIL** (backsplash atrás da torneira) — veio sutil, nunca veião de mansão fake.
- **Tampo** pedra escura controlada, sem competir com o backsplash — `~[45,43,40]`.
- **Metais** bronze/champagne **discretos, só em detalhe** — `~[171,119,63]`; cuba e torneira **pretas**.
- **Luz** LED linear quente **2700K** (sob aéreo/nicho), contínuo — nunca spot bolinha, nunca frio 4000K+.
- **Eletros** inox dark / grafite / preto, **reflexivo** (devolve luz, ajuda a sair da caverna) — `~[82,84,84]`.
- **Piso** (default seguro) grafite médio acetinado OU cimento queimado quente — **NÃO** preto como default.

## Sensação desejada
O ambiente deve parecer: **premium · compacto · urbano · elegante · aconchegante · dramático sem virar
caverna · feito sob medida para apartamento brasileiro** (74m² real, não mansão de catálogo).

## Checks obrigatórios (o "juiz" do Felipe)
- **cave_check** — escuro, mas **não caverna** (LED + madeira/reflexo compensam).
- **fake_luxury_check** — dourado sutil, **nunca cafona/exagerado**.
- **compact_premium_check** — impacto sem matar circulação (apê 74m², compacto).
- **warmth_check** — madeira/luz quente suficientes; sem cair no frio.
- **material_hierarchy_check** — pedra é protagonista; preto é base; bronze/madeira são pontuação.
- **usability_check** / **maintenance_check** — bonito mas **morável**; manutenção viável ACIMA de material delicado.
- **felipe_taste_match** — parece o apê boutique dark premium do Felipe?

## Anti-patterns (NÃO GOSTOU — vira WARN/FAIL)
- Branco puro / chapado (cheira MDF barato). · Tudo preto sem compensação de luz/reflexo = caverna.
- Veio dourado exagerado = mansão fake / fake luxury. · Puxador dourado demais = ostentação fake.
- Reflecta em **todos** os aéreos = showroom, marca dedo. · Madeira na área molhada (cuba/pia) = parece fake.
- LED frio 4000K+. · Coifa industrial gigante fora de escala. · Piso preto demais (pesa) ou claro demais (suja).
- Mover posição fixa do PDF (pia/parede/porta/janela) por causa de uma referência.

## Hardware / detalhe
Sem puxador tradicional: **cava / gola / perfil-J / push-amortecedor**. Bronze/champagne só em detalhe sutil.
Armários **até o teto** (anti-pó + guarda item de pouco uso). Gavetões inferiores pra peso quando couber.

## Processo (a regra do Felipe)
Fecha preferências → atualiza agente → gera **3 variações reais** → Felipe julga A/B/C → **só depois** olha
Pinterest em lote e desce pra material/cuba/manutenção/custo. **Não** gerar 30 imagens no olhômetro.

## Por cômodo (detalhe específico vive na fonte machine-readable)
- **Cozinha** (piloto, GOLDEN_SAMPLE_004 congelado): ver `felipe_kitchen_preference_profile.json` —
  eletros must-have, torre quente, layout linear FIXO do PDF (r004), nichos, vidro reflecta pontual.
- **Sala / lavabo / quarto**: ainda sem profile próprio — herdam esta DNA até o Felipe fechar o gosto do cômodo.

## Aprendido via Consult GPT
- Sofá industrial premium para Felipe deve ser derivado de referência real, com assento profundo, braços contidos, encosto baixo levemente inclinado e pés finos em metal escuro. _(Consult GPT · LP-SOFA-001)_
- Evitar sofá-caixa: todo sofá precisa ter leitura clara de assento volumoso, braço suavizado, encosto confortável e base leve. _(Consult GPT · LP-SOFA-001)_
- Couro grafite/slate funciona bem no BLACK_WOOD_GOLD quando tem roughness controlado e não parece plástico brilhante. _(Consult GPT · LP-SOFA-001)_
- Em sala compacta, preservar profundidade útil do assento e reduzir largura antes de sacrificar conforto visual. _(Consult GPT · LP-SOFA-001)_
- Não copiar dimensão de sofá de referência: a referência define linguagem/formalidade/material; o footprint final vem da planta + gates de circulação (sala compacta). _(Consult GPT · LP-SOFA-001)_
- Eletros e coifa devem ser `dark stainless`, `graphite` ou `matte black metal`, nunca inox claro dominante. _(Consult GPT · kitchen_skin_045756)_
- Em cozinha dark premium, eletro pode ser integrado visualmente, mas precisa manter leitura sutil de volume. _(Consult GPT · kitchen_skin_045756)_
- Coifa é elemento coadjuvante; backsplash dark-gold é o protagonista. _(Consult GPT · kitchen_skin_045756)_
- Preto sobre preto precisa de separação por luz, sombra, roughness ou borda, não por cor forte. _(Consult GPT · kitchen_skin_045756)_
