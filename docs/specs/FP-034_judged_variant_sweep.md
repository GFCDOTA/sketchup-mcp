# FP-034: PLACAR DE VARIANTES JULGADAS — variant sweep + corpus julgado

> **depends on FP-032** (ACL de visao: `render -> visual_findings.json` tipado). Sem o detector tipado de FP-032, este front roda em modo STUB (`visual_findings=null`, `verdict=PENDING_VISION`) — honesto, nao fabrica achados.

## Problem

Hoje o sistema gera UMA planta mobiliada por vez (`tools/furnish_apartment.py`), com um unico estilo escolhido a mao (env `FURNISH_STYLE`), e o julgamento do resultado vive espalhado: em `tools/batch_theme_render.py` os vereditos (`gpt`, `gates`, `RANKING`) sao **hard-coded curados de GPT/Felipe** (ver `THEMES`/`RANKING`, linhas 32-57) — nao saem de uma rodada real. `tools/sofa_class_matrix.py` PROVA que o padrao "matriz de variantes derivadas -> gate -> render SU-free -> grid + `matrix_report.json`" funciona, mas **so para um movel (sofa)**, nunca para a planta inteira.

Falta o **placar**: rodar N variantes de planta (eixos estilo x material x layout) o dia todo em fundo, anotar cada uma com os achados visuais tipados (de FP-032) e **armazenar como CORPUS JULGADO** — o registro `variante -> params -> achados_visuais -> verdito` que materializa o insight que o Felipe pediu ("melhor nesse caso, pior naquele"). Esse corpus e' o **insumo cru do RAG (FP-035)**; sem ele o RAG nao tem o que indexar alem das referencias curadas que `reference_db.py` ja tem.

## Scope

1. **Gerador de variantes** (`tools/variant_sweep.py`, NOVO): expande um produto cartesiano controlado de eixos e, para cada celula, roda o furnish da planta, renderiza, coleta achados (FP-032) e grava um registro julgado. Espelha a arquitetura provada de `sofa_class_matrix.py` (derive -> gate -> render -> sheet -> report), elevada de movel para planta.
   - **Eixo `estilo`**: `FURNISH_STYLE ∈ {baseline(None), industrial, modern_warm}` — REAL, ja gated em `furnish_apartment.py:280,350,393` + `style_spec.STYLE_TOKENS`.
   - **Eixo `material/tema`**: `KITCHEN_THEME ∈ {warm_compact(""), hotel_boutique, dark_walnut, black_wood_gold}` — REAL, presets em `artifacts/reference_lab/themes/*.json`, consumido pelo render path (`kitchen_vray.py:102`, `vray_export.rb`). (Coordenar com FP-036 "material de verdade" — FP-034 so VARIA o tema; FP-036 melhora a textura por tras dele.)
   - **Eixo `layout`**: `layout_seed` / variacao de plano por comodo (`living_room_planner`, `bedroom_designer`, `bathroom_layout`). Slice inicial: seed determinístico que perturba a escolha de parede-TV / lado-da-cama quando ha candidatas ambíguas (`layout_candidates.py` ja expõe `candidates`/`ranking`).
2. **Formato do registro julgado** (`judged_variant.schema.json`, NOVO): contrato JSON estável `variante -> params -> render_refs -> visual_findings -> machine_score -> verdict`. Append-only JSONL por run (`corpus.jsonl`) espelhando o protocolo append-only do NOC ledger e o `matrix_report.json`.
3. **Runner de fundo** (`kind=variant-sweep` na fila do NOC): uma task enfileiravel em `.ai_bridge/noc/queue.jsonl` que dispara `variant_sweep.py --loop` sob os rails existentes do `noc_dispatcher.py` (lock de 1-atuador, NUNCA main, APARENCIA -> enfileira VISUAL_REVIEW).
4. **Ponte para FP-035** (`corpus_to_rag.py` ou flag de export, NOVO leve): emite o corpus num shape que `reference_db.py` / `project_memory_db.py` conseguem ingerir (ver Artifact contract). FP-034 PRODUZ; FP-035 INDEXA/CONSULTA.

## Non-goals

