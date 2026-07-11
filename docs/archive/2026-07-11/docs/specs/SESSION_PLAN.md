# Programa Visão + RAG + Autonomia — plano de sessões

> 5 fronts pra o sistema **gerar/melhorar plantas sem o humano no laço interno**.
> O Felipe valida periodicamente pelo dashboard/cockpit. A **ordem importa** (dependências).
> Cada front = 1 spec FP (`docs/specs/FP-0xx_*.md`) + 1 sessão (ou 1-2).

## Ordem recomendada

1. **FP-032 (Olhos / ACL de visão)** — fundação, tudo depende.
2. **FP-036 (Material de verdade)** — independente; **quick win** que já conserta o 'móveis brancos' que o Felipe viu. Pode rodar em paralelo a qualquer momento.
3. **FP-033 (Loop de correção)** — usa os olhos do FP-032.
4. **FP-034 (Placar de variantes)** — usa os olhos; gera o corpus julgado.
5. **FP-035 (RAG consultável)** — indexa o corpus do FP-034.

Paralelizável: FP-036 a qualquer hora; FP-033 e FP-034 podem ir juntos depois do FP-032.

## Tabela

| Front | Spec | Sessões | Microtasks | Depende de |
|---|---|---|---|---|
| ACL de Visão | [FP-032](FP-032_vision_acl.md) | 1-2 sessões | 5 | — |
| Closed Correction Loop | [FP-033](FP-033_closed_correction_loop.md) | 1-2 sessões | 5 | FP-032 |
| PLACAR DE VARIANTES JULGADAS | [FP-034](FP-034_judged_variant_sweep.md) | 1-2 sessoes | 5 | FP-032 |
| RAG Consultável de Design | [FP-035](FP-035_rag_design_retrieval.md) | 1-2 sessoes | 5 | FP-034 |
| Material de Verdade | [FP-036](FP-036_material_de_verdade.md) | 1-2 sessoes | 5 | — |

## Como abrir cada sessão (cole o prompt de kickoff)

### Sessão 1 — FP-032: ACL de Visão
- **Spec:** `docs/specs/FP-032_vision_acl.md` · **1-2 sessões** · **5 microtasks** · depende de: —
- **1ª fatia (menor risco):** Rodar negative_dogfood.py com 3 backends (ollama_vision qwen2.5vl:7b, moondream, Claude :8765-vision-extension) sobre o defeito missing_wall já injetado em planta_74 e gravar discrimination_report.json com a TAXA DE DISCRIMINAÇÃO de cada um — isso prova, em uma microtask, qual ACL serve sem tocar no pipeline.

**Prompt de abertura:**

```text
Sessão: executar FP-032 (ACL de Visão) no repo apps/sketchup-mcp. Leia primeiro a spec FP-032 em docs/specs/FP-032_vision_acl.md (crie-a a partir do markdown que vou colar abaixo se ainda não existir) e os arquivos âncora: tools/run_skp_visual_review.py, tools/oracle_providers.py (OllamaVisionProvider já existe, default qwen2.5vl:7b), tools/negative_dogfood.py, tools/claude_bridge/server.py (o /ask é TEXT-ONLY hoje — _ask_route lê só prompt/question via parse_ask_payload; POST_ROUTES não tem rota de imagem), schemas/visual_findings.schema.json, e o achado-chave em artifacts/_archive/review_legacy_20260609/negative_dogfood_20260529T201219Z/summary.md (ollama_vision deu FAIL no render LIMPO e no CORROMPIDO → NOT_DISCRIMINATED).

REGRA DURA (Felipe): honestidade — o OllamaVisionProvider já RODA e devolve v1 válido, mas NÃO discrimina defeito real (negative-dogfood provou). O objetivo do FP-032 NÃO é "ligar visão" (já está ligada) — é tornar a ACL render→findings CONFIÁVEL o suficiente pros agentes cegos (Ollama do furnish) e o loop FP-033 agirem, OU declarar honestamente o teto de cada backend. Veredito visual final IMPROVED/SAME/WORSE continua sendo SÓ do Felipe — a ACL emite findings TIPADOS e DETERMINÍSTICOS-quando-possível, nunca decide aparência final.

Develop-first: branch feat/vision-acl a partir de origin/develop. Micro-fixture→prova→planta real. Comece pela 1a fatia: rode tools/negative_dogfood.py comparando os 3 backends de visão (qwen2.5vl:7b, moondream, e o :8765 estendido pra imagem) no defeito missing_wall já injetado em planta_74, e grave a taxa de discriminação de cada um. Só depois mexa no resto da spec. Ollama vivo em :11434 (qwen2.5vl:7b e moondream confirmados instalados). Não suba bridge manual em paralelo ao :8765 (Hard Rule).
```

