# GPT Visual Verdicts (Modo B) — quarto SUITE 01

Consults feitos via ChatGPT (thread "Veredito minimalista FAIL") após o clipboard destravar.
Schema textual, GPT instruído a NÃO gerar imagem / NÃO redesenhar.

## FASE 2 — Bedroom PLACEMENT (suite01_top)

```
VERDICT: PASS
BED_PLACEMENT: PASS — cama bem ancorada na parede limpa, sem parecer solta
WARDROBE_PLACEMENT: PASS — guarda-roupa em parede correta, frente livre e fora da circulação
NIGHTSTANDS: WARN — criados corretos, mas o criado superior fica muito próximo da porta/abertura
CIRCULATION: PASS — circulação lateral e pé da cama livres
ORIENTATION: PASS — orientação da cama clara e coerente
TOP_3_ISSUES:
  1) criado superior perto demais da abertura/porta
  2) guarda-roupa poderia parecer mais planejado/embutido
  3) tapete correto, mas pode centralizar levemente mais com a cama
NEXT_ACTION: afastar/reduzir o criado superior p/ garantir respiro e folga real perto da porta
```
→ **Gate Fase 2 GREEN** (GPT não-FAIL em placement/circulation: ambos PASS).

## FASE 3 — Bedroom ANATOMY (montage cama+guarda-roupa+criado)

```
VERDICT: PASS
OBJECT_ANATOMY: PASS — cama, guarda-roupa e criado já leem como móveis compostos, não caixas únicas
MATERIAL_READABILITY: PASS — madeira escura, linho/colchão, manta e corpo têm papéis visuais distintos
PROPORTION: PASS — cama e guarda-roupa convincentes; criado aceitável, um pouco blocado
PREMIUM_REALISM: WARN — móvel real de projeto, mas não premium por falta de bordas suaves/acabamento
TOP_3_ISSUES:
  1) criado-mudo ainda parece o mais "bloco" dos três
  2) guarda-roupa bom, mas portas ainda muito planas
  3) cama convence, mas manta/travesseiros ainda geométricos demais
NEXT_ACTION: bevel/chamfer sutil nas arestas visíveis dos três móveis, começando pelo criado-mudo
```
→ **Gate Fase 3 anatomia GREEN** (GPT não-FAIL em object anatomy: PASS; móveis não são blocos).

## V-RAY render premium (Fase 8) — GPT Modo B iterado

Render V-Ray real (export .vrscene + vray.exe headless). Iterações guiadas pelo GPT:
- **Dollhouse distante**: CAMERA=FAIL ("não valoriza móveis").
- **Câmera interior (zoom sala)**: melhorou; LIGHTING=FAIL (janela estourada).
- **Exposição balanceada**: contraste recuperado.
- **TEXTURAS procedurais (madeira grão + tecido trama)**: **MATERIALS=PASS** — *"a madeira com grão
  e o tecido com trama já dão leitura muito melhor de material real; deixou de parecer plástico liso."*
- **Lighting final (céu 0.3 + ISO100/f7/1-160)**: **GPT VERDICT=PASS** (planta_74_vray_sala_final.png):
  ```
  VERDICT: PASS
  PREMIUM_REALISM: WARN — melhorou de forma clara vs versão anterior; sala ganhou contraste e leitura,
    mas ainda não é "premium de revista"
  MATERIALS: PASS — madeira e tecido leem melhor porque a luz não está mais lavando tudo
  LIGHTING: PASS — a janela segurou bem melhor e recuperou detalhe/contraste interno vs antes
    (resta uma área quente no piso junto à abertura)
  CAMERA: WARN — continua alta e técnica, mais "overview" do que interior premium
  FURNITURE_DETAIL: PASS — sofá, mesa e tapete mais legíveis agora que a exposição está controlada
  TOP_3_ISSUES: 1) câmera ainda alta demais 2) highlight forte no piso junto à janela
    3) materiais melhoraram, mas a vista ainda não valoriza textura fina
  NEXT_ACTION: baixar a câmera (eye-level interior)
  ```

