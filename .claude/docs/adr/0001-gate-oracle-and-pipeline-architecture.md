# ADR-0001 — Claude decision-gate, orquestrador & o pipeline PDF→SKP

- **Status:** Accepted / LIVE
- **Data:** 2026-05-31
- **Deciders:** Felipe (owner) + Claude (modo B — autonomia delegada)
- **Escopo:** a arquitetura operacional que cerca o objetivo do produto (gerar `.skp` fiel a uma planta PDF).

---

## Contexto

O produto é: **PDF de planta → `.skp` SketchUp fiel**, generalizável pra qualquer planta.
Pra tocar isso de forma **autônoma** (modo B — Felipe delega tudo EXCETO o julgamento visual),
faltavam três coisas que esta arquitetura resolve:

1. um **oráculo de decisão** que resolva bifurcações técnicas / A-B-C / merge **sem** transformar
   o Felipe num roteador de copy-paste;
2. **observabilidade** de múltiplas sessões autônomas rodando em paralelo (estão progredindo ou travadas?);
3. **ground truth determinístico** (não opinião de LLM) pra aprovar fidelidade.

---

## Visão geral (mapa do sistema)

```
            ┌───────────────────────── modo B (autonomia delegada) ─────────────────────────┐
            │                                                                                │
  sessões   │   POST /ask {prompt,mode}        ┌──────────────────────────┐                  │
  Claude  ──┼──────────────────────────────▶  │   GATE  :8765  (oráculo)  │                  │
  (loops)   │   POST /heartbeat {sid,cycle}    │  claude -p  Opus 4.8      │                  │
            │   ◀── {verdict,confidence,...}   │  + effort xhigh           │                  │
            │                                  │  cwd=tempdir (fora do repo)│                 │
            │   GET /sessions  /events  /health│  SYSTEM = modo B          │                  │
            │   GET /  (painel operacional) ◀──┤  /heartbeat /sessions     │                  │
            │                                  └─────────────┬────────────┘                  │
            │                                                │ append                         │
            │                                   .ai_bridge/audit/audit.jsonl (audit-core)     │
            └────────────────────────────────────────────────────────────────────────────────┘
                       │ decide bifurcações técnicas                  ▲
                       ▼                                              │ VISUAL_REVIEW (único gate humano)
   ┌───────────────────────────── PIPELINE PDF → SKP ──────────────────────────────────────┐
   │  PDF ─(anotação HUMANA)─▶ consensus.json ─▶ build_plan_shell_skp(.py→.rb/SketchUp)      │
   │       (não há extrator;            walls/openings/         shell 2D + extrude + aberturas │
   │        raster+Hough fabrica)       rooms/soft_barriers      3D + portas + soft barriers   │
   │                                                                  │                         │
   │                                                                  ▼                         │
   │                                              .skp + renders (iso/top) + geometry_report    │
   │                                                                  │                         │
   │                            gates DETERMINÍSTICOS (ground truth)  ▼                         │
   │             opening_host_audit · wall_overlap_audit · overlay_diff(vs PDF) · self-check    │
   │                                                                  │ PASS                    │
   │                                                                  ▼                         │
   │                              VISUAL_REVIEW (humano/GPT-Chrome: PDF×BEFORE×AFTER)           │
   │                                                                  │ IMPROVED                │
   │                                                                  ▼                         │
   │                                          artifacts/<plant>/  (deliverable canônico)        │
   └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Decisões

### D1 — Oráculo de decisão é o próprio Claude, na assinatura (`:8765`)
- HTTP local: `GET /health` + `POST /ask {prompt}` → `{response}`. Contrato drop-in (era ChatGPT bridge).
- Motor: **`claude -p` headless, `--model claude-opus-4-8 --effort xhigh`** — o "juiz". Auth por **OAuth token
  da assinatura** (`claude setup-token` → `.oauth_token`), **sem API key**.
- Roda com **`cwd=tempdir`** (fora do repo): não carrega o `CLAUDE.md`/hooks do projeto → sem prompt de
  permissão e, crítico, **sem disparar o SessionStart hook que sobe o próprio gate (recursão)**.
- **Por quê:** dogfood (o sistema usa Claude pra se decidir) + custo zero de API + decide na cadência da sessão.

### D2 — Gate framework §6 (qualidade da decisão, não só "uma resposta")
- **§6.4** Verdict + **Confidence** + **Assumptions** — parseado por `ask_gpt_gate` (tem dente: o asker
  sabe o que re-checar deterministicamente vs aceitar).
- **§6.3** File-fetch read-only — oráculo pede arquivo via `MORE-INFO` + `Need-files:`; allowlist **default-deny**,
  bloqueia traversal/secrets (`.oauth_token`/`.env`/`*.key`).
- **§6.2** Red-team mode — nos triggers pesados (`a_b_c_decision_with_tradeoff`, `risk_of_inventing_geometry`,
  `big_pr_changes_gate_or_spec`) o oráculo **steelman a oposição** antes de decidir (combate o viés de
  concordância de um Claude consultando outro).
- **§6.5** Robustez — UTF-8 tolerante, aceita `prompt`|`question`, `/health` auto-documentado.
- **§6.1 multi-oracle routing: DELETADO.** Era independência FALSA (claude+chatgpt no mesmo `:8765`); torná-la
  real = infra-pela-infra. O ground truth real é o **determinístico**, não um 2º LLM. *(decisão tomada pelo
  próprio gate em redteam — dogfood.)*

### D3 — Orquestrador de liveness (observe-only)
- `POST /heartbeat {session_id, cycle}` + `GET /sessions` → flags **STALLED** (sem ponto há >10min) /
  **PARALYZED** (`cycle` congelado por 3+ pontos) / **OK**.
- `cycle` = **token de progresso monotônico** — o sinal que distingue *progredindo* de *vivo-mas-travado*
  (log passivo de consult é cego a trabalho silencioso).
- **Detecta, não previne.** Prevenção de colisão multi-agent = **isolamento de worktree** (follow-up aberto).
- **audit-core:** `.ai_bridge/audit/audit.jsonl` append-only (heartbeats + consults).

### D4 — O gate serve o próprio painel operacional (sem Spring Boot)
- `GET /` → dashboard HTML auto-contido. Polling de `/health`+`/sessions`+`/events` a cada 5s.
- **Por quê não Spring Boot:** stack Java inteira pra um status de servidor Python localhost = infra-pela-infra.
  O gate servir a própria página é zero-stack e auto-coerente (se a página não abre, o gate caiu).
- Persistência: **Startup folder do Windows** (login, sem admin) + SessionStart hook + `LIGAR-BRIDGE.cmd`.

### D5 — O pipeline PDF→SKP (o "processamento")
| etapa | ferramenta | auto/humano |
|---|---|---|
| PDF → consensus | **anotação humana** (PNG → JSON) + gap-detection assist | **HUMANO** (não há extrator; raster+Hough fabrica falso) |
| consensus → shell 2D | `build_plan_shell_skp.py` (shapely: union de paredes, carve de openings 2D) | auto |
| shell → `.skp` 3D | `build_plan_shell_skp.rb` (SketchUp: extrude paredes 2.70m, pisos, **aberturas 3D de janela** preservando peitoril/verga, portas, soft barriers 1.10m) | auto |
| `.skp` → veredito determinístico | `opening_host_audit` · `wall_overlap_audit` · `overlay_diff`(vs PDF) · `gates_self_check` | auto (**ground truth**) |
| veredito visual | montagem PDF×BEFORE×AFTER | **HUMANO / GPT-Chrome** (nunca auto) |
| `runs/` → `artifacts/<plant>/` | `promote_artifact.py` / `promote_canonical.py` | auto |

### Hard Rules (invariantes — quebrar = RED)
1. **Nunca inventar** wall/room/opening — `consensus.json` é a fonte de verdade.
2. **Nunca carve janela full-height** — preserva massa abaixo do peitoril e acima da verga (path 3D).
3. **Nunca mutar fixture canônica** (`fixtures/<plant>/`) sem aprovação humana.
4. **Nunca push direto em `main`** — PRs `feat/`|`chore/` → `develop`.

---

## Consequências

**Positivas**
- Decisões autônomas com qualidade alta (Opus 4.8 + xhigh + red-team), sem o Felipe virar roteador.
- Observabilidade real (orquestrador + painel) — dá pra ver no `:8765/` se uma sessão travou.
- Fidelidade protegida por **ground truth determinístico**, não por opinião de LLM.

**Tensões / dívidas conhecidas**
- **Multi-agent:** sessões dividindo um worktree colidem; o orquestrador **VÊ**, mas o fix-raiz (isolamento
  de worktree / lock) é follow-up aberto.
- **Gargalo de produto:** `consensus.json` é **autoria humana** (sem extrator) → generalizar pra planta nova
  depende disso. Blueprint das constantes do builder em `specs/generalize_builder_constants.md`.
- **Custo:** cada consulta = Opus+xhigh na assinatura (mais lento / mais cota) — aceito porque é o juiz.

**Gates humanos (os ÚNICOS pontos onde o humano entra):**
- `VISUAL_REVIEW` (a aparência do `.skp` vs PDF).
- Promover o 1º consensus de uma planta nova a canônico.
- Autoria/aprovação do consensus de uma planta nova.

---

## Referências
- `tools/claude_bridge/server.py` (gate + orquestrador + painel)
- `tools/ask_gpt_gate.py` (o asker / os 9 triggers)
- `.claude/specs/gate_framework_and_audit.md` (§6)
- `.claude/specs/generalize_any_plant.md` + `generalize_builder_constants.md`
- `.claude/skills/autonomous-fidelity-loop` · `gpt-auto-consult-gate` · `gh-autopilot`