### Sessão 2 — FP-036: Material de Verdade
- **Spec:** `docs/specs/FP-036_material_de_verdade.md` · **1-2 sessoes** · **5 microtasks** · depende de: —
- **1ª fatia (menor risco):** No path interativo (place_layout_skp.rb / pl_material), atribuir m.texture por kind a partir do mapa texture_map_for(style) que JA existe em style_spec.py, usando os PNGs JA versionados em assets/textures/procedural/ — provando num unico .skp da sala r002 que o sofa/rack saem com trama/veio em vez de branco chapado.

**Prompt de abertura:**

```text
Sessao: executar FP-036 (Material de Verdade) no repo apps/sketchup-mcp. Develop-first: branch nova `feat/material-de-verdade` a partir de origin/develop.

CONTEXTO ja ancorado (li o codigo, confie nestes fatos):
- O BUG real do Felipe ("moveis brancos, sem textura") esta no path HUMANO/interativo: tools/place_layout_skp.rb funcao pl_material (linhas 43-50) so faz `m.color = ...` + `m.alpha = 1.0`. NUNCA seta `m.texture`. O .skp que o Felipe abre (artifacts/planta_74/furnished/planta_74_furnished.skp, gerado por tools/furnish_apartment.py) sai com material de COR CHAPADA.
- O path V-Ray (tools/vray_export.rb, linhas 14-143) JA aplica `m.texture` corretamente, por kind, via tex_map gated por VRAY_TEX_DIR. Mas isso so existe na exportacao V-Ray, nao no .skp interativo.
- tools/style_spec.py JA tem `kind_texture` por estilo (_INDUSTRIAL_TEX, _MODERN_WARM_TEX) e a funcao `texture_map_for(style)` que documenta/espelha o mapa do .rb. apply_style hoje so reescreve b['rgb'] (cor chapada) — e a fonte UNICA da cor do material ph_<kind>.
- 17 PNGs procedurais JA versionados em assets/textures/procedural/ (wood_dark.png, wood_medium.png, fabric_charcoal.png, fabric_light.png, concrete.png, metal_black_matte.png, stone_counter.png, porcelain.png, wood_floor.png, etc.), gerados por tools/gen_textures.py (com override PBR CC0 de assets/textures/pbr/ quando presente).
- references/materials/{wood,metal,stone,lacquer}.md tem RGB + linguagem de finish/roughness/metalness (ex.: grafite fosco roughness 0.6-0.8; inox escovado metalness alto roughness 0.3-0.5; gloss roughness baixa). NAO ha hoje estrutura de dados de finish — so prosa.
- tools/interior_studio/render_fingerprint.py extrai palette/saturation/clipped_white/zone_colors de um PNG sem LLM (PIL+numpy) — use isso pro flat-white gate.
- NAO existe gate de flat-white ainda.

LER PRIMEIRO (na ordem): a spec FP-036 inteira; tools/style_spec.py; tools/place_layout_skp.rb; tools/vray_export.rb (so o bloco tex_map); tools/furnish_apartment.py (collect_boxes + main); tools/style_coherence_gate.py (molde do gate a espelhar).

REGRAS DURAS (inegociaveis): (1) kind = fonte UNICA do material — NUNCA pintar tudo com a textura da 1a peca; cada material ph_<kind> recebe a textura do SEU kind ou nenhuma. (2) NAO regredir os renders V-Ray que ja sao PASS (sofa-sala, quarto) — o path V-Ray ja funciona; nao mexer no comportamento default dele. (3) Veredito visual IMPROVED/SAME/WORSE e SO do Felipe — nenhuma maquina decide aparencia FINAL; o flat_white_check e gate DETERMINISTICO ("isto NAO esta chapado de branco?"), nao julga se ficou bonito. (4) ler-arquivo > acoplar. (5) micro-fixture -> prova -> planta real. (6) Ollama vivo em :11434 se precisar consultar; oraculo de decisao real e o :8765 (gpt-auto-consult-gate).

METODO: comecar pela primeira fatia (texturizar o path interativo de UM comodo r002 e provar que sai textura, nao branco), so depois generalizar pra planta inteira, depois o finish/BRDF token, depois o flat_white_check gate, por fim rodar na planta_74 real e entregar o .skp pro Felipe dar o veredito. Nada de --mode headless em dev local. Promover .skp de evidencia pra artifacts/ (nao deixar em runs/). Nunca deixar PR aberto: landar contra develop ou descartar explicitamente.
```

