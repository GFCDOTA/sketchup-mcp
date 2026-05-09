# Milestone SKP planta_74 — Relatório final (formato pedido)

> **Resultado:** ✅ SKP gerado, validado e utilizável.
> Critério de parada satisfeito.

## 1. Caminho do SKP gerado

```
E:\Claude\sketchup-mcp\runs\_milestone_skp_planta74_2026_05_09\_smoke_out\model.skp
```

- Tamanho: **96,903 bytes** (post-export); 97,197 bytes (post-inspector
  re-save — ver §5)
- sha256 (model.skp): `534f6e677947eaa238990b9fd2ecd46784b243c317180029e55092e2b6d89cd9`
- Abre limpo em SU 2026 (testado nesta sessão via autorun inspector)

Sidecar metadata (`model.skp.metadata.json`) confirma binding
consensus → SKP:
```json
{
  "schema_version": "1.0.0",
  "consensus_sha256": "f9814dc56f7c746d28bf0ca397e23b46bad7aa9772e1d8f8fdd02990243556a6",
  "git_commit": "9df2fee73a0e0bbee57d0ed8efc2b08c0b694975",
  "sketchup_path": "C:\\Program Files\\SketchUp\\SketchUp 2026\\SketchUp\\SketchUp.exe",
  "created_at": "2026-05-09T02:39:49Z"
}
```

## 2. Commit / run usado

