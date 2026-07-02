# FP-033: Closed Correction Loop — detector → typed finding → fix → re-render → re-check

> **Status slice 3 (2026-07-01) — drifts resolvidos a favor do CÓDIGO:**
> `BLOCKED_NEEDS_FP032` (spec) virou status do **CONSUMIDOR**
> (`tools/vision_queue_consumer.py`), não estado do loop — o loop usa
> `PENDING_VISION`. `pending_vision_findings()` existe agora, keyed por
> **out_dir** (não fixture — todas as filas do loop já são relativas ao
> `--out`). O `--once` da spec é `--max-cycles 1` na task NOC
> (`kind:"correction_cycle"`, que reusa `dispatch()` via o seam `run_worker` —
> os helpers de pseudocódigo `enqueue_render_then_vision`/`FP032_available`/
> `noc_commit_cycle` não existem e não foram criados). Promoção FAIL só com
> dogfood `DISCRIMINATED` (paridade FP-032 por import de
> `run_skp_visual_review.promote_oracle_verdict`, não cópia).

> **Honestidade de partida (lido no código):** quase todas as PEÇAS já existem isoladas.
> O que NÃO existe é a **máquina de estados que costura o laço** e decide, por finding, se
> conserta sozinha (determinístico), delega pra VISÃO (FP-032) ou sobe pro FELIPE. A
> "auto-fix loop" é literalmente listada como *Follow-up (not in this PR)* no FP-030
> (`docs/specs/FP-030_visual_oracle_gate.md` §"Loop" e §"Follow-ups"). E a
> `autonomous-fidelity-loop` é um **protocolo que uma sessão segue à mão**, não código.
> FP-033 transforma esse protocolo num **driver programático**.

## Problem

Hoje a fidelidade da planta avança com o humano no laço interno: alguém roda um gate, lê o
FAIL, decide o conserto, reconstrói, olha de novo. As peças determinísticas já existem e são
boas — `tools/run_deterministic_gates.py` (opening_host + wall_overlap + render_bbox +
wall_presence + position_fidelity), `tools/geometry_sanity.py` (móvel-vs-cômodo) e
`tools/furniture_overlap_gate.py` (móvel-sobre-móvel) — mas **ninguém as encadeia**. O FP-030
gera `visual_findings.json` tipado com `suspected_owner` e `proposed_fix`, porém o runner
**para no primeiro FAIL e não auto-conserta** (`run_skp_visual_review.py`; FP-030 §Loop:
"the script does not auto-fix"). A `autonomous-fidelity-loop` SKILL descreve o ciclo
(PROGREDINDO/PATINANDO/BLOCKED, heartbeat, parar em RED/patinagem/NEEDS-HUMAN) mas é prosa
que uma sessão Claude executa manualmente — não há `correction_loop.py`.

Resultado: o sistema não roda sozinho. FP-033 entrega o **driver** que fecha o laço interno
sem o humano, deixando pro Felipe só o que de fato exige o olho dele (veredito visual final
IMPROVED/SAME/WORSE).

## Scope

1. **Máquina de estados do laço** (`tools/correction_loop.py`): `DETECT → CLASSIFY → FIX →
   REBUILD → RE-CHECK → {PROGRESS|STALL|RED|NEEDS_FELIPE|CLEAN}`, com **log por ciclo** (1
   linha, formato da `autonomous-fidelity-loop`) e detecção de **patinagem** (2 ciclos sem
   progresso novo → para).
2. **Classificador de finding** — a peça nova de inteligência: dado um finding tipado
   (vindo dos gates determinísticos OU do `visual_findings.json` do FP-032), decidir a
   **rota**:
   - `DETERMINISTIC_AUTOFIX` — o loop conserta sozinho (handler registrado por tipo).
   - `NEEDS_VISION` — não há medida determinística; enfileira render→FP-032 ACL e re-injeta
     o achado visual tipado no próximo ciclo.
   - `NEEDS_FELIPE` — veredito de APARÊNCIA final ou conserto que inventa geometria →
     `VISUAL_REVIEW_QUEUED`, **nunca auto**.