### Sessão 3 — FP-033: Closed Correction Loop
- **Spec:** `docs/specs/FP-033_closed_correction_loop.md` · **1-2 sessões** · **5 microtasks** · depende de: FP-032
- **1ª fatia (menor risco):** Slice 0 (engine puro, sem NOC, sem visão): tools/correction_loop.py com a máquina de estados + classificador de finding (DETERMINISTIC_AUTOFIX / NEEDS_VISION / NEEDS_FELIPE) + um único fix-handler determinístico real (ex.: furniture_overlap_gate FAIL → re-roda o brain do cômodo / aplica nudge documentado) sobre uma micro-fixture, parando em PASS/patinagem/RED. Prova que o laço fecha 1 ciclo antes de tocar render/NOC/cockpit.

**Prompt de abertura:**

```text
Você vai EXECUTAR a spec FP-033 (Closed Correction Loop) no app `apps/sketchup-mcp` do workspace E:\Claude. Leia a spec inteira primeiro: `apps/sketchup-mcp/docs/specs/FP-033_closed_correction_loop.md`. Ela depende de FP-032 (ACL de visão) — se FP-032 ainda não existir, a rota NEEDS_VISION degrada honesto pra BLOCKED_NEEDS_FP032 (NUNCA fabrique um achado visual).

CONTEXTO QUE A SPEC ANCORA (já confirmado lendo o código — releia antes de codar): o laço quase todo já existe em peças soltas e seu trabalho é COSTURAR, não reescrever: `tools/run_deterministic_gates.py` (detector shell, `run_all()`), `tools/geometry_sanity.py` + `tools/furniture_overlap_gate.py` (detectores de móvel), `tools/run_skp_visual_review.py` + `schemas/visual_findings.schema.json` v1 (rebuild+re-check; auto-fix é o Follow-up não-feito do FP-030 — É O QUE VOCÊ ENTREGA), `tools/claude_bridge/noc_dispatcher.py` (worktree isolado off develop + VISUAL_REVIEW_QUEUED), `tools/claude_bridge/server.py` (`POST /heartbeat` + `sessions_view`), e `apps/sketchup-mcp-bff/noc_mirror.py` (cockpit lê o ledger). A `autonomous-fidelity-loop` SKILL é o protocolo humano — você está transformando em código (`tools/correction_loop.py`).

REGRAS DURAS INEGOCIÁVEIS (do Felipe): (1) Veredito visual final IMPROVED/SAME/WORSE é SÓ do Felipe — nenhuma máquina decide aparência final; aparência → SEMPRE rota NEEDS_FELIPE → VISUAL_REVIEW_QUEUED. (2) Honestidade: nunca pintar stub de pronto; tipo sem handler determinístico real → roteado honesto, não fingido consertado. (3) Fix é source-supported (só usa dados da consensus, nunca inventa parede/móvel) e idempotente. (4) NÃO mutar fixtures de input (`fixtures/planta_74/`, `fixtures/quadrado/`); NÃO `--mode headless` em dev local; NÃO push em main / auto-merge / tocar worktree de sessão viva. (5) ler-arquivo > acoplar; candidato ≠ canônico; develop-first.

COMECE PELA PRIMEIRA FATIA (menor risco que prova valor): `tools/correction_loop.py` com a máquina de estados + `tools/finding_router.py` (classificador) + `tools/correction_fixes.py` com UM handler determinístico real (`furniture_overlap` FAIL → re-roda o brain do cômodo / nudge documentado), provando detect→fix→re-check fechando em ≤2 ciclos sobre uma MICRO-FIXTURE sintética, ANTES de tocar render/NOC/cockpit. Red→green: escreva o teste que falha antes do fix. Só depois ligue o wiring NOC e o heartbeat. Branch nova off `origin/develop` (`feat/fp-033-correction-loop`). Termine com suíte verde + 1 prova em planta real e PR contra develop — não deixe PR aberto.
```

