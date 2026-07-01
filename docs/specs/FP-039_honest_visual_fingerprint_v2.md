# FP-039 — Honest Visual Fingerprint v2

> Formaliza a lição do [[FP-036]]. **Dependência PENDENTE:** as métricas `near_white_pct` e
> `texture_frac` e o `flat_white_gate` vêm do branch `feat/material-de-verdade` (ainda NÃO mergeado
> em `develop` — checado 2026-07-01). Este spec generaliza esse gate; não o reimplementa.

## 1. Contexto

O FP-036 tentou um gate de "tem textura?" por variância de pixel (`texture_frac`) e a **revisão
adversarial multi-agente CONFIRMOU 2 defeitos** (registro literal do FP-036):
- **Falso-negativo:** o tecido do pipeline é sutil (`fabric_charcoal.png` std de tile ~1.0) → um sofá
  GENUINAMENTE texturizado lia como chapado → o gate **falso-FALHAVA o próprio sofá que o FP-036
  entrega** (`texture_frac lo=2.0` acima da amplitude do tecido).
- **Falso-positivo:** as **arestas antialiased** do render de linha do SketchUp caem na banda-média
  (std ~5-11) → uma peça de cor CHAPADA porém facetada (sofá tufado, rack ripado) **passava** por
  "textura" sem material nenhum.

Conclusão que virou decisão de engenharia no FP-036: **`texture_frac` NÃO é veredito confiável** num
render de linha do SU; ficou **advisory** (reportado como `texture_frac_advisory`, não decide), e o
veredito do gate passou a ser `near_white_frac` (sinal limpo de "lavado/branco") + WARN de
render-quase-vazio (contraste global mínimo). A prova de textura aplicada é o **log per-kind do
`.rb`** + o **olho do Felipe** — não um limiar de pixel.

Essa lição foi aprendida uma vez de forma cara. FP-039 a **cristaliza num contrato durável** pra que
nenhum gate futuro volte a fingir saber estética por pixel.

## 2. Problema concreto

Hoje o `render_fingerprint.py` mistura, no mesmo dict plano, métricas de **confiabilidades
diferentes** sem marcar qual pode decidir:
- confiáveis: `near_white_pct`, `exposure.contrast_std`, `clipped_pct`;
- traiçoeiras: `texture_frac` (provado falho nos dois sentidos);
- e não há métrica pra dois casos reais de "chapado" que o Felipe cita: **grandes áreas chapadas** e
  **dominância de cinza/bege uniforme** (o render "morto"/monótono).

Sem uma **taxonomia explícita** (confiável × advisory × proibido), o próximo gate corre o risco de:
(a) reusar `texture_frac` como veredito de novo (o erro do FP-036), ou (b) escorregar pra julgamento
estético automático ("parece premium", "tecido bonito") — o que os gates deste repo **nunca** podem
fazer (memória `feedback_visual_review_chrome_only`; o veredito IMPROVED/SAME/WORSE é do Felipe).

## 3. Escopo

Especificar um **fingerprint v2 honesto** com **três tiers explícitos** e um gate que só decide com o
tier confiável:

1. **Métricas CONFIÁVEIS (decision-grade)** — o gate PODE decidir com elas:
   - `near_white_frac` — excesso de branco/washed (já existe, FP-036).
   - `neutral_dominance` — fração em **cinza/bege dessaturado uniforme** (render "morto"/monótono). NOVA.
   - `contrast_std` — contraste global (já existe); baixo ⇒ render quase-vazio/liso.
2. **Métricas ADVISORY** — reportadas, **nunca** decidem:
   - `texture_frac` (já existe; motivo documentado no FP-036).
   - ⚠️ `large_flat_area_frac` — **era p/ ser confiável, mas a IMPLEMENTAÇÃO (calibração) DEMOVEU pra
     advisory**: mede "área de cor sólida ampla", mas parede/piso e blocos coloridos LEGÍTIMOS também
     são sólidos (fixture colorida=0.87, deliverable texturizado=0.59) → não distingue "chapado ruim"
     de "sólido ok", então não pode decidir. Fica reportada. (O próprio fingerprint honesto se
     auto-corrigindo — é o espírito do FP-039.)
   - `edge_frac` — fração de tiles de alto gradiente (arestas do SU); NOVA, advisory (confunde textura).
   - `palette_entropy` — entropia de Shannon da paleta dominante; NOVA, advisory (diversidade de cor).
3. **Julgamentos PROIBIDOS pra decisão automática** — o gate **NÃO** pode emitir:
   - "parece premium", "tecido bonito", "madeira elegante", "ficou bonito/feio", ou qualquer veredito
     estético subjetivo. Isso é do Felipe.

O gate v2 emite `result ∈ {PASS, WARN, FAIL}` + `flags` de um **vocabulário FIXO e confiável** (ex.
`chapado_de_branco`, `grande_area_chapada`, `neutro_monotono`, `quase_vazio`) — e **só** esses.

## 4. Não-escopo

