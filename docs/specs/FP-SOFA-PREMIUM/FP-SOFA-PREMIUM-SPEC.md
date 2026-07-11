# FP-SOFA-PREMIUM — Spec de geometria, harness e revisão visual

## 0. Missão

Eliminar definitivamente o aspecto **“Minecraft / caixas empilhadas”** do sofá procedural e estabelecer uma base reutilizável para móveis premium no projeto `sketchup-mcp`.

O objetivo não é apenas “deixar o sofá mais bonito”. O objetivo é criar um **sistema verificável** em que:

1. a geometria seja construída a partir de uma tipologia real de sofá;
2. o harness prove proporção, silhueta, ergonomia e acabamento;
3. a revisão visual detecte blockiness antes de o objeto entrar na planta;
4. o agente consulte o GPT **antes e depois de cada alteração visual ou geométrica**, sem exceção;
5. nenhuma alteração seja mantida sem verdict explícito `IMPROVED`;
6. nenhuma melhoria seja considerada concluída sem `.skp`, renders e evidências.

---

## 1. Regra principal

> **Detalhe não significa empilhar blocos.**

Um sofá premium precisa ser lido como um volume estofado contínuo. Almofadas, braços, base e encosto podem ser componentes distintos, mas devem formar uma silhueta coerente, macia e deliberada.

É proibido resolver “realismo” adicionando placas retangulares sobre outras placas retangulares.

---

## 2. Escopo desta entrega

### Dentro do escopo

- Novo arquétipo de sofá premium para a sala.
- Harness canônico em cena vazia.
- Testes determinísticos de proporção e montagem.
- Contact sheet visual obrigatória.
- Contrato de consulta ao GPT.
- Gate de “Minecraft/blockiness”.
- Integração do sofá aprovado na sala existente sem alterar a geometria arquitetônica.
- Commit do `.skp` canônico e do `.skp` da planta mobiliada.

### Fora do escopo

- Redesenhar paredes, portas ou janelas.
- Mudar o layout da sala antes de aprovar o novo sofá.
- Corrigir todos os móveis do apartamento no mesmo ciclo.
- Resolver iluminação V-Ray final antes de aprovar a geometria do sofá.

---

## 3. Fonte de verdade

### Arquitetura

A geometria da sala existente é congelada. Nenhuma parede, abertura, peitoril, porta ou janela pode ser inventada, movida ou redimensionada.

### Layout

O layout atual é referência inicial:

- sofá na parede principal;
- poltrona em diálogo;
- mesa central;
- tapete ancorando o conjunto;
- luminária de piso;
- quadro;
- sheer no vão.

O sofá pode ter largura e profundidade ajustadas dentro dos limites de circulação, mas sua parede hospedeira e orientação permanecem.

### Estilo

`BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE`

- base preto/grafite quente;
- tecido escuro, mas legível;
- madeira âmbar como pontuação;
- bronze/champagne em apenas um ponto;
- luz quente 2700 K;
- dramático sem virar caverna;
- “casa de gente rica, não oficina”.

---

## 4. Arquétipo obrigatório do sofá

Nome sugerido:

`PREMIUM_LOW_PROFILE_LOUNGE`

### Características

- perfil baixo;
- assento profundo;
- braços baixos e mais finos que os atuais;
- base visualmente recuada;
- almofadas de assento largas, não empilhadas;
- encosto macio, com leve inclinação ou volume posterior;
- cantos suavizados;
- silhueta horizontal limpa;
- costuras discretas;
- pés ocultos ou plinto recuado.

### Proibições

- braço com aparência de bloco maciço sem raio;
- três ou mais placas horizontais empilhadas no encosto;
- almofadas com espessura idêntica a lajes;
- base com a mesma projeção do assento;
- quinas 90° sem bevel/roundover visível;
- módulos repetidos mecanicamente sem variação de função;
- peças “flutuando” ou apenas encostadas sem leitura estrutural;
- sofá com leitura de trono, banco de concreto ou veículo militar.

---

## 5. Parâmetros geométricos

Os valores abaixo são faixas, não números absolutos. O gerador deve validar a coerência entre eles.

```yaml
sofa:
  seats: 3
  overall_width_mm: 2200..2600
  overall_depth_mm: 900..1100
  overall_height_mm: 720..860
  seat_height_mm: 400..460
  seat_depth_mm: 560..700
  arm_width_mm: 100..190
  arm_height_above_seat_mm: 120..240
  base_recess_mm: 50..120
  plinth_height_mm: 30..90
  seat_cushion_thickness_mm: 110..180
  back_cushion_thickness_mm: 120..220
  back_angle_deg: 4..12
  edge_radius_mm: 12..40
  cushion_gap_mm: 8..25
```

