# SOFA_LEARNING_LOG

Registro de aprendizado do builder paramétrico de sofá. Cada correção vira regra de CLASSE (não exemplar). O objetivo NÃO é consertar um sofá específico, é fazer a classe inteira ficar melhor.

---

## TEMPLATE DE ENTRADA

Copie o bloco abaixo para cada nova entrada. Preencha TODOS os campos.

```
Data:
Caso:
Problema observado:
Causa provavel:
Correcao feita:
Onde a correcao entrou:
  [ ] spec
  [ ] schema
  [ ] primitive
  [ ] component
  [ ] generator
  [ ] eval gate
Impacto esperado em outros sofas:
Risco de overfit:
Proximo teste:
```

---

## REGRA

**Correcao que nao entra no learning log nao conta como aprendizado.**

Se você consertou algo e não registrou aqui, o aprendizado não existe: não é reproduzível, não generaliza, e vai voltar como bug no próximo sofá. Toda correção visual/geométrica que muda o resultado PRECISA virar uma entrada — apontando o lugar CERTO do sistema onde a regra passa a viver.

---

## PRINCIPIOS (lei da casa)

1. **NAO overfit.** A regra vive na CLASSE (spec/primitive/component/generator/gate), nunca num exemplar. Se a correção só serve pro `sofa_3seat_v1`, está errada — generalize ou rejeite.
2. **Forma antes de detalhe.** Ordem de prioridade fixa: silhueta > proporção > anatomia > maciez > composição > detalhe > material. Não se mexe em detalhe enquanto a forma a montante estiver ruim.
3. **O sofa precisa PARECER estofado.** Volume, topo coroado, bordas suaves, encosto com espessura + rake, braço com massa, base recuada, costura sutil. Caixa com cantos vivos não é sofá.
4. **Generalizacao obrigatoria.** Toda correção é testada mentalmente contra outros sofás (2 lugares, chaise, modular, poltrona). Se quebra um deles, não entrou no lugar certo.
5. **Detalhe nunca esconde forma ruim.** Piping/costura/material são a última camada. Não se usa detalhe pra disfarçar silhueta, proporção ou anatomia ruins.

---

## ERROS PROIBIDOS (lista de reprovação automática)

- `CAIXOTAO_FAIL` — sofá lê como caixote/bloco retangular sem volume estofado.
- Piping grosso / facetado / tipo mangueira / flutuante (solto no espaço, sem ancoragem).
- Encosto vertical tipo parede (sem rake, sem espessura, lê como placa).
- Assento reto tipo caixa (sem coroa, sem volume, cantos vivos).
- Braço monolítico (bloco maciço sem massa nem leitura de estofado).
- Pés colados na borda (sem recuo de base).
- Ausência de base / recuo (corpo apoiado direto no chão como tijolo).
- Detalhe antes da forma (costura/piping/material aplicados com a silhueta ainda ruim).
- Hardcode de um único sofá (constantes que só servem ao exemplar atual).
- Autoaprovacao falsa — escrever "GPT PASS" no render sem veredito real do oráculo.

---

## ENTRADAS

### Entrada 1 — Piping do encosto flutuando

```
Data: 2026-06-09
Caso: sofa_3seat_v1 (ciclo blockout) — retrospectiva
Problema observado: piping do encosto FLUTUA atras do sofa; a vista side mostra uma barra solta no espaco, desconectada da almofada.
Causa provavel: o piping era criado como grupo IRMAO da almofada do encosto, nao como FILHO. Por nao estar no mesmo frame transformado, nao acompanha a rotacao do rake do encosto e fica para tras.
Correcao feita: piping deve ser FILHO do grupo da almofada (herdar a transformacao do frame ja rotacionado) OU o seam_system desenhar a costura no frame JA transformado da peca. Costura nunca e geometria independente no mundo — e sempre relativa a peca que ela contorna.
Onde a correcao entrou:
  [ ] spec
  [ ] schema
  [x] primitive   (back_cushion_primitive passa a incluir a propria costura)
  [x] component   (build_seam_system desenha no frame transformado)
  [ ] generator
  [ ] eval gate
Impacto esperado em outros sofas: qualquer costura (assento, braco, base) passa a acompanhar a transformacao da peca-mae; resolve flutuacao em chaise/modular onde pecas tem angulos proprios.
Risco de overfit: baixo — a regra "costura e filha/relativa da peca" e estrutural, vale para toda peca de todo sofa.
Proximo teste: render side de um sofa com rake forte (10-12) e confirmar que o piping segue o encosto sem barra solta.
```

