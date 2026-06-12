# SCENE-LIVINGROOM-MWM — cycle 002 (TOP3 fixes do WARN cycle001)

- **Data:** 2026-06-11
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto") — review VISUAL real via browsing das duas
  URLs raw.githubusercontent (ANTES @402b66e vs DEPOIS @39bb7f2), citou GitHub como fonte.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- **Imagens julgadas:** contact_sheet.png cycle001 (SHA 402b66e) vs cycle002 (SHA 39bb7f2),
  ambas em artifacts/review/scenes/living_room_modern_warm_minimal/.
- **Gate deterministico previo:** SceneSpatialGate PASS 15/15 (12 HARD + 3 SOFT; os 2 HARD
  novos do cycle002 inclusos), 8/8 sabotagens FAIL.

## VEREDITO: IMPROVED

> "cycle 002 melhorou claramente o conjunto: o sul deixou de ser um vazio morto, a cortina
> perdeu protagonismo na vista 3/4 humana, e o miolo agora tem mais area de ancoragem.
> Ainda nao e' PASS limpo de composicao; e' WARN melhorado."

## STATUS DOS TOP3 DO CYCLE 001

1. **FIX1_ACCENT: parcialmente resolvido.** A poltrona quebra o vazio sul/oeste com intencao
   — existe conversa sofa<->poltrona. Mas entrou "quadradao solto", bloco no tapete, sem
   rotacao ou gesto de recepcao. Melhorou o peso, ainda nao e' decisao refinada.
2. **FIX2_CORTINA: resolvido na 3/4 humana; ainda incomoda na camera SketchUp.** Na vista
   central virou moldura de fundo. Na vista SU os paineis verticais ainda sao barras fortes
   de primeiro plano competindo com sofa/poltrona.
3. **FIX3_MIOLO: melhorou bastante, mas nao fechou.** Tapete maior pega sofa + mesa + frente
   da poltrona. A mesa continua pequena/baixa demais — parece acessorio, nao centro compositivo.

## NOVOS_PROBLEMAS

- Poltrona muito ortogonal e "caixote" — melhora o vazio mas enrijece o layout.
- Excesso de blocos pequenos PRETOS no lado direito/sudeste criando ruido.
- Composicao mais cheia, mas ainda sem hierarquia elegante no primeiro plano.

## TOP3_FIXES (cycle 003, so composicao)

1. **Rotacionar a poltrona 10–15 graus** em direcao ao sofa/mesa (nao paralela ao tapete):
   "objeto colocado" -> "conversa de estar". ⚠️ Implica suportar rotacao LIVRE no composer
   (place_parts/_rot_pt hoje so 0/90/180/270 exatos — verts8 ja gira, falta generalizar).
2. **Reduzir presenca da cortina na vista SU (direita):** paineis mais finos/recuados ou mais
   colados nas extremidades, pra nao virarem barras de primeiro plano.
3. **Mesa de centro maior/oval/organica** ocupando o eixo sofa<->poltrona; o tapete cresceu,
   o miolo pede mesa com presenca proporcional.

## Traducao pra regra/spec (pre-cycle 003)

- Composer: rotacao arbitraria em place_parts (rot real nos verts8 + bbox AABB recalculado);
  gate sem_colisao/circulacao hoje operam em AABB — ok, mas conferir folgas com rot 15.
- CurtainSpec: panel_w menor (ex. 0.40) e/ou fold_amp/thickness menores; possivel check de
  largura projetada por vista.
- CoffeeTableSpec: variante oval/racetrack (verts8) ~1.3x0.7; manter mesa_distancia [0.35,0.45].
- "Blocos pretos no SE": plant_pot/side_table metal — considerar clarear pot ou mover side
  table pro lado oposto; candidato a regra de densidade de massas escuras por quadrante.