- **NAO** decide aparencia final. A maquina grava `visual_findings` (tipado, de FP-032) + `machine_score` rotulado `machine_provisional`. O veredito estetico final (IMPROVED/SAME/WORSE, "melhor nesse caso") e' **exclusivo do Felipe** — gravado so quando ele revisa, em `human_verdict`. (negative_dogfood ja provou que auto-veredito visual nao e' confiavel.)
- **NAO** promove nenhuma variante a canonica. Todo registro nasce `candidate`. Promocao a golden e' fora de escopo (segue `promote_canonical.py` + decisao humana).
- **NAO** constroi o detector de visao — isso e' FP-032. Aqui so CONSUMIMOS `visual_findings.json` via um adapter fino; se ausente, `verdict=PENDING_VISION`.
- **NAO** implementa o RAG consultavel — isso e' FP-035. Aqui so emitimos o corpus num shape ingerivel.
- **NAO** melhora textura/BRDF — isso e' FP-036. Aqui so VARIAMOS o eixo tema/material existente.
- **NAO** mexe nas fixtures de input (`fixtures/planta_74/`, `fixtures/quadrado/`) — Hard Rule #3 do projeto.

## Artifact contract

| Path | Mudanca | Quem |
|---|---|---|
| `tools/variant_sweep.py` | **NOVO** — gerador: `expand_axes()`, `run_variant()`, `sweep()`, CLI `--n/--axes/--loop/--dry-run/--render su-free\|vray`. Espelha `sofa_class_matrix.py`. | FP-034 |
| `tools/variant_axes.py` | **NOVO** — declaracao tipada dos 3 eixos (estilo/material/layout) + `Variant` dataclass; le `style_spec.STYLE_TOKENS` e `themes/*.json` como fontes (nao duplica). | FP-034 |
| `.claude/specs/judged_variant.schema.json` | **NOVO** — schema do registro julgado (contrato estavel p/ FP-035). | FP-034 |
| `runs/variant_sweep/<run_id>/corpus.jsonl` | **NOVO (scratch, gitignored)** — append-only, 1 registro julgado por linha. | gerado |
| `runs/variant_sweep/<run_id>/<variant_id>/` | **NOVO (scratch)** — renders (iso SU-free e/ou hero V-Ray) + `params.json` por variante. | gerado |
| `runs/variant_sweep/<run_id>/contact_sheet.png` | **NOVO (scratch)** — grid das variantes (reusa `_grid_sheet` de `sofa_class_matrix.py`). | gerado |
| `tools/render_parts_iso.py` | **REUSO** (`render_parts`) — renderer barato p/ proporcao; nenhuma mudanca. | existente |
| `tools/furnish_apartment.py` | **REUSO via subprocess/env** — `FURNISH_STYLE`+`PT_TO_M=0.0259`+`KITCHEN_THEME`. Talvez extrair `collect_boxes()` como entrada importavel (refactor minimo, sem mudar comportamento). | existente |
| `tools/style_spec.py` / `artifacts/reference_lab/themes/*.json` | **REUSO** — fontes dos eixos estilo/material. | existente |
| `.ai_bridge/noc/queue.jsonl` | **APPEND** — task `kind=variant-sweep` (`safe:true`, `appearance:true` -> VISUAL_REVIEW). | FP-034 |
| `tools/corpus_to_rag.py` | **NOVO leve** — exporta `corpus.jsonl` -> linhas ingeriveis por `reference_db`/`project_memory_db` (FP-035 consome). | FP-034 |
| `tools/png_history.py` | **NAO EXISTE hoje** (memoria descreve protocolo nunca construido). Se quisermos manifest de renders, criar AQUI e' opcional; o `corpus.jsonl` ja carrega sha+source. NAO assumir que existe. | (decisao) |
| FP-032 `visual_findings.json` (por variante) | **DEPENDENCIA externa** — produzido por FP-032; consumido por `variant_sweep` via adapter `_collect_findings(render_path)`. Ausente -> `null` + `PENDING_VISION`. | FP-032 |

## Algorithm

