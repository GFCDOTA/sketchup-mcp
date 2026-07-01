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

## Conclusão

**O olho confiável do sistema é o Claude via `/ask-vision`.** Os modelos de visão LOCAIS
(qwen2.5vl/moondream) NÃO servem como detector de regressão visual — não discriminam um
defeito estrutural evidente. Isso valida a arquitetura do FP-032: a ACL render→findings
roda no Claude (`:8765`), não no Ollama.

Isso NÃO muda o gate humano: o veredito visual FINAL (IMPROVED/SAME/WORSE) continua sendo
só do Felipe. A ACL emite **findings tipados** (achado + localização), não o veredito final.

## O que falta no FP-032 (próxima sessão — plumbing)

1. **Publicar o `server.py` (com `/ask-vision`) no `:8765` que roda** — o vivo usa o
   `server.py` do repo MAIN, não o desta worktree. Flow de restart (`subir-noc.ps1`).
   ⚠️ O `:8765` andou instável hoje (stall do watchdog) — endurecer é uma fatia à parte.
2. **`ClaudeBridgeVisionProvider`** em `tools/oracle_providers.py` (reusa `_build_compact_prompt`
   + `_extract_first_json_object` + `_normalize_to_visual_findings`; transporte = POST
   `/ask-vision` em vez do Ollama `/api/generate`) + registrar em `get_provider` + `--provider`
   no `negative_dogfood` → o placar acima roda pelo harness, automático.
3. **Schema** `schemas/visual_findings.schema.json`: `confidence`/`source`/`discriminated` +
   tests + integrar em `tools/run_skp_visual_review.py` (parar de rebaixar
   `global_visual`/`scale_rotation` pra WARN quando o backend foi provado discriminativo).

Base commitada nesta branch (`feat/vision-acl`): a rota `/ask-vision` + `ask_claude_vision`.