### Entrada 2 — Almofadas de assento pequenas e afundadas num poço

```
Data: 2026-06-09
Caso: sofa_3seat_v1 (ciclo blockout) — retrospectiva
Problema observado: as almofadas de assento parecem pequenas e AFUNDADAS, lendo como tijolinho no fundo de um poco.
Causa provavel: o braco (altura ~0.62) fica ~0.19m acima do topo do assento (~0.43), criando um degrau grande; com a parede do braco tao alta em volta, a almofada visualmente "afunda".
Correcao feita: introduzir regra de PROPORCAO braco-vs-assento (limitar o degrau braco-acima-do-assento) + tornar a almofada do assento mais cheia/coroada (mais volume, topo abaulado) para subir e preencher o vao.
Onde a correcao entrou:
  [x] spec        (regra de proporcao braco x assento)
  [ ] schema
  [x] primitive   (seat_cushion_primitive ganha volume/coroa)
  [x] component   (build_seat_module ajusta encaixe assento x braco)
  [ ] generator
  [ ] eval gate
Impacto esperado em outros sofas: a regra de proporcao normaliza a relacao braco/assento em todos os modelos; evita "poco" em sofas de braco alto e mantem o assento legivel.
Risco de overfit: medio — usar RAZAO/limite relativo (nao numeros absolutos 0.62/0.43); numeros fixos so serviriam a este sofa.
Proximo teste: variar altura de braco em 2-3 sofas e confirmar que a almofada nunca afunda alem do limite da regra.
```

### Entrada 3 — Encosto fino lê como placa/tábua

```
Data: 2026-06-09
Caso: sofa_3seat_v1 (ciclo blockout) — retrospectiva
Problema observado: o encosto, fino, le como uma PLACA / tabua chapada, nao como almofada estofada.
Causa provavel: espessura de 0.20 combinada com so um rounded box, sem volume interno nem coroa convincente — fica chato e duro.
Correcao feita: back_cushion_primitive passa a ter espessura MINIMA garantida + topo COROADO (abaulado) + volume; e a spec fixa rake na faixa 6-12 graus para o encosto nunca cair vertical tipo parede.
Onde a correcao entrou:
  [x] spec        (espessura minima + faixa de rake 6-12)
  [ ] schema
  [x] primitive   (back_cushion_primitive: espessura min + topo coroado + volume)
  [ ] component
  [ ] generator
  [ ] eval gate
Impacto esperado em outros sofas: todos os encostos ganham espessura+coroa+rake garantidos; elimina o "encosto-parede" e o "encosto-placa" da classe inteira.
Risco de overfit: baixo — espessura minima e faixa de rake sao limites de classe, parametrizados, nao um valor unico.
Proximo teste: gerar encosto no limite inferior de espessura e confirmar que ainda le como estofado (nao placa) em vista iso e side.
```

### Entrada 4 — Câmera FRONT com zoom demais (corta o sofá)

```
Data: 2026-06-09
Caso: sofa_3seat_v1 (ciclo blockout) — retrospectiva
Problema observado: a camera FRONT da zoom demais e nao mostra o sofa inteiro (corta pes/bracos).
Causa provavel: framing — a camera nao enquadra o bounding box completo do modelo, fica apertada.
Correcao feita: regra de camera no generator — enquadrar o sofa INTEIRO com margem, nunca cortar pes nem bracos; framing derivado do bounding box + folga, valido para todas as vistas.
Onde a correcao entrou:
  [ ] spec
  [ ] schema
  [ ] primitive
  [ ] component
  [x] generator   (cameras: framing pelo bounding box + margem)
  [ ] eval gate
Impacto esperado em outros sofas: todas as vistas (front/side/iso) de qualquer sofa passam a mostrar o objeto completo; comparacoes visuais ficam justas (nao se confunde corte de camera com defeito de forma).
Risco de overfit: muito baixo — framing por bounding box e generico por construcao.
Proximo teste: renderizar um sofa modular largo e confirmar que nenhuma vista corta a peca.
```

### Entrada 5 — Piping facetado ("miçanga") e exagerado