3. **Registry de fix-handlers determinísticos** (`tools/correction_fixes.py`): map
   `finding_type → handler(con, finding) -> FixResult`. Cada handler é *source-supported*
   (não inventa parede/móvel) e idempotente. MVP cobre os tipos que os gates atuais já
   emitem; tabela em §Algorithm.
4. **Wiring com o NOC**: cada ciclo que muda artefato roda escopado num **worktree isolado
   off `origin/develop`** via `noc_dispatcher`. Mudança determinística → commit+push branch;
   mudança de APARÊNCIA → `VISUAL_REVIEW_QUEUED` (igual hoje em `_appearance_changed`).
5. **Report no cockpit**: heartbeat por ciclo no `:8765` (`POST /heartbeat`, `cycle`
   monotônico) e o ledger NOC que o BFF já taila (`noc_mirror.py` → `/api/noc/ledger`,
   `/api/noc/status`). Slice de UI fora de escopo — só garantir que o estado do loop é
   **legível pelo que o cockpit já lê de arquivo**.

## Non-goals

- **NÃO** implementar o ACL de visão (render → `visual_findings.json`) — isso é **FP-032**,
  dependência dura. FP-033 só **consome** o contrato `visual_findings.v1` e **roteia** o
  achado; quando FP-032 não está pronto, a rota `NEEDS_VISION` degrada pra um stub honesto
  (enfileira o pedido, marca `BLOCKED_NEEDS_FP032`, não fabrica achado).
- **NÃO** auto-julgar aparência. Veredito IMPROVED/SAME/WORSE é **só do Felipe**
  (`visual_regression_gate.py` mantém o scaffold; o loop nunca preenche o VERDICT).
- **NÃO** auto-merge / push em `main` / mexer em worktree de sessão viva (Hard Rules do
  workspace + rails do `noc_dispatcher`).
