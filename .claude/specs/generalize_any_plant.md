# Spec — Generalizar PDF → SKP para QUALQUER planta

> **STATUS: DRAFT** (2026-05-31, não commitado — para revisão do Felipe).
> Regra-raiz deste spec: **não quero mais infra pela infra.**
> Prioridade, nesta ordem: **(1) produto · (2) `.skp` fiel · (3) artefato
> humano revisável · (4) infra — só se destravar os três de cima.**

---

## 0. A verdade central (ler antes de tudo)

**Hoje NÃO existe extrator automático PDF → consensus.** O `consensus.json`
da planta_74 é **autorado por humano** (anotação em PNG → JSON), com um assist
semi-automático de detecção de vãos (gaps colineares). `build_vector_consensus.py`
foi **abandonado** (raster+Hough fabrica parede falsa em PDF vetorial — LL #7).

Logo, "generalizar para qualquer planta" **não é** construir um extrator mágico.
É três coisas, em ordem de barato→caro:

1. **Tirar os defaults `planta_74`** que estão espalhados (refactor puro).
2. **Padronizar o fixture por-planta** + o workflow de anotação humana.
3. **Fazer o loop build→gates→review rodar para um `<plant>` qualquer.**

Extrator automático e RAG indexado são **enhancement DEPOIS** que o loop manual
funcionar para ≥2 plantas. Não entram neste spec.

---

## 1. O que está hardcoded para `planta_74`?

Inventário (de varredura real do código — ver evidência file:line no HANDOFF):

- **Defaults `--fixture planta_74`** em ~10 ferramentas (`run_deterministic_gates`,
  `opening_host_audit`, `wall_overlap_audit`, `regenerate_consensus`,
  `pdf_overlay_verify`, `opening_audit`, `visual_regression_gate`,
  `run_skp_visual_review`, `negative_dogfood`). → roda planta_74 se você esquecer o arg.
- **Nome do arquivo de consensus** `consensus_with_human_walls_and_soft_barriers.json`
  (planta_74) vs `consensus_with_window.json` (quadrado) — **inconsistente já hoje**.
- **Âncora de escala `0.19 m`** (espessura nominal de parede BR) embutida em
  `opening_audit.py:36`, `pdf_overlay_verify.py:61` (PT_TO_M = 0.19/wall_thickness_pts).
  `wall_thickness_pts` já vem do consensus; só o `0.19 m` é constante.
- **Constantes arquitetônicas no builder Ruby**: `WALL_HEIGHT_M=2.70`,
  `WINDOW_SILL_M=0.90`, `WINDOW_HEAD_M=2.10`, `DOOR_HEIGHT_M=2.10`,
  `PARAPET_HEIGHT_M=1.10` (`build_plan_shell_skp.rb`). Assumem residencial BR.
- **Layout do PDF**: `DEFAULT_PDF_CROP=(0.05,0.07,0.78,0.55)` (`compose_side_by_side.py`),
  `page_idx=0` sempre, `PDF_SCALE=3.0`/`2.0` (DPI).
- **Contagens pinadas nos testes**: 4 janelas, 8 carved, 9 soft_barriers
  (`test_opening_routing_invariants.py`).
- **`negative_dogfood` CORRUPTION_RECIPES["planta_74"]**: coords de pixel absolutas.
- **`brightness_thresh=160`** e heurísticas de `overlay_diff` calibradas no olho da planta_74.

**Já parametrizado** (não precisa mexer): `wall_thickness_pts`, `planta_region`,
`page_size_pts`, `rooms`/`openings`/`soft_barriers` vêm todos do consensus;
`PT_TO_M` é override-ável por `ENV['PT_TO_M']` no Ruby; `known_warnings.json` já é
carregado por nome de fixture.

---

## 2. Inputs mínimos de qualquer planta nova

1. **O PDF** (vetorial de preferência) + `page_idx` + `planta_region` (crop do
   desenho na página).
2. **UMA âncora física de escala** — uma dimensão real conhecida (espessura de
   parede em m, ou uma cota dimensionada). **Sem âncora → BLOCKED.** Nunca usar
   default 0.0254/72 (regra-raiz de extração honesta).
3. **O `consensus.json`** (walls/openings/rooms/soft_barriers) — hoje **produzido
   por anotação humana**.
4. **Config por-planta** (`plant.json`): alturas arquitetônicas (ou aceita defaults
   BR), crop, page_idx, âncora de escala.
5. **PNGs de anotação** (provenance: `human_walls_annotation.png`, etc.).

`expected_counts.json` (janelas/carved/soft_barriers) **não é input** — é
**gerado** no primeiro build limpo e **pinado depois do VISUAL_REVIEW**.

---

## 3. Como registrar uma planta nova como fixture

`fixtures/<plant>/` por convenção, contendo:

```
fixtures/<plant>/
  consensus.json            # nome PADRONIZADO (não mais *_with_human_walls_*)
  plant.json                # config por-planta (pdf, page_idx, crop, âncora, alturas)
  known_warnings.json       # começa vazio
  expected_counts.json      # gerado no 1º build limpo, pinado pós-VISUAL_REVIEW
  annotation/*.png          # provenance da anotação humana
```

+ `fixtures/index.json` listando plantas + status (`draft|building|canonical`).

**Hard Rule #3 continua valendo:** fixture é canônico; promover o **primeiro**
consensus de uma planta nova a canônico exige **VISUAL_REVIEW** (Felipe).

---

## 4. Calibração escala / orientação / página

- **Página**: `plant.json.page_idx` (default 0) + `planta_region` (crop bbox).
- **Escala**: `PT_TO_M = wall_thickness_m / wall_thickness_pts`, com
  `wall_thickness_m` (hoje fixo 0.19) virando campo de `plant.json`. Exige âncora
  física medida (§2.2). Opcional: `tools/calibrate_plant.py` que recebe uma cota
  conhecida + seus pts e cospe o PT_TO_M — **só construir se manual em `plant.json`
  doer.**
- **Orientação**: hoje paredes são **axis-aligned (h/v)**. Planta girada → passo de
  calibração (rotacionar crop/consensus pra alinhar, ou gravar ângulo). Planta
  rotacionada = **flag para VISUAL_REVIEW** (o olho confirma o alinhamento).

---

## 5. Detecção de paredes/portas/janelas/muretas/soft-barriers

**Honesto: hoje = anotação humana.** Mantém-se como baseline (é o que dá fidelidade;
auto-extração foi abandonada por fabricar). Workflow repetível por planta:

1. Render do `planta_region` do PDF.
2. Humano pinta paredes/vãos/soft-barriers no render (os PNGs de anotação).
3. Conversor **determinístico** transforma anotação + gaps detectados (colinear
   gap-detection, que já existe) em `consensus.json`.
4. **kind classification** segue `kind_v5` + a semântica do PDF (legenda de cores;
   **peitoril/grade/porta-vidro NÃO são paredes estruturais**):
   - `window` → abertura 3D (preserva peitoril+verga).
   - `door/passage/porta-vidro` → carve 2D full-height.
   - `mureta/grade/parapeito` → `soft_barrier` (extrusão a 1.10 m, não parede).

**Auto-extração vetorial** (walls = filled paths) = enhancement futuro, atrás do
gate "loop manual funciona em ≥2 plantas". **Fora do escopo aqui.**

---

## 6. Automático vs VISUAL_REVIEW humano

| AUTOMÁTICO (modo B, sem humano) | VISUAL_REVIEW (humano / GPT-via-Chrome) |
|---|---|
| build SKP a partir do consensus | "o AFTER parece o PDF?" (montagem PDF×BEFORE×AFTER) |
| gates determinísticos (opening_host, wall_overlap, wall_presence) | promover o **1º** consensus de uma planta nova a canônico |
| self-check do `geometry_report` (4 booleans) | qualquer mudança de **aparência** da planta |
| match de contagem (janelas 3D == kind=window) | planta rotacionada / escala suspeita |
| sanity de escala/área | — |

Regras travadas: **nunca** auto-julgar IMPROVED/SAME/WORSE; review visual **só** por
humano ou GPT-via-Chrome (computer-use desktop proibido). Anotação é **autoria**, não
review.

---

## 7. SKP canônico + artefatos humanos versionados

Reusa o pipeline que já existe (plant-agnóstico exceto os defaults):

`consensus.json → build_plan_shell_skp.{py,rb} → runs/<plant>/ → artifacts/<plant>/`

- `artifacts/<plant>/`: `<plant>.skp` + `.skp.metadata.json` (SHA do consensus) +
  iso/top PNG + `side_by_side_pdf_vs_skp.png` + `geometry_report.json` + `README.md`.
- `artifacts/review/<plant>/<run>/final/`: `regression_summary.md` (veredito por
  eixo) + `visual_findings.json`.
- **Promoção `runs/ → artifacts/` é manual hoje** (`tools/promote_artifact.py` é TODO).
  Construir esse promotor **É infra justificada** (destrava o deliverable por-planta
  e remove erro manual). → única peça de infra que o spec recomenda construir cedo.

---

## 8. Gates que provam que a planta está boa

- **Determinísticos (auto, têm que passar)**: `opening_host` (0 fail),
  `wall_overlap` (0 overlaps), self-check 4-booleans, match de janelas
  (`window_apertures_3d == count(kind=window)`), sem floating door / orphan glass,
  `wall_presence` (se houver render+sidecar). **Todos já plant-agnósticos.**
- **Pinados por-planta**: `expected_counts.json` (gerado no 1º build, pinado pós-VISUAL).
- **Escala**: PT_TO_M dentro de faixa plausível; área total plausível.
- **Visual (final)**: montagem PDF×BEFORE×AFTER julgada **IMPROVED/SAME** por humano/GPT-Chrome.

**Planta "boa" = determinístico GREEN + VISUAL_REVIEW IMPROVED**, ambos gravados no
`regression_summary.md`.

---

## 9. Critérios de parada (não virar loop infinito)

Herda o `autonomous-fidelity-loop` + específicos por-planta:

- **RED** (Hard Rule quebrada / regressão de gate) → para.
- **Patinagem** (N ciclos sem ganho líquido nas métricas determinísticas) → para.
- **VISUAL_REVIEW pendente** → para (gate humano).
- **Input faltando = BLOCKED, não spin**: sem âncora de escala → BLOCKED (pede 1 cota);
  sem anotação → BLOCKED (input não existe, não é loop). Não ficar tweakando no escuro.
- **Cap de tentativas** por defeito de fidelidade (os 3 attempts do skp-visual-self-correction).
- **Convergência = DONE**: determinístico GREEN + counts pinados + VISUAL IMPROVED.
  "Done is a valid stop."
- **Nunca loopar construindo infra.** Se o passo pede INPUT humano (âncora, anotação,
  aprovação visual), PARA e sobe a pendência.

---

## Ordem de construção (produto primeiro)

1. **Strip dos defaults `planta_74`** → `--plant` obrigatório, `consensus.json`
   padronizado, `plant.json`. *(refactor puro, destrava qualquer planta. FAZER 1º.)*
2. **`tools/promote_artifact.py`** (runs→artifacts). *(infra justificada — o deliverable.)*
3. **Uma 2ª planta de verdade** como forcing function: pega um PDF simples, roda o
   loop parametrizado ponta-a-ponta, deixa os gaps reais aparecerem. *(generalização
   se PROVA com uma 2ª planta, não com abstração.)*
4. **Config por-planta** (alturas/crop/page/expected_counts) — conforme a 2ª planta forçar.

## Não-goals (explícito)

- ❌ extrator automático PDF→consensus (abandonado; futuro, atrás de ≥2 plantas no loop).
- ❌ RAG indexado (o file-fetch §6.3 já é "RAG-bebê" suficiente por enquanto).
- ❌ arquitetura grande de qualquer tipo.
- ❌ generalização que não entre no loop build→gates→review (a lição do §6: módulo
  testado e desplugado = infra pela infra).
