# FP-032: ACL de Visão — render → visual_findings.json tipado e DISCRIMINATIVO

> ACL = Anti-Corruption Layer. Os agentes locais (Ollama do furnish / placement)
> e o loop autônomo (FP-033) são CEGOS: agem sobre `consensus.json` e
> `geometry_report.json`, nunca sobre o que *se vê*. Esta FP define o tradutor
> `render → visual_findings.json` tipado — a única porta por onde "o que só o
> olho pega" entra no sistema de forma consumível por máquina.

## Problem

Hoje o sistema decide fidelidade a partir de números (`geometry_report.json`)
e de 10 heurísticas determinísticas. Isso pega *contagem/topologia* (porta
flutuante, vidro órfão, janela full-height, floor ausente) mas é **cego ao
render**: rotação, escala, vazamento visual de chão, "monte de geometria",
desalinhamento vs PDF — os eixos `global_visual` e `scale_rotation` ficam
eternamente em `WARN: needs_human_or_agent`. O humano vira o detector de
regressão visual, o que o projeto proíbe explicitamente
(`skp-visual-self-correction`: "The user is NOT the visual regression detector").

Há um caminho de visão **já codificado** (`OllamaVisionProvider`, default
`qwen2.5vl:7b`) que devolve `visual_findings.v1` válido — **mas ele não
discrimina defeito real**. Prova determinística no repo
(`artifacts/_archive/.../negative_dogfood_20260529T201219Z/summary.md`):
injetando `missing_wall_continuation` no `planta_74_top.png`, o oráculo deu
`FAIL` no render **limpo** E no **corrompido** → `NOT_DISCRIMINATED`. Ou seja:
a ACL existe na forma, mas é **ruído**, não sinal. Um agente cego que confie
nela vai "corrigir" fantasmas.

Em paralelo, o oráculo interno que **enxerga de verdade** (Claude no `:8765`,
modo B) tem o `/ask` **text-only** hoje (`_ask_route` → `parse_ask_payload` lê
só `prompt`/`question`; `POST_ROUTES` não tem rota de imagem). O provider
`chatgpt_bridge_image` já tenta POST multipart e cai em `incompatible` +
escreve `oracle_request_package/` — exatamente porque o servidor recusa imagem.

## Scope

1. **Provar e medir a ACL antes de confiar nela.** Tornar
   `tools/negative_dogfood.py` um gate de *discriminação* multi-backend
   (qwen2.5vl:7b, moondream, Claude-:8765-vision), com taxa de acerto por
   tipo de defeito injetado. Sem isso, nenhum backend é promovido a fonte de
   `global_visual`/`scale_rotation`.
2. **Estender o `:8765` para aceitar imagem** (rota nova `/ask-vision`
   multipart OU campo `images` no `/ask`), emitindo `visual_findings.v1`. É o
   caminho "sem Chrome" e melhor que GPT-via-Chrome (Claude já enxerga, modo B).
   O `chatgpt_bridge_image` provider passa a casar com um servidor real.
3. **Endurecer o schema `visual_findings.v1`** com os campos que a ACL precisa
   pra virar ação: `confidence`, `source` (`deterministic`|`ollama_vision`|
   `claude_bridge`|`human`), `discriminated` (bool, do dogfood) — mantendo
   retrocompat com os findings v1 já gravados.
4. **Definir o contrato de consumo**: como um finding tipado vira uma ação
   consumível pelo agente cego / loop FP-033 (`suspected_owner` →
   builder|opening_routing|consensus; `proposed_fix` acionável). FP-032 entrega
   o *contrato*; FP-033 implementa o atuador.

## Non-goals

- **NÃO** dar veredito visual final IMPROVED/SAME/WORSE por máquina — isso é
  exclusivo do Felipe (regra dura, `negative_dogfood` já provou não-confiável).
  A ACL emite *findings*; o gate de aparência final continua humano.
- **NÃO** implementar o atuador/loop de correção (é FP-033).
- **NÃO** trocar o renderer nem mexer no builder `.skp`.
- **NÃO** acoplar a um serviço externo (Vision API paga / GPT-via-Chrome)
  enquanto Ollama local + Claude :8765 cobrirem — `ler-arquivo > acoplar`.