- **Não** decidir aparência/estética automaticamente — o gate diz "risco de chapado/washed", nunca
  "está bonito". Veredito final = Felipe.
- **Não** tentar de novo um veredito de "tem textura?" por pixel — `texture_frac` fica advisory.
- **Não** LLM/visão de rede aqui — só PIL+numpy determinístico (o LLM de visão é o [[FP-032]]).
- **Não** quebrar consumidores existentes do `fingerprint()` (`render_judge.py`, `flat_white_gate`) —
  a v2 é **aditiva/compatível** (chaves antigas preservadas; tiers adicionados).
- **Não** tocar geometria/material/render.

## 5. Arquivos ancorados

| Arquivo | Papel | Mudança FP-039 |
|---|---|---|
| `tools/interior_studio/render_fingerprint.py` | `fingerprint()` → dict plano (exposure/clipped/near_white_pct/texture_frac/palette/zones) | NOVO: `large_flat_area_frac`, `neutral_dominance`, `edge_frac`, `palette_entropy` + `METRIC_TIERS` (manifesto de tiers); chaves antigas preservadas |
| `tools/flat_white_gate.py` | veredito = near_white + blank WARN; `texture_frac_advisory` reportado (FP-036) | Passa a consumir **só o tier CONFIÁVEL** via `METRIC_TIERS`; ganha flags `grande_area_chapada`/`neutro_monotono`; vocabulário de flags FIXO |
| `tools/interior_studio/render_judge.py` | lê `fp["exposure"]`, `clipped_pct`, `warmth`, `palette` (l.99-111) | READ-ONLY (compat: só lê chaves que continuam existindo) |
| `references/…` (memórias) | `feedback_visual_review_chrome_only`, `negative_dogfood` | READ-ONLY (fonte da regra "estética = humano") |

## 6. Estratégia técnica

**Manifesto de tiers (a espinha dorsal do contrato):**
```
METRIC_TIERS = {
  "reliable": ["near_white_frac", "large_flat_area_frac", "neutral_dominance", "contrast_std"],
  "advisory": ["texture_frac", "edge_frac", "palette_entropy"],
  # "forbidden" não é métrica: é a LISTA de julgamentos que o gate não pode emitir (enforced por teste)
}
FORBIDDEN_JUDGMENT_TERMS = ["bonito","feio","premium","elegante","lindo","caro","barato","chique", ...]
```

**Novas métricas confiáveis (determinísticas, PIL+numpy):**
- `large_flat_area_frac(arr, win=32, eps=2.0)`: fração de tiles GRANDES (win×win) com std < eps →
  "grandes áreas chapadas". Janela grande (32) porque o alvo é ÁREA ampla lisa, não micro-liso;
  distinto do `texture_frac` (win=8, banda-média). Uma parede/tampo chapado grande ⇒ alto; render com
  variação ⇒ baixo.
- `neutral_dominance(arr, sat_max=0.12, lum=(70,215))`: fração de pixels com **baixa saturação**
  (HSV S ≤ sat_max) dentro de uma faixa de luminância média → dominância de cinza/bege uniforme
  (render monótono/"morto"). Não confunde com preto/branco puro (fora da faixa de lum).

**Novas métricas advisory:**
- `edge_frac(arr, win=8, hi=20.0)`: fração de tiles com std > hi (arestas de alta amplitude do SU).
  Explicitamente advisory — mede densidade de LINHA, não material.
- `palette_entropy(img, k=8)`: entropia de Shannon das % da paleta dominante (`dominant_palette`).
  Advisory: diversidade de cor ≠ beleza.

**Gate v2 (consome só o tier confiável):**
```
def flat_white_check(png, style=None):
    fp = fingerprint(png)
    rel = {k: _get(fp, k) for k in METRIC_TIERS["reliable"]}   # decide SÓ com estes
    flags, result = [], "PASS"
    if rel["near_white_frac"]     >= WHITE_FAIL:  flags += ["chapado_de_branco"];  result="FAIL"
    if rel["large_flat_area_frac"] >= FLAT_FAIL:  flags += ["grande_area_chapada"]; result="FAIL"
    if rel["neutral_dominance"]    >= NEUTRAL_WARN: flags += ["neutro_monotono"];   result=max(result,"WARN")
    if rel["contrast_std"]         <  BLANK_WARN:   flags += ["quase_vazio"];        result=max(result,"WARN")
    # advisory vai nas metrics, NÃO no veredito:
    return {"result": result, "flags": flags,
            "reliable": rel, "advisory": {k:_get(fp,k) for k in METRIC_TIERS["advisory"]}}
```
Thresholds **calibrados como no FP-036**: micro-fixtures (chapado grande → FAIL; textura → PASS;
neutro monótono → WARN) ANTES de qualquer render real; o baseline chapado deve WARN/FAIL, o
texturizado não pode falso-FALHAR (o guard do sofá de tecido do FP-036 continua valendo).

**Enforcement do contrato (o coração honesto):**
- Um teste garante que a função de veredito **não lê nenhuma chave advisory** (o veredito é função
  pura das confiáveis) — refatorando o gate pra receber só `rel` é o jeito de tornar isso testável.
- Um teste garante que **nenhuma `flag` nem chave de saída** contém termo de `FORBIDDEN_JUDGMENT_TERMS`
  (o gate não pode dizer "bonito"/"premium").
- `texture_frac` continua reportado em `advisory`, com o caveat do FP-036 no docstring.

## 7. Testes obrigatórios

| Teste | Tipo | Prova |
|---|---|---|
| `test_metric_tiers_partition` | unit | `reliable ∩ advisory = ∅`; toda chave do veredito ∈ `reliable` |
| `test_verdict_ignores_advisory_metrics` | contract | mutar só `texture_frac`/`edge_frac`/`palette_entropy` NÃO muda `result` (veredito é função das confiáveis) |
| `test_gate_never_emits_aesthetic_judgment` | contract | nenhuma `flag`/chave de saída contém termo de `FORBIDDEN_JUDGMENT_TERMS`; o gate não tem campo "premium/bonito" |
| `test_large_flat_area_fails_on_big_chapado` | unit (micro-fixture) | imagem com grande área de cor uniforme → `large_flat_area_frac` alto → FAIL/`grande_area_chapada` |
| `test_neutral_dominance_warns_on_monotone` | unit (micro-fixture) | imagem cinza/bege dessaturada uniforme → `neutral_dominance` alto → WARN/`neutro_monotono` |
| `test_white_still_fails` | unit | PNG quase-branco → FAIL/`chapado_de_branco` (regressão do FP-036 preservada) |
| `test_textured_sofa_not_false_failed` | unit (guard FP-036) | sofá de tecido enchendo o frame → result ≠ FAIL (o falso-negativo do FP-036 não volta) |
| `test_fingerprint_backward_compatible` | unit | chaves antigas (`exposure`,`clipped_pct`,`warmth`,`palette`,`near_white_pct`,`texture_frac`) continuam presentes → `render_judge` não quebra |
| `test_edge_frac_is_advisory` | unit | `edge_frac` existe em `advisory` e não em `reliable` |

## 8. Critério de aceite

- O gate **pode** dizer "risco de chapado/washed" (`chapado_de_branco`, `grande_area_chapada`,
  `neutro_monotono`, `quase_vazio`) — flags de vocabulário fixo, tier confiável.
- O gate **NÃO** pode dizer "está bonito"/"premium"/"elegante" — provado por
  `test_gate_never_emits_aesthetic_judgment`.
- O **veredito é função pura das métricas confiáveis** — provado por `test_verdict_ignores_advisory_metrics`.
- `texture_frac` permanece advisory; o falso-negativo do sofá de tecido **não** volta.
- Compatibilidade: `render_judge.py` e o resto da suíte continuam verdes.
- Veredito estético FINAL segue exclusivamente do Felipe.

## 9. Riscos

- **Calibração das novas métricas.** `large_flat_area_frac`/`neutral_dominance` precisam de thresholds
  calibrados; risco de falso-FAIL num render legítimo (parede grande lisa É comum). Mitigação:
  micro-fixtures primeiro + baseline real; começar com thresholds conservadores (preferir WARN a FAIL)
  e deixar o FAIL só pro caso extremo (near-white).
- **Reintroduzir julgamento por baixo do pano.** Alguém pode usar advisory numa condição de veredito.
  Mitigação: `test_verdict_ignores_advisory_metrics` (mutação) trava isso mecanicamente.
- **Compat com `render_judge`.** Ele lê chaves específicas do `fingerprint`. Mitigação: v2 é aditiva
  (nunca remove chave) + `test_fingerprint_backward_compatible`.
- **"Neutro monótono" é meio-estético.** Cuidar pra `neutral_dominance` medir só saturação/uniformidade
  (fato mensurável), não "feio". Mitigação: definição puramente física (S ≤ sat_max) + nome de flag
  descritivo, não valorativo.

## 10. Plano de implementação em fatias pequenas

- **Fatia 0 — `METRIC_TIERS` + refactor do gate pra receber só `reliable`** + `test_metric_tiers_partition`
  + `test_verdict_ignores_advisory_metrics` + `test_gate_never_emits_aesthetic_judgment`. Sem métrica
  nova: só cristaliza o contrato honesto sobre o gate do FP-036 (near_white). Micro, verde.
- **Fatia 1 — `large_flat_area_frac` + flag `grande_area_chapada`** + micro-fixtures (chapado grande →
  FAIL; textura/variação → PASS; guard do sofá de tecido). Calibra antes de real.
- **Fatia 2 — `neutral_dominance` + flag `neutro_monotono`** (WARN) + micro-fixtures.
- **Fatia 3 — advisories `edge_frac` + `palette_entropy`** (reportados, testes de tier).
- **Fatia 4 — validação nos renders reais** (baseline chapado do FP-036 → WARN/FAIL; deliverable
  texturizado → não falso-FALHA) + `test_fingerprint_backward_compatible`. **PARA**; sem veredito
  estético automático.