- **NÃO** tocar fixtures de input (`fixtures/planta_74/`, `fixtures/quadrado/`) sem aprovação
  — a smoke suite pina contra elas (Hard Rule #3 do app).
- **NÃO** rodar `--mode headless` em dev local (proibido); rebuild do loop usa o modo
  interactive existente.
- **NÃO** construir novo dashboard/aba (slice de UI é outro front).

## Artifact contract

| Path | Mudança | Quem |
|---|---|---|
| `tools/correction_loop.py` | **NOVO** — máquina de estados + CLI (`--fixture --max-cycles --once --dry-run --room`) | loop driver |
| `tools/correction_fixes.py` | **NOVO** — registry `finding_type → handler`, `FixResult` dataclass, handlers determinísticos idempotentes | fix registry |
| `tools/finding_router.py` | **NOVO** — `classify(finding) -> Route{DETERMINISTIC_AUTOFIX\|NEEDS_VISION\|NEEDS_FELIPE}`; tabela source-of-truth dos tipos | classificador |
| `schemas/correction_finding.schema.json` | **NOVO** — finding tipado UNIFICADO (normaliza gate-determinístico + `visual_findings.v1` num só shape: `type, severity, source_check, suspected_owner, route, evidence`) | schema |
| `tools/run_deterministic_gates.py` | **EXISTE** — reusar `run_all()` como detector; **adicionar** `--json-out` p/ o loop consumir o dict de gates (hoje só printa) | gate suite |
| `tools/geometry_sanity.py`, `tools/furniture_overlap_gate.py` | **EXISTE** — reusar `audit()/overlap_gate()` como detectores de móvel; sem mudança de regra | gates móvel |
| `tools/run_skp_visual_review.py` | **EXISTE** — reusar como REBUILD+RE-CHECK determinístico (gera .skp + `geometry_report.json` + findings); o loop chama, não reescreve | runner FP-030 |
| `tools/claude_bridge/noc_dispatcher.py` | **EXISTE** — reusar `dispatch()`/`_appearance_changed`; **adicionar** `kind:"correction_cycle"` na fila roteado pra um ciclo do loop (sem duplicar o caminho de worktree/commit/VISUAL_REVIEW) | NOC actuator |
| `tools/claude_bridge/server.py` | **EXISTE** — reusar `POST /heartbeat` + `sessions_view()`; o loop bate ponto com `session_id` estável e `cycle` monotônico (sem mudança de servidor) | bridge :8765 |
| `apps/sketchup-mcp-bff/noc_mirror.py` | **EXISTE** — já taila ledger e filtra `VISUAL_REVIEW_QUEUED`; **opcional** adicionar contagem de `correction_cycle` no `status_view()` (read-only) | cockpit BFF |
| `.ai_bridge/noc/queue.jsonl` / `actions.jsonl` | **EXISTE** — formato reusado; o loop enfileira/auditoria pelos mesmos campos | ledger NOC |
| `tests/test_correction_loop.py`, `tests/test_finding_router.py`, `tests/test_correction_fixes.py` | **NOVO** — ver §Required tests | testes |
| `.claude/skills/autonomous-fidelity-loop/SKILL.md` | **EXISTE** — atualizar p/ apontar "o motor agora é `correction_loop.py`; a skill é o protocolo humano de supervisão" | skill |
| `docs/specs/FP-033_closed_correction_loop.md` | **NOVO** — esta spec | doc |

## Algorithm

```
# tools/correction_loop.py — máquina de estados (1 fixture, N ciclos)
run_loop(fixture, max_cycles, room=None, dry_run=False):
    sid = stable_session_id(fixture)          # p/ heartbeat :8765
    history = []                              # (cycle, findings_signature) — detector de patinagem
    for cycle in 1..max_cycles:
        heartbeat(sid, cycle, "detect")       # best-effort; falhou -> segue (nunca trava o trabalho)

        # 1. DETECT (determinístico, barato, consensus-only + móvel)
        findings = []
        det = run_deterministic_gates.run_all(fixture=fixture)      # shell: walls/openings
        findings += normalize_det(det)                              # -> correction_finding.schema
        findings += normalize(geometry_sanity.sanity_room(con, r))  # móvel-vs-cômodo
        findings += normalize(furniture_overlap_gate.overlap_gate(con, r))  # móvel-sobre-móvel
        # findings VISUAIS (se houver de um ciclo anterior que pediu visão):
        findings += pending_vision_findings(fixture)               # do FP-032, re-injetados

        if not findings:                       # backlog determinístico esgotado
            return state(CLEAN, "sem findings — laço fechado, parando (não inventa ciclo)")

        # 2. CLASSIFY — a inteligência nova
        for f in findings: f.route = finding_router.classify(f)

        # patinagem: assinatura idêntica à de 2 ciclos atrás e nada consertou
        sig = signature(findings)
        if stalled(history, sig):              # mesma assinatura 2x / nada commitado
            return state(STALL, f"patinando em {sig.top()} — parando, não insisto no escuro")
        history.append((cycle, sig))

        # 3. roteia — prioriza o que FECHA sozinho
        autofix = [f for f in findings if f.route == DETERMINISTIC_AUTOFIX]
        vision  = [f for f in findings if f.route == NEEDS_VISION]
        felipe  = [f for f in findings if f.route == NEEDS_FELIPE]

        if felipe:                             # aparência final / inventaria geometria
            enqueue_visual_review(fixture, felipe)   # noc -> VISUAL_REVIEW_QUEUED
            # NÃO bloqueia o ciclo se ainda há autofix a fazer; só marca

        if autofix:
            # 4. FIX (source-supported, idempotente)
            applied = []
            for f in sort_by_roi(autofix):
                fr = correction_fixes.apply(con, f)   # handler por tipo
                if fr.ok and fr.source_supported: applied.append(fr)
                else: f.route = NEEDS_FELIPE          # não consertou honesto -> sobe
            if applied:
                # 5. REBUILD + RE-CHECK (reusa o runner FP-030)
                heartbeat(sid, cycle, "rebuild")
                run_skp_visual_review(fixture, out=run_dir(cycle))   # .skp + report + findings
                post = run_deterministic_gates.run_all(fixture)
                if improved(post, det):  state_tag = PROGRESS
                else:                    revert(applied); state_tag = STALL  # piorou -> reverte (igual visual_regression: SAME/WORSE => revert)
                # wiring NOC: muda artefato -> worktree isolado off develop -> commit branch
                noc_commit_cycle(fixture, cycle, applied)            # NUNCA main/merge
                if state_tag == PROGRESS: continue
                return state(STALL, "fix não melhorou métrica determinística — revertido")

        if vision and FP032_available():
            enqueue_render_then_vision(fixture, vision)   # render -> FP-032 ACL -> re-injeta no próximo ciclo
            continue
        elif vision:
            return state(BLOCKED_NEEDS_FP032, "achado precisa de visão; FP-032 ausente")

    return state(MAX_CYCLES, "teto de ciclos — anti-runaway")
```

**Tabela de roteamento (source-of-truth do `finding_router`):**

| finding_type | origem (detector REAL) | rota | handler determinístico? |
|---|---|---|---|
| `wall_overlap` / duplicate wall | `wall_overlap_audit` (run_deterministic_gates) | DETERMINISTIC_AUTOFIX | dedup wall do consensus (já há lógica de canonicalização) |
| `opening_host_mismatch` | `opening_host_audit` | DETERMINISTIC_AUTOFIX | re-host opening na wall mais próxima (graph-based, source-supported) |
| `position_fidelity FAIL` (centro/largura/host) | `position_fidelity_gate` | NEEDS_FELIPE¹ | não — re-posicionar contra PDF = aparência |
| `furniture_overlap FAIL` (móvel-sobre-móvel) | `furniture_overlap_gate` | DETERMINISTIC_AUTOFIX | re-roda brain do cômodo / nudge documentado |
| `outside_room` / `blocks_door` | `geometry_sanity` | DETERMINISTIC_AUTOFIX | re-anchor móvel ao cômodo / clearance |
| `degenerate_bbox` / `absurd_bbox` / `off_axis` | `geometry_sanity` | DETERMINISTIC_AUTOFIX | escala/eixo: regenera box do brain |
| `floating_door` / `orphan_glass` / `bad_window_aperture` | `run_skp_visual_review` heurísticas | NEEDS_FELIPE² | não — conserto mexe em builder/.skp = aparência |
| `wall_stub` (residual) | `diagnose_wall_stubs` (FP-026) | NEEDS_VISION³ | parcial — FP-026 tem diagnóstico, mas confirmação é ambígua |
| `global_visual` / `scale_rotation` | `visual_findings.v1` (FP-032) | NEEDS_VISION | não — qualitativo, sobe pra visão e depois Felipe |
| veredito IMPROVED/SAME/WORSE final | `visual_regression_gate` | NEEDS_FELIPE | **nunca auto** (regra dura) |

> ¹ position_fidelity pode no futuro virar autofix se o ajuste for puramente determinístico
> contra a consensus (não contra o PDF); MVP = NEEDS_FELIPE pra ser honesto.
> ² esses tipos mudam o builder/.skp → APARÊNCIA → gate humano por construção.
> ³ enquanto FP-032 não existe, `wall_stub` cai em `BLOCKED_NEEDS_FP032` (não fabrica conserto).

## Acceptance

| Caso | PASS | WARN | FAIL |
|---|---|---|---|
| Micro-fixture com 1 `furniture_overlap` consertável | loop fecha em ≤2 ciclos, gate vira PASS, ledger registra PROGRESS→CLEAN | consertou mas deixou WARN documentado | não fecha / inventa geometria / muta fixture de input |
| Finding `floating_door` (aparência) | roteado p/ `NEEDS_FELIPE`, `VISUAL_REVIEW_QUEUED` no ledger, loop **não** auto-conserta | — | loop tenta auto-fix de aparência OU preenche veredito visual |
| Finding `global_visual` com FP-032 ausente | estado `BLOCKED_NEEDS_FP032`, pedido enfileirado, **nenhum** achado fabricado | — | inventa um finding visual / declara PASS visual |
| Patinagem (mesma assinatura 2 ciclos) | para com `STALL: <motivo>`, ledger honesto | — | continua girando no escuro / runaway |
| Fix piora a métrica determinística | reverte o patch, marca STALL (paridade com SAME/WORSE→revert) | — | mantém patch que piorou |
| Heartbeat :8765 offline | loop segue (best-effort), ciclo não trava | log nota `heartbeat skipped` | loop trava esperando o bridge |
| Mudança determinística limpa | commit em branch off develop via NOC, `COMMITTED` no ledger | — | push em main / auto-merge / worktree de sessão viva |
| Veredito final de aparência | sempre `NEEDS_FELIPE` | — | qualquer auto IMPROVED/SAME/WORSE |

## Required tests

| Teste | Tipo | Asserção |
|---|---|---|
| `test_finding_router::routes_furniture_overlap_to_autofix` | unit | `classify` de overlap → `DETERMINISTIC_AUTOFIX` |
| `test_finding_router::routes_appearance_types_to_felipe` | unit | `floating_door`/`orphan_glass`/veredito → `NEEDS_FELIPE` (nunca autofix) |
| `test_finding_router::routes_global_visual_to_vision` | unit | `global_visual`/`scale_rotation` → `NEEDS_VISION` |
| `test_correction_fixes::overlap_fix_is_idempotent` | unit | aplicar 2× = mesmo resultado; não muta input fixture |
| `test_correction_fixes::fix_is_source_supported` | unit | handler só usa dados da consensus; rejeita inventar parede/móvel |
| `test_correction_loop::closes_on_synthetic_overlap` | integração (micro-fixture) | detect→fix→re-check vira PASS em ≤2 ciclos |
| `test_correction_loop::stops_on_stall` | integração | assinatura repetida → `STALL`, não runaway |
| `test_correction_loop::reverts_when_fix_worsens` | integração | métrica pior → revert + STALL |
| `test_correction_loop::appearance_finding_queues_visual_review` | integração | `NEEDS_FELIPE` → `VISUAL_REVIEW_QUEUED` no ledger, sem auto-fix |
| `test_correction_loop::vision_blocked_without_fp032` | integração | `NEEDS_VISION` + FP-032 ausente → `BLOCKED_NEEDS_FP032`, zero achado fabricado |
| `test_correction_loop::heartbeat_offline_does_not_block` | integração | bridge mockado offline → loop completa o ciclo |
| `test_correction_finding_schema::normalizes_visual_findings_v1` | contract | `visual_findings.v1` e gate-determinístico normalizam pro mesmo shape |

> Determinismo (regra do workspace): nada de clock/random/ordem-de-dict — `signature()` e
> `sort_by_roi()` ordenam estável; ledger usa clock injetado nos testes.

## Done means

- [ ] `tools/correction_loop.py` roda 1 fixture e fecha o laço determinístico sozinho (sem humano no laço interno), com log por ciclo no formato da `autonomous-fidelity-loop`.
- [ ] `tools/finding_router.py` classifica todo finding em `DETERMINISTIC_AUTOFIX | NEEDS_VISION | NEEDS_FELIPE` pela tabela da §Algorithm; aparência final → SEMPRE `NEEDS_FELIPE`.
- [ ] `tools/correction_fixes.py` tem ≥1 handler determinístico REAL, idempotente e source-supported (MVP: `furniture_overlap`), com os demais tipos honestamente roteados (não stubados como "consertados").
- [ ] `schemas/correction_finding.schema.json` unifica gate-determinístico + `visual_findings.v1`; normalização testada por contract test.
- [ ] Patinagem PARA (2 ciclos sem progresso) e fix-que-piora REVERTE (paridade com SAME/WORSE→revert).
- [ ] Wiring NOC: ciclo que muda artefato passa pelo worktree isolado off develop, commit em branch (NUNCA main/merge); APARÊNCIA → `VISUAL_REVIEW_QUEUED`.
- [ ] Heartbeat por ciclo no `:8765` (`cycle` monotônico); offline = best-effort, não trava.
- [ ] Cockpit lê o estado do loop pelo que o BFF já taila (`noc_mirror`); nenhum achado visual fabricado quando FP-032 ausente (`BLOCKED_NEEDS_FP032`).
- [ ] Suíte verde (todos os testes da §Required tests) + 1 prova em planta real (micro-fixture → planta_74), terminando em decisão explícita (regra raiz canonical-artifact).
- [ ] Skill `autonomous-fidelity-loop` atualizada apontando pro motor `correction_loop.py`.
- [ ] PR contra `develop` (develop-first); nada de PR aberto ao fim.

## Reference

Lido e confirmado nesta sessão:
- `tools/run_deterministic_gates.py` — `run_all()`, exit PASS=0/FAIL=1/INCOMPLETE=3, gates opening_host/wall_overlap/render_bbox/wall_presence/railing/position_fidelity.
- `tools/geometry_sanity.py` — `audit()` (hermético) + `sanity_room()` (consensus): outside_room/blocks_door/degenerate/absurd/off_axis.
- `tools/furniture_overlap_gate.py` — `overlap_gate()`: móvel-sobre-móvel (footprint×altura), FAIL≥30% / WARN≥12%.
- `tools/visual_regression_gate.py` — scaffold IMPROVED/SAME/WORSE preenchido **só por humano** ("auto looks-like-PDF is exactly what the vision oracle was proven unable to do").
- `tools/run_skp_visual_review.py` + `schemas/visual_findings.schema.json` (v1) — findings tipados com `suspected_owner`/`proposed_fix`; **auto-fix é Follow-up não implementado** (FP-030 §Loop/§Follow-ups).
- `docs/specs/FP-030_visual_oracle_gate.md` — taxonomia de findings de aparência (floating_door, orphan_glass, bad_window_aperture, etc.) e axes qualitativos (global_visual, scale_rotation → WARN needs human/agent).
- `.claude/skills/autonomous-fidelity-loop/SKILL.md` — protocolo do ciclo (log, heartbeat, patinagem, parar em RED/NEEDS-HUMAN); hoje é prosa seguida à mão.
- `tools/claude_bridge/noc_dispatcher.py` — `dispatch()`, worktree isolado off origin/develop, `_appearance_changed` → `VISUAL_REVIEW_QUEUED`, NUNCA main/merge; `kind:local_llm` (Ollama, token=0); fila/ledger `.ai_bridge/noc/{queue,actions}.jsonl`.
- `tools/claude_bridge/server.py` — `POST /heartbeat` + `sessions_view()` com flags STALLED (>10min) / PARALYZED (`cycle` congelado 3 beats).
- `apps/sketchup-mcp-bff/noc_mirror.py` — read-only do ledger NOC; `/api/noc/ledger` filtra `VISUAL_REVIEW_QUEUED`, `/api/noc/status` dá lock/queue/task counts.
- `tools/fidelity_loop.py` — KPI Learning-Cycle-Time (FAIL→PASS por objeto); padrão de ledger reusável.
- **Depende de FP-032** (ACL de visão): FP-033 consome `visual_findings.v1` e roteia; sem FP-032 a rota `NEEDS_VISION` degrada honesto pra `BLOCKED_NEEDS_FP032`.