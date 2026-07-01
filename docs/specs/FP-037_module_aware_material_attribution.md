# FP-037 — Module-aware Material Attribution

> Segue direto do [[FP-036]] (Material de Verdade). **Dependência PENDENTE:** o branch
> `feat/material-de-verdade` (2 commits: `28fcf5b` feat + `be7ae75` chore/artifact) **ainda NÃO
> foi mergeado em `develop`** (checado 2026-07-01: `git branch --merged origin/develop` não lista).
> Este spec assume o código do FP-036 como base; não reimplementar o que já existe lá.

## 1. Contexto

O FP-036 fez o path interativo (`tools/place_layout_skp.rb`) aplicar `m.texture` **por `kind`**:
`pl_run` resolve `png = tex_map[kind]` (de `style_spec.texture_map_for`), cria o material
`ph_#{kind}` e seta a textura. Provou-se na planta_74 real que 6 kinds texturizaram
(`seat_cushion/back_cushion/arm/tapete ← fabric_charcoal`, `parede_concreto ← concrete`,
`frame ← metal_black_matte`), invariante "kind = fonte única" intacta.

O FP-036 deixou uma **limitação honesta explícita** (PR body + memória
`project_vision_rag_autonomy_program`): *"rack/mesa (kinds `base`/`top`/`front` decompostos,
sobrecarregados entre móveis) não texturizam por kind sem cross-contaminar o sofá → precisa de
texturização por MÓDULO."* Este spec ataca exatamente essa limitação.

## 2. Problema concreto

O material hoje é resolvido **só por `kind`**, mas vários kinds são genéricos e aparecem em
**módulos diferentes com material diferente**. Evidência ancorada no código:

- `tools/rack_class.py::build_rack` emite as partes com kinds **`foot`, `base`, `top`, `front`,
  `niche`** (linhas 120, 129/137/139/141/146, 147, 169, 172). O corpo do rack é kind `base`; a
  frente é `front`; o tampo é `top`.
- `tools/sofa_builder` (via `place_sofa_boxes`) emite o sofá com kinds **`seat_cushion`,
  `back_cushion`, `arm`, `base`, `foot`** — ou seja, `base` e `foot` **colidem** com os do rack.
- `tools/coffee_table_class.py` (mesa de centro `two_tier`) emite **`top`, `leg`** (confirmado no
  log do FP-036: `top bbox 20x37x2`, `leg` ×4, `top bbox 15x30x1`).

Consequência: mapear `kind "base" → wood` texturizaria **também a base do sofá** (que deve ser
grafite), e mapear `kind "top" → wood` é seguro só por sorte (hoje `top` é madeira em rack/mesa de
centro/mesa de jantar). Não há como texturizar o **rack de madeira** sem risco de contaminar o sofá,
enquanto a resolução for **só por kind**. Por isso o FP-036 deliberadamente NÃO mapeou os kinds
sobrecarregados — e o rack/mesa saíram com cor chapada de madeira, sem textura.

Fato adicional relevante (não-regressão): o rack decomposto **também não é texturizado pelo V-Ray
hoje** — `tools/vray_export.rb` tem `'ph_rack_tv' => wm` no `tex_map`, mas o rack agora é
`base/top/front/niche` (kind `rack_tv` não existe mais nesse fluxo). Logo, texturizar o rack no path
interativo é **ganho novo**, não regressão do V-Ray.

## 3. Escopo

1. **Normalizador de família de módulo** — `module_family(module_str) -> str` que mapeia o rótulo
   humano de `b["module"]` (ex. `"Rack TV"`, `"Mesa de centro"`, `"Sofa"`, `"Cadeira jantar"`,
   `"Guarda-roupa"`, `"Cama"`, `"Criado-mudo 1"`, cozinha `"base_cabinet_01"`, banho `"Bancada"`)
   pra uma **família canônica** (`rack`, `coffee_table`, `dining_table`, `dining_chair`, `sofa`,
   `wardrobe`, `bed`, `nightstand`, `kitchen_cabinet`, `bathroom_vanity`, `decor`, …). Determinístico,
   case-insensitive, tolerante a sufixo numérico.
2. **Resolução de material por `(família, kind)`** com **hierarquia de fallback explícita**:
   1. `module_kind` — override específico `(família, kind)` → png/tile/finish;
   2. `kind` — o mapa do FP-036 (`texture_map_for`) como fallback;
   3. **flat color** — sem entrada → cor chapada (comportamento do FP-036 preservado).