### Regras relacionais

- `arm_width / overall_width <= 0.09` por braço.
- `seat_depth > seat_height`.
- base deve ser recuada em relação ao assento.
- braço nunca pode ultrapassar visualmente o encosto em massa.
- almofadas de assento devem dominar a leitura horizontal.
- encosto deve parecer apoiado/estofado, não uma parede atrás do sofá.
- o raio visual das bordas precisa aparecer no render clay.

---

## 6. Regras de construção

### 6.1 Volume principal

Construir primeiro a massa contínua do sofá:

- base;
- assento;
- braços;
- encosto estrutural.

Antes de adicionar almofadas, a silhueta do sofá já deve parecer plausível.

### 6.2 Bevel e suavização

Todo volume estofado precisa de bevel ou arredondamento real, não apenas `soften edges` cosmético.

Requisito mínimo:

- bevel visível em braços;
- bevel visível na frente do assento;
- bevel visível nas almofadas;
- quinas externas sem aspecto cortante.

### 6.3 Almofadas

Cada almofada deve ter:

- frente levemente abaulada ou arredondada;
- traseira coerente com apoio;
- espessura variável;
- pequeno afastamento entre módulos;
- contato plausível com assento/encosto.

Não usar caixas perfeitas como almofadas finais.

### 6.4 Base

A base não pode parecer uma terceira laje.

Usar uma destas soluções:

- plinto recuado escuro;
- pés curtos recuados;
- shadow gap contínuo.

### 6.5 Costura

A costura é detalhe secundário. Não deve ser simulada com blocos adicionais.

Pode ser feita por:

- linha/edge discreta;
- sulco raso;
- textura normal/bump no render.

---

## 7. Materiais mínimos para prova

Criar dois modos de render:

### A. Clay review

- sofá cinza médio;
- fundo claro;
- iluminação neutra;
- sem materiais escuros escondendo geometria.

Objetivo: provar silhueta, bordas e proporção.

### B. Style review

- tecido grafite quente;
- roughness suficiente para mostrar volume;
- base preta;
- costura discreta;
- sem preto puro `#000000`;
- evitar material tão escuro que apague as quinas.

---

## 8. Harness canônico

Criar um harness isolado chamado:

`sofa_premium_harness`

### Cena canônica

- piso plano neutro;
- parede de fundo neutra;
- escala humana opcional em camada separada;
- câmera fixa;
- luz fixa;
- sem decoração;
- sem outros móveis.

### Câmeras obrigatórias

1. `front_3q_left`
2. `front_3q_right`
3. `side_profile`
4. `top`
5. `front_orthographic`
6. `detail_arm_cushion`

### Saídas obrigatórias

```text
artifacts/sofa_premium/<run_id>/
  sofa_premium_harness.skp
  sofa_metrics.json
  sofa_gate_results.json
  sofa_contact_sheet.png
  front_3q_left.png
  front_3q_right.png
  side_profile.png
  top.png
  front_orthographic.png
  detail_arm_cushion.png
  review_request.json
  review_response.json
```

---

## 9. Gates determinísticos

### G1 — Bounding box

Verifica largura, profundidade e altura dentro da faixa definida.

### G2 — Ergonomia

Verifica:

- altura do assento;
- profundidade útil;
- altura do braço;
- inclinação do encosto;
- largura útil por pessoa.

### G3 — Base recess

A base precisa ser recuada visualmente.

Falha se a projeção da base for igual ou maior que a do assento.

### G4 — Arm mass ratio

Falha se os braços dominarem a largura total.

### G5 — Cushion hierarchy

Falha se:

- almofadas de assento forem finas como placas;
- encosto tiver mais camadas horizontais que o necessário;
- houver peças decorativas repetidas sem função.

### G6 — Edge treatment

Falha se mais de 20% das quinas externas visíveis permanecerem com aspecto 90° cortante.

### G7 — Floating/intersection

Falha se houver:

- peças flutuando;
- almofadas atravessando braços;
- faces coplanares z-fighting;
- interseções incoerentes.

### G8 — Scene cleanliness

- grupo único do sofá;
- componentes nomeados;
- materiais nomeados;
- sem faces invertidas;
- sem geometria solta fora do grupo;
- origem/pivô coerente.

### G9 — Layout fit

Ao inserir na sala:

- manter folga de circulação;
- não atravessar tapete, parede ou mesa;
- não bloquear vão;
- manter distância coerente da mesa de centro.

### G10 — No-SKP-no-progress

Sem os dois `.skp` abaixo, o ciclo é automaticamente FAIL:

- `sofa_premium_harness.skp`
- `planta_74_furnished_with_sofa_premium.skp`

