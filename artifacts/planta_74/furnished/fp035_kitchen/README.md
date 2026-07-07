# FP-035 — Cozinha planta_74 gerada com o RAG ativo (evidência)

Prova de que o `reference_db.retrieve()` (FP-035) alimenta o pipeline de furnish da
cozinha planta_74 (r004). Gerado em worktree isolada `chore/fp035-kitchen-proof`
(off origin/develop @4bbfb99). **Veredito visual (IMPROVED/SAME/WORSE) é do Felipe** —
esta pasta só produz a evidência.

## O laço, em ordem

1. `reference_db retrieve --room kitchen --style black_wood_gold` →
   **DesignSpecBundle.v1** (`retrieved_bundle_kitchen_black_wood_gold.json`).
   6 tokens de marcenaria curados, 7 anti-patterns, 16 gate_refs, 1 layout_hint.
   **confidence = LOW** (honesto: corpus julgado do FP-034 ausente → sem sinal de
   curadoria julgada; ranking só por facet+curadoria de disco).
2. `architect_program r004` injeta o bundle no prompt do Arquiteto (deepseek-r1:14b):
   - `architect_prompt_r004.txt` — o PROMPT montado, mostrando o bloco
     "TOKENS DE MARCENARIA RECUPERADOS (confidence=LOW)" + anti-padrões + LAYOUT
     dentro do prompt (prova de injeção, não só de execução).
   - `architect_program_r004.json` — a PROPOSTA do Arquiteto: 6 itens core
     (cooktop, geladeira, bancada, pia, gavetas, armário_de_geladeira). Gate
     determinístico: 0 removidos / 0 injetados (LLM respeitou o cômodo).
3. Geometria da cozinha via `kitchen_layout.build_boxes` (brain determinístico
   cujo `_KC` espelha os tokens) — 57 peças, `kitchen_validation => PASS`
   (pia no anchor hidráulico oeste do PDF).
4. `.skp` mobiliado real via `furnish_apartment.py FURNISH_STYLE=industrial`
   (SketchUp 2026, modo interactive) + proof por cômodo via `material_review.py`.

## Arquivos

| arquivo | o que é |
|---|---|
| `retrieved_bundle_kitchen_black_wood_gold.json` | o DesignSpecBundle recuperado (RAG) |
| `architect_prompt_r004.txt` | prompt montado com o bundle injetado |
| `architect_program_r004.json` | programa de móveis proposto (deepseek-r1:14b) |
| `kitchen_r004_boxes.json` | 57 peças da cozinha (schema place_layout) + módulos |
| `kitchen_material_proof_SU.png` | **render SketchUp REAL** da cozinha isolada (FP-038) |
| `kitchen_r004_sufree_iso.png` | iso SU-free (matplotlib) da mesma geometria |
| `kitchen_r004_sufree_top.png` | top SU-free |
| `planta_74_furnished_after_iso.png` | iso SU do apê inteiro (cozinha no canto) |
| `furnish_build_log.txt` | log do build SU (validation PASS + módulos + flat_white PASS) |

O `.skp` mobiliado real fica em
`artifacts/planta_74/furnished/planta_74_furnished.skp` (regerado neste run).

## Honestidade

- **RAG confidence = LOW** — por design. O corpus julgado do FP-034
  (`kind=judged_variant`) não existe no índice; o retrieve degrada honesto pra LOW
  em vez de fabricar ranking. Os 6 tokens vêm de `references/tokens/` (curados pelo
  Felipe) + sinal de curadoria dos cards/theme_presets do índice.
- **Build SketchUp REAL rodou** (exit 0, `.skp` 1.4 MB, flat_white_check PASS).
  Não é fallback SU-free — este é o SU 2026 de verdade. O iso SU-free está junto
  só como leitura barata de proporção/anatomia.
- **V-Ray final não rodou** — os renders são do rasterizador do SketchUp
  (hidden-line/shaded), não V-Ray. Um render V-Ray de portfólio precisa de re-run
  na máquina do Felipe.