3. **Nome de material module-aware** no `.skp`: quando um override `(família, kind)` casa, a peça
   recebe o material `ph_#{família}_#{kind}` (distinto de `ph_#{kind}`), pra que `rack.base` (madeira)
   e `sofa.base` (grafite) sejam materiais SEPARADOS. Sem override → mantém `ph_#{kind}` (compat V-Ray).
4. **Resolução no PYTHON, não no `.rb`** (lição do FP-036: o `.rb` não é testável headless). O
   `furnish_apartment`/`place_layout_skp.py` anexa a cada box o material já resolvido
   (`b["mat_name"]`, `b["tex_png"]`, `b["tile_in"]`); o `.rb` só aplica o que recebe (fica burro e
   auditável). Isso torna a invariante testável em pytest, sem SketchUp.
5. **Tabela de overrides `module_kind_texture`/`module_kind_finish`** no `style_spec.py` por estilo,
   começando pelo mínimo que fecha a lacuna: `rack.{top,front,base,niche}`, `coffee_table.{top,leg}`,
   `dining_table.{top}` → madeira; e a garantia de que `sofa.{base,foot}` **NÃO** herda madeira.

## 4. Não-escopo

- **Não mexer no V-Ray** (`vray_export.rb`) — o rack já é flat lá; texturizar o V-Ray por módulo é
  follow-on (ver Riscos). O default do V-Ray (sofá-sala/quarto PASS) fica byte-estável.
- **Não redesenhar geometria** / layout / escala (`PT_TO_M=0.0259`) / consensus / builders de móvel.
- **Não julgar estética automaticamente** — veredito visual IMPROVED/SAME/WORSE continua do Felipe.
- **Não** criar texturas novas — usar os PNGs já versionados em `assets/textures/procedural/`.
- **Não** tocar no `flat_white_gate` (isso é o FP-039).

## 5. Arquivos ancorados

| Arquivo | Papel | Mudança FP-037 |
|---|---|---|
| `tools/style_spec.py` | tokens de estilo; `texture_map_for`/`finish_map_for`/`tile_map_for`/`texture_env` (FP-036) | NOVO: `module_family()`, `_STYLE.module_kind_texture`/`module_kind_finish`, `resolve_material(style, family, kind)` (3-níveis) |
| `tools/place_layout_skp.rb` | `pl_run` resolve `png=tex_map[kind]`, cria `ph_#{kind}` | Preferir `b["mat_name"]`/`b["tex_png"]`/`b["tile_in"]` resolvidos pelo Python; fallback = comportamento FP-036 |
| `tools/furnish_apartment.py` | `collect_boxes` já seta `b["room"]`+`b.setdefault("module")` (l.428-429); injeta `texture_env` (FP-036) | Resolver material por box (module-aware) ANTES do dump `LAYOUT_BOXES` |
| `tools/place_layout_skp.py` | slice r002; injeta `texture_env` | Mesma resolução por box |
| `tools/rack_class.py` | emite `foot/base/top/front/niche` (fonte da sobrecarga) | READ-ONLY (fonte de verdade dos kinds) |
| `tools/coffee_table_class.py` | emite `top/leg` | READ-ONLY |
| `tools/vray_export.rb` | `tex_map` por `ph_#{kind}` | READ-ONLY (não-goal; ver Riscos) |
| `references/materials/*.md` | linguagem de material (madeira clara/escura) | READ-ONLY (fonte do finish) |

## 6. Estratégia técnica

