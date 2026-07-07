# FP-035: RAG Consultável de Design — room/style/budget → spec recuperada injetada no furnish

## Problem

O conhecimento de design existe, mas **não é consultável pelo gerador**. Hoje:

- `tools/reference_db.py` indexa o `reference_lab` num SQLite **faceted** (confirmado BUILT: 74 rows — 25 cards, 6 theme_presets, 43 renders). Mas `query()` é **exact-match puro** (`WHERE room=? AND theme=?`), sem ranking, sem noção de "qual spec serve melhor pra esse cômodo/estilo/orçamento", e sem **nenhum consumidor que injete no furnish** — só `tools/studio_dashboard.py` lê pra mostrar.
- `references/tokens/*.json` (12 tokens builder-consumíveis de cozinha — `hot_tower_niche`, `coordinated_medium_dark_wood_base`, etc., cada um com `params/applies_to_kinds/anti_pattern/gate_refs`) **nem estão no índice** — o `ingest()` varre `artifacts/reference_lab/**/tokens/`, não `references/tokens/`.
- O GERADOR (`tools/interior_studio/architect_program.py`) injeta no prompt do deepseek-r1 o **texto cru** de `.claude/memory/felipe_style_dna.md` truncado em 900 chars. Não consulta tokens curados, não sabe de anti-patterns, não recupera medida/material/layout.
- A curadoria do Felipe (`tools/interior_studio/reference_packs.py` → `references/felipe/<bucket>/`) e o corpus julgado do FP-034 produzem o sinal de "o que é bom", mas **esse sinal morre no dashboard** — o laço curadoria→.skp está aberto.

Resultado: o conhecimento de design é uma pasta de JSON que ninguém consulta na hora de gerar. **Falta o verbo de retrieval** (`room/style/budget → spec de móvel + material + layout + anti-padrões`) e o ponto de **injeção no furnish**.

## Scope

Tornar o conhecimento de design **consultável e injetável**, fechando o laço curadoria→.skp:

1. **Schema `DesignSpecBundle.v1`** — o contrato tipado que o retrieval devolve: `{tokens[], palette, anti_patterns[], layout_hints[], provenance[], confidence}`. `schemas/design_spec_bundle.schema.json`.
2. **Verbo `retrieve(room, style, budget)` em `reference_db.py`** — JOIN faceted sobre as tabelas JÁ populadas + tokens de `references/tokens/`, **rankeado** por `(facet_match, curation_status, gate_pass, cost_fit)`. Colapsa sinônimos via `reference_grammar.TOKEN_SYNONYMS`. Devolve um `DesignSpecBundle.v1`.
3. **Indexação dos `references/tokens/*.json`** no índice (estender `ingest()` ou ler disco no retrieve — decisão na spec).
4. **Injeção no gerador** — `architect_program.py` passa a injetar o bundle estruturado (não o `felipe_style_dna` cru truncado) no prompt, fechando o laço curadoria→furnish→.skp.
5. **Decisão honesta embeddings**: faceted-first; embeddings (`nomic-embed-text` via Ollama) só como fatia OPCIONAL atrás de flag, provada num caso onde a busca faceted falha.

## Non-goals

- **NÃO** construir um vector store por dogma. Ollama `/api/embed` funciona, mas o caso real (`room+style+budget→tokens`) é exact-match sobre dados estruturados — embeddings entram só se um caso NL difuso provar que facet não acha.
- **NÃO** mover geometria nem tocar `consensus.json`/PDF. O bundle manda na LINGUAGEM (token/material/medida); o PDF manda na POSIÇÃO (regra de `reference_grammar`).
- **NÃO** autojulgar aparência. O veredito IMPROVED/SAME/WORSE da cozinha gerada é SÓ do Felipe. O bundle recuperado é **candidato**, não canônico.
- **NÃO** reescrever a curadoria (`reference_packs.py`) nem o placar (FP-034) — apenas **consumir** o `curation_status`/`gate_verdicts` que eles produzem.
- **NÃO** acoplar `reference_db` ao `furnish` por import circular — o gerador **lê** o bundle (chama o verbo), não vira dependência do índice.