- **NÃO** plugar `FutureVisionAPIProvider` (continua stub honesto).
- **NÃO** mexer em `fixtures/planta_74/` input (Hard Rule #3).

## Artifact contract

| Path | Mudança | Quem |
|---|---|---|
| `schemas/visual_findings.schema.json` | **EDIT (REAL)** — add `confidence`, `source`, `discriminated` opcionais nos findings + top-level; bump tolerante (v1 continua válido) | sessão |
| `tools/oracle_providers.py` | **EDIT (REAL)** — `OllamaVisionProvider` já existe; add `ClaudeBridgeVisionProvider` (novo) que fala com a rota de imagem do :8765; registrar no `_REGISTRY` | sessão |
| `tools/claude_bridge/server.py` | **EDIT (REAL→NOVO)** — nova rota `/ask-vision` (ou `images` no `/ask`): aceita PNGs b64/multipart + prompt, chama `claude -p` com as imagens, devolve `visual_findings.v1` | sessão |
| `tools/negative_dogfood.py` | **EDIT (REAL)** — multi-backend + multi-defeito; emite `discrimination_report.json` com taxa por backend×defeito; vira gate | sessão |
| `tools/run_skp_visual_review.py` | **EDIT (REAL)** — quando um backend foi PROVADO discriminativo p/ um defeito, deixar de rebaixar `global_visual`/`scale_rotation` p/ WARN-automático e usar o veredito do oráculo (marcado `source`) | sessão |
| `tools/prompts/visual_oracle_reviewer.md` | **EDIT (REAL)** — já existe; ajustar p/ casar campos novos do schema | sessão |
| `tools/prompts/visual_oracle_reviewer_compact.md` | **NOVO (opcional)** — extrair o prompt compacto hoje hardcoded em `OllamaVisionProvider._build_compact_prompt` p/ arquivo (ler-arquivo > hardcode) | sessão |
| `fixtures/visual_acl/defects/*.json` | **NOVO** — catálogo de defeitos injetáveis (rect, rgb, tipo esperado) p/ o dogfood multi-defeito | sessão |
| `tests/test_vision_acl.py` | **NOVO** — contract test do schema endurecido + normalização dos 2 providers + parse da rota de imagem | sessão |
| `artifacts/review/planta_74/vision_acl_<ts>/` | **NOVO (evidência)** — discrimination_report + visual_findings de prova | sessão |
| `docs/specs/FP-032_vision_acl.md` | **NOVO** — esta spec | sessão |

## Algorithm

```
# --- Fatia 1: medir antes de confiar (microtask, sem tocar pipeline) ---
backends = [ollama_vision(qwen2.5vl:7b), ollama_vision(moondream),
            claude_bridge_vision]           # 3o só após a rota :8765 existir
defects  = load(fixtures/visual_acl/defects/*.json)  # missing_wall, floor_leak,
                                                     # rotated, scaled, ...
for backend in backends:
  for defect in defects:
    clean      = render_or_load(planta_74)            # baseline limpo
    corrupted  = inject(clean, defect.rect, defect.rgb)
    vf_clean     = backend.review(clean)              # visual_findings.v1
    vf_corrupted = backend.review(corrupted)
    discriminated = severity(vf_corrupted) > severity(vf_clean)  # pegou a piora?
    record(backend, defect, discriminated, vf_clean, vf_corrupted)
write discrimination_report.json   # taxa por backend × defeito; NUNCA fabrica

# --- Fatia 2: rota de imagem no :8765 (caminho "sem Chrome") ---
POST /ask-vision  {prompt, images:[b64...], context:{gates, stats}}
  -> claude -p (modo B, Opus) COM as imagens anexadas
  -> resposta TEM que ser visual_findings.v1 (valida c/ _normalize_to_visual_findings)
  -> 200 {visual_findings} | 422 se não-normalizável (NUNCA inventa verdict)
ClaudeBridgeVisionProvider.call() casa com isso (mesmo contrato dos outros providers)

# --- Fatia 3: schema -> ação consumível ---
finding = {
  id, severity(WARN|FAIL), axis, type, location, evidence_image, evidence,
  source(deterministic|ollama_vision|claude_bridge|human),   # NOVO
  confidence(low|med|high),                                  # NOVO
  discriminated(bool|null),                                  # NOVO: passou no dogfood?
  suspected_owner(builder|opening_routing|consensus|soft_barrier_routing),
  proposed_fix   # texto acionável p/ o atuador FP-033
}
# Regra de promoção: um finding de oráculo só vira FAIL "duro" se o backend que
# o emitiu tem discriminated=true p/ aquele defect-type no último dogfood.
# Senão -> WARN (sinal fraco, não bloqueia, mas registra).

# --- Fatia 4: integrar no runner ---
run_skp_visual_review --oracle <backend>:
  se backend PROVADO discriminativo p/ o axis -> usa veredito do oráculo (source marcado)
  senão -> mantém WARN-automático honesto (comportamento atual, zero regressão)
```

## Acceptance

| Critério | PASS | WARN | FAIL |
|---|---|---|---|
| Discriminação medida | `discrimination_report.json` gravado p/ ≥3 defeitos × ≥2 backends, com taxa real | só 1 defeito ou 1 backend | nenhum report / taxa fabricada |
| Backend promovido | ≥1 backend discrimina ≥1 defect-type real e isso gateia a promoção a FAIL | nenhum backend discrimina, mas o teto é declarado honestamente no report | runner promove FAIL de backend não-discriminativo |
| Rota :8765 imagem | `/ask-vision` aceita PNG + devolve v1 válido p/ render real de planta_74 | rota existe mas só normaliza em fixture sintética | rota inventa verdict / 500 silencioso / fabrica |
| Schema endurecido | v1 antigo continua validando + campos novos opcionais aceitos | campos novos exigidos (quebra retrocompat) | schema rejeita findings v1 existentes |
| Honestidade | `source` e `discriminated` presentes em todo finding de oráculo | source presente, discriminated ausente | finding de oráculo se passa por determinístico |
| Aparência final | nenhuma máquina emite IMPROVED/SAME/WORSE | — | qualquer auto-veredito de aparência final |

## Required tests

| Teste | Tipo | O que prova |
|---|---|---|
| `test_schema_v1_backcompat` | contract | findings v1 já gravados (kitchen_fix etc.) ainda validam contra o schema endurecido |
| `test_schema_accepts_new_fields` | contract | `source`/`confidence`/`discriminated` aceitos e tipados |
| `test_claude_bridge_vision_normalizes` | unit | resposta da rota de imagem → `_normalize_to_visual_findings` v1 (mock do claude -p) |
| `test_ask_vision_route_rejects_non_v1` | unit | rota devolve 422, NÃO fabrica verdict, quando claude responde fora do schema |
| `test_negative_dogfood_records_discrimination` | integration | dado clean vs corrupted, `discriminated` é computado e gravado (sem rede: providers mockados) |
| `test_promotion_requires_discrimination` | unit | runner NÃO promove FAIL de backend com `discriminated=false` p/ aquele defect-type |
| `test_no_machine_appearance_verdict` | guard | nenhum caminho escreve IMPROVED/SAME/WORSE |
| `test_ollama_vision_offline_writes_package` | unit (já existe padrão) | offline → `oracle_request_package`, status honesto, sem fabricar |

## Done means

- [ ] `discrimination_report.json` real gravado em `artifacts/review/planta_74/vision_acl_<ts>/` cobrindo ≥3 defeitos × ≥2 backends (qwen2.5vl:7b + moondream no mínimo).
- [ ] Rota de imagem no `:8765` (`/ask-vision`) implementada + `ClaudeBridgeVisionProvider` registrado e casando com ela.
- [ ] `schemas/visual_findings.schema.json` endurecido (campos novos opcionais) com retrocompat provada por teste.
- [ ] Regra de promoção "só FAIL duro se discriminado" no `run_skp_visual_review.py`, com `source` marcado em todo finding de oráculo.
- [ ] Catálogo `fixtures/visual_acl/defects/*.json` com ≥3 defeitos (missing_wall já existe no dogfood; add floor_leak, rotated/scaled).
- [ ] Suite de testes nova verde; suite existente (`test_oracle_providers.py`) sem regressão.
- [ ] `docs/specs/FP-032_vision_acl.md` escrita; skill `skp-visual-self-correction` atualizada apontando p/ a ACL provada.
- [ ] Evidência (renders + findings) promovida; nenhuma máquina emite veredito de aparência final.
- [ ] PR `feat/vision-acl` → develop landada (URL de compare se `gh pr create` falhar por escopo do PAT).

## Reference

- `tools/run_skp_visual_review.py` — runner FP-030; 10 checks determinísticos (`inspect_report`), provider call, agregação `worst_verdict`, `--oracle {none,chatgpt_bridge_image,ollama_vision,future_vision_api}`.
- `tools/oracle_providers.py` — `OracleProvider`/`OracleResponse`; **`OllamaVisionProvider` (REAL, default qwen2.5vl:7b)** com prompt compacto, resize 900px, extração de JSON balanceado; `_normalize_to_visual_findings` (gate de schema); `ChatGPTBridgeImageProvider` tenta multipart e cai em `incompatible` (porque o :8765 é text-only).
- `tools/claude_bridge/server.py` — `_ask_route` (TEXT-ONLY: `parse_ask_payload` lê só `prompt`/`question`); `GET_ROUTES`/`POST_ROUTES` (sem rota de imagem); modo B (Opus 4.8, `VISUAL_REVIEW` é o único gate humano).
- `tools/negative_dogfood.py` — harness de discriminação (REAL). Prova em `artifacts/_archive/review_legacy_20260609/negative_dogfood_20260529T201219Z/summary.md`: ollama_vision deu FAIL no LIMPO e no CORROMPIDO → **NOT_DISCRIMINATED**.
- `schemas/visual_findings.schema.json` — `visual_findings.v1` (campos: `kind`/`type`, `severity`, `axis`, `location`, `evidence`, `source_check`, `suspected_owner`, `proposed_fix`).
- `tools/prompts/visual_oracle_reviewer.md` — prompt full do reviewer (6 eixos + tabela de defeitos + JSON estrito).
- `fixtures/planta_74/known_warnings.json` — WARNs arquiteturais carregados (oráculo PASS não os apaga).
- Modelos Ollama instalados (host, :11434, confirmado): `qwen2.5vl:7b`, `moondream` (ambos visão), `deepseek-r1:14b`, `qwen2.5-coder:14b`, `interior-designer`.
- Renders consumíveis: `furnish_apartment.py` → `planta_74_furnished_after_top.png` / `_after_iso.png`; `run_skp_visual_review` → `model_top.png`/`model_iso.png` + `side_by_side_pdf_vs_skp.png` (via `compose_side_by_side.compose_to_file`).
- Git: branch atual `chore/ci-gate`; OllamaVisionProvider landou em `#206`, dogfood-prova em `#209`. Branch desta FP: `feat/vision-acl` off `origin/develop`.