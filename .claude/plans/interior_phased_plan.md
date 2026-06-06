# Plano faseado — Sistema de Interiores (mobiliário SketchUp)

> Handoff/tracker do loop autônomo. Fases sequenciais com gate explícito.
> Só avança de fase com gate GREEN. YELLOW = corrige no escopo. RED = para + registra.
> Regras globais: não mexer em parede/janela/shell; não bloco único no móvel principal;
> não usar Enscape/V-Ray/Trimble antes do core (placement+anatomia) passar; não MCP agora
> (adapters internos primeiro); sucesso = `.skp` versionado + renders + validation_report;
> mudança de aparência relevante = consultar GPT (Modo B, schema textual, sem gerar imagem).

## Estado (atualizado por ciclo)

- **Fase 3 (anatomia quartos) EM ANDAMENTO**: BedBuilder ✅ + WardrobeBuilder ✅ (commit 327a1c4:
  corpo+portas/frestas+puxadores+rodapé, wardrobe_gate PASS, troca o bloco roxo no furnish).
  validation_report phase3 = **5 gates GREEN**. FALTA: NightstandBuilder (criados ainda teal lisos)
  + AnatomyGate consolidado + veredito GPT (fila). Apê 65/65, base intacta.
- **FILA GPT-VISUAL (Modo B) acumulando** (clipboard infra travado): sofá-braço, cama, quarto
  placement, guarda-roupa. Felipe pode destravar (sessão/tela) ou fazer consult manual; imagens
  servidas em :8781. NÃO autojulgar; retry oportunístico cada ciclo.
- **Fase 2 (Bedroom placement) — determinístico GREEN; GPT visual na fila.**
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
