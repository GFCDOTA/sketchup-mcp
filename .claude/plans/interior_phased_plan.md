# Plano faseado — Sistema de Interiores (mobiliário SketchUp)

> Handoff/tracker do loop autônomo. Fases sequenciais com gate explícito.
> Só avança de fase com gate GREEN. YELLOW = corrige no escopo. RED = para + registra.
> Regras globais: não mexer em parede/janela/shell; não bloco único no móvel principal;
> não usar Enscape/V-Ray/Trimble antes do core (placement+anatomia) passar; não MCP agora
> (adapters internos primeiro); sucesso = `.skp` versionado + renders + validation_report;
> mudança de aparência relevante = consultar GPT (Modo B, schema textual, sem gerar imagem).

## Estado (atualizado por ciclo)

- **Fase 4 (RenderProvider abstraction) FECHADA GREEN** (commit 4ffe7af): interior/renderers/
  (render_provider.py interface + sketchup_basic_provider FUNCIONAL provado + enscape/vray stubs +
  get_provider). Render via provider básico = idêntico ao inline, base intacta.
- **Fase 5 (Spike Enscape/V-Ray/Trimble/MCP) FECHADA GREEN** (docs/spikes/render_and_asset_providers.md):
  Enscape=GUI-only (manual, sem API) → Fase 6 fica manual/blocked, pular sem forçar. V-Ray=tem Ruby API
  (`module VRay`, vray4sketchup2026.so) + vray.exe headless = MELHOR candidato, mas precisa LICENÇA +
  registrar ext no SU 2026 (Fase 8, risco crack-SU). 3DW=Chrome MCP existente + manifest (Fase 7).
  **MCP separado = NÃO** (adapters internos bastam). Sem inventar API.
- **V-Ray VIÁVEL CONFIRMADO** (commit d9fa80c; Felipe apontou as extensões): Enscape+V-Ray carregam no
  SU 2026 (loaded=true); `module VRay` 100% alcançável de -RubyStartup; fluxo render→save MAPEADO
  (RenderSessionProduction/Export.new(context:).start, VRayImage#save, ModelExporter#update_camera,
  vray.exe headless). vray_final_provider.available()=True. Probes: .claude/scratch/probe_vray*.rb.
  - **FASE 8 (V-Ray render) FUNCIONANDO** (commit ae85b8c): pipeline premium PROVADO end-to-end.
    `context = VRay::Context.active`; `tools/vray_export.rb` (camera iso/top + RenderSessionExport →
    .vrscene); `vray.exe -sceneFile=x.vrscene -imgFile=y.png -display=0 -autoClose=1` → PNG ~3s GPU.
    `VRayFinalProvider.render(in_skp)` funcional, available()=True. Render planta mobiliada gerado.
    **REFINO premium EM ANDAMENTO** (commits 2e1c2a5 exposure, 01a5aa1 camera, eaf0999 exposure-balance):
    - EXPOSURE: tools/tweak_vrscene.py pos-processa o .vrscene (export sai p/ exterior f/8-1/300-ISO100
      = interior escuro). Tuning POR-SHOT: dollhouse overview pede mais luz; interior fechado pede menos
      (ISO~100, f~5.6, shutter~1/125, sky~0.55) p/ não estourar a janela.
    - CAMERA: vray_export.rb aceita VRAY_EYE/VRAY_TARGET/VRAY_FOV (inches). Interior eye-level OBSTRUI
      pela L-shape (sofá entre 2 paredes m013/m014); o que funciona = high 3/4 zoom olhando por cima das
      paredes (teto aberto). tools/compute_room_cam.py computa eye/target do grupo de móveis.
    - GPT Modo B iterado: dollhouse CAMERA=FAIL → interior zoom WARN (sofá legível) → exposure-balance
      (LIGHTING recuperado). Render atual = sala interior bem exposta, sofá golden visível.
    - MATERIAIS: `tweak_vrscene.apply_materials` (commit 32e298a) edita BRDFs dos móveis por papel —
      madeira satin / tecido matte / metal. SUTIL (reflexão discreta na luz difusa); propriedades só,
      SEM texture maps de imagem.
    - **PRÓXIMO salto premium = TEXTURE MAPS reais** (grão madeira, trama tecido): precisa de imagens de
      textura aplicadas via TexBitmap (object/world mapping, móveis sem UV) OU materiais SU texturizados
      no renderer (place_layout_skp.rb) que o V-Ray traduz. Sourcing de textura = território Fase 7
      (asset catalog) ou geração procedural. Pede direção/assets do Felipe.
    - Outros premium: câmera eye-level cinematográfica (resolver oclusão L-shape); render dos quartos.
  - **SALA PREMIUM = VERDICT PASS (2026-06-07/08; commits 6684876 texturas, ececc16 janela, a02f174 eye+luz):**
    - TEXTURAS procedurais (madeira grão + tecido trama, numpy/PIL, `tools/gen_textures.py`, aplicadas no
      vray_export.rb via material.texture): **GPT MATERIALS=PASS** ("deixou de parecer plástico liso").
    - LIGHTING janela estourada (FAIL recorrente) → ISO100/f7/1-160/sky0.3 → **GPT LIGHTING=PASS** (segurou).
    - CÂMERA eye-level (z 150→62, DENTRO da sala, costas p/ parede sul; oclusão resolvida pela geometria
      real via `tools/room_introspect.py`): **GPT CAMERA=PASS** ("vende o sofá como ambiente real").
    - LUZ INTERNA quente (LightSphere fill procedural injetada no .vrscene, `tweak_vrscene.add_fill_light`):
      **GPT VERDICT=PASS / LIGHTING=PASS** ("sofá virou herói, paredes com preenchimento, janela controlada").
    - Recipe reproduzível: `tools/render_room.ps1` (export+tweak+vray, hash base) + `tools/tune_render.ps1`
      (tune fill/exposição sem re-export). Deliverable: planta_74_vray_sala_eyefill3.png. GOTCHA: fill
      <55in da câmera = orb escuro visível.
    - **PRÓXIMO ROI** (backlog, não-bloqueante): (a) enquadramento final da sala (faixa cinza inferior +
      parede lateral — PREMIUM_REALISM/CAMERA WARN); (b) **estender o pipeline premium aos QUARTOS**
      (suite01: textura+eye-level+fill, usando o template provado); (c) integrar câmera/fill no VRayFinalProvider.
## GATE GPT_REVIEW (Felipe 2026-06-08) — validação visual formal

`tools/gpt_review.py` (prepare/record/show) + skill `gpt-review-gate`. Toda mudança de aparência
atravessa o gate; NUNCA autojulgar. PASS|WARN promove (WARN=backlog), **FAIL ou qualquer dimensão
FAIL BLOQUEIA**. Ledger append-only `artifacts/review/interior/gpt_review_ledger.jsonl` (texto cru do
GPT) + espelho `gpt_verdicts.md`. Hook no `render_room.ps1 -ReviewId`. Test verde `tools/test_gpt_review.py`.
PROVADO: sala_framing_crop→PASS; quarto v1→FAIL (bloqueou).

## QUARTO SUITE 01 (r000) — WARN-promotable, lighting PASS, polish premium pendente

> WORDING (correção Felipe 2026-06-08): NÃO chamar de "premium PASS". O gate passou só LIGHTING;
> o cômodo inteiro ainda é **VERDICT WARN** (MATERIALS/CAMERA/FURNITURE_DETAIL/PREMIUM_REALISM WARN).
> Status honesto = "WARN-promotable, lighting PASS, polish premium pendente". PASS premium = schema
> sem FAIL E com PREMIUM_REALISM/FURNITURE_DETAIL melhores (deep verdict do GPT).


Reusa o template provado: texturas + eye-level + luz interna + exposição, via `render_room.ps1`/`tune_render.ps1`.
Geometria: `room_introspect.py <room_id>`. Cama centro (636,789), cabeceira leste, 2 janelas norte, área sul aberta.
- **v1** fill 820 (= sala) → **GATE FAIL**: LIGHTING FAIL, cama "massa branca" (quarto menor superexpôs).
- **v2** fill 260 + sky0.22 → LIGHTING WARN (cama recuperou, janela segurou), mas hotspot direto na cama.
- **v3** fill DIFUSO (raio 42, z92, fora do eixo da cama) + sky0.18 + câmera recuada → LIGHTING WARN (difusa, sem
  hotspot agressivo) mas **CAMERA FAIL** (cama não inteira + faixa cinza). Crop aplicado (`crop_render.py`).
- **LIÇÃO LL-FURN**: fill premium é POR-CÔMODO (não reusar intensidade da sala); quarto menor/cama perto da luz
  pede fill DIFUSO (raio grande, deslocado do eixo do móvel, z alto, intensidade baixa). Janela 2x pede sky menor.
