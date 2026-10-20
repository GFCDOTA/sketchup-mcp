# FP-044 — Validação final (raiz e `tools/`)

**Data:** 2026-10-20. **Estado global:** `PARTIAL` — **não** declarar a FP-044 concluída.
**Base verificada:** `develop` @ `ce25e8c` (merge do #335). Documento técnico; **não** é `VISUAL_REVIEW`.
**Spec:** [FP-044](../specs/FP-044_root_and_tools_consolidation.md) · **Decisões:** [FP-043_open_decisions](../specs/FP-043_open_decisions.md)
(D-001…D-012) · **Contrato do que fica em `tools/*.py`:** [`tools/PUBLIC_API.md`](../../tools/PUBLIC_API.md) ·
**Evidência L2:** [`artifacts/review/fp044/f7_l2_20261020/`](../../artifacts/review/fp044/f7_l2_20261020/README.md).

## 1. Por fatia

| Fatia | PR | Merge | Resultado | CI |
|---|---|---|---|---|
| spec | #320 | `1f63549` | spec + `fp044_tools_facades.v1.json` | 4/4 |
| F0 guards + baseline | #321 | `362d011` | `test_fp044_root_guard` (raiz e `tools/*.py` só encolhem), `fp044_baseline` | 4/4 |
| F1 README/mapa | #322 | `1beb78e` | documentação fiel; `test_fp044_readme` | 4/4 |
| F2 sofá sai da raiz | #323 | `6d44833` | `configs/ renders/ textures/` → donos (63 R100 + spec V-Ray R077); 3 fachadas de `scripts/` removidas; README de proveniência em `sofa_program/{check,sofa_vray}` (padrão D-006) | 4/4 |
| F3 schemas | #324 | `b113177` | `schemas/` → `core/schemas/` (8 R100 + 1 só caminho na descrição); `core.schemas.{SCHEMA_DIR,schema_path,load}`; `test_fp044_schemas` | 4/4 |
| F6 `sketchup/*` | #325 | `1bf82d8` | 3 fachadas; `tools/PUBLIC_API.md`; `test_fp044_tools_facades`; D-011 | 4/4 |
| F6 `interior_studio` | #326 | `bb98725` | 3 | 4/4 |
| F6 `rooms/bathroom` | #327 | `0f5a96c` | 4 | 4/4 |
| F6 `rooms/bedroom` | #328 | `ec4c12e` | 5 | 4/4 |
| F6 `rooms/kitchen` | #329 | `a0e81b8` | 6 (CLI do `kitchen_validation` movida para `anchor_rules.main`, saída e exit code idênticos) | 4/4 |
| F6 `rooms/living` | #330 | `abcee11` | 12; D-012 (`sofa_class_matrix` fica) | 4/4 |
| F6 `rooms/shared` + `service` | #331 | `095ac6a` | 13 | 4/4 |
| F6 `validation` | #332 | `4079341` | 24 | 4/4 |
| F6 `rendering` | #333 | `0543eb2` | 13 | 4/4 |
| F6 `orchestration` | #334 | `9c0ecac` | 10 | 4/4 |
| F6 `knowledge` + `oracle` | #335 | `ce25e8c` | 15 | 4/4 |
| F4 front do estúdio | — | — | **não executada**: depende da D-009 (Felipe) | — |
| F5 `.impeccable/` | — | — | **não executada**: depende da D-008 (Felipe) | — |

CI = pytest py3.11, pytest py3.12, deterministic fidelity gates, MCP smoke + stdio — merge só com os 4 verdes
(`waitmerge.sh`). Nenhum merge direto em `main`; nenhum PR aberto ao fim.

## 2. Antes × depois

| | Antes (`develop` @ `1f63549`, baseline F0) | Depois (`ce25e8c`) |
|---|---|---|
| Pastas na raiz | 20 | 16 — saíram `configs/ renders/ textures/ schemas/`; ficam `.impeccable/` (D-008), `ops/` (D-009), `scripts/` (só `set_clipboard_image.ps1`, D-005) |
| `tools/*.py` | 123 | **15**: 8 públicas + `furnish_plan`/`trace_view` (D-003/D-004) + 4 lidas pelo Inspector do harness (D-011) + `sofa_class_matrix` (D-012) |
| Fachadas aposentadas | — | 108 (`REMOVED` no JSON de fachadas; mapa P0 `path_resolver_unico`) |

Método da F6, por lote: identidade `tools.X is <dono>` (alias) ou cada atributo `is` o do dono (re-export) **nas duas
ordens de import, antes da remoção** → reescrita dos consumidores (imports por AST; `tools.X`, `python -m tools.X`,
`tools/X.py` por regex ancorado; histórico e blobs protegidos fora) → remoção → manifestos FP-042, mapa P0,
`OWNER_TABLE`, `LEGACY_FACADES`, `LEGACY_ROOM_MODULES` e guia de migração no mesmo PR. Contratos de teste que liam o
**arquivo da fachada** foram reescritos para o **dono** (mesma intenção: implementação única, helpers compartilhados,
CLI preservada pelo `__main__` do dono); nenhum esperado de comportamento mudou.

## 3. Saída idêntica e gates (cada fatia e no final)

- `fp044_baseline compare` (`PT_TO_M=0.0259`): **IDENTICO** em todas as fatias (caixas por cômodo + canônicos).
- `inventory_gate --strict`, `p0_map --check`, `docs_check`, `ownership_audit`, `capability_catalog`,
  `reference_provenance`, `asset_provenance`, `run_deterministic_gates` (quadrado e planta_74), `mcp_server.smoke`,
  `mcp_server.stdio_check`: exit 0 em todas.
- pytest completo nas duas escalas, comparado lote a lote com `develop`: **nenhuma falha nova**; as falhas locais de
  ambiente (28 failed / 35 errors, preexistentes e idênticas) seguem iguais. O CI é a referência.
- Vínculo especialista → receita → fonte (regra das aulas): `capability_catalog` verde sem editar esperados;
  `test_fp043_specialists` e `test_fp043_capability_catalog` verdes. Nenhuma receita, perfil ou índice de conhecimento
  cita as fachadas removidas; nos textos consultivos (`tools/sketchup/knowledge.py`, skills de marcenaria,
  `sketchup-tooling-specialist`) mudou **só o caminho**, para um símbolo que existe no dono. Nenhum símbolo com digest
  em `evidence[]` foi tocado (medido).

## 4. L2 real (SketchUp 26.0.429, PIDs próprios)

- **F2** (programa do sofá, antes × depois): caminho absoluto — antigo (PID 40892) e novo (PID 29096) OK, bbox
  1,52×0,963×0,818 m, 10 peças, renders SHA-256 idênticos; caminho relativo (como diz o cabeçalho do `.rb`) **não executa
  nem no código antigo** (PIDs 38840 / 32320, 40776) — pendência preexistente de documentação do `.rb`.
- **F7 integrado** (`develop` final, MCP stdio real): `su_build_shell` → `su_furnish` (402 caixas, PID 32996) →
  `su_inspect` (PID 29556); `planta_check` **igual ao do P8 (mesmo blob git `aed8834f…`)**: 402/402, erro máx. 0,05 mm. Canônicos:
  `7512d592…` `planta_74.skp`, `dfc431da…` `geometry_report.json`, `d2846ab6…` furnished (iguais à F0/P8).
- **F7 sofá** (`develop` final, PID 40784): OK, mesmos 5 renders byte a byte do código anterior à FP-044.
- Nenhum `taskkill /IM`; cada SketchUp fechado pelo PID que a própria chamada devolveu; 0 SketchUp aberto ao fim.

## 5. Achados novos (registrados, não contornados)

| ID | Achado | Por que fica | Saída |
|---|---|---|---|
| D-011 | o Inspector do `apps/harness-app` (Java, `SourceVerifier`) lê `tools/{reference_db,rag_embed_backend,ollama_bridge,run_deterministic_gates}.py` em runtime | consumidor externo que o JSON de fachadas (só imports Python) não viu | PR **no harness** repontando o catálogo; depois uma fatia remove as 4 |
| D-012 | `bed_class` (quarto) importa `_grid_sheet` do programa do sofá (living) **pela fachada** `tools.sofa_class_matrix`; com o import direto o gate de fronteira reprova (`CROSS_ROOM_DEPENDENCY`) | mover `_grid_sheet` para `shared` não foi pedido | fatia própria movendo o helper; depois a fachada sai |
| — | dois testes de regra vigiavam **arquivos de fachada vazios** desde o P4 (`test_fp043_no_global_taskkill` em `render_banho_vray`/`place_bedroom_skp`/`kitchen_vray`/`bake_theme_skp`; `test_vision_acl::test_no_machine_appearance_verdict`) | — | agora leem o código real dos donos (a regra vale de fato) |

Correção honesta durante a execução: uma suposta D-012 "fachadas dentro de símbolos do catálogo" foi medida de novo
antes do commit — nenhum símbolo com digest era afetado — e **retirada**; não chegou a `develop`.

## 6. O que NÃO foi feito (e por quê)

1. **F4** (`ops/estudio-front/`) e **F5** (`.impeccable/`): aguardam D-009 e D-008 do Felipe.
2. **`tools/*.py` = 8 + 2** (critério §11): não fecha — D-011 (consumidor externo) e D-012 (dependência escondida).
3. Repontar o `apps/harness-app` (outro repositório): fora desta spec (D-010/D-011).
4. Pendências herdadas seguem: D-001 (referência do `quadrado`), D-002…D-005, D-007 (`xfail(strict)` sintéticas) e
   o veredito visual dos reparos da FP-043. Nenhum `VISUAL_REVIEW` atribuído.
5. Cabeçalho dos `.rb` do sofá diz para rodar com caminho relativo, o que não funciona (nem antes): só documentação,
   fora de uma fatia de movimento.
6. Textos **históricos** (`artifacts/`, `docs/archive/`, `docs/handoffs/`, `docs/reports/`, `.ai_bridge/`,
   `references/`, `fixtures/`) e blobs **protegidos** (`assets/furniture/sofa/manifests/…`, `assets/textures/pbr/SOURCES.md`)
   continuam citando caminhos antigos de propósito; o [guia de migração](../architecture/migration_guide.md) traduz.

## 7. Fora do repositório (workspace `E:\Claude`, sem git)

Referências vivas repontadas para o dono (só o caminho): `CLAUDE.md` (`tools\oracle\ask_gpt_gate.py`),
`.claude/agents/interior-orchestrator.md` (cozinha), `LESSONS-NOC.md` e `TOOLCHAIN-SKILLS.md`
(`tools.knowledge.retrieval_eval`). O `apps/harness-app` não foi tocado (consome só as 8 públicas e as 4 da D-011).

## 8. Definição de pronto (§11)

| Critério | Estado |
|---|---|
| raiz com as pastas-alvo, sem pasta de matéria única | PARCIAL — `.impeccable/` (D-008), `ops/` (D-009), `scripts/` (D-005) |
| `tools/*.py` = 8 públicas + 2 bloqueadas | PARCIAL — 15 (D-011, D-012) |
| guards da raiz e de `tools/` no CI | OK |
| README, mapa e guia iguais ao que existe (teste) | OK |
| saída idêntica à F0 em todas as fatias | OK |
| L2 real do build integrado e do programa do sofá | OK |
| canônicos com SHA-256 iguais | OK |
| CI verde em cada merge | OK |
| relatório com PRs, SHAs e pendências | OK (este documento) |

**Estado: `PARTIAL`** — motivos: decisões do Felipe (D-008, D-009) e consumidor externo/dependência escondida
(D-011, D-012).
