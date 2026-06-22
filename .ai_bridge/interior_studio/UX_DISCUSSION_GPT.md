# Discussão de UX/arquitetura do dash — Claude × GPT (via ponte) · 2026-06-22

> Felipe: "tá confuso, não entendo o que tá rolando / qual o próximo passo / como destravar". Pediu
> ajuda do GPT pra ver UX fluida (tipo infra), desbloqueio estilo n8n, e inventário dinâmico por ambiente.
> Capturado o que Claude e GPT CONCORDAM (consenso forte) e o que GPT adicionou.

## Posições do Claude (minhas) × veredito do GPT
1. **UX fluida = uma "hero" só (agora/próximo/bloqueado) + DEMOVER os 3 chats dos LLMs locais que dominam o meio.**
   → GPT **CONCORDA** (vira o GAP 3: separar operação de observabilidade).
2. **Desbloqueio n8n = cada etapa mostra o que falta + UMA ação contextual (sistema=botão "rodar"; curadoria=você decide; consult=ponte GPT). Só o próximo, não 8 botões.**
   → GPT **CONCORDA** ("regra de ouro: o painel não mostra TODAS as ações possíveis, mostra a PRÓXIMA ação correta;
   os 8 botões podem existir escondidos em 'avançadas'; no fluxo normal, só UM botão grande"). Vira o GAP 2.
3. **Inventário DINÂMICO por cômodo (não móveis hardcoded).**
   → GPT **CONCORDO 100%** ("inventário fixo de sofá/mesa/rack mistura produto com etapa; o certo é por cômodo,
   cada cômodo tem os assets que fazem sentido pra ele; deve NASCER de um modelo `room.asset.pipeline_state`").

## Os 3 GAPs do GPT (o que falta pra virar fluido)
- **GAP 1 — STATE MACHINE oficial.** Estado hoje espalhado (ciclo, markdown, patch, status derivado, bundle, dash).
  Precisa de uma entidade canônica: `ProjectState / RoomState / AssetState / PipelineStepState`. O dash **consome**
  esse estado, não "interpreta" tudo ad-hoc. Estados do asset:
  `not_started → references_needed → curation_needed → build_spec_ready → building → form_review_needed →
  context_review_needed → vray_ready → approved → learned → frozen`. Modelo:
  ```json
  {"room":"sala","asset":"sofa","current_step":"vray","status":"ready",
   "next_action":{"label":"Gerar render V-Ray","type":"system_action","command":"render_vray_sofa_room"},
   "blocked_by":null,"last_artifact":"sofa_venezia_room.png"}
  ```
- **GAP 2 — NEXT-ACTION RESOLVER.** O sistema decide sozinho o PRÓXIMO botão a partir do estado:
  refs ausentes→"Curar referências" · GPT question sem resposta→"Abrir pergunta GPT" · resposta sem patch→
  "Gerar Learning Patch" · patch draft→"Revisar diff" · context PASS→"Gerar V-Ray". "Vira o coração do dashboard."
- **GAP 3 — SEPARAR operação de observabilidade** em 3 camadas:
  1. **Operação:** hero + pipeline + próxima ação.
  2. **Inventário:** cômodos × assets × status × últimos artefatos.
  3. **Observabilidade:** chats dos LLMs, logs, markdown, artefatos (DEMOVIDOS pra baixo/aba — hoje disputam o espaço mental).

## Inventário por cômodo (estrutura sugerida pelo GPT)
```
Apartamento 74m²
├── Sala:   Sofá (GPT Contexto aprovado · próximo V-Ray) · Rack (forma congelada) · Mesa de centro (pendente) · Tapete · Iluminação
├── Cozinha: Marcenaria (forma aprovada) · Geladeira (spec pendente) · Pedra/backsplash (curadoria) · Piso · Iluminação
└── Suíte:  Cama (forma aprovada) · Cabeceira (aprovada) · Guarda-roupa (...)
```

## Plano (consenso Claude+GPT)
1. **AssetState/RoomState state machine** (entidade canônica) + os 11 estados → backbone.
2. **next_action resolver** (1 função: estado → próxima ação/botão).
3. **Inventário por cômodo** (substitui o de móveis hardcoded), nascendo do state machine.
4. **3 camadas** (operação / inventário / observabilidade) — demover os chats.

⚠️ Limitação da ponte descoberta: o digitador sintético do Chrome **corrompe `→` e acentos em msg longa** —
mandar sem setas (usar vírgula/"->") pra chegar intacto.
