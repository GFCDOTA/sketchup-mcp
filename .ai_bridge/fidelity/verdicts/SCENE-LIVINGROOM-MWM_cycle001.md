# SCENE-LIVINGROOM-MWM — cycle 001 (Intent-to-Scene slice 1)

- **Data:** 2026-06-11
- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto") — review VISUAL real: abriu o contact sheet
  via browsing na URL raw.githubusercontent (repo publico), citou GitHub como fonte.
  Chat: https://chatgpt.com/c/6a2a2c0e-6494-83e9-a616-9f22566ef8da
- **Imagem julgada:** artifacts/review/scenes/living_room_modern_warm_minimal/contact_sheet.png
  (= https://raw.githubusercontent.com/GFCDOTA/sketchup-mcp/feat/intent-to-scene/artifacts/review/scenes/living_room_modern_warm_minimal/contact_sheet.png)
- **Gate deterministico previo:** SceneSpatialGate PASS 13/13.

## VEREDITO: WARN

> "A cena ja le como 'sala modern warm minimal' e o eixo sofa + quadro + tapete funciona,
> mas a composicao ainda esta com cara de layout correto, nao de direcao de arte fechada.
> **SpatialGate PASS != composicao PASS.**"

## PROBLEMAS

1. **Peso visual esmagado no eixo norte/leste.** Sofa charcoal + cortina full-height +
   planta + janela concentram quase tudo no canto direito/norte. A metade sul/esquerda
   fica muito vazia — "um set encostado na parede", nao um ambiente inteiro composto.
2. **Cortina virou protagonista errada.** Na 3/4 a cortina domina mais que sofa, quadro e
   mesa: full-height, offset 0, muito proxima do hero = parede listrada pesada que compete
   com o sofa.
3. **Tapete/mesa nao seguram o centro.** Tapete 3.0x2.0 le pequeno pra sala 5.2x4.2 com
   tudo colado no norte; mesa 1.1x0.6 timida no vazio; o miolo nao amarra o ambiente.

## TOP3_FIXES (proximo ciclo, so composicao)

1. **Rebalancear pro lado sul/esquerdo:** elemento baixo oposto ao sofa (puff / banco slim /
   poltrona leve / console baixo). Nao lotar; quebrar o vazio com intencao.
2. **Domar a cortina:** afastar/abrir paineis lateralmente, mais respiro da janela; cortina
   como MOLDURA da janela, fundo — nao personagem principal.
3. **Ancorar o miolo:** tapete ~3.4x2.3 OU mais presenca da mesa/objetos centrais; o tapete
   precisa "pegar" o conjunto sofa + mesa + luminaria/planta.

## Traducao pra regra/spec (pre-cycle 002)

- Novo furniture type candidato: `accent_seat` (puff/poltrona leve) com placement_hint
  `opposite_hero` + check de equilibrio de massa por quadrante no SpatialGate.
- CurtainSpec: `panel_split` (2 paineis abertos) + recuo lateral; gate: peso visual da
  cortina (area projetada) < peso do hero na 3/4.
- Intent da fixture: tapete 3.4x2.3 (manter overhang >= 0.4 e tuck 0.15) ou coffee_table
  maior; re-medir hero_coverage.