### Sessão 4 — FP-034: PLACAR DE VARIANTES JULGADAS
- **Spec:** `docs/specs/FP-034_judged_variant_sweep.md` · **1-2 sessoes** · **5 microtasks** · depende de: FP-032
- **1ª fatia (menor risco):** Slice 0 (micro-fixture, ZERO dependencia de FP-032): definir o `Variant` dataclass + `expand_axes()` (estilo x material x layout-seed) e o esquema `judged_variant.schema.json`, e rodar um sweep de 4-6 variantes SU-FREE com `render_parts_iso`/montagem, gravando os registros em `runs/variant_sweep/<run_id>/corpus.jsonl` com `visual_findings=null` (placeholder ate FP-032). Prova: `python -m tools.variant_sweep --dry-run --n 4` emite 4 linhas validas no JSONL + uma folha de contato. So depois pluga o detector real de FP-032.

**Prompt de abertura:**

```text
Sessao: implementar FP-034 (PLACAR DE VARIANTES JULGADAS) no repo apps/sketchup-mcp. Leia a spec FP-034 inteira antes de tocar codigo — ela esta ancorada em arquivos REAIS que voce DEVE reler: tools/furnish_apartment.py (eixo estilo via env FURNISH_STYLE industrial/modern_warm; PT_TO_M=0.0259 obrigatorio), tools/style_spec.py (STYLE_TOKENS), tools/sofa_class_matrix.py (o padrao de matriz derive->gate->render->grid->matrix_report.json que voce vai espelhar pra plantas), tools/render_parts_iso.py (renderer SU-free barato), tools/batch_theme_render.py (eixo material/tema; HOJE os vereditos sao curados a mao — FP-034 os torna gerados a partir de achados), tools/reference_db.py + tools/project_memory_db.py (os 2 RAGs SQLite que FP-035 vai consumir), e o NOC dispatcher (tools/claude_bridge/noc_dispatcher.py + .ai_bridge/noc/queue.jsonl/actions.jsonl) pra entender o kind=variant-sweep de fundo.

REGRAS DURAS (inegociaveis): (1) HONESTIDADE — png_history.py NAO existe (a memoria descreve um protocolo nunca construido); o produtor de visual_findings.json e' FP-032 (sua dependencia) — se FP-032 ainda nao landou, rode com adapter STUB que grava visual_findings=null e marque o registro verdict=PENDING_VISION, NUNCA finja achados. (2) VEREDITO VISUAL final (IMPROVED/SAME/WORSE / "melhor nesse caso") e' SO do Felipe — a maquina so registra achados tipados + um score DERIVADO/PROVISORIO rotulado machine_provisional; nunca grave um veredito estetico final como se fosse humano. (3) candidato != canonico — o corpo do sweep e' candidato; nada vira golden sem o Felipe. (4) develop-first (branch feat/judged-variant-sweep off origin/develop), micro-fixture->prova->planta real, ler-arquivo > acoplar. (5) PT_TO_M=0.0259 SEMPRE no furnish da planta_74 (senao movel flutua 1.36x).

Comece pelo firstSlice (Slice 0, SU-free, sem depender de FP-032): Variant dataclass + expand_axes() + judged_variant.schema.json + sweep de 4-6 variantes gravando runs/variant_sweep/<run_id>/corpus.jsonl com visual_findings=null. Prove com `python -m tools.variant_sweep --dry-run --n 4`. So depois pluge o detector de FP-032 e o registro julgado real. Ao terminar uma fatia que muda APARENCIA, enfileire VISUAL_REVIEW pro Felipe — nao auto-aprove.
```