```
# --- variant_axes.py ---
@dataclass(frozen=True)
class Variant:
    variant_id: str          # estavel/determinístico: f"{plant}__{style}__{theme}__L{layout_seed}"
    plant: str               # "planta_74"
    style: str | None        # FURNISH_STYLE: None|"industrial"|"modern_warm"
    theme: str               # KITCHEN_THEME: ""|"hotel_boutique"|"dark_walnut"|"black_wood_gold"
    layout_seed: int         # perturba escolha de parede/lado quando ha candidatas ambíguas

AXES = {
  "style":  [None, "industrial", "modern_warm"],         # de style_spec.STYLE_TOKENS (+ baseline)
  "theme":  ["", "hotel_boutique", "dark_walnut", "black_wood_gold"],  # de themes/*.json
  "layout": [0, 1, 2],
}

def expand_axes(axes=AXES, n=None, sampler="grid"):
    # grid = produto cartesiano (determinístico, ordenado); 'sample' = primeiras n celulas
    # (sem random sem seed — testes determinísticos). n limita o sweep diario.
    cells = [Variant(...) for s,t,l in itertools.product(...)]
    return cells[:n] if n else cells

# --- variant_sweep.py ---
def run_variant(v: Variant, render="su-free", out_dir, find_adapter):
    env = {**base_env, "PT_TO_M": "0.0259",              # gotcha real: senao movel flutua 1.36x
           "FURNISH_STYLE": v.style or "", "KITCHEN_THEME": v.theme,
           "LAYOUT_SEED": str(v.layout_seed)}
    boxes, summary = furnish_apartment.collect_boxes(con, env)   # REUSO (sem relançar SU no su-free)
    # determinístico ANTES de render: overlap/geometry gates ja existentes
    gate = run_deterministic_gates(boxes)                # furniture_overlap_gate, geometry_sanity...
    if render == "su-free":
        png = render_parts(boxes_to_parts(boxes), out_dir/"iso.png")   # barato, comparavel
    else:
        png = furnish_apartment.main_render(env)         # caro: V-Ray hero (so amostra/golden cells)
    findings = find_adapter(png)                         # FP-032: visual_findings.json | None
    record = build_record(v, summary, gate, png, findings)
    return record

def build_record(v, summary, gate, png, findings):
    score = machine_provisional_score(gate, findings)    # SO se findings != None; rotulado provisional
    verdict = ("PENDING_VISION" if findings is None
               else "FAIL" if gate.failed or findings.has_blocker
               else "CANDIDATE")                         # nunca IMPROVED/SAME/WORSE (=humano)
    return {                                              # === judged_variant.schema.json ===
      "schema": "judged_variant/1.0.0",
      "run_id": RUN_ID, "variant_id": v.variant_id, "created_at": iso_utc_from_mtime,
      "plant": v.plant,
      "params": {"style": v.style, "theme": v.theme, "layout_seed": v.layout_seed},
      "geometry": {"n_boxes": len(...), "rooms": summary, "deterministic_gates": gate.results},
      "render_refs": {"iso": rel(png), "sha256": sha(png), "renderer": render},
      "visual_findings": findings,        # tipado de FP-032 | null
      "machine_score": score,             # {"value": float|None, "label": "machine_provisional"}
      "verdict": verdict,                 # CANDIDATE|FAIL|PENDING_VISION
      "human_verdict": None,              # SO o Felipe preenche (IMPROVED/SAME/WORSE/"melhor p/ X")
    }

def sweep(n, render, out_root):
    cells = expand_axes(n=n)
    rec = []
    for v in cells:
        r = run_variant(v, render, out_root/v.variant_id, find_adapter=_collect_findings)
        append_jsonl(out_root/"corpus.jsonl", r)         # append-only (idempotente por variant_id)
        rec.append(r)
    write_contact_sheet(rec, out_root/"contact_sheet.png")   # reusa _grid_sheet
    return rec

def _collect_findings(png):                              # adapter FINO p/ FP-032
    fp = png.with_name("visual_findings.json")            # produzido por FP-032 ao lado do render
    return json.loads(fp.read_text()) if fp.exists() else None   # honesto: ausente -> None

# --- NOC: kind=variant-sweep (rodar o dia todo) ---
# queue.jsonl: {"id":"VS1","kind":"variant-sweep","safe":true,"appearance":true,
#   "title":"Sweep diario de variantes planta_74","prompt":"python -m tools.variant_sweep --loop --n 12 --render su-free"}
# noc_dispatcher: lock 1-atuador -> roda -> appearance:true => enfileira VISUAL_REVIEW (Felipe), NUNCA auto-aprova.
```