Estado: **VERDICT PASS** (milestone premium da sala atingido via V-Ray). LIGHTING resolvido FAIL→PASS
(era o #1 recorrente). MATERIALS + FURNITURE_DETAIL + LIGHTING todos PASS. Único WARN acionável:
CAMERA (baixar p/ eye-level — esbarra na oclusão L-shape; tentar 1x). Render: planta_74_vray_sala_final.png.

### Câmera EYE-LEVEL + LUZ INTERNA (continuação)
- **Eye-level** (eye z 150→62, dentro da sala, costas p/ parede sul): **GPT CAMERA=PASS** —
  *"eye-level ficou melhor e mais premium que overview; vende o sofá como ambiente real, não planta técnica"*.
  BEST_SHOT=eyelevel. Novo achado: paredes laterais escuras (sala fechada, só janela ilumina).
- **Luz interna quente** (LightSphere fill procedural injetada no .vrscene, intensity 820, warm, invisible):
  **GPT VERDICT=PASS / LIGHTING=PASS** (planta_74_vray_sala_eyefill3.png) —
  *"resolveu: sofá virou herói, paredes ganharam preenchimento e a janela continua controlada"*.
  MATERIALS+FURNITURE_DETAIL PASS. Remanescente: PREMIUM_REALISM WARN + CAMERA WARN =
  **enquadramento** (faixa cinza inferior + parede lateral escura; sala deve ocupar o quadro inteiro).
- Pipeline: `tweak_vrscene.add_fill_light` (LightSphere warm) + `render_room.ps1`/`tune_render.ps1` (scratch).
  GOTCHA: 2ª fill perto da câmera (<55in) vira orb escuro visível — manter fills longe da câmera.

## Refinamentos WARN (não-bloqueantes, backlog)

- **Placement**: afastar o criado superior da porta (NIGHTSTANDS WARN).
- **Premium**: bevel/chamfer sutil nas arestas (criado > portas do guarda-roupa > manta/travesseiros).
  Casa com o WARN do sofá-braço (silhueta externa) — bevel/fillet de acabamento é a etapa premium comum.

### GPT_REVIEW [2026-06-08T01:25:25] id=sala_framing_v5 → GATE **WARN**
- artifact: `planta_74_vray_sala_eyefill5.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: ajustar o crop/framebuffer da camera para remover a faixa cinza inferior sem aproximar mais, preservando sofa + mesa inteiros no quadro.

### GPT_REVIEW [2026-06-08T01:28:50] id=sala_framing_crop → GATE **PASS**
- artifact: `planta_74_vray_sala_eyefill_crop.png`
- VERDICT: **PASS** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:PASS · FURNITURE_DETAIL:PASS
- NEXT_ACTION: aplicar mais suavidade visual no sofa, com tecido/bump mais evidente e bordas/almofadas menos rigidas.

### GPT_REVIEW [2026-06-08T01:37:37] id=quarto_suite01_v1 → GATE **FAIL**
- artifact: `planta_74_vray_quarto.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:FAIL · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: reduzir a intensidade/exposure da luz interna quente para recuperar detalhe da cama e da janela antes de mexer em camera ou materiais.

### GPT_REVIEW [2026-06-08T01:41:59] id=quarto_suite01_v2 → GATE **WARN**
- artifact: `planta_74_vray_quarto.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:WARN · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: transformar a luz interna em fill indireto/difuso, reduzindo o hotspot direto na cama sem escurecer o quarto inteiro.

### GPT_REVIEW [2026-06-08T01:46:25] id=quarto_suite01_v3 → GATE **FAIL**
- artifact: `planta_74_vray_quarto.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:WARN · CAMERA:FAIL · FURNITURE_DETAIL:WARN
- NEXT_ACTION: corrigir o crop/framebuffer primeiro para remover a faixa cinza inferior e enquadrar a cama inteira sem aproximar mais.

### GPT_REVIEW [2026-06-08T02:01:46] id=quarto_suite01_crop → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:WARN · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: reduzir ou afastar mais o fill quente da cama para recuperar textura da roupa de cama sem escurecer o quarto inteiro.

### GPT_REVIEW [2026-06-08T02:04:06] id=quarto_suite01_v5 → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: corrigir o crop/framebuffer para remover a faixa cinza inferior, mantendo essa iluminacao como base.

### GPT_REVIEW [2026-06-08T02:06:26] id=quarto_suite01_v6 → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: fazer crop final removendo totalmente a faixa cinza inferior sem cortar a cama.

### GPT_REVIEW [2026-06-08T10:42:11] id=quarto_suite01_polish → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: reduzir intensidade/escala da textura de linho da cama para ficar mais sutil e natural, mantendo a iluminacao atual.

### GPT_REVIEW [2026-06-08T10:45:40] id=quarto_suite01_polish2 → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: fazer o crop/frame final removendo a faixa cinza inferior e reduzindo a leitura de shell/teto aberto, mantendo materiais e iluminacao atuais.

### GPT_REVIEW [2026-06-08T10:49:00] id=quarto_suite01_final → GATE **WARN**
- artifact: `planta_74_vray_quarto_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: fazer um crop final minimo removendo totalmente a faixa cinza inferior, sem mexer mais em luz/material/camera.

### GPT_REVIEW [2026-06-08T12:50:58] id=quarto_piso_madeira → GATE **WARN**
- artifact: `planta_74_vray_quarto_floor_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: remover/cropar totalmente a faixa cinza inferior para deixar so o piso de madeira dentro do frame.

### GPT_REVIEW [2026-06-08T13:06:08] id=sala_piso_madeira → GATE **PASS**
- artifact: `planta_74_vray_sala_floor_crop.png`
- VERDICT: **PASS** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: manter o piso de madeira, mas reduzir levemente a textura do piso perto da janela.

### GPT_REVIEW [2026-06-08T13:14:15] id=suite02_premium → GATE **WARN**
- artifact: `planta_74_vray_suite02_crop.png`
- VERDICT: **WARN** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:WARN · FURNITURE_DETAIL:WARN
- NEXT_ACTION: ajustar camera/crop para remover a faixa cinza inferior e reduzir a oclusao do movel a direita, mantendo cama e janela no quadro.

### GPT_REVIEW [2026-06-08T13:54:12] id=sala_autocam_full → GATE **PASS**
- artifact: `planta_74_vray_sala_autocrop.png`
- VERDICT: **PASS** · PREMIUM_REALISM:WARN · MATERIALS:PASS · LIGHTING:PASS · CAMERA:PASS · FURNITURE_DETAIL:PASS
- NEXT_ACTION: reduzir a presenca da parede esquerda no auto-framing para concentrar mais o quadro em sofa+mesa+tapete.

### GPT_REVIEW [2026-06-08T15:55:01] id=cozinha_product → GATE **PASS**
- artifact: `?`
- VERDICT: **PASS** · PREMIUM_REALISM:WARN · MATERIALS:WARN · LIGHTING:WARN · CAMERA:WARN · FURNITURE_DETAIL:PASS
- NEXT_ACTION: adicionar/validar detalhes funcionais visiveis da cozinha — cuba+torneira, cooktop com bocas, forno com vidro/puxador e portas/gavetas nos modulos — sem mexer no layout.