**Resolução (Python, testável):**
```
def module_family(module_str) -> str:
    # normaliza rótulo humano -> família canônica (regex/keyword, strip sufixo numérico)
    # "Rack TV"->rack, "Mesa de centro"->coffee_table, "Mesa de jantar"->dining_table,
    # "Cadeira jantar"->dining_chair, "Sofa"->sofa, "Guarda-roupa"->wardrobe, "Cama"->bed,
    # "Criado-mudo 2"->nightstand, "base_cabinet_01"->kitchen_cabinet, "Bancada"->bathroom_vanity
    # desconhecido -> "" (cai no fallback por kind)

def resolve_material(style, family, kind) -> {mat_name, tex_png|None, tile_in, finish|None}:
    st = STYLE_TOKENS[style]
    if (family, kind) in st.module_kind_texture:          # NÍVEL 1: override por módulo
        return {mat_name: f"ph_{family}_{kind}", tex_png: st.module_kind_texture[(family,kind)],
                tile_in: st.module_kind_finish.get((family,kind),{}).get("tile_in",40), ...}
    if kind in st.kind_texture:                            # NÍVEL 2: mapa por kind (FP-036)
        return {mat_name: f"ph_{kind}", tex_png: st.kind_texture[kind], tile_in: tile_map_for[kind]}
    return {mat_name: f"ph_{kind}", tex_png: None, tile_in: 40}   # NÍVEL 3: flat (cor chapada)
```

**Onde roda:** dentro de `collect_boxes` (furnish) / `build_boxes` (slice), depois do `apply_style`,
antes do `json.dumps(boxes)`. Para cada box: `fam = module_family(b["module"])`; `r =
resolve_material(style, fam, b["kind"])`; anexa `b["mat_name"]=r["mat_name"]`,
`b["tex_png"]=r["tex_png"]`, `b["tile_in"]=r["tile_in"]`. Só sob `FURNISH_STYLE` (sem estilo → não
anexa → `.rb` mantém 100% o comportamento atual).

**No `.rb` (`pl_run`):** se `b["mat_name"]` presente → usa ele + `b["tex_png"]` (join com
`LAYOUT_TEX_DIR`) + `b["tile_in"]`; senão → path FP-036 (`ph_#{kind}` + `tex_map[kind]`). Mantém o
log per-kind auditável (`tex #{mat_name} <- #{png}`) e o `tex_applied` gated em `File.exist?`.

**Overrides mínimos (estilo `industrial`/`modern_warm`)** — só o que fecha a lacuna, cada valor
com a mesma disciplina de citação do FP-036 (madeira = `wood_dark.png`/`wood_medium.png` por estilo):
- `(rack, top)`, `(rack, front)`, `(rack, base)` → madeira; `(rack, niche)` → madeira escura/dark;
  `(rack, foot)` → grafite (pés).
- `(coffee_table, top)`, `(coffee_table, leg?)` → madeira (leg pode ser grafite conforme builder);
  `(dining_table, top)` → madeira; `(dining_table, foot)` → grafite.
- **`(sofa, base)` e `(sofa, foot)`: SEM override de madeira** — resolvem por kind/flat (grafite),
  garantindo que a madeira do rack NÃO vaze pro sofá.

**Invariante nova:** `(família, kind) = fonte única` do material `ph_{família}_{kind}`. Generaliza o
"kind = fonte única" do FP-036 sem quebrá-lo (kind puro continua sendo o fallback nível 2).

## 7. Testes obrigatórios

| Teste | Tipo | Prova |
|---|---|---|
| `test_module_family_normalizes_known_labels` | unit | `"Rack TV"→rack`, `"Mesa de centro"→coffee_table`, `"Criado-mudo 2"→nightstand`, `"base_cabinet_01"→kitchen_cabinet`; desconhecido→"" |
| `test_rack_base_resolves_wood_not_sofa` | unit (anti-contaminação) | `resolve_material(style,"rack","base")` → png de madeira + `mat_name=="ph_rack_base"` |
| `test_sofa_base_never_gets_wood` | unit (anti-contaminação) | `resolve_material(style,"sofa","base")` → tex_png é None OU não-madeira; `mat_name=="ph_base"` (não `ph_rack_base`) |
| `test_same_kind_different_module_distinct_materials` | contract | `sofa.base` e `rack.base` → `mat_name` DIFERENTES (não colidem em `ph_base`) |
| `test_fallback_chain_module_then_kind_then_flat` | unit | `(rack,top)`→nível1; `(sofa,seat_cushion)`→nível2 (fabric, FP-036); `(sofa,foot)`→nível3/flat |
| `test_no_paint_all_across_families` | contract | nenhuma família recebe a textura de outra; cada `(fam,kind)` só a sua |
| `test_resolved_pngs_exist` | unit | todo `tex_png` de todo override aponta pra PNG existente em `assets/textures/procedural/` |
| `test_boxes_carry_resolved_material_when_style_set` | unit | com `FURNISH_STYLE`, cada box do `collect_boxes` tem `mat_name`/`tex_png`/`tile_in`; sem estilo, não tem (compat) |
| `test_pl_run_prefers_resolved_material` (contrato-TEXTO `.rb`) | contract | o `.rb` referencia `b['mat_name']`/`b['tex_png']` e mantém o fallback FP-036; FLAG "confirmar em build SU real" |
| smoke planta_74 (manual) | e2e | gerar `.skp` com rack/mesa de madeira texturizados + sofá intacto; log per-módulo prova; Felipe dá veredito |