---

## 10. Gate visual “Minecraft”

O gate visual deve responder às perguntas abaixo em escala de 0 a 5:

- `blockiness_score`: 0 = orgânico/premium; 5 = Minecraft.
- `silhouette_coherence`: 0 = incoerente; 5 = excelente.
- `upholstery_readability`: 0 = concreto/caixa; 5 = estofado convincente.
- `arm_quality`: 0 = bloco grosseiro; 5 = braço premium.
- `cushion_quality`: 0 = placas empilhadas; 5 = almofadas plausíveis.
- `base_quality`: 0 = laje; 5 = base recuada elegante.

### Critério de aprovação

```yaml
blockiness_score: <= 1
silhouette_coherence: >= 4
upholstery_readability: >= 4
arm_quality: >= 4
cushion_quality: >= 4
base_quality: >= 4
```

Qualquer score fora do limite impede integração definitiva na planta.

---

## 11. Contrato de consulta ao GPT

A consulta ao GPT não é opcional nem condicionada a dúvida. Ela é um **gate obrigatório por alteração**.

O agente deve consultar o GPT:

1. **antes de executar cada alteração**, para validar a hipótese e limitar o escopo;
2. **depois de executar cada alteração**, para decidir se ela foi `IMPROVED`, `SAME` ou `WORSE`;
3. novamente antes de iniciar qualquer alteração seguinte.

Nenhuma alteração visual pode ser autoaprovada pelo agente que a implementou.

### 11.1 O que conta como alteração

Qualquer mudança que possa afetar a imagem ou a leitura do objeto conta como uma alteração independente, incluindo:

- largura, altura, profundidade, raio ou inclinação;
- topologia, bevel, roundover ou subdivisão;
- posição, rotação ou escala de uma peça;
- criação, remoção ou substituição de componente;
- material, roughness, cor, bump ou textura;
- câmera, exposição ou iluminação usada para julgar a alteração;
- posição do sofá, tapete, mesa ou poltrona na integração da sala.

Só ficam dispensadas mudanças puramente mecânicas sem efeito visual, como renomear arquivo, corrigir log ou ajustar teste que não altera a cena.

### 11.2 Regra de atomicidade

Cada ciclo deve conter **uma única hipótese visual**.

Exemplos válidos:

- reduzir a largura dos braços de 220 mm para 150 mm;
- substituir três placas de encosto por duas almofadas contínuas;
- recuar o plinto em 80 mm;
- aumentar o bevel frontal do assento de 8 mm para 24 mm.

Exemplo inválido:

- afinar braços, arredondar almofadas, trocar base e mudar material na mesma alteração.

Batch de mudanças é FAIL automático porque impede saber o que melhorou ou piorou o sofá.

### 11.3 Gate obrigatório antes da alteração

Antes de editar a geometria, o agente deve gerar `change_request.json`, anexar a evidência atual e perguntar ao GPT:

> Estou prestes a executar UMA alteração no sofá. Avalie a evidência atual e a hipótese abaixo. A mudança proposta ataca o defeito dominante ou estou mexendo no lugar errado? Aprove, revise ou rejeite. Preserve explicitamente o que não deve ser alterado. Responda estritamente no contrato `ALTERATION_REVIEW_CONTRACT.json`.

A execução só pode continuar quando o verdict for `APPROVE_CHANGE`.

- `REVISE_CHANGE`: reformular a hipótese e consultar novamente;
- `REJECT_CHANGE`: abandonar a hipótese;
- ausência de resposta: status `waiting_gpt_answer`, sem alterar a cena.

### 11.4 Gate obrigatório depois da alteração

Depois de executar a única mudança aprovada, o agente deve:

- renderizar exatamente as mesmas câmeras e condições;
- gerar comparação before/after;
- anexar métricas antes/depois;
- gerar `change_result_request.json`;
- consultar novamente o GPT.

Pergunta obrigatória:

> Esta é a comparação antes/depois da alteração aprovada. Julgue somente o efeito desta mudança. O sofá ficou claramente menos Minecraft e mais premium? Responda `IMPROVED`, `SAME` ou `WORSE`, indique a evidência visual e dê apenas uma próxima instrução.

Regra de decisão:

- `IMPROVED`: manter a alteração e registrar o novo baseline;
- `SAME`: reverter a alteração;
- `WORSE`: reverter imediatamente a alteração;
- `WARN` ou resposta ambígua: não manter; pedir esclarecimento.

### 11.5 Pacote obrigatório por alteração

```text
artifacts/sofa_premium/<run_id>/changes/<alteration_id>/
  before.png
  after.png
  before_after.png
  change_request.json
  change_pre_response.json
  change_result_request.json
  change_post_response.json
  metrics_before.json
  metrics_after.json
  diff_summary.md
```