| Item | Valor |
|---|---|
| **git commit** | `9df2fee73a0e0bbee57d0ed8efc2b08c0b694975` (develop tip post-PR #101) |
| **branch** | `develop` |
| **run dir** | `runs/_milestone_skp_planta74_2026_05_09/` |
| **PDF source** | `planta_74.pdf` (LIVING GRAND WISH JARDIM, Torre 1, 74.83 m²) |
| **expected_model** | `ground_truth/planta_74/expected_model.json` |
| **consensus_sha256** | `f9814dc56f7c746d28bf0ca397e23b46bad7aa9772e1d8f8fdd02990243556a6` |
| **reproducível** | sha256 baseline-idêntico ao CLAUDE.md §10 (post-Cycle-8b) |

Pipeline executado (5 passos canônicos OVERVIEW.md §4.4):
```
1. tools.build_vector_consensus  → 33 walls
2. tools.extract_room_labels     → 15 labels
3. tools.rooms_from_seeds        → 11 rooms (concave-hull default)
4. tools.extract_openings_vector → 12 candidates
5. tools.classify_openings_by_room_context → 11 kept, 4 dropped
```

Final consensus: **33 walls / 11 rooms / 11 openings / 8 soft_barriers**.

## 3. Fidelity antes / depois

Como **0 overrides foram aplicados** (justificativa em §5), não há
"depois" diferente. O smoke harness gates E2/E3 (amend + amended
fidelity) corretamente SKIPped por ausência de
`review_overrides.json`.

| Métrica | Valor (raw == post-override) |
|---|---|
| `global_fidelity` | **0.917** |
| `room_score` | 1.0 |
| `count_score` | 1.0 |
| `bbox_score` | 1.0 |
| `adjacency_score` | 0.667 |
| `hard_fails` | 0 |
| `warnings` | 2 |

Warnings (advisory, não bloqueantes):
1. `area_in_range:TERRACO TECNICO actual=1.612` — abaixo do limite
   inferior esperado
2. `adjacency_f1=0.67<0.80` — abaixo do advisory mas acima do hard
   threshold (0.60)

### Diff view explícito vs run canônico anterior

Comparando `_milestone_skp_planta74_2026_05_09` (atual,
post-Cycle-8b) com `feature_room_context_2026_05_06`
(pre-Cycle-8b, mesmo plant):

| Room | atual (m²) | pré-Cycle-8b (m²) | Δ |
|---|---:|---:|---:|
| **SUITE 01** | 26.75 | **69.91** | **−43.16** |
| **SUITE 02** | 14.38 | 32.03 | −17.65 |
| A.S. | 2.52 | 10.39 | −7.87 |
| TERRACO TECNICO | 1.61 | 5.77 | −4.16 |
| TERRACO SOCIAL | 11.70 | 13.64 | −1.94 |
| COZINHA | 8.80 | 11.34 | −2.54 |
| BANHO 01 | 5.48 | 5.48 | 0.00 |
| BANHO 02 | 6.24 | 6.24 | 0.00 |
| LAVABO | 3.40 | 3.40 | 0.00 |
| SALA DE ESTAR | 10.82 | 10.82 | 0.00 |
| SALA DE JANTAR | 13.07 | 13.07 | 0.00 |

Cycle 8b (concave-hull default) **CONSERTOU** SUITE 01 / SUITE 02
(FP-012 leakage gigante eliminada) e **APERTOU DEMAIS** TERRACO
TECNICO. Esse é o trade-off já documentado em CLAUDE.md §10 e
honest-reported como warning na fidelity.

## 4. F0 verdict

```json
{
  "schema_version": "pre_skp_review_v1",
  "verdict": "PASS",
  "reasons": ["fidelity=0.917 ≥ 0.85, 0 hard_fails, 2 warnings"],
  "fidelity_score": 0.917,
  "hard_fails_count": 0,
  "warnings_count": 2,
  "active_overrides_count": 0,
  "block_skp_export": false,
  "recommendation": "safe to export SKP",
  "using_amended_fidelity": false
}
```

**Verdict = PASS.** Recommendation = "safe to export SKP". F0 não
exigiu nenhuma intervenção humana.

## 5. Overrides aplicados

**Total: 0 (zero) overrides.**

Justificativa estrita à regra "somente se realmente necessários":

1. **F0 já reporta PASS** (verdict acima) sem nenhuma intervenção humana
2. **0 hard_fails** — nenhum bloqueador estrutural existe
3. **As 2 warnings são advisory** — não bloqueiam o gate F (SKP export)
4. **8 proposed_actions são todas flags / human_review** — nenhuma é
   um fix concreto:
   - 5× `request_human_review` em openings com decision=debug
   - 2× `mark_low_confidence` em openings com confidence<0.7
   - 1× `request_human_review` em room TERRACO TECNICO (área warning)
5. **Per ADR-002 §2.8: SKP exporter é overrides-blind em v1.** Mesmo
   se eu aplicasse `mark_suspect` em TERRACO TECNICO, o `.skp`
   seria byte-idêntico ao atual. Aplicar override = decorar relatório,
   não mudar produto

A escolha honesta foi não aplicar nenhum override.

### Smoke harness — 12 gates executados

```
A → B → C → D → E → E2 → E3 → F0 → F0pa → F → G → G2
```

| Gate | Status | Mensagem-chave |
|---|---|---|
| A. Preparation | PASS | sketchup detected at canonical install |
| B. Acquire consensus | PASS | loaded consensus.json (112,883 bytes) |
| C. JSON structural | PASS | walls=33, rooms=11, openings=11 |
| D. Preview PNG | PASS | top + axon previews rendered |
| E. Hash + cache | PASS | cache miss; cache_key=`e0816cc1b0f9` |
| E2. Amend observed | SKIP | sem review_overrides.json (esperado — ver §5) |
| E3. Amended fidelity | SKIP | idem |
| **F0. Pre-SKP review** | **PASS** | **verdict=PASS** (review-mode=warn) |
| F0pa. Proposed actions | PASS | 8 actions emitidos para `proposed_actions.json` |
| **F. Export .skp** | **PASS** | **`model.skp` 96,903 bytes** |
| G. Validate .skp | PASS | size 96,903 bytes ≥ threshold |
| G2. Inspector v2 | SKIP no smoke run; rodado manualmente (resultado abaixo) |

### Inspector v2 — autorun manual

```
schema_version          1.0
skp_sha256              534f6e677947...
skp_size_bytes          97,197
default_faces_count     0          ← nenhuma face órfã
materials_count         18
wall_overlaps_count     0          ← nenhuma colisão geometria
components_count        0
groups_by_layer         {walls: 34, parapets: 31, doors: 5, windows: 12}
-> is_clean:            True
```

**O SKP é estruturalmente limpo.**

## 6. Cockpit walkthrough headless — 6 camadas

| Camada | Status | Evidência |
|---|---|---|
| L1 SVG overlay (Cycle 12) | ✅ | `_cockpit_overlay.svg` 27 KB; renderiza walls/rooms/openings/ground_truth status |
| L2 expected_match (12d) | ✅ | 11 rooms: **10 in_range, 1 out_of_range_low** (TERRACO TECNICO) |
| L3 RunSummary (12f) | ✅ | fidelity=0.917; sub_scores corretos |
| L4 pre_skp_review (12f) | ✅ **PASS** | `recommendation: safe`; mesma lógica do gate F0 |
| L5 proposed_actions (Slice 4) | ✅ | 8 chips advisory carregados |
| L6 review_overrides (Slice 2) | ✅ | 0 overrides (vazio — nenhum criado) |

Diff view (cockpit `diff_summary`) executado entre run atual vs
canônico anterior — tabela de deltas em §3.

## 7. Problemas visuais restantes

### Side-by-side PDF × SKP top × SKP axon

`runs/_milestone_skp_planta74_2026_05_09/_sidebyside_pdf_skp.png`
(2831×920 px) compõe os 3 lado-a-lado.

| Item | Severidade | Categoria |
|---|---|---|
| **SUITE 01 polygon visualmente "vaza"** sobre footprint de BANHO 02 (concave-hull aproxima entre walls não-adjacentes) | Média (cosmético) | Refinamento |
| **TERRACO TECNICO** = 1.61 m² vs esperado ~10 m² (concave-hull cortou demais; ver §3 diff) | Média | Refinamento — flagged como warning |
| **SALA DE ESTAR** com fold triangular no canto inferior-esquerdo | Baixa | Refinamento (concave-hull artifact) |
| **adjacency_f1 = 0.67** abaixo do advisory 0.80 (5/11 openings com decision=debug) | Baixa | Refinamento — não bloqueia |
| **Sem mobiliário** (PDF tem camas, sofá, balcão; SKP só tem envelope) | Alta para uso "venda"; baixa para uso "estrutural" | **Feature ausente — fora do mission v1** |
| **Sem entorno** (terreno, vizinhança) | Baixa | Refinamento out-of-scope |

## 8. SKP utilizável para layout/furniture planning?

**Sim.** Avaliação ponto-a-ponto contra o mission statement
("structural fidelity for furniture/layout planning"):

| Critério | Atende? | Por quê |
|---|---|---|
| Abre em SU 2026 sem erros | ✅ | testado via autorun inspector |
| Geometria limpa (sem overlaps, sem orphans) | ✅ | inspector v2 `is_clean=True` |
| Todos os cômodos identificáveis | ✅ | 11/11 rooms com nome correto |
| Walls posicionados em escala correta | ✅ | wall_thickness anchor 0.19 m via `t/0.19` |
| Aberturas (portas/janelas) carved nos walls certos | ✅ | 5 doors + 12 window/parapet groups, all in expected walls |
| Floors coloridos por cômodo | ✅ | palette estável (Cycle 12 hash modulo) |
| Soft barriers (peitoris) extrudados | ✅ | 31 parapet groups |
| Materiais atribuídos (sem default-face leak) | ✅ | 18 materials, default_faces_count=0 |
| Áreas próximas das esperadas | ✅ 10/11 in_range; 1 (TERRACO TECNICO) out_of_range_low — não bloqueante |
| Pronto para receber móveis | ✅ | floors planos extrudados como faces SU; trivialmente populáveis |

## 9. Menor bloqueio real (caso não tenha ficado boa)

**Não se aplica** — o SKP ficou utilizável.

Se Felipe rejeitar o critério "estruturalmente válido + cômodos
identificáveis + posicionamento correto" e exigir "visualmente
indistinguível do PDF", aí o **menor bloqueio real** seria:

→ **Furniture layer ausente** (P0). Nenhuma feature do pipeline
v1 popula móveis. PDF mostra camas, sofá, balcão de cozinha,
mesa de jantar; SKP só tem envelope. Esse é o gap que vira
"vergonha visual" se o cliente comparar lado-a-lado.

Ranking dos próximos ROIs (caso Felipe queira continuar):
1. **P0 — Furniture layer** (não existe; muda o que o cliente vê)
2. **P1 — ADR-002 / Slice 6e** (room polygon override + amended_consensus
   para SKP) — só vira valor depois de P0, porque hoje a polygon
   imprecisa só afeta floor color, não o produto
3. **P2 — Multi-PDF corpus** (RED, depende do Felipe fornecer PDFs)

## 10. Critério de parada — aplicado

> Se gerar SKP aceitável, parar.
> Se não gerar, apontar o bloqueio mínimo real.
> Não continuar criando slices/ADRs/refactors sem provar que são
> necessários para o SKP.

**SKP aceitável gerado. Parando.**

Nenhum slice/ADR/refactor novo foi criado neste milestone. ADR-002
(merged em PR #101 antes deste milestone começar) **não foi
implementada** porque o SKP foi gerado sem precisar dela.

## Artefatos (resumo final)

```
runs/_milestone_skp_planta74_2026_05_09/
├── consensus_walls.json                       # passo 1 (33 walls)
├── labels.json                                 # passo 2 (15 labels)
├── consensus.json                              # passo 5 (final, sha256 f9814dc56f7c)
├── fidelity_report.json                        # global=0.917
├── fidelity_scorecard.md
├── coherence_report.json                       # 11 openings, by_decision={clean:6, debug:5}
├── questions.json                              # 5 advisory dúvidas
├── _micro_truth.json                           # score=1.0 / 4 rooms / 0 fired
├── _expected_model.json                        # cópia local do ground_truth
├── _cockpit_overlay.svg                        # 27 KB — L1 cockpit walkthrough
├── _pdf_page1.png                              # PDF rasterizado (input visual)
├── _sidebyside_pdf_skp.png                     # 2831×920 — PDF | SKP top | SKP axon
└── _smoke_out/
    ├── _bootstrap.skp                           # template SU
    ├── model.skp                                # ✅ PRODUTO 96,903 bytes
    ├── model.skb                                # SU backup
    ├── model.skp.metadata.json                  # sha256 + git_commit binding
    ├── preview_top.png                          # render top
    ├── preview_axon.png                         # render axon
    ├── axon_iso.png                             # render axon ISO via tools.render_axon
    ├── proposed_actions.json                    # 8 advisory actions
    ├── pre_skp_review_report.json               # F0 verdict=PASS
    ├── inspect_report.json                      # ✅ INSPECTOR V2 is_clean=True
    ├── sketchup_smoke_report.{json,md}          # 12 gates summary
    └── skp_from_consensus.log                   # log do gate F
```