## Artifact contract

| Path | Mudança | Quem |
|---|---|---|
| `schemas/design_spec_bundle.schema.json` | **NOVO** — contrato `DesignSpecBundle.v1` | nova sessão |
| `tools/reference_db.py` | **ESTENDER** — verbo `retrieve(room, style, budget)` + ranking + leitura de `references/tokens/`; subcomando CLI `retrieve` | nova sessão |
| `tools/reference_db.py::ingest()` | **ESTENDER** — varrer também `references/tokens/*.json` (hoje só pega `artifacts/reference_lab/**/tokens/`) | nova sessão |
| `tools/interior_studio/architect_program.py` | **ESTENDER** — `room_context()` chama `retrieve()`; `PROMPT` injeta o bundle estruturado no lugar do `dna` cru truncado | nova sessão |
| `tools/reference_grammar.py` | **LER (reuso)** — `collapse_token()`/`TOKEN_SYNONYMS`/`CANON_TOKENS` pra normalizar tokens do bundle | reuso, sem edição |
| `references/tokens/*.json` | **LER** — fonte dos tokens builder-consumíveis (NÃO mutar) | reuso |
| `references/felipe/<bucket>/*.json` + corpus FP-034 | **LER** — sinal de `curation_status`/`gate_verdicts` pro ranking | reuso (dep FP-034) |
| `tests/test_design_retrieval_contract.py` | **NOVO** — contrato bundle + ranking determinístico | nova sessão |
| `tools/reference_db.py::retrieve(..., backend="embed")` | **NOVO OPCIONAL/STUB** — caminho `nomic-embed-text`, atrás de flag, default off | nova sessão (fatia 5) |

## Algorithm

```
# DesignSpecBundle.v1 (o contrato de saída)
DesignSpecBundle := {
  schema_version: "design_spec_bundle.v1",
  query: {room, style, budget},
  tokens:        [ {name, builder_kind, params, applies_to_kinds, source_path} ],  # canônicos (sinônimo colapsado)
  palette:       {role: rgb, ...},          # do theme_preset/token vencedor
  anti_patterns: [ "string", ... ],         # union dos anti_pattern dos tokens + refs anti do Felipe
  layout_hints:  [ "string", ... ],         # position/ergonomia extraídos dos tokens (ex. "torre quente na ponta oposta à geladeira")
  gate_refs:     [ "tools/...::check", ... ],# gates que o builder deve rodar
  provenance:    [ {path, curation_status, gate_verdicts} ],  # honestidade: de onde veio cada peça
  confidence:    "HIGH" | "MEDIUM" | "LOW"  # LOW se FP-034 ainda não julgou / facet fraco
}

def retrieve(room, style, budget=None, backend="faceted"):
    # 1. CANDIDATOS — facets sobre o índice já populado + tokens do disco
    cands  = db.query(room=room, theme=normalize_theme(style))      # cards/theme_presets/renders
    cands += load_tokens_from_disk(references/tokens/, room=room)   # builder-consumíveis
    # 2. NORMALIZA — colapsa sinônimo p/ token canônico (reference_grammar), dedup
    cands = [collapse_token(c) for c in cands]; dedup_by(name)
    # 3. RANKING (determinístico, sem clock/random) — peso por sinal:
    def score(c):
        s  = 3 * facet_exact_match(c, room, style)        # casou room E style?
        s += 2 * curation_weight(c)                       # main=3 approved=2 candidate=1 anti=-5
        s += 1 * gate_pass_count(c.gate_verdicts)         # gates PASS contam
        s += budget_fit(c.cost_relative, budget)          # cost_relative vs budget alvo (-1 se estoura)
        return s
    ranked = sorted(cands, key=score, reverse=True)
    # 4. MONTA o bundle — top-N tokens (não-anti) + anti-patterns + layout_hints
    tokens   = [c for c in ranked if c.kind=="token" and c.status!="anti"][:N]
    antis    = union(c.anti_pattern for c in ranked) + felipe_anti_refs(room, style)
    hints    = extract_layout_hints(tokens)               # campos position/ergonomia dos params
    conf     = confidence(ranked, fp034_corpus_present)   # LOW se FP-034 vazio → honesto, não fabrica
    return DesignSpecBundle(room, style, budget, tokens, palette, antis, hints, gate_refs, provenance, conf)

# INJEÇÃO no gerador (architect_program.room_context):
def room_context(room_id):
    rm = ...
    bundle = retrieve(rm.room_type, felipe_style, rm.budget)   # <- NOVO: troca o dna cru
    ctx["design_spec"] = render_bundle_for_prompt(bundle)      # bloco estruturado, não texto truncado
    # PROMPT passa a citar tokens canônicos + anti-patterns + layout_hints recuperados

# EMBEDDINGS (fatia 5, OPCIONAL, atrás de flag) — só se facet falhar num caso real:
def retrieve(..., backend="embed"):
    qv  = ollama_embed("nomic-embed-text", f"{room} {style} {budget}")  # /api/embed, 768-dim
    sims = cosine(qv, token_vectors)   # token_vectors pré-computados e cacheados por sha256
    # reordena SÓ o desempate; facet/curation continuam dominando o score
```

