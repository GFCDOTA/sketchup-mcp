# CARD: Pedra de veio sutil

**Problema:** backsplash/tampo liso parece parede pintada ("parede mineral fosca"),
sem materialidade nem assinatura.

**Solução:** textura de pedra **clara quente com veio SUTIL** e baixo contraste — tampo
e backsplash são a MESMA pedra, contínuos (o backsplash é o tampo subindo pela parede).
Nunca mármore dramático/escuro (rouba a cena de uma cozinha econômica).

**Aplicável em:** tampo, backsplash, nicho molhado, soleira.

**Gate:**
- veio SUTIL: contraste (desvio padrão da luminância) ~3–10. < ~2 = chapado; > ~12 =
  veio chamativo/mármore.
- tileable (FFT periódico) — sem costura nem veio reto repetindo.
- mesma cor tampo = backsplash (continuidade).

**Valores (golden sample):** pedra [222,219,212]; textura `A_quartzo_fio` (nuvem quente +
fio de veio fino esparso, contraste ~4.0) — escolhida num painel de 4 candidatos vs os
anti-padrões; BRDF `reflect 0.17 / gloss 0.8` (polish). Tampo fino 2–4 cm proud;
backsplash sobe ~50 cm até o aéreo.

**Token:** `references/tokens/subtle_veined_stone.json`

**Evidência:** GPT — *"agora lê como pedra clara com veio sutil… ficou no ponto, sem
virar mármore dramático"*. Textura gerada em `assets/textures/procedural/candidates/`.