```
Data: 2026-06-09
Caso: sofa_3seat_v1 (ciclo blockout) — retrospectiva
Problema observado: o piping aparece FACETADO (tipo "micanga", 8 lados) e exagerado, roubando a cena e chamando mais atencao que a forma do sofa.
Causa provavel: detalhe forte aplicado ANTES de a forma amadurecer — viola "forma antes de detalhe".
Correcao feita: piping sutil/opcional — mais segmentos no tubo (suave, nao facetado) OU desligado por padrao; o detalhe fica SUBORDINADO a forma. Adicionar gate DETAIL_RESTRAINT_PASS que reprova quando o detalhe domina a silhueta.
Onde a correcao entrou:
  [ ] spec
  [ ] schema
  [ ] primitive
  [x] component   (build_seam_system: piping sutil/opcional, mais segmentos)
  [x] eval gate   (DETAIL_RESTRAINT_PASS: detalhe nao pode dominar a forma)
  [ ] generator
Impacto esperado em outros sofas: nenhum sofa promove detalhe acima da forma; piping default discreto evita "micanga" na classe toda; o gate barra qualquer regressao de detalhe-prematuro.
Risco de overfit: baixo — a regra e de hierarquia (forma > detalhe), nao um valor de segmento especifico.
Proximo teste: rodar DETAIL_RESTRAINT_PASS num sofa de forma ainda crua e confirmar que ele reprova o detalhe ate a forma melhorar.
```

### Entrada 6 — Crown de 2 tiers lê como TAMPA escalonada, não cúpula macia

```
Data: 2026-06-10
Caso: rodada v2 (sistema da classe) — primitives board + 5 sofas (3 archetypes + 2 eval)
Problema observado: com o sistema montado, as almofadas (seat/back) AINDA leem como rounded
  box com topo em DEGRAU. O crowned_box usa 2 tiers de inset+raise; mesmo com soften, le como
  TAMPA escalonada (lid), nao puff abaulado. SOFTNESS_PASS nao passou (criterio da Fase 11).
Causa provavel: o crown por inset-degrau cria OMBROS retos visiveis (cada tier e um patamar).
  Soften suaviza as arestas mas a SILHUETA do degrau permanece. Falta transicao continua (dome):
  a borda do topo precisa "rolar" pra dentro, nao subir em patamar.
Correcao feita (proximo ciclo, alvo na PRIMITIVA): trocar o crown escalonado por (a) roll
  generoso da BORDA do topo contornando todo o perimetro + (b) UM dome suave (centro levemente
  mais alto) com mais segmentos, OU (c) perfil de almofada via followme de um arco no topo.
  Tudo em crowned_box / seat_cushion_primitive / back_cushion_primitive -> todos herdam.
Onde a correcao entrou:
  [ ] spec
  [ ] schema
  [x] primitive   (crowned_box/seat_cushion/back_cushion: dome continuo, nao degrau)
  [ ] component
  [ ] generator
  [x] eval gate   (SOFTNESS_PASS so passa com almofada lendo como dome continuo, sem patamar)
Impacto esperado em outros sofas: TODOS (almofada e a peca mais repetida); mata o tell de
  "rounded box" da classe inteira de uma vez.
Risco de overfit: baixo — correcao na primitiva de almofada, compartilhada por todos.
Proximo teste: re-renderizar o primitives board e confirmar seat/back como puff (sem degrau no
  topo); so entao re-montar a suite.
```

---

## RESULTADO DA RODADA v2 (2026-06-10)

**Passou (objetivo):** PIPELINE · SCHEMA · COMPONENTS · ARCHETYPE · GENERALIZATION · BLOCKOUT ·
PROPORTION · DETAIL_RESTRAINT. 5 configs distintos gerados sem crash (3 archetypes + 2 casos
novos) → generalizacao no nivel de pipeline confirmada (nao e overfit de 1 sofa).

**Fixes v1 que LANDARAM no sistema (anti-overfit):** seam filho+sutil (nao flutua) · back
grosso+coroado (nao placa) · proporcao braco x assento (nao afunda) · camera deterministica
(nao corta/over-zoom).

**Residual #1 (bloqueia ASSET_PASS / SOFTNESS_PASS):** topo das almofadas ainda em degrau →
Entrada 6. Proximo ciclo ataca a primitiva de almofada (dome continuo). **Veredito visual final
(ASSET/SOFTNESS/CAIXOTAO) é do Felipe/GPT — nao autoaprovado aqui.**
