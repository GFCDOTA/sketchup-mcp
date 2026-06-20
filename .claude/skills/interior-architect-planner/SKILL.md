---
name: interior-architect-planner
description: >-
  Planejar mobiliário/interiores como ARQUITETO + MARCENEIRO (não "colocar objetos no espaço"):
  função do ambiente, móvel-herói, paredes boas/ruins, circulação, proporção, marcenaria útil,
  hierarquia visual, e só então câmera/render. Use SEMPRE que for mobiliar/renderizar um cômodo
  da planta (quarto/sala/cozinha/banho/área), gerar .skp de móvel, decidir layout, ou revisar
  render/câmera. Antes de qualquer .skp: produzir DesignIntentSpec → geometry_sanity (determinístico)
  → auto-camera → veredito visual GPT. Frase-guia: "planejar como arquiteto/marceneiro, validar como
  engenheiro, só depois renderizar como artista."
---

# Interior Architect + Carpentry Planner + Auto Camera Review

> Regra central: **imagem bonita não basta**. O layout precisa FUNCIONAR em planta e em uso real.
> Não decorar por sorte — planejar, validar, depois renderizar.

## 1. Mental model (ordem fixa, ANTES de .skp ou render)

1. **Função** do ambiente. 2. **Móvel-herói**. 3. **Paredes boas × ruins**. 4. **Circulação**.
5. **Proporção** dos móveis. 6. **Armazenamento / marcenaria**. 7. **Hierarquia visual**.
8. **Câmera / render**. 9. **Gates determinísticos**. 10. **Visual review final (GPT)**.

## 2. Regras gerais de interiores

- NÃO bloquear porta/janela/abertura. NÃO atravessar parede. NÃO pôr móvel fora do cômodo.
- NÃO pôr móvel alto na frente da janela (salvo decisão explícita).
- NÃO desperdiçar a MELHOR parede limpa com móvel pequeno (ela é p/ cama/rack/armário/bancada).
- NÃO criar móvel solto sem função. NÃO priorizar decoração antes do programa mínimo.
- SEMPRE declarar trade-offs e SEMPRE declarar quando o cômodo não comporta o programa completo.
- Cômodo pequeno → solução COMPACTA. Cômodo com espaço → solução PREMIUM.
- Marcenaria resolve armazenamento / aproveitamento vertical / canto / nicho / integração — nunca enfeite gratuito.

## 3. Regras por ambiente (prioridade → regras)

**QUARTO** — cama › circulação › guarda-roupa › criados › decoração.
Cabeceira em parede limpa; cama não bloqueia porta/janela; guarda-roupa em parede que permite abrir;
criado só com clearance; quarto pequeno = cama+armário+circulação vencem decoração; tamanho da cama
pelo espaço REAL (não estética); cama encostada numa lateral = declarar trade-off; dresser não domina o 1º plano.

**SALA** — sofá › TV/rack › circulação › mesa de centro/tapete › poltrona/decoração.
Sofá orientado p/ TV; distância sofá-TV plausível; mesa de centro só com circulação; tapete ancora
sofá/mesa (não solto); poltrona só se não virar obstáculo; aproveitar a parede principal; sem showroom aleatório.

**COZINHA** — pia › fogão/cooktop › geladeira › bancada › armazenamento.
Fluxo pia-fogão-geladeira plausível (triângulo); bancada linear/L/U conforme geometria; NÃO inventar
ilha onde não cabe; aproveitar cantos com marcenaria; armário superior/inferior quando faz sentido; não bloquear passagem.

**BANHO/LAVABO** — vaso › pia › box (se aplicável) › circulação › armazenamento mínimo.
Sem marcenaria exagerada em lavabo pequeno; porta abre/funciona; peças proporcionais; nada bloqueia uso.

**ÁREA DE SERVIÇO** — máquina › tanque › acesso técnico › armazenamento vertical.
Aproveitar verticalidade; não bloquear acesso; separar fluxo técnico do da cozinha quando possível.

## 4. DesignIntentSpec (OBRIGATÓRIO antes de placement/render)

Um por cômodo, em `artifacts/planta_74/design_intent/<room_id>.json`. Schema:
`room_id` · `room_type` · `dimensions_estimate` · `fixed_constraints{doors,windows,openings,clean_walls,no_place_zones}`
· `program_priority{required,desired,decorative}` · `layout_strategy` · `furniture_plan[{item,function,
candidate_wall_or_zone,approximate_size,reason,risk}]` · `circulation_rules` · `carpentry_opportunities`
· `must_not_violate` · `tradeoffs` · `confidence` · `needs_human_review`.