## Acceptance

| Caso | PASS | WARN | FAIL |
|---|---|---|---|
| `expand_axes()` determinístico | mesma entrada -> mesma lista ordenada (2 chamadas iguais) | — | ordem/conteudo varia entre chamadas |
| Registro segue schema | toda linha do `corpus.jsonl` valida contra `judged_variant.schema.json` | campo opcional ausente mas required presentes | required faltando / tipo errado |
| Honestidade da visao | sem FP-032: `visual_findings=null` + `verdict=PENDING_VISION` em 100% | — | qualquer `visual_findings` fabricado/inventado |
| Honestidade do veredito | `human_verdict=null` ate o Felipe revisar; `machine_score.label="machine_provisional"` | score presente sem findings (so gates) -> WARN | `verdict ∈ {IMPROVED,SAME,WORSE}` gravado pela maquina |
| Escala da planta | toda variante roda com `PT_TO_M=0.0259` | — | qualquer variante com 0.0352 (movel flutua) |
| Gates determinísticos por variante | `furniture_overlap_gate`+`geometry_sanity` rodam ANTES do render; FAIL marcado no registro | overlap WARN registrado | variante com overlap FAIL gravada como CANDIDATE |
| Sweep de fundo (NOC) | task `kind=variant-sweep` roda sob lock, dren a fila, para em NO_TASK | `--max-cycles` corta runaway | roda em `main` / auto-aprova aparencia |
| Ponte FP-035 | `corpus_to_rag.py` emite linhas que `reference_db ingest` / `project_memory_db index` aceitam | shape parcial mas ingerivel | corpus que nenhum dos 2 RAGs consegue ler |
| Candidato != canonico | nenhuma variante escreve em `artifacts/.../canonical/` | — | sweep promove variante a golden sozinho |

## Required tests

| Teste (nome = comportamento) | Tipo | Verifica |
|---|---|---|
| `expand_axes_is_deterministic_and_ordered` | unit | 2 chamadas == ; ordem estavel |
| `expand_axes_n_limits_cells` | unit | `--n 4` -> exatamente 4 celulas, prefixo do grid |
| `variant_id_is_stable_for_same_params` | unit | mesmo (style,theme,seed) -> mesmo id |
| `record_validates_against_schema` | contract | jsonschema valida cada registro emitido |
| `missing_findings_yields_pending_vision` | unit | adapter sem arquivo -> `null` + `PENDING_VISION` (NUNCA fabrica) |
| `machine_never_writes_human_verdict` | unit | nenhum caminho grava IMPROVED/SAME/WORSE ou `human_verdict` |
| `sweep_uses_pt_to_m_0_0259` | unit | env da variante carrega 0.0259 (mock subprocess/collect) |
| `deterministic_gate_fail_marks_record_fail` | unit | overlap/geometry FAIL -> `verdict=FAIL` |
| `corpus_jsonl_is_append_only_idempotent` | unit | rerun mesmo variant_id nao duplica linha (dedup por id) |
| `corpus_to_rag_output_is_ingestible` | contract | linha exportada passa pelo upsert de `reference_db`/index de `project_memory_db` (fixture mínima) |
| `su_free_sweep_smoke_4_variants` | integration | `--dry-run --n 4 --render su-free` -> 4 linhas + contact_sheet, sem SU |

## Done means