## 8. Critério de aceite

- `rack` e `coffee_table`/`dining_table` recebem **madeira real** (`m.texture`) no path interativo,
  verificável no log (`tex ph_rack_front <- wood_dark.png`, `tex ph_coffee_table_top <- …`).
- O **sofá NÃO muda**: `sofa.base`/`sofa.foot` continuam grafite/flat — nenhum `ph_rack_base` aplicado
  ao sofá; provado por `test_sofa_base_never_gets_wood` + `test_same_kind_different_module_distinct_materials`.
- Fallback preservado: kind não-sobrecarregado (ex. `seat_cushion`) continua resolvendo pelo mapa
  FP-036; sem estilo → tudo flat (comportamento atual).
- Suíte verde (incl. os testes acima). V-Ray default byte-estável.
- `.skp` da planta_74 gerado, promovido pra `artifacts/planta_74/furnished/`, **veredito visual do
  Felipe** (IMPROVED/SAME/WORSE) — não auto.

## 9. Riscos

- **Colisão de nome de material com o V-Ray.** O V-Ray casa `tex_map` por `ph_#{kind}`. Materiais
  novos `ph_#{família}_#{kind}` **não** batem com as entradas do V-Ray → o V-Ray não os texturiza
  (ficam como estão: flat, = hoje). Isso **não é regressão** (o rack decomposto já era flat no V-Ray),
  mas é uma **divergência** interativo×V-Ray. Mitigação: documentar; follow-on adiciona entradas
  `ph_rack_*` no `tex_map` do V-Ray (fora deste FP).
- **Normalização de módulo frágil.** Rótulos humanos (`"Mesa de centro"`) podem mudar. Mitigação:
  `module_family` tolerante + teste que cobre TODOS os rótulos reais emitidos pelos brains (varrer
  `furnish_apartment` por `module=`), e fallback seguro (desconhecido→"" → resolve por kind).
- **Kind `top` já "funcionava por sorte".** Hoje `top` é madeira em rack/mesa. Introduzir
  `(família,top)` muda o nome do material de `ph_top` pra `ph_família_top` — conferir que nada
  depende do nome `ph_top` (grep). Se depender, manter `top` no nível 2 (por kind) e só sobrescrever
  os kinds de conflito real (`base`/`foot`).
- **Explosão de materiais.** Muitos `ph_família_kind` incham a lib de materiais do `.skp`. Mitigação:
  só criar material module-aware quando há override real (kinds não-conflitantes ficam em `ph_#{kind}`).

## 10. Plano de implementação em fatias pequenas

- **Fatia 0 — `module_family` + testes** (Python puro, sem tocar `.rb`/geometria). Normalizador +
  `test_module_family_normalizes_known_labels` cobrindo os rótulos reais. Micro, verde, isolado.
- **Fatia 1 — `resolve_material` (3 níveis) + tabela de overrides mínima** (`rack.*`, `coffee_table.*`,
  garantia `sofa.base` sem madeira) + testes anti-contaminação/anti-paint-all. Ainda sem `.rb`.
- **Fatia 2 — anexar material resolvido por box** em `furnish_apartment`/`place_layout_skp.py` +
  `test_boxes_carry_resolved_material`. Ainda sem render.
- **Fatia 3 — `.rb` prefere material resolvido** (mantém fallback FP-036) + contrato-TEXTO. FLAG SU.
- **Fatia 4 — smoke planta_74 real** (`FURNISH_STYLE=industrial`): rack/mesa de madeira texturizados,
  sofá intacto, log per-módulo. Promove `.skp` → `artifacts/`. **PARA** e entrega pro veredito do Felipe.
- **Follow-on (fora deste FP):** entradas `ph_rack_*`/`ph_coffee_table_*` no `tex_map` do V-Ray.