Regra: o spec pode ser ajudado por LLM/local-LLM/fast-tier, MAS **colisão, circulação e sanidade
geométrica são validados DETERMINISTICAMENTE** (geometry_sanity) sempre que possível — não confiar só no LLM.

## 5. Candidate layout workflow (quando houver ambiguidade)

Gerar 2-3 candidatos ANTES de construir: **A** mais funcional · **B** mais premium/visual · **C** mais compacto (se preciso).
Ranquear por: circulação · aproveitamento de parede limpa · armazenamento · não-bloqueio de porta/janela ·
ergonomia · proporção visual · simplicidade construtiva · compatibilidade com câmera/render.
Escolher o melhor e **registrar por que os outros foram descartados**.

## 6. geometry_sanity (gate determinístico BARATO — obrigatório antes de promover)

`tools/geometry_sanity.py` (consensus + móveis + polígono do cômodo + aberturas). Bloqueia:
underground · degenerada · off-axis · bbox absurda · móvel fora do cômodo · móvel atravessando parede ·
móvel bloqueando porta · móvel sobre janela · abertura fantasma · parede do baseline sumida ·
diferença absurda consensus×.skp×render. (Shell: complementa `tools/run_deterministic_gates.py`.)
Resultado: **PASS** (sem regressão objetiva) · **WARN** (segue com motivo explícito) · **FAIL** (bloqueia promoção).
**Não aprova beleza/premium/fidelidade subjetiva** — só impede caos geométrico.

## 7. Auto-camera rules (`tools/auto_camera.py`)

USA: bounds reais do cômodo · centro do CLUSTER funcional (não só o herói) · sightline limpa ·
penalidade de oclusor grande no 1º plano/FOV · eye-level · fov proporcional · auto-crop (remove área morta).
RESPEITA (limites duros):
- NÃO cortar o móvel-herói; NÃO cortar o ENTENDIMENTO do layout; NÃO mascarar problema de composição com crop agressivo.
- Cômodo pequeno SEM bom ângulo → declarar **`LIMITED_BY_ROOM_GEOMETRY`** (não forçar com crop).
- Melhor shot ainda WARN → registrar como **caso-limite**, NÃO forçar PASS.
- Todo render promovido tem câmera/crop **rastreáveis**.
Validação honesta (estado 2026-06-08): **SALA full-auto = VERDICT PASS + CAMERA PASS**. **SUITE01/SUITE02 =
WARN-promotable** (caso-limite: cômodo pequeno → herói foreshortened OU dresser no quadro). **Auto-camera NÃO
garante PASS universal**; sala PASS não prova universalidade — revalidar cada cômodo no pipeline full-auto.

## 8. Quando chamar GPT / deep visual review (`gpt-review-gate`)

GPT/deep é necessário p/: veredito visual FINAL · premium realism · composição subjetiva · comparação com
expectativa humana · artifact approval · conflito entre gates. **NUNCA** usar local-worker/geometry_sanity p/
aprovar "bonito" (negative_dogfood: veredito visual auto é não-confiável).

## 9. Fluxo de execução por cômodo (o slice)

1. DesignIntentSpec (§4) ANTES do .skp. 2. `geometry_sanity` (§6) antes de promover. 3. auto-camera/full-auto (§7).
4. Render → `gpt-review-gate` (§8) se a aparência muda. 5. Registrar o STATUS honesto do cômodo:
- **`READY_FOR_SKP`** — spec + geometry_sanity OK, layout funcional.
- **`NEEDS_LAYOUT_FIX`** — geometry_sanity ou regra de interiores violada (corrigir o layout, não o crop).
- **`LIMITED_BY_ROOM_GEOMETRY`** — cômodo não comporta bom shot/programa; documentar, não mascarar.
- **`BLOCKED_BY_GEOMETRY`** — geometry_sanity FAIL (caos geométrico) → não promove.
NÃO criar infra grande / daemon / UI / mexer em tier. NÃO fingir PASS quando é WARN.

## 10. Definition of done (por passada)

skill/spec ✓ · DesignIntentSpec de ≥1 cômodo real ✓ · critérios de layout documentados ✓ · trade-offs explícitos ✓ ·
geometry_sanity preservado/implementado ✓ · auto-camera aplicada ou plano ✓ · teste/validação mínima ✓ · **veredito honesto** ✓.