**Honestidade de dependência (FP-034):** o ranking usa `curation_status` + `gate_verdicts`. Se o corpus julgado do FP-034 ainda não existe, o retrieve **degrada pra facets+gates** e marca `confidence: LOW` — **não fabrica** um ranking de julgamento que não tem. Isso é o `SKIPPED_OFFLINE` do RAG.

## Acceptance

| Critério | PASS | WARN | FAIL |
|---|---|---|---|
| Retrieval faceted | `retrieve(kitchen, black_wood_gold)` devolve ≥3 tokens canônicos relevantes (hot_tower_niche, coordinated_medium_dark_wood_base, ...) ranqueados | devolve tokens mas ranking sem sinal de curadoria (FP-034 ausente) → `confidence: LOW` | devolve vazio ou tokens de outro cômodo |
| Contrato do bundle | valida contra `design_spec_bundle.schema.json`; todo campo preenchido ou explicitamente null | falta `provenance`/`confidence` mas estrutura ok | schema inválido / campo inventado |
| Anti-patterns | bundle carrega os `anti_pattern` dos tokens + refs anti do Felipe | carrega só dos tokens (sem refs Felipe) | anti-pattern ausente quando o token tem |
| Determinismo | 2× `retrieve(...)` = bundle byte-idêntico (ranking estável, sem clock/random) | — | ordem muda entre runs |
| Injeção no gerador | `architect_program` gera programa da cozinha planta_74 citando tokens/anti-patterns recuperados (não o dna cru truncado) | gera mas ainda mistura dna cru | não injeta / quebra o gerador |
| Honestidade FP-034 | corpus ausente → `confidence: LOW` + provenance marca `curation_status: candidate` | — | finge HIGH sem julgamento |
| Embeddings (fatia 5) | só liga atrás de flag; caso real documentado onde facet falhou e embed achou | flag existe mas sem caso provado (stub honesto) | embeddings ligados por default sem prova |
| Veredito visual da cozinha gerada | — | — | sessão autojulga IMPROVED/SAME/WORSE (é SÓ do Felipe) |

## Required tests

| Teste | Tipo | Verifica |
|---|---|---|
| `test_retrieve_kitchen_black_wood_gold_returns_tokens` | unit | facets devolvem tokens canônicos certos do cômodo/estilo |
| `test_retrieve_excludes_wrong_room_tokens` | unit | token de cozinha não vaza em query de bedroom (espelha ROOM_EXCLUSIVE) |
| `test_bundle_validates_against_schema` | contract | saída valida contra `design_spec_bundle.schema.json` |
| `test_ranking_is_deterministic` | unit | 2× = bundle idêntico; sem clock/random/ordem-de-dict |
| `test_synonym_collapse_dedup` | unit | `integrated_fridge_tower`→`fridge_tower`; sem duplicata no bundle |
| `test_anti_pattern_carried` | unit | anti_pattern do token aparece no bundle.anti_patterns |
| `test_confidence_low_when_fp034_corpus_absent` | unit | corpus julgado vazio → confidence LOW, não HIGH fabricado |
| `test_budget_fit_penalizes_overshoot` | unit | token `cost_relative: alto` rebaixado quando budget é baixo |
| `test_architect_prompt_injects_bundle` | integration | `room_context` injeta bloco estruturado do bundle (não dna cru truncado) |
| `test_tokens_dir_indexed` | unit | `references/tokens/*.json` aparecem no índice após ingest |