### Sessão 5 — FP-035: RAG Consultável de Design
- **Spec:** `docs/specs/FP-035_rag_design_retrieval.md` · **1-2 sessoes** · **5 microtasks** · depende de: FP-034
- **1ª fatia (menor risco):** Adicionar verbo `retrieve(room, style, budget)` em reference_db.py que faz JOIN faceted sobre as tabelas JÁ populadas (74 rows) + tokens de references/tokens/*.json, rankeia por (facet_match desc, curation_status, gate_pass), e devolve um DesignSpecBundle.v1 tipado {tokens[], palette, anti_patterns[], layout_hints[], provenance[]}. Prova: `python tools/reference_db.py retrieve --room kitchen --style black_wood_gold --json` devolve hot_tower_niche + coordinated_medium_dark_wood_base + anti-patterns, SEM tocar furnish ainda. Embeddings ficam fora desta fatia (faceted paga primeiro).

**Prompt de abertura:**

```text
Sessão: executar FP-035 (RAG Consultável de Design) no repo apps/sketchup-mcp. Leia a spec FP-035 inteira ANTES de tocar código (ela está no handoff desta sessão; o markdown completo está no campo `markdown` do StructuredOutput desta FP). Contexto-âncora que JÁ confirmei lendo o código real (não re-descubra do zero, mas VALIDE):

- `tools/reference_db.py` EXISTE e está BUILT (74 rows: 25 cards, 6 theme_presets, 43 renders). Tem `query()` SÓ exact-match faceted (room/theme/kind/sub_element/tag/curation/gate_pass). NÃO tem ranking, NÃO tem embeddings, NÃO tem verbo room+style+budget→spec. NÃO tem nenhum consumidor que injete no furnish (só `studio_dashboard.py` lê pra mostrar).
- `references/tokens/*.json` = 12 tokens builder-consumíveis (cozinha): cada um tem `name/rule/params/applies_to_kinds/anti_pattern/cost_relative/gate_refs`. Estes NÃO estão indexados na reference.db hoje (o ingest pega `**/tokens/*.json` dentro de artifacts/reference_lab, não references/tokens). Honestidade: confirmar isso e decidir se o retrieve lê o token do disco direto OU se estende o ingest.
- `tools/reference_grammar.py` tem CANON_TOKENS (token→builder_kind→rooms) + TOKEN_SYNONYMS — é o vocabulário canônico ligado a builder. O retrieve DEVE colapsar sinônimos por aqui (não inventar token novo).
- `tools/interior_studio/architect_program.py` é o GERADOR: injeta `felipe_style_dna.md` (texto cru, truncado em 900 chars) no prompt do deepseek-r1. É AQUI que o spec recuperado entra (fatia 4): trocar/aumentar o `dna` cru por um DesignSpecBundle estruturado recuperado pelo room/style.
- `tools/interior_studio/reference_packs.py` = curadoria do Felipe (approve/reject/main/anti → references/felipe/<bucket>/). O corpus julgado do FP-034 (placar de variantes) é a fonte de `curation_status`/`gate_verdicts` que o ranking consome. FP-034 é dependência — se o corpus julgado ainda não existe, o retrieve degrada pra facets+gates sem o sinal de julgamento (marcar como WARN honesto, não fabricar ranking).
- EMBEDDINGS: Ollama vivo em :11434 TEM `nomic-embed-text` (768-dim) instalado; `/api/embeddings` e `/api/embed` retornam vetor real (confirmei via curl). MAS: a decisão honesta da spec é FACETED-FIRST. O caso real (room+style+budget→tokens) é exact-match sobre dados estruturados; embeddings só pagam pra query NL difusa. Implementar o caminho faceted+ranked primeiro; embeddings entram como fatia OPCIONAL atrás de flag, provada num caso onde facet falha. Não construir embeddings por dogma.

Ordem de execução (develop-first, branch feat/fp-035-rag-design-retrieval off origin/develop):
1. micro-fixture → DesignSpecBundle.v1 schema + retrieve() faceted+ranked (prova via CLI, sem tocar furnish).
2. teste de contrato do bundle + teste de ranking determinístico.
3. ligar tokens de references/tokens/ ao índice (decidir: estender ingest vs ler disco).
4. injetar o bundle no architect_program (fechar laço curadoria→.skp); rodar na planta_74 cozinha REAL.
5. fatia embeddings OPCIONAL atrás de flag, só se um caso real provar que facet não acha.

Regras duras: honestidade (stub é stub, marcar WARN onde FP-034 não entregou ainda); ler-arquivo > acoplar (o retrieve LÊ o db/tokens, não importa o furnish); o veredito visual IMPROVED/SAME/WORSE da cozinha gerada é SÓ do Felipe — a sessão NÃO autojulga aparência; candidato != canônico (o spec recuperado é proposta, Felipe aprova). Termina numa cozinha planta_74 real gerada com o spec recuperado + handoff. Não abrir PR sem os testes verdes.
```