O `alteration_id` deve ser estável e sequencial, por exemplo:

`SOFA-CHG-001-arm-width`

### 11.6 Pacote visual mínimo enviado ao GPT

- vista 3/4 fixa antes/depois;
- perfil fixo antes/depois quando a silhueta for afetada;
- close da área alterada;
- contact sheet atual;
- métricas JSON;
- descrição de uma única hipótese;
- lista `do_not_change`;
- hash ou identificador da versão anterior.

### 11.7 Revisão global

Além do gate por alteração, ao final de cada versão completa o agente deve usar `VISUAL_REVIEW_CONTRACT.json` para revisar o sofá como um todo.

Pergunta padrão da revisão global:

> Você é um crítico exigente de mobiliário premium e modelagem procedural. Avalie este sofá sem aliviar. Ele ainda parece Minecraft, caixas empilhadas ou placeholder de SketchUp? Identifique o principal defeito de silhueta, o principal defeito de estofamento e a única mudança geométrica de maior impacto. Responda no JSON do contrato, sem elogios genéricos.

---

## 12. Loop obrigatório de melhoria

```text
1. Gerar sofá em cena canônica.
2. Rodar gates determinísticos.
3. Renderizar clay contact sheet.
4. Rodar gate visual local.
5. Escolher UMA hipótese de melhoria.
6. Criar `change_request.json` e consultar o GPT ANTES da alteração.
7. Esperar `APPROVE_CHANGE`; sem aprovação, não editar.
8. Executar somente a alteração aprovada.
9. Gerar nova versão com novo run_id usando as mesmas câmeras.
10. Criar comparação before/after e consultar o GPT DEPOIS da alteração.
11. Registrar `IMPROVED`, `SAME` ou `WORSE`.
12. Manter apenas `IMPROVED`; reverter `SAME` e `WORSE`.
13. Não iniciar outra alteração antes de fechar o ciclo anterior.
14. Só integrar na sala após PASS isolado.
15. Na integração, cada ajuste de posição/material/luz também passa pelo mesmo gate antes/depois.
16. Revalidar escala, circulação e coerência com poltrona/mesa/tapete.
17. Salvar e commitar `.skp` + evidências + histórico completo de consultas.
```

É proibido fazer várias mudanças grandes de uma vez sem saber qual delas melhorou ou piorou o objeto.

---

## 13. Casos de teste

### T1 — Sofá isolado, 3 lugares

Objetivo: aprovar o arquétipo base.

### T2 — Sofá escuro em fundo neutro

Objetivo: garantir que o material não esconda a geometria.

### T3 — Sofá na sala atual

Objetivo: validar escala e diálogo com a poltrona.

### T4 — Distância da mesa

Validar faixa de 350–500 mm entre assento e mesa, conforme circulação real.

### T5 — Tapete

Validar que ao menos os pés frontais/área frontal do sofá estejam visualmente ancorados.

### T6 — Render eye-level

O sofá deve ser legível sem depender da vista superior.

### T7 — Silhueta em preto

Gerar uma máscara/silhueta. Se a leitura for um retângulo pesado com blocos sobrepostos, FAIL.

---

## 14. Critérios de aceitação final

A tarefa só está concluída quando:

- todos os gates determinísticos passam;
- `blockiness_score <= 1`;
- a revisão GPT não aponta “caixas empilhadas” como defeito dominante;
- a versão nova é julgada `IMPROVED` contra a anterior;
- o sofá funciona no clay e no material final;
- a sala mantém circulação e layout;
- há contact sheet antes/depois;
- há `.skp` canônico;
- há `.skp` da planta;
- os artefatos estão salvos em pasta versionada;
- o commit contém código, evidências e `.skp` relevante.

---

## 15. Definition of Done

```yaml
done:
  harness_skp_committed: true
  apartment_skp_committed: true
  deterministic_gates_pass: true
  visual_blockiness_pass: true
  gpt_review_recorded: true
  every_change_preapproved_by_gpt: true
  every_change_postreviewed_by_gpt: true
  no_unreviewed_visual_changes: true
  only_improved_changes_kept: true
  before_after_contact_sheet: true
  room_fit_pass: true
  no_architecture_changes: true
```

---

## 16. Próxima expansão após o sofá

Depois de aprovar o sofá, repetir o mesmo contrato para:

1. poltrona;
2. mesa de centro;
3. cadeira de jantar;
4. cama;
5. criado-mudo;
6. luminária;
7. vegetação.

Cada classe deve ter harness próprio. Nenhum móvel pode entrar na planta apenas porque “preenche o espaço”.