- [ ] `tools/variant_axes.py` + `tools/variant_sweep.py` criados; eixos lem `style_spec.STYLE_TOKENS` e `themes/*.json` (sem duplicar valores).
- [ ] `.claude/specs/judged_variant.schema.json` (`judged_variant/1.0.0`) versionado e validado pelos testes contract.
- [ ] Slice 0 SU-FREE provado: `python -m tools.variant_sweep --dry-run --n 4 --render su-free` emite 4 registros validos + `contact_sheet.png`, `visual_findings=null`, `verdict=PENDING_VISION`.
- [ ] Adapter `_collect_findings` plugado em FP-032 quando este landar; com FP-032 vivo, ao menos 1 variante grava `visual_findings` tipado real (nao stub) e `verdict ∈ {CANDIDATE,FAIL}`.
- [ ] Suite de testes (tabela acima) verde — incl. os 2 contract (schema + ingestao RAG) e os 3 de honestidade (no-fabricate, no-human-verdict, pt_to_m).
- [ ] Task `kind=variant-sweep` adicionada a `.ai_bridge/noc/queue.jsonl` e validada num `--once` do `noc_dispatcher` (roda sob lock; `appearance:true` -> VISUAL_REVIEW enfileirado; nada em main).
- [ ] `corpus_to_rag.py` prova (fixture mínima) que 1 registro vira linha ingerivel por `reference_db` E `project_memory_db` (handoff explicito p/ FP-035).
- [ ] Planta real: 1 sweep de >=6 variantes da `planta_74` rodado, `corpus.jsonl` inspecionado, e o resultado (incl. qualquer mudanca de aparencia) enfileirado p/ VISUAL_REVIEW do Felipe — nao auto-aprovado.
- [ ] Branch `feat/judged-variant-sweep` off `origin/develop`; PR aberta (URL de compare se `gh pr create` falhar por escopo do PAT). Nenhuma PR deixada aberta ao fim.

## Reference

**Arquivos REAIS lidos e confirmados (ancoras):**
- `tools/sofa_class_matrix.py` — padrao matriz-de-variantes (derive->gate->render->`_grid_sheet`->`matrix_report.json`); espelhar para planta. **Reuso direto**: `_grid_sheet`.
- `tools/furnish_apartment.py` — furnish da planta inteira; eixo ESTILO via env `FURNISH_STYLE` (linhas 280/350/393), `collect_boxes()` (l.407), `apply_style` (l.437), gotcha `PT_TO_M=0.0259` (l.27-28).
- `tools/style_spec.py` — `STYLE_TOKENS` `{industrial, modern_warm}` (kind->rgb + textura); fonte do eixo estilo.
- `tools/batch_theme_render.py` — eixo MATERIAL/TEMA (`KITCHEN_THEME`); HOJE `THEMES`/`RANKING` (l.32-57) sao **vereditos curados a mao** — FP-034 substitui isso por verdito derivado de achados (prior art, nao reuso cego).
- `artifacts/reference_lab/themes/*.json` — 4 presets (`black_wood_gold` etc.) com `gates`/`status`; fonte do eixo tema.
- `tools/render_parts_iso.py` — `render_parts()` SU-free; renderer barato de proporcao p/ o sweep. **Reuso direto.**
- `tools/reference_db.py` (RAG #1, SQLite/visual) e `tools/project_memory_db.py` (RAG #2, SQLite + Ollama `nomic-embed-text`) — consumidores em FP-035; ja existem.
- `tools/claude_bridge/noc_dispatcher.py` + `.ai_bridge/noc/queue.jsonl` + `actions.jsonl` — runner de fundo (lock 1-atuador, NUNCA main, APARENCIA->VISUAL_REVIEW); base do `kind=variant-sweep`.
- `tools/layout_candidates.py` — expõe `candidates`/`ranking` de parede-TV (ambíguo) — base do eixo `layout_seed`.

**STUB / NAO EXISTE (honestidade):**
- `tools/png_history.py` e `docs/png_history_protocol.md` — **NAO existem** no repo (a memoria `reference_png_history_protocol.md` descreve um protocolo nunca implementado). Nao assumir; o `corpus.jsonl` ja carrega sha+source por render.
- `visual_findings.json` (detector tipado) — **NAO existe**; e' o entregavel de **FP-032** (dependencia). Ate landar, `variant_sweep` roda em modo STUB (`null` + `PENDING_VISION`).
- Vereditos de `batch_theme_render` sao **curados a mao**, nao gerados — FP-034 nasce justamente pra fechar essa lacuna.

**Regras do Felipe aplicadas:** veredito visual final = SO humano (`human_verdict`); maquina = achados + score `machine_provisional`; candidato != canonico; ler-arquivo > acoplar (furnish via env/subprocess); develop-first; micro-fixture(Slice 0 SU-free)->prova->planta real; Ollama (`:11434`) ja usado por `project_memory_db` (embeddings) — sem infra nova.