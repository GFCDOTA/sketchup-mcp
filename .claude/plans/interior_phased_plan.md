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
