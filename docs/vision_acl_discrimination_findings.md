# FP-032 — Placar de discriminação da ACL de visão (1ª fatia)

> Defeito injetado (determinístico, reproduzível): `erase_top_exterior_wall_segment`
> (`missing_wall_continuation`) no `planta_74_top.png`, rect=(500,200,900,224) preenchido
> com o cinza de fundo. Só o render é corrompido; consensus/geometry ficam idênticos.
> Pergunta: **qual backend de visão DISCRIMINA o render limpo do corrompido?**

## Resultado (rodado de verdade, 2026-06-30)

| Backend | Como | Resultado | Discrimina? |
|---|---|---|---|
| `qwen2.5vl:7b` (Ollama local) | `negative_dogfood.py --model qwen2.5vl:7b` | **NOT_DISCRIMINATED** — `PASS` no limpo E no corrompido | ❌ cego |
| `moondream:latest` (Ollama local) | `negative_dogfood.py --model moondream` | **INCONCLUSIVE_ORACLE_ERROR** — não devolve saída válida | ❌ inútil |
| **`claude_bridge`** (`:8765` `/ask-vision`, este PR) | POST `/ask-vision {prompt, images:[abs]}` → `claude -p` com `--add-dir` lê os renders | **DISCRIMINADO** — `DEFEITO_EM=B`, localizou: "parede externa superior do salão azul, gap onde em A a linha é contínua" | ✅ **o defeito exato** |
| **`claude_bridge_vision`** (pelo harness, 2026-07-01) | `negative_dogfood.py --backend claude_bridge_vision` (provider real → `/ask-vision`) | **DISCRIMINATED** — `clean=PASS` / `corrupted=FAIL` (primary+secondary); achado `missing_wall_continuation` "top perimeter wall of the central living room is discontinuous" | ✅ **placar automático** |

Evidência do run automático: `artifacts/review/planta_74/vision_acl_20260701T162323Z/`
(`discrimination_report.json` + `summary.md` + renders limpo/corrompido, hashes SHA-256).
Rodado contra um `server.py` FP-032 em `:8799` (o `:8765` vivo ainda é text-only — Hard Rule #1,
não se toca o cockpit vivo pra provar valor).

## Conclusão

**O olho confiável do sistema é o Claude via `/ask-vision`.** Os modelos de visão LOCAIS
(qwen2.5vl/moondream) NÃO servem como detector de regressão visual — não discriminam um
defeito estrutural evidente. Isso valida a arquitetura do FP-032: a ACL render→findings
roda no Claude (`:8765`), não no Ollama.

Isso NÃO muda o gate humano: o veredito visual FINAL (IMPROVED/SAME/WORSE) continua sendo
só do Felipe. A ACL emite **findings tipados** (achado + localização), não o veredito final.

## Estado do FP-032

**Fatia 2 (provider + placar automático) — FEITA.** `ClaudeBridgeVisionProvider`
registrado (`claude_bridge_vision`) em `tools/oracle_providers.py`; `negative_dogfood.py`
multi-backend (`--backend`/`--bridge-url`). O placar acima rodou pelo harness → DISCRIMINATED.

**Fatia 3 (schema + promoção + tests) — FEITA.**
- `schemas/visual_findings.schema.json` endurecido: `source`/`confidence`/`discriminated`
  opcionais (top-level + por finding), retrocompat provada (`tests/test_vision_acl.py`).
- `tools/run_skp_visual_review.py`: **regra de promoção** — um FAIL de oráculo só endurece o
  gate se o backend foi provado DISCRIMINATED (`load_latest_discrimination` +
  `promote_oracle_verdict`); senão degrada pra WARN (sinal fraco, registra, não bloqueia).
  Todo finding de oráculo carrega `source`; o merged registra
  `oracle_discriminated`/`discrimination_result`/`oracle_verdict_effective`.
- 20 testes novos (`tests/test_vision_acl.py`) + suíte cheia verde (980 passed).

**Fatia 1 (deploy no `:8765` vivo) — PENDENTE (mão do Felipe/infra).** O `:8765` vivo usa o
`server.py` do repo MAIN (text-only, sem `/ask-vision`). Restart seguro: `Stop-Process` no PID
da `:8765` e DEIXAR o `gate-watchdog` relançar (`ops\bridge\subir-noc.ps1`) — NUNCA subir manual
em paralelo, NUNCA remover worktree referenciada (Hard Rule #1: já derrubou o `:8765`). Depois do
deploy, `run_skp_visual_review --oracle claude_bridge_vision` usa a URL default (`:8765`) e a
promoção fica ativa em produção. O `:8765` andou instável (stall do watchdog) — endurecer é fatia à parte.

> Nada disto muda o gate humano: o veredito visual FINAL (IMPROVED/SAME/WORSE) continua só do
> Felipe (chrome-only). A ACL emite findings tipados, nunca o veredito de aparência.
