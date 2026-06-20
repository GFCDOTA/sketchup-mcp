# Validation Report — Cozinha r004 (Design Critic)

**Artefato julgado:** `artifacts/planta_74/furnished/kitchen_angles/cozinha_montagem.png`
(+ crops `cozinha_ang_01_hero_3q`, `_02_elevacao`, `_04_dollhouse`, `_05_detalhe`)
**Data:** 2026-06-19
**Papel:** Design Critic (interiores, exigente)
**Modo de render:** FLAT (massa/material básico, sem V-Ray). Veios de pedra,
reflexo de inox e brilho de LED NÃO julgados — julgo FORMA, PROPORÇÃO, COR,
COMPOSIÇÃO, INTEGRAÇÃO e leitura de "planejado caro".

---

## VEREDITO: WARN

A base está certa — layout LINEAR disciplinado, coluna da geladeira INTEGRADA
de verdade (filler + aéreo flush = leitura de marcenaria, não objeto solto),
ritmo de módulos correto embaixo (gaveteiro + portas), rodapé grafite ancora.
Mas três coisas derrubam o "planejado caro": o bicolor está agressivo demais,
a transição aéreo→coluna está com stub cru / vão aberto pro céu, e o backsplash
está pelado. Nenhuma exige mover pia/parede/layout/medida — são cor + arremate.

**Felipe dá o PASS final.** Eu NÃO aprovo sozinho.

---

## O QUE ESTÁ BOM (manter)

- **Layout linear** na parede OESTE, pia FIXA — respeita o PDF. Não virou U/L.
- **Coluna da geladeira integrada**: filler lateral + armário superior flush no
  topo da geladeira = leitura de torre planejada, não geladeira solta. Esse é o
  acerto mais caro do projeto.
- **Modulação inferior**: gaveteiro de 3 gavetas + portas com proporção crível;
  cooktop e cuba embutidos no tampo; coifa slim integrada sob o aéreo.
- **Rodapé/sóculo grafite** recuado — dá o "pé" certo da marcenaria.

---

## DEFEITOS PRIORITÁRIOS (máx. 4 — dentro das constraints)

### 1. [P1] Bicolor agressivo demais → lê "kit builder-grade", não planejado caro
**Evidência:** elevação + hero. Inferiores marrom médio saturado (171,140,100)
contra aéreos fendi quente (224,215,199). O salto de valor E de croma é grande
e arbitrário — é a assinatura visual de cozinha de loja, não de marcenaria.
**Fix (cor, não posição):** puxar a madeira inferior PRA DENTRO da família fendi
quente — dessaturar e clarear ~15–20% (ex.: algo na faixa 190,165,135) mantendo
os aéreos como estão. Resultado: paleta coordenada com UM degrau tonal (base mais
quente/escura, aéreo mais claro), não dois materiais brigando.

### 2. [P1] Transição aéreo→coluna quebrada: stub diagonal cru + vão aberto pro céu
**Evidência:** hero, dollhouse e detalhe. Onde o corrido de aéreos morre na coluna
da geladeira há um pedaço de parede triangular/diagonal cru e uma fresta aberta —
o backsplash vaza pro céu atrás. É o elemento mais "inacabado" da cena e mata a
leitura de planejado bem ali no ponto mais visível.
**Fix (arremate, não medida):** fechar o vão com painel lateral / filler de
acabamento flush à face da coluna, terminando o corrido de aéreos num plano
limpo e vertical. Sem expor parede atrás nem deixar a diagonal aparente.

### 3. [P2] Backsplash pelado → zona mais visível sem hierarquia, lê barato
**Evidência:** elevação + hero. Faixa grande de pedra clara totalmente lisa entre
tampo e aéreo, sem nada. Em flat isso vira um campo cinza morto que apaga o "caro".
**Fix (composição, não posição):** introduzir uma quebra horizontal — prateleira
slim de madeira (combina com o nicho aberto já existente) OU uma faixa de material
definida (régua/junta) cruzando o backsplash, dando hierarquia ao olho. NÃO mover
a pia nem a cuba.

### 4. [P2] Portas dos aéreos são placas únicas grandes, sem ritmo com a base
**Evidência:** elevação. As portas superiores são lajões largos que não alinham
com a modulação dos inferiores — leem pesadas e desalinhadas verticalmente.
**Fix (proporção, não layout):** alinhar a largura/junta das portas dos aéreos
aos módulos inferiores (gaveteiro / portas), pra os prumos empilharem. Mesma
quantidade de módulos, juntas verticais coincidindo base↔aéreo.

---

## NÃO-DEFEITOS (não penalizar — é flat)
- Ausência de veio na pedra, reflexo no inox da geladeira, brilho do LED quente:
  são do render flat, não do design. Aparecem no V-Ray.
- Cor "inox" cinza chapado da geladeira: idem.

## REGRA RESPEITADA
Referência manda na LINGUAGEM (cor coordenada, arremate, hierarquia) → todos os
fixes acima são cor/arremate/proporção. PDF manda na POSIÇÃO → nenhum fix toca
pia, parede, porta, layout linear ou medida. Gates seguem PASS.