## Done means

- [ ] `schemas/design_spec_bundle.schema.json` (`DesignSpecBundle.v1`) commitado.
- [ ] `reference_db.py retrieve --room kitchen --style black_wood_gold [--budget mid] [--json]` devolve bundle ranqueado válido.
- [ ] `references/tokens/*.json` indexados (ingest estendido OU lidos no retrieve — documentado no código).
- [ ] Ranking determinístico (sinal: facet + curation + gate_pass + budget_fit); colapso de sinônimo via `reference_grammar`.
- [ ] `architect_program.py` injeta o bundle estruturado no prompt; cozinha planta_74 REAL gerada com tokens/anti-patterns recuperados (laço curadoria→.skp fechado num caso real).
- [ ] Honestidade FP-034: corpus ausente → `confidence: LOW`, não finge julgamento.
- [ ] Embeddings: caminho `nomic-embed-text` atrás de flag, default OFF; marcado STUB até um caso real provar que facet falhou.
- [ ] Todos os `Required tests` verdes; suíte do repo verde.
- [ ] Veredito visual da cozinha gerada deixado EXPLICITAMENTE pro Felipe (não autojulgado).
- [ ] PR `feat/fp-035-rag-design-retrieval` → develop (não deixar PR aberta ao fim).

## Reference

- `tools/reference_db.py` — índice SQLite faceted EXISTENTE (BUILT, 74 rows). `query()` exact-match em `reference_db.py:210-230`; `ingest()` varre `artifacts/reference_lab/**` em `reference_db.py:193-207` (NÃO pega `references/tokens/`).
- `references/tokens/*.json` — 12 tokens builder-consumíveis (cozinha) com `params/applies_to_kinds/anti_pattern/gate_refs` (ex.: `hot_tower_niche.json`, `coordinated_medium_dark_wood_base.json`).
- `tools/reference_grammar.py` — `CANON_TOKENS` (token→builder_kind→rooms), `TOKEN_SYNONYMS`, `collapse_token()` (`reference_grammar.py:39-101,152`). Vocabulário canônico ligado a builder; o bundle DEVE colapsar por aqui.
- `tools/interior_studio/architect_program.py` — GERADOR. `room_context()` injeta `felipe_style_dna.md` cru truncado (`architect_program.py:108-120`); `PROMPT` em `:145-156`. Ponto de injeção do bundle.
- `tools/interior_studio/reference_packs.py` — curadoria Felipe (approve/reject/main/anti → `references/felipe/<bucket>/`), `curate()`/`_write_verdict()`/`_sync_cycle()`. Fonte do `curation_status`.
- **FP-034** (dependência) — corpus julgado de variantes; fonte de `gate_verdicts`/`curation_status` que alimenta o ranking. Sem ele, retrieve degrada pra `confidence: LOW`.
- **Embeddings (decisão honesta):** Ollama :11434 tem `nomic-embed-text` (768-dim, F16) instalado; `/api/embeddings` e `/api/embed` retornam vetor real (verificado por curl nesta sessão). MAS o caso real é exact-match sobre dados estruturados → **faceted-first**; embeddings são fatia OPCIONAL, não fundação.
- `tools/interior_studio/cycles.py`, `schemas/visual_findings.schema.json` (FP-030) — padrão de schema versionado + degradação honesta (`SKIPPED_OFFLINE`) a espelhar.