- **v4** câmera recuada/subida (cama INTEIRA com margem) → **CAMERA FAIL→WARN** ("cama praticamente inteira").
- **v5** fill 150 + sky0.14 (afastado/mais alto) → **LIGHTING PASS** ("fill menos agressivo, cama menos estourada,
  janela mais controlada, quarto ainda iluminado"). Cama recuperou textura.
- **v6** crop final (faixa de piso até o foot + trim do topo técnico) → **VERDICT WARN promotable** (LIGHTING PASS;
  CAMERA/MATERIALS/FURNITURE_DETAIL/PREMIUM_REALISM WARN). **DELIVERABLE: planta_74_vray_quarto_premium.png**
  (nível WARN honesto, sem FAIL — gate promove).
- **LIÇÃO LL-FURN**: fill premium POR-CÔMODO (quarto pediu fill DIFUSO raio~42, deslocado do eixo da cama, z alto,
  intensidade ~150 vs 820 da sala; sky menor p/ 2 janelas). Câmera: recuar p/ cama inteira + crop framebuffer
  da faixa de piso (NÃO aproximar). Sequência GPT: lighting→câmera/crop→materiais.
- **POLISH FINAL (2026-06-08, decisão Felipe "1 passada + congela se WARN")**: linho DEDICADO sutil p/ roupa de
  cama (gen_textures.linen multiplicativo+slub; vray_export mapeia colchao/travesseiro/headboard→fabric_linen,
  SOFA fica em fabric_light = sofa-safe) + crop com leitura de teto/shell aberto reduzida. Resultado GPT:
  **MATERIALS PASS + FURNITURE_DETAIL PASS + LIGHTING PASS** (3/5); CAMERA+PREMIUM_REALISM WARN.
- **CONGELADO WARN-promotable** (deliverable: planta_74_vray_quarto_WARN_promotable.png). Único bloqueio p/ PASS
  = **faixa de piso inferior**: conflito Felipe(quer margem pequena) × GPT(quer remover) × Felipe(não quer pé colado);
  com piso cinza não-mobiliado é incompatível sem tapete/material novo (fora do escopo small-polish). Per regra do
  Felipe: NÃO entrar em looping de render — congela e avança. (LL-FURN: linho forte=grid/xadrez procedural → usar
  weave multiplicativo de baixa amplitude + slub dominante; fill é por-cômodo.)
- **NEXT**: SUITE 02 (r003) + COZINHA (r004), mesmo pipeline pelo GATE GPT_REVIEW (fill difuso por-cômodo,
  exposição que segura janela, eye-level dentro do cômodo, crop).
- **PISO — RESOLVIDO (Felipe 2026-06-08, fix root-cause apartment-wide)**: a "faixa cinza" era o PISO pastel chapado
  (material `floor_<room_id>`), recorrente em TODO cômodo. Fix aplicado: textura `wood_floor.png` (carvalho CLARO)
  em todos os `floor_*` via PREFIXO em `vray_export.rb` (robusto a id; tile [120,120]; sofá/parede intactos = distinct
  materials). **GPT: MATERIALS PASS** ("madeira clara lê bem, não parece mais piso chapado") **+ LIGHTING PASS**
  ("quarto bem exposto"). Carvalho CLARO de propósito: piso escuro reduzia o bounce → escurecia o quarto + estourava
  a janela; o claro reflete → NÃO atrapalha render nenhum. **Permanente no pipeline** (commitado): todo render futuro,
  qualquer cômodo, herda o piso de madeira automaticamente. Evidência: planta_74_vray_quarto_piso.png, _iso_floor.png.
  Resíduo: "faixa/crop inferior" = composição (não o piso) — backlog visual, mesma questão margem-Felipe×no-faixa-GPT.
- **SALA re-renderizada com o piso de madeira = VERDICT PASS** (2026-06-08, planta_74_vray_sala_floor_crop.png):
  *"madeira clara lê bem e combina MELHOR com sofá/mesa/tapete do que o cinza chapado"*; MATERIALS+LIGHTING+
  FURNITURE_DETAIL PASS. Apê agora com piso coeso (sala+quarto). WARN residual: textura do piso levemente forte
  perto da janela (backlog — não loopar; piso já é PASS-quality nos dois cômodos).
- **SUITE 02 (r003) premium** (2026-06-08, planta_74_vray_suite02_crop.png): pipeline GENERALIZOU — num 3º cômodo
  (o menor) o piso de madeira + fill por-cômodo deram **MATERIALS PASS + LIGHTING PASS de primeira** (câmera 3/4
  do canto SE; eye=448,800,74 target=368,710,36 fov66 fill 375,775,90,150,40 sky0.16). VERDICT WARN só por
  ENQUADRAMENTO (guarda-roupa/dresser à direita domina o foreground + faixa inferior). Congelado WARN-promotable.
- **LIÇÃO SISTÊMICA**: a família de WARN que sobra em TODOS os cômodos (sala/suite01/suite02) = **enquadramento**
  (faixa inferior + oclusão), NUNCA materiais/luz/piso (esses são PASS). Próximo salto de maior ROI no render NÃO é
  grindar câmera per-room — é resolver o enquadramento de forma SISTÊMICA (auto-câmera das bounds do cômodo +
  crop-rule), que conserta os 3 cômodos de uma vez. (Análogo ao piso: fix root-cause apartment-wide.)
- **AUTO-CAMERA + AUTO-CROP — BUILT + VALIDADO (2026-06-08)**: `tools/auto_camera.py` deriva eye/target/fov das
  bounds REAIS do cômodo — alvo no CENTRO DO CLUSTER de estar/dormir + sightline LIMPA pro herói + penalidade de
  occluder grande no FOV + eye-level — **sem coords hardcoded (robusto a rebuild do `.skp`, nunca fica stale)**;
  + auto-crop rule (top 11% / bottom 28%) remove o foreground morto. **GPT na SALA: VERDICT PASS + CAMERA PASS**
  ("auto-camera + auto-crop resolveram a área morta, o conjunto ocupa o quadro"; MATERIALS/LIGHTING/FURNITURE PASS).
  Regressão: `tools/test_auto_camera.py` (eye dentro do cômodo, eye-level, fov/dist sãos nos 3). Deliverable:
  planta_74_vray_sala_autocrop.png. Resíduo PREMIUM_REALISM (janela clara / parede esq / textura do piso) =
  polish de catálogo (backlog). Cômodos pequenos (suite02) seguem constrangidos pela geometria (auto dá shot
  válido, não ótimo — o herói foreshortened OU o dresser no quadro; caso-limite documentado).
- **SKILL interior-architect-planner + geometry_sanity (Felipe 2026-06-08)**: design implícito virou regras
  executáveis em `.claude/skills/interior-architect-planner/SKILL.md` (mental model 10 passos · regras gerais +
  por ambiente · DesignIntentSpec obrigatório · candidate-layout · geometry_sanity · limites da auto-camera ·
  quando chamar GPT). `tools/geometry_sanity.py` = gate determinístico BARATO (móvel dentro do cômodo / não
  bloqueia porta / alto-sobre-janela / bbox sã) — calibrado: PASS nos cômodos, WARN real só na suite02 (dresser
  perto da porta 10in²), ZERO falso-FAIL; teste `tools/test_geometry_sanity.py`. **1º slice = COZINHA r004**:
  DesignIntentSpec (`artifacts/planta_74/design_intent/r004.json`) → geometry_sanity PASS → auto-camera → render.
  VERDITO HONESTO: geometry **READY_FOR_SKP** · program **NEEDS_LAYOUT_FIX** (pia/cooktop/geladeira distintos
  ausentes — bancada agregada) · câmera **LIMITED_BY_ROOM_GEOMETRY** (galley pequena → eye-level vira close-up da
  bancada; cozinha pede modo top/iso/door-wide, não o eye-level-cluster). NÃO mascarado com crop.

- Backlog WARN (não bloqueia): bevel premium nas arestas (criado>portas>manta>braço) + afastar criado da porta.

- **Fase 2 (Bedroom placement) — FECHADA GREEN (determinístico + GPT PASS).** GPT Modo B no
  suite01_top: VERDICT PASS (BED/WARDROBE/CIRCULATION/ORIENTATION PASS; NIGHTSTANDS WARN = criado
  superior perto da porta). Ver artifacts/review/interior/gpt_verdicts.md.
- **Fase 3 (anatomia quartos) — FECHADA GREEN (determinístico + GPT PASS)** (commits 327a1c4 wardrobe,
  9cc09f0 nightstand): Bed+Wardrobe+Nightstand builders golden. validation_report = 6 gates GREEN
  (= AnatomyGate consolidado). GPT Modo B no montage dos 3 móveis: VERDICT PASS (OBJECT_ANATOMY/
  MATERIAL/PROPORTION PASS — "leem como móveis compostos, não caixas"; PREMIUM_REALISM WARN = falta
  bevel/acabamento). Apê 93/93, base intacta. → próxima fase: **Fase 4 RenderProvider abstraction**.
- **Clipboard DESTRAVADO** (Felipe destravou a sessão) — GPT Modo B operacional de novo (setclip.ps1 +
  paste; receita: click composer + wait 1s + ctrl+v, depois type + Enter; montage via System.Drawing c/ casts [int]).
- **BACKLOG de refinamento (WARN, não bloqueia)**: (a) afastar criado superior da porta; (b) bevel/chamfer
  sutil nas arestas (criado > portas guarda-roupa > manta/travesseiros > braço do sofá) = etapa premium.
  - BedPlacementGate (`interior/validators/bed_placement_gate.py`, commit 523894c): valida
    cama (ancorada+cabeceira-parede-limpa+não-bloqueia-porta+orientação) + guarda-roupa
    (ancorado+frente-livre+não-bloqueia-porta) + criados (flanqueiam) + circulação. Fixtures
    erro (rotacionada/flutuando/bloqueando-porta=FAIL) + quarto-válido=PASS. r000/r003 reais
    = **PASS** (cabeceira m018/m014 limpas, wardrobe+nightstands PASS). Sem regressão.
  - validation_report phase2_bedroom = GREEN (4 gates). bedroom_placement_report.json gerado.
  - **PENDENTE/YELLOW: veredito GPT Modo B do quarto + veredito visual da CAMA (c0521d3).**
    Bloqueado por INFRA de anexo-de-imagem ao ChatGPT: clipboard SetImage trava persistente
    (10+ retries Clear+STA), upload_image não acessa imageId de screenshot, file_upload rejeita
    path do worktree, screenshot do PNG servido corta (tamanho nativo>viewport). NÃO autojulgar.
    Retry próximo ciclo. O placement é deterministicamente PASS (gate cobre as dimensões do schema).
    - **DIAGNÓSTICO clipboard**: SetText E SetImage falham (não é só imagem); GetOpenClipboardWindow=0
      (ninguém segura o clipboard aberto) → acesso à window-station/desktop interativo no contexto
      do shell. Funcionou cedo na sessão (sofá) → INTERMITENTE/ambiental (lock de tela/sessão), não
      um app travando. NÃO solúvel por código. Retry oportunístico; se persistir = NEEDS-HUMAN p/ os
      passos GPT-visual (Felipe pode fazer o consult manual OU destravar a sessão).
    - **PLANO FORWARD**: não bloquear o determinístico. Próximo ciclo: (a) retry image-attach; se OK,
      limpar backlog GPT (cama c0521d3 + quarto placement); (b) avançar Fase 3 anatomia determinística
      (WardrobeBuilder + NightstandBuilder golden + anatomy gates) — construção não precisa de GPT;
      o veredito VISUAL fica na fila até o anexo voltar.
- Fases 0 e 1 fechadas GREEN.
- Fase 1 GREEN: `interior/planners/placement_brain.py` (FurniturePlacementBrain base:
  RoomGraph+CirculationGraph+NoFurnitureZones+WallAffordanceMap+CandidateLayout+ScoreBreakdown
  + `place_against_wall(ftype,w,d)` genérico). wall_affordance generalizado (bed_score/wardrobe_score).
  Sala NÃO regrediu (validation_report GREEN). Nuance: o base escolhe a melhor parede por
  score+circulação (serve cama/guarda-roupa direto); o SOFÁ mantém a restrição extra "frente
  pra TV" no living_room_planner (não foi tocado — marco preservado).
- **Fase 2 approach**: BedPlacementBrain = `brain.place_against_wall("bed", w, d)` (cabeceira na
  melhor parede LIMPA via bed_score, frente p/ dentro) + NightstandPlacement (flanqueia a cama,
  só 2 se couber). WardrobePlacementBrain = `place_against_wall("wardrobe", ...)`. Fixtures de erro
  obrigatórias (cama bloqueando porta / sem cabeceira limpa / rotacionada / circulação; guarda-roupa
  bloqueando porta / sem frente livre = FAIL; quarto válido = PASS) + GPT verdict textual (Modo B).
- Branch: `feat/mobiliar-bedroom-layout` (sync com remote). develop +13 commits out-of-band
  (cockpit/dashboard — não tocam mobília; sem conflito). 26 ahead de develop.
- Python: a instalação user-level quebrou → usar venv `E:\Claude\sketchup-mcp\.venv\Scripts\python.exe`.

## Marco da SALA (GPT-validado)

- SofaPlacementBrain existe: `interior/planners/living_room_planner.py` (plan_living: solver
  TV-wall limpa + sofá de frente, fora circulação).
- SofaPlacementGate existe: `interior/validators/sofa_placement_gate.py` (ancorado/frente-foco/
  fora-circulação/clearance/justificativa; fixtures flutuando/rotacionado/corredor=FAIL, solver=PASS).
- Sofá placement **FAIL→PASS** confirmado pelo GPT ("agora existe um estar de verdade").
- Sofá objeto: materiais linho+madeira + bevel almofadas (GPT PASS visual). Braço frustum.
- **WARN/future (não bloqueia): arredondamento total da silhueta do braço (aresta vertical) — precisa fillet.**

## Componentes golden já construídos

- Sofá: `tools/sofa_builder.py` + `furniture_anatomy_spec.SofaSpec` + `sofa_gate.py` + `furniture_visual_gate.py`.
- Cama: `tools/bed_builder.py` + `BedSpec` + `interior/validators/bed_gate.py` (PASS king/queen/casal/solteiro).
  Aplicada em r000/r003. **PENDENTE: veredito GPT visual da cama (clipboard travou; retry).**
- Apê inteiro: `tools/furnish_apartment.py` (BRAINS por tipo) → `planta_74_furnished.skp` (53 placeholders).

## Próximos gaps (ordem do plano)

- **Fase 1**: extrair FurniturePlacementBrain base genérico (RoomGraph/CirculationGraph/
  NoFurnitureZones/WallAffordanceMap/CandidateLayout/ScoreBreakdown) sem quebrar a sala.
- **Fase 2**: BedPlacementBrain + WardrobePlacementBrain + NightstandPlacement + fixtures + GPT verdict.
- **Fase 3**: anatomia dos quartos (BedBuilder feito; WardrobeBuilder + NightstandBuilder + AnatomyGate).
- **Fase 4**: RenderProvider abstraction (só sketchup_basic_provider funcional; Enscape/V-Ray stubs).
- **Fase 5**: spike técnica Enscape/V-Ray/Trimble/MCP (doc honesto, sem inventar API).
- **Fases 6-10**: Enscape preview / Asset catalog / V-Ray final / cena integrada / learning loop.

## Gates por fase (resumo)

| Fase | Gate GREEN = |
|---|---|
| 0 | baseline gerado, artifact localizado, tree explicado, report escrito ✅ |
| 1 | sofá fixtures verdes, brain base existe, score+rejected no report, sala não regrediu |
| 2 | quarto fixture PASS, planta sem regressão, GPT não-FAIL em placement/circulation |
| 3 | cama/guarda-roupa/criado não-bloco, layout passa, GPT object anatomy não-FAIL |
| 4 | renders via provider básico ok, paths não quebrados, Enscape/V-Ray documentados |

## Validation report

`artifacts/review/interior/validation_report.{json,md}` — gerado por
`python -m interior.validators.validation_report <phase_tag>`. Baseline Fase 0 = **GREEN**.

## Learning (LL-FURN)

- LL-FURN-001: móvel com quinas retas parece bloco; bevel ajuda, fillet real é etapa premium.
- LL-FURN-002: placement passa ANTES de render premium.
- LL-FURN-003: cama precisa de cabeceira em parede limpa.
- LL-FURN-005: Enscape = preview; V-Ray = final.
- LL-FURN-006: ambiente estilizado → gerar referência GPT (Modo A) + DesignIntentSpec ANTES de construir.
- LL-FURN-007: placement valida ANTES da beleza — BedPlacementGate (determinístico) cobre as dimensões
  do schema GPT (ancorado/parede-limpa/circulação), então o determinístico não trava por falta de GPT.
- LL-FURN-008: builder de móvel = espelhar sofa_builder (peças _p + place_sofa_boxes genérico +
  parts_to_boxes + gate anatomia). Reuso barato: cama e guarda-roupa saíram rápido assim.
- LL-FURN-009: anexo-de-imagem ao ChatGPT é o gargalo do GPT-visual (clipboard window-station
  intermitente). Não bloquear o determinístico nele; acumular a fila e destravar em lote.
