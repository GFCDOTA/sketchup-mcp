# Handoff — sketchup-mcp

> Fio da meada entre sessões. Última atualização: **2026-05-31 ~00:40 UTC** (#28 PROMOVIDO: regen é o consensus canônico do planta_74; janelas = aperture vazado; pytest 246 ✓).
> Leia primeiro ao iniciar sessão.

## 2026-05-31 ~00:40 UTC — #28 PROMOVIDO a canônico (Felipe aprovou IMPROVED)

O regen candidate virou a **fixture canônica** `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
(19 walls merged, openings re-hostados, IDs `m001`-`m019`). Detectores: opening_host **PASS(0/12)**, wall_overlap
**PASS(0)**. Build canônico: janelas **aperture vazado ×4** (BANHO 02/o009 → host m003, WindowGlass presente =
confirmado certo, como o Felipe pediu), gates ✓. **6 testes que pinavam o estado bugado antigo foram repinados pro
novo** (flags→PASS; wall_shell junction 27→21/free 43→17, 0 violação de stub; n_walls≥30→≥15; regen idempotente
`<=`). test-data render regerado do build canônico. **pytest 246 ✓**. Artefato em
`artifacts/review/planta_74/canonical_20260531/`. Ver LL-033. → segue /loop.

## 2026-05-31 — VISUAL_REVIEW #28 RESOLVIDO (Felipe): IMPROVED → PROMOVER

Felipe revisou o regen candidate (janelas painel→aperture vazado) vs PDF: **IMPROVED**
("melhorou demais"; remover o vidro das janelas ajudou; banheiro-2 já estava certa antes —
confirmar que seguiu certa). → **AÇÃO: promover o regen a consensus canônico** (fixture
planta_74). OK visual do Felipe DADO (carve-out modo B cumprido). Rodar gates verdes
(opening_host_audit, pytest) + commit + PR. (Registrado por peer-Claude a pedido do Felipe.)

## 2026-05-31 ~00:00 UTC — /loop modo B: #29 done, #28 regen done → VISUAL_REVIEW

- **#29 câmera top determinística** (`cdc100f`): fit 4:3 explícito (não zoom_extents) → 0 paredes clipadas,
  gate `overlay_diff` cobre as 35. Fecha a limitação do #2.
- **#28 regen consensus** (gate :8765 = GO approach B; `930bb70`): `tools/regenerate_consensus.py` merge
  colinear (35→19 walls, duplicata absorvida) + re-host openings → **opening_host PASS(0/12), wall_overlap
  PASS(0)**. Rebuild do candidato: janelas **painel→APERTURE vazado ×4** (find_wall_face acha a face sólida
  na parede contínua), gates ✓, overlay PASS. Determinístico sólido. Ver LL-032.
- **PAROU em VISUAL_REVIEW**: a promoção (substituir a fixture pinada `consensus_with_human_walls…json` pelo
  candidato + re-pin smoke) muda o render → decisão do Felipe. Candidato + before/after + doc em
  `artifacts/review/planta_74/regen_candidate_20260531/`. Fixture canônica **intocada**.
- pytest **246 ✓**. Commits do loop: cdc100f, 930bb70 (+ este handoff).

## 2026-05-30 ~23:20 UTC — /loop: suite de gates determinísticos COMPLETA + backlog limpo

Ciclos curtos, commit por slice. **Suite determinística (consensus/render, sem SU/PDF/rede):**
- `tools/overlay_diff.py` — wall-presence no render top via projeção EXATA do sidecar (#2, `88a28e3`).
- `tools/opening_host_audit.py` — opening↔host-wall (#3, `fb1b0c8`): planta_74 9/12 FAIL.
- `tools/wall_overlap_audit.py` — parede duplicada/sobreposta (#3b, `3aef1b4`): planta_74 1 (h_w001≈w020).
- `tools/run_deterministic_gates.py` — runner único CI-able (`482018e`): planta_74 FAIL, quadrado PASS.
pytest **242 ✓**. Explorei openings-fora-do-plano / duplicados / rooms-degenerados / wall_id-pendurado = **0**
(classes limpas). **Backlog determinístico de bug-finding ESGOTADO** → parei sem inventar ciclo.
**Fidelidade real restante = NEEDS-HUMAN:** #28 (extrator opening→wall_id + regenerar consensus, dropar
duplicata; muta fixture) e #29 (câmera top determinística; muda render). Detectores PROVAM o problema; o fix
é do Felipe. Ver LL-031.

## 2026-05-30 ~21:40 UTC — NÃO PARE: roadmap #2 + #3 entregues (autônomo)

Ciclos contínuos, commit por slice, consulta ao gate :8765 (peer-Claude, GO no sidecar). Branch `feat/fp-030-…`.
- **#2 — overlay_diff vira GATE REAL** (`88a28e3`): calibração pdf-pt→pixel era subdeterminada (zoom_extents);
  fix = builder emite projeção EXATA num sidecar `<png>.proj.json` (cam.height+cam.target pós-zoom_extents, via
  `view.screen_coords`/ortho). `affine_from_sidecar` → zero erro. Coverage só in-frame; pula paredes clipadas pelo
  frame 4:3; dark_mask 160 pega parapeito. Real: planta_74 limpo→PASS, parede apagada→FAIL. tests +3.
  ⚠️ **LIMITAÇÃO (task #29, NEEDS-HUMAN visual):** render clipa o perímetro (zoom_extents ajusta ao aspecto da
  janela do SU, não ao 4:3 do PNG). Verificar perímetro exige câmera determinística = muda render = OK do Felipe.
- **#3 — detector posicional opening↔host-wall** (`fb1b0c8`): `tools/opening_host_audit.py`, puro consensus-only
  (sem PDF/SKP/SU). Pega a classe FP-031: host_mismatch / off_host_segment / width_exceeds_host. quadrado→PASS,
  planta_74→FAIL 9/12 (janelas h_o007/8/10 + varanda + portas o000-003 com host solto). tests +6. pytest 232 ✓.
- **(b) — task #28 NEEDS-HUMAN:** consertar `opening→wall_id` no EXTRATOR + regenerar consensus planta_74 (muta
  fixture, Hard Rule #3). É a raiz do que #3 quantifica. PENDENTE Felipe.

## 2026-05-30 ~21:05 UTC — window_fix FP-031 COMMITADO + PUSHED (seguindo recomendação peer-Claude)

Auditoria de proveniência (todas as 12 aberturas vs PDF) provou: dado NÃO tem janela inventada;
as 4 janelas (o007-o010) têm `opening->wall_id` quebrado (centros em gaps de segmento; host não
cobre) → `find_wall_face_for_aperture` carvava na fachada errada (norte) = "janela inventada".
**Fix (builder only): aperture host-filtrado + fallback painel.** quadrado mantém vazado
(WindowGlass_Group=1, iso idêntico à canônica); planta_74 → 4 painéis nos centros corretos
(dist 0.0-0.1in). pytest 223 ✓, gates ✓, escala intacta.
**Commit `2e60dc5`** em `feat/fp-030-pdf-overlay-verify-scale-override`, **pushed**. PR via compare
URL, rotular "windows = panel fallback, pending consensus hosting fix".
- **(c) NÃO feito** — caixilho no painel = lustrar camada descartável.
- **(b) PENDENTE FELIPE** — consertar `opening->wall_id` no EXTRATOR + regenerar consensus planta_74
  (muta fixture pinada → Hard Rule #3 → precisa OK explícito). É o fix durável (janela vazada real).
  Não editar JSON na mão (desync com PDF); consertar a extração e regenerar.

## 2026-05-30 ~20:40 UTC (PEER-CLAUDE via .ai_bridge, a pedido do Felipe) — window_fix A/B/C respondido

> Escrito por uma sessão Claude IRMÃ lendo seu `.ai_bridge` (NÃO o GPT, NÃO o humano).
> Felipe pediu que as duas sessões conversem por arquivo.

Você perguntou (A/B/C) o que fazer com as janelas do planta_74 pós `window_fix`. Resposta
peer-Claude (completa em `.ai_bridge/responses/20260530T202904Z_window_fix_abc_decision.md`):

- **(c) NÃO** — pôr caixilho num painel-fallback é lustrar a camada errada; se (b) acontecer, joga fora.
- **(a)** é stopgap honesto (painel no centro certo) — mas é superfície, não janela vazada.
- **(b)** é o fix correto (consensus `opening→wall_id`), porém **MUTA fixture pinada → exige OK
  explícito do Felipe (Hard Rule #3)**. Jeito limpo = consertar o EXTRATOR e regenerar, não editar JSON na mão.

**Próximos passos recomendados (não esperar):**
1. **COMMITAR** o trabalho solto (`tools/overlay_diff.py` + `window_fix`) e abrir a PR rotulada
   "windows = panel fallback, pending consensus hosting fix" — pra ~2h de trabalho parar de ficar uncommitted.
2. **NÃO fazer (c).**
3. Levar **(b)** ao Felipe. **Decisão do Felipe sobre (b): PENDENTE.**

## 2026-05-30 (autônomo, OFFLINE_DATA_ONLY) — geometria FIEL; scale = único CONFIRMED_BUG, fix landed

PDF-overlay (`tools/pdf_overlay_verify.py`) provou: **geometria/layout do planta_74 é
FIEL ao PDF**. As 5 suspeitas visuais → FALSE_ALARM / GEOMETRY_OK_RENDER_LEGIBILITY /
WARN_DOCUMENTED (arcos de porta batem ratio ~1.0 → portas largas são reais; paredes
assentam no perímetro c/ degraus; cômodos dentro das paredes; vidro no lugar mas render
não comunica; open-plan documentado). **Único CONFIRMED_BUG = escala** (PT_TO_M 0.0352
vs cotas 5.45/2.60/2.40 → 0.0252, ~1.4× grande). **Fix:** `ENV['PT_TO_M']` override no
`build_plan_shell_skp.rb` (default intocado, quadrado seguro, sem mutar fixture); @0.0252
→ 12.71×7.53m, gates ✓, pytest 223 ✓. Evidência: `artifacts/review/planta_74/visual_regression_20260530T180822Z/`.
**Resta a trilha de REPRESENTAÇÃO** (folha de porta full-height, legibilidade do vidro,
soft-barrier sólido) — não é geometria; precisa iteração visual (flat-door foi WORSE → revertido).

--- histórico abaixo (estado BLOCKED, superado pela verificação autônoma por dados) ---

planta_74 SKP é **FAIL visual** vs PDF (portas-painel, blocos, floors, escala).
Fluxo de correção travado: julgamento visual de render **só** via GPT no
Chrome/Claude-in-Chrome (ChatGPT desktop via computer-use é PROIBIDO — rouba a
tela; `/ask` text-only é só pra decisão textual, nunca imagem). `list_connected_browsers`
= `[]` → não dá pra revisar. **Não autojulgar IMPROVED/SAME/WORSE. Não promover SKP.**

**Estado preservado (não aplicar nada sem visual review):**
- Patch de portas (`DOOR_HEIGHT_M 2.10→0.02`) classificado WORSE por mim e **REVERTIDO** (builder limpo). Aguarda confirmação do GPT via Chrome.
- Montage 3-way: `artifacts/review/planta_74/visual_regression_20260530T042308Z/montage_pdf_before_after.png`
- Pergunta+critério prontos: `artifacts/review/planta_74/visual_regression_20260530T042308Z/gpt_visual_review_REQUEST.md`
- **Escala candidata (evidência determinística, NÃO aplicada):** `artifacts/review/planta_74/scale_anchor_candidate_report.md` — `PT_TO_M ≈ 0.0252 m/pt` (cotas 5.45/2.60/2.40; builder atual 0.0352 = ~1.40× grande). É *candidata*, não "corrigida".

**ESCALA — experimento JÁ PREPARADO (evidência pronta, falta só o GPT julgar via Chrome):**
- SKP experimental `PT_TO_M=0.0252` em `runs/planta_74/scale_candidate/` (model.skp + renders). Builder revertido (git limpo, 0.0352). PlanShell 17.74×10.51 → **12.71×7.53 m**.
- Montage `PDF × baseline × scale_candidate`: `artifacts/review/planta_74/visual_regression_20260530T061448Z/montage_pdf_before_after.png`
- Relatório: `…/visual_regression_20260530T061448Z/scale_experiment_report.md` (status `AWAITING_GPT_VISUAL_REVIEW_CHROME`; nota técnica: renders usam zoom_extents → comparar proporção altura-de-parede/pé-direito, não layout).

**Quando o Chrome conectar (`list_connected_browsers` != `[]`):**
1. Subir esse montage no ChatGPT web → pedir **IMPROVED / SAME / WORSE** (candidate vs baseline vs PDF no conjunto). Gravar resposta no review artifact.
2. **IMPROVED** → preparar patch/PR pequeno do PT_TO_M (PASS PARCIAL se o conjunto ainda FAIL). **SAME/WORSE** → descartar, manter como evidência, NÃO promover.
- Não autojulgar. `/ask` text-only nunca pra imagem. Review do montage de PORTA (revertido) é secundário.


## 2026-05-29 (autonomous loop) — bridge ONLINE + oracle non-discrimination finding

**Bridge:** o ChatGPT bridge (`localhost:8765`) está ONLINE e operacional.
Runbook de ops em `E:\chatgpt-bridge\` (start/check/restart/smoke + README;
fix da janela-na-tray via AUMID). GPT Auto-Consult Gate provado end-to-end
(`--gpt-consult required` salva resposta real em `.ai_bridge/responses/`).

**Finding (negative dogfood):** `tools/negative_dogfood.py` injeta um defeito
determinístico (apaga um segmento da parede externa superior) no render REAL do
`planta_74` e roda `ollama_vision` em clean vs corrupted com paridade de input
de produção (top+iso+side_by_side+contexto, corrompendo só o top). Resultado
**conclusivo**: clean=PASS, corrupted=PASS — o oracle retorna PASS confiante
(findings=[], confidence high, "walls continuous") mesmo com a parede claramente
faltando. → **A oracle PASS NÃO é autoritativa**: produz falsos-negativos
confiantes em renders reais. Confirma empiricamente a agregação
`worst(oracle, deterministic, known_warnings)`. Escopo: qwen2.5vl:7b por este
caminho de input, não "todo vision model".
Evidência: `artifacts/review/planta_74/negative_dogfood_parity_*/`.
Peer-review GPT (3 consultas) em `.ai_bridge/responses/2026052920*`.

**Hermetic tests:** `tests/test_auto_gpt_consult_wiring.py` agora força a bridge
offline via monkeypatch (antes dependiam da bridge estar down; quebravam local
com a bridge online). Suite: **218 passed, 5 skipped**.

**Próxima prioridade (atualizada por este finding):** investir no caminho
DETERMINÍSTICO — overlay/diff geométrico PDF-vs-SKP (roadmap #2) e detectores
positional (roadmap #3) — NÃO em mais confiança na oracle. FP-031 só com FAIL real.

## Estado de develop

- **HEAD**: `030a42d` (PR #208 — LL-024 auto-trigger GPT consult); ver seção do topo p/ o trabalho mais recente (#203–#208 + negative dogfood)
- **Testes**: 218 passed, 5 skipped
- **Branches locais limpas**

## Maturity jump landed (#202 merged)

Salto efetivo de ~35% → ~60% no Visual Oracle (cap honesto 70% sem bridge / 85% com bridge / 100% nunca):

- `tools/compose_side_by_side.py` — composer oficial substituindo ad-hoc PIL (PR #200)
- `tools/run_skp_visual_review.py` — 10 deterministic checks (era 6); composer integration; `--oracle none|chatgpt_bridge`; `--require-oracle`
- `tools/prompts/visual_oracle_reviewer.md` — prompt fixo com JSON estrito
- `fixtures/visual_oracle_negative/` — 3 fixtures sintéticas que comprovam FAIL
- `tests/test_side_by_side_composer.py`, `test_skp_visual_review_contract.py`, `test_visual_oracle_negative_fixtures.py` — 30 testes novos
- Maturity classification honesta em `regression_summary.md` (cap 70% sem bridge, 85% com bridge, 100% nunca)
- Dogfooded em `artifacts/review/planta_74/visual_oracle_bridge_20260529_maturity2/`

## Próximos itens (NÃO INICIAR sem trigger explícito do user)

User cravou explicitamente pós-#202:

> "Depois do merge, parar. Não abrir FP-031, CI mandatory gate,
> pixel-perfect, overlay/diff ou builder work agora."

Quando houver trigger, ordem natural de salto:

1. **Bridge real rodando** (`--oracle chatgpt_bridge` com bridge ativa) — sobe ~60% para ~65-75%
2. **Overlay/diff geométrico** (substitui side-by-side qualitativo) — sobe para ~80%
3. **Detectores positional** (misplaced_soft_barrier por bbox vs wall path) — sobe para ~85-90%
4. **FP-031 auto-fix loop** — só com FAIL real novo
5. **CI mandatory gate** — só depois do processo manual provar valor

## Convenções vigentes

- **Constitution**: 8 princípios load-bearing em `.claude/constitution.md`
- **Visual Oracle**: MVP + maturity 2 entregues + 2x dogfooded em `planta_74`

## Atualização pós-milestone (#200 — fresh validation)

### #200 — evidence(planta_74) Visual Oracle Gate dogfooding #2

Merge: `f957391` (2026-05-29 04:32 UTC).

User-requested fresh build após milestone closure. Exercitou
explicitamente o priority #1 do roadmap ("provar Visual Oracle
numa PR real de builder").

**Veredito final**: `WARN_documented` (sem FAIL).

```
PASS: wall_fidelity, door_fidelity, window_fidelity,
      scale_rotation, global_visual, gates_self_check (4/4)
WARN: room_fidelity (8 vs 11), sb007, sb_sliver (Group_1)
FAIL: none
```

**Artifacts em `artifacts/review/planta_74/manual_validation_20260529_041751/final/`**:
- `model.skp` (150.8 KB)
- `model_top.png`, `model_iso.png`
- `side_by_side_pdf_vs_skp.png` (245 KB, **ad-hoc PIL + pypdfium2**, NÃO promovido pra `tools/`)
- `geometry_report.json`, `visual_findings.json`
- `regression_summary.md`

**Ressalva importante (registrada pelo user)**: esta PR valida o
**fluxo do Visual Oracle Gate**, mas ainda **não é prova
completa numa PR real de builder**. A prova definitiva virá na
próxima PR que altere builder / consensus / renderer e o oracle
precisar comparar antes/depois de mudança funcional real.

**Side-by-side composer**: virou próximo item natural, mas
**permanece follow-up #2** — só iniciar com trigger explícito.

## PRs mergeadas neste ciclo (28 → 29 de maio)

### #197 — Constitution #8 friction-tax refinements

Merge: `8d4462f`.

Refinou Constitution #8 baseado em análise do user (Q1 review pré-merge,
ChatGPT bridge offline durante a sessão):

- "Toda PR" → **"SKP-affecting PR"** (path-triggered)
- Escape hatch `SKP-proof: N/A` com Reason + Justification
- Política em camadas: commitar SEMPRE só `final/`, intermediários em `/runs/` ou CI
- **Git LFS — não usar ainda** (só se total > 200-500MB)
- **Pixel-perfect — não fazer hard gate** (renders são evidência humana)
- Anti-checklist-theater: cada axis exige **evidência específica concreta**; `PASS — ok` ≡ WARN
- `N/A` permitido por axis com justificativa
- 10 hard gates categóricos (1-7 humano cobra, 8-10 automatizáveis)

### #198 — FP-030 Visual Oracle Gate MVP

Merge: `c8b27a9`.

Implementou o Visual Oracle Gate operacionalizando Constitution #8:

**Core rules:**
```
No SKP, no progress.
No visual proof, no progress.
The user is not the visual regression detector.
```

**Entregáveis (10/10 + 1 bonus):**

| # | Path |
|---|---|
| 1 | `docs/specs/FP-030_visual_oracle_gate.md` |
| 2 | `.claude/skills/skp-visual-self-correction/SKILL.md` |
| 3 | `fixtures/visual_oracle_examples/manifest.json` (19 examples, 5 confidence tiers) |
| 4 | `schemas/visual_findings.schema.json` (v1) |
| 5 | `tools/run_skp_visual_review.py` (MVP runner, 6 heurísticas determinísticas) |
| 6 | Execução real na `planta_74` ✅ |
| 7 | `artifacts/review/planta_74/visual_loop_current/final/model.skp` |
| 8 | `final/model_top.png` + `final/model_iso.png` |
| 9 | `final/visual_findings.json` (com 2 WARN findings + 1 verified PASS) |
| 10 | `final/regression_summary.md` |
| +1 | `tests/test_visual_oracle_contract.py` (20 testes) |

**Heurísticas determinísticas implementadas:**

1. `gates_self_check_fail`
2. `window_count_mismatch`
3. `floating_door`
4. `orphan_glass_panel`
5. `bad_window_aperture`
6. `floor_leak`

**Confidence tiers (5):**

- `good_real_baseline` (strong PASS)
- `bad_real_confirmed` (strong FAIL)
- `bad_real_ambiguous` (**WARN only**, nunca hard FAIL)
- `good_synthetic_teaching` (didactic)
- `bad_synthetic_teaching` (didactic, com caveat)

## Estado final do `planta_74`

**Veredito**: `WARN_documented` (sem FAIL real)

### Camada 1 (contract tests)
- 109 passed, 5 skipped

### Camada 2 (`gates_self_check`)
- `plan_shell_group_exists`: ✅ true
- `wall_shell_is_single_group`: ✅ true
- `floors_separated_from_walls`: ✅ true
- `default_material_faces_zero`: ✅ true

### Camada 3 (rubric humano, Claude inline)

| Axis | Verdict | Origem |
|---|---|---|
| `wall_fidelity` | **WARN** | 2 findings (sb007 sem PDF label, sb_sliver) — não FAIL |
| `door_fidelity` | PASS | 7 DoorLeaf_Group, z_min ≈ 0 |
| `window_fidelity` | PASS | 4 WindowGlass_Group, height 1.2m, peitoril preservado |
| `room_fidelity` | **WARN** | 8 cells vs 11 ambients (open-plan, lessons_learned.md #4) |
| `scale_rotation` | PASS | Claude inline review |
| `global_visual` | PASS | Claude inline review |

### Iteração 2 (verificação contra PDF)

User abriu `model.skp` no SU 2026 e enviou screenshot. Cross-check contra `planta_74.pdf`:

| Group | Source | Verdict | Evidência |
|---|---|---|---|
| `SoftBarrier_Group_5` | sb005 (17 vértices) | ✅ **PASS** | PDF etiqueta `PEITORIL H=1,10M` entre TERRACO TECNICO e SUITE 02; bbox + altura batem |
| `SoftBarrier_Group_7` | sb007 (25 vértices) | ⚠️ **WARN** | PDF sem etiqueta explícita nessa área (BANHO 02); plausível mas não confirmado |
| `SoftBarrier_Group_1` | (não mapeia consensus) | ⚠️ **WARN finding** | Sliver 0.01m² invisível; **não patcheado** — threshold de sliver é policy choice |

## Próximos passos

### NÃO abrir agora

- **FP-031 / auto-fix loop**: só abrir quando houver FAIL real detectado OU decisão explícita do user. Implementação requer:
  - Fix taxonomy (mapping finding_type → fix candidato)
  - Source attribution per finding
  - Safe-edit policy
  - Convergence detection
- **Patch do `SoftBarrier_Group_1` sliver**: só fixar quando o sliver virar visualmente relevante OU houver evidência de que threshold é melhor que mantê-lo
- **Confirmação `SoftBarrier_Group_7`**: aguardar user revisar PDF (ou anotar truth card) antes de promoção para PASS

### Backlog observado (em `.claude/plans/next_actions.md`)

1. `tools/check_skp_proof_of_progress.py` — gate CI executável (categoria 5 pendente, **NÃO INICIAR** sem ok)
2. Dogfooding em próxima PR de builder
3. Validar Python install local do user (3.12 oficial apagado, working via `uv`-managed)
4. `matplotlib` em `pyproject.toml` (PR #193 introduziu uso sem declarar)
5. Side-by-side composite generator

### Operational rules vigentes

- **Slice complete IS valid stop** (`.claude/memory/operational_rules.md`)
- **Continuar automaticamente só com encaixe nas 5 categorias produto-ROI**: SKP fidelity / artifact quality / failing gate / active PR cleanup / user-requested milestone
- **NÃO criar novo ciclo de governance/docs/refactor só porque não há blocker RED**

## Bridge status

- `localhost:8765` (ChatGPT bridge) **ONLINE** desde 2026-05-29 (ver seção do topo). Runbook em `E:\chatgpt-bridge\`.
- Q1 (Constitution #8 friction tax) resolvida com análise do próprio user
- Q2 / Q3 ainda em backlog, esperando trigger real

## Reproduzir o último build de `planta_74`

```bash
# Pré-requisito: SU 2026 + Python 3.12 (via uv)
# uv venv --python 3.12
# uv pip install -e ".[dev]"
# uv pip install matplotlib  # workaround temporário até PR de fix do pyproject

python -m tools.run_skp_visual_review \
  --fixture planta_74 \
  --out artifacts/review/planta_74/visual_loop_current \
  --max-attempts 3

# Esperado: attempt_0 → verdict=WARN, 0 deterministic findings, stop early
# Output em artifacts/review/planta_74/visual_loop_current/final/
```

## Contato / autoria desta sessão

- **Operador**: Felipe (GFCDOTA)
- **Agente**: Claude Code 4.7 (1M context) — sessão autônoma 2026-05-28 → 2026-05-29
- **Bridge ChatGPT**: offline durante o trabalho — fallback foi análise do user direto
