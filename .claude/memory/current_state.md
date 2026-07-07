# Current state — sketchup-mcp

> **Snapshot:** 2026-07-06. Verificar com `git`/`gh` antes de agir em
> decisões remotas — este arquivo decai rápido.

## Branch base & release

`develop` é a integration branch. `main` só recebe `develop` via merge
(Hard Rule #4 — nunca commitar/push direto em `main`).

- **`develop` @ `65427c4`** — tip canônico. Contém o programa completo
  **FP-032 → FP-040** (ver abaixo).
- **`main`** foi reconciliado com `develop` nesta sessão (2026-07-06) via
  release merge — antes estava ~115 commits atrás (o programa FP-032..040
  inteiro estava só em develop; último release anterior = PR #234, 21/jun).
- **CI existe** (`.github/workflows/ci.yml`, 3 jobs: `pytest` [3.11+3.12] ·
  `fidelity-gates` · `mcp-server`). Rodava **vermelho** por `jsonschema`
  ausente no `[dev]` do `pyproject` (4 testes novos importavam e a coleção
  abortava) — **corrigido nesta sessão** (`jsonschema>=4.18` no `[dev]`).
  Suíte hoje = **85 arquivos** de teste.

## O que foi entregue — programa FP-032 → 040 (jun/28 → jul/04)

Stack autônomo de melhoria de planta, sob a regra dura: máquina emite
`findings` tipados + roda gates determinísticos; veredito estético
`IMPROVED/SAME/WORSE` continua **só do Felipe** (VISUAL_REVIEW).

- **FP-032 Vision ACL** (live) — rota `/ask-vision` no `:8765`; o modelo vê
  o render e discrimina defeito real vs ruído (provado em prod).
- **FP-033 Correction Loop** (live) — detect→classifica→conserta o
  determinístico→re-checa; aparência sobe pro Felipe.
- **FP-034 Variant Sweep** (live) — eixos tipados + varredura SU-free +
  corpus julgado (nunca fabrica veredito → `PENDING_VISION`).
- **FP-035 RAG de design** — **única frente ainda aberta.** Só a metade de
  export (`corpus_to_rag.py`) landou; `retrieve()` + injeção no gerador em
  progresso (branch `feat/fp035-rag-retrieve`).
- **FP-036/037/038 Material de verdade** (done) — textura real por peça no
  `.skp` + material por (família, peça) + câmera de prova por cômodo.
- **FP-039 Fingerprint honesto v2** (done) — tiers reliable/advisory/forbidden.
- **FP-040 Bridge hardening** (live) — watchdog v3 (singleton + backoff +
  spawn capturado + BOM-safe) + `/health` com build-id.
- **Night loop** (live) — `night_feeder` capado + painel de 3 juízes no
  `/ask-vision` + `variant-vision-drain` fecham o laço sem clique humano.

## Baselines estáveis (não retrabalhar)

- **planta_74 canonical:** `artifacts/planta_74/planta_74.skp` (shell,
  escala `PT_TO_M=0.0259` travada 09/jun) + renders + report. Deliverable.
- **planta_74 mobiliada:** `artifacts/planta_74/furnished/planta_74_furnished.skp`
  (textura madeira no rack/mesa, FP-037, 01/jul).
- **quadrado canonical**, **runs/ vs artifacts/ convention**,
  **`--mode headless` proibido em dev local**, **opening routing invariants**
  pinados (4 windows / 7 doors / 1 glazed_balcony / 8 carves), **Constitution
  + #8 No-SKP-no-progress**.
- **`ops/latest/` (workspace)** espelha o último `.skp` gerado (hook Stop).

## Problemas abertos

- **Room fidelity = WARN** para `planta_74`: 8 cells fechadas vs 11 ambientes
  semânticos (open-plan funde r001/r002) — geometricamente honesto, não
  inventar paredes. Overlay `semantic_zones` em progresso nesta sessão
  (branch `feat/semantic-zones-overlay`); validação end-to-end precisa de
  SketchUp (não disponível em sessão remota).
- **DIFF-001** (consensus = autoria humana, sem extrator PDF→consensus, HIGH)
  — DEFERRED/roadmap (M4).
- **Higiene de branches NOC:** o `night_feeder`/dispatcher gera branches
  `chore/noc-*` efêmeras; podar as consumidas periodicamente (as `visdrain`
  carregam corpus único → drenar/arquivar antes de deletar).

## TODO — verificar live

- [ ] `git worktree list` — confirmar agentes ativos ANTES de op de
      branch/worktree (o tree principal `E:/Claude/apps/sketchup-mcp` pode
      estar em branch stale; ler fonte-da-verdade via `git show develop:<path>`).
- [ ] `gh run list --branch develop` — CI verde após o fix do `jsonschema`.
- [ ] NOC `:8765` → `/health` (build_sha12) + placar.
