# FP-036: Material de Verdade — textura SU real no .skp humano + finish/BRDF por kind + flat-white gate

## Problem

O Felipe abre o `.skp` mobiliado (`artifacts/planta_74/furnished/planta_74_furnished.skp`) e ve **moveis brancos / cor chapada, sem textura**. O diagnostico (ancorado no codigo) e que existem DOIS caminhos de material e so um aplica textura:

- **Path V-Ray (`tools/vray_export.rb`)** — JA REAL. Aplica `m.texture = <png>` por kind via `tex_map` (linhas 18-143), gated por `VRAY_TEX_DIR`, com 17 PNGs procedurais/PBR ja versionados em `assets/textures/procedural/`. Funciona — mas SO na exportacao `.vrscene` (render premium).
- **Path interativo/line (`tools/place_layout_skp.rb` -> `pl_material`, linhas 43-50)** — o `.skp` que o Felipe efetivamente abre. So faz `m.color = Sketchup::Color.new(...)` + `m.alpha = 1.0`. **Nunca seta `m.texture`.** Por isso o material `ph_<kind>` e cor RGB chapada.

Alem disso, `tools/style_spec.py::apply_style` (a fonte UNICA da cor do material `ph_<kind>`) so reescreve `b['rgb']` — cor chapada por kind. Ja existe `kind_texture` e `texture_map_for(style)` (linhas 40-46, 69-73, 109-112) que **documentam** o mapa de textura, mas o path interativo nunca consome esse mapa. E nao ha nenhuma nocao de **finish/roughness/metalness** como dado (so prosa em `references/materials/*.md`), entao mesmo onde ha cor, falta a leitura de reflexo que distingue inox de grafite de laca.

Resultado: material so existe "de verdade" no render V-Ray; o artefato humano principal (o `.skp` aberto) parece de papelao branco.

## Scope

1. **Texturizar o path interativo** — `pl_material` (em `place_layout_skp.rb`) passa a aceitar e aplicar `m.texture` por kind, lendo um mapa `kind -> png` injetado pelo Python (`LAYOUT_TEX_MAP` no ENV, espelhando o que `texture_map_for(style)` ja produz). `kind` continua sendo a **fonte unica**: cada material `ph_<kind>` recebe a textura do SEU kind ou nenhuma — jamais pintar tudo com a 1a peca.
2. **Token de finish/BRDF por kind** em `style_spec.py` — uma `kind_finish: dict` (`kind -> {finish, roughness, metalness, tile_in}`) destilada de `references/materials/*.md`, consumida (a) pelo path interativo pra setar `m.alpha`/cor-de-reflexo aproximada quando aplicavel e (b) como contrato unico tambem pro V-Ray (substitui os numeros hardcoded espalhados em `vray_export.rb`/`tweak_vrscene.py`). Sem inventar valor: cada entrada cita a faixa do `.md`.
3. **`flat_white_check` gate** (`tools/flat_white_gate.py`) — gate DETERMINISTICO que le o render `after_top`/`after_iso` via `tools/interior_studio/render_fingerprint.py` e FALHA se os moveis estao chapados de branco / sem variacao (proxy de "sem textura"): fracao de pixel quase-branco + baixa variancia local nas zonas de movel.
4. **Fio na planta real** — `furnish_apartment.py` injeta o `LAYOUT_TEX_MAP` no ENV (a partir de `texture_map_for(FURNISH_STYLE)`), gera o `.skp` texturizado e roda o `flat_white_check` antes de promover. Entrega o `.skp` pro Felipe dar o veredito visual.

## Non-goals

- **NAO** decidir IMPROVED/SAME/WORSE por maquina. O `flat_white_check` so responde "isto esta chapado de branco? (sim/nao)"; a aprovacao estetica FINAL e exclusiva do Felipe.
- **NAO** mexer no comportamento default do path V-Ray que ja e PASS (sofa-sala, quarto). A refatoracao do finish-token pro V-Ray e byte-equivalente ou fica gated; se houver risco de regressao, fica fora desta FP.
- **NAO** baixar assets externos / 3D Warehouse / texturas com licenca. Usar os PNGs procedurais/PBR-CC0 ja versionados; novas texturas saem de `gen_textures.py`.
- **NAO** material PBR completo (normal/displacement/AO multi-map) no `.skp` interativo — SU material so suporta um `texture` difuso; normal/displacement continuam exclusivos do V-Ray.
- **NAO** tocar geometria, layout, escala (`PT_TO_M=0.0259`), consensus, paredes/portas.

## Artifact contract

| Path | Mudanca | Quem |
|---|---|---|
| `tools/place_layout_skp.rb` | `pl_material` aceita `tex_dir`+`png` e seta `m.texture = path` + `m.texture.size`; `pl_run` le `LAYOUT_TEX_MAP` (JSON `kind->png`) e `LAYOUT_TEX_DIR` do ENV e passa o png do kind. Fallback: sem png -> cor chapada (comportamento atual). | NOVO (estende REAL) |
| `tools/style_spec.py` | `StyleSpec` ganha `kind_finish: dict` (`kind -> {finish,roughness,metalness,tile_in}`); novo `finish_map_for(style)`. `texture_map_for` ja existe (REAL) — passa a ser a fonte consumida pelo interativo tambem. | NOVO campo (estende REAL) |
| `tools/furnish_apartment.py` | `main()` injeta `env["LAYOUT_TEX_MAP"]=json(texture_map_for(style))` e `env["LAYOUT_TEX_DIR"]=assets/textures/procedural` quando `FURNISH_STYLE` setado; chama `flat_white_check` no render gerado antes de promover. | NOVO (3 linhas + call) |
| `tools/place_layout_skp.py` | mesma injecao de `LAYOUT_TEX_MAP`/`LAYOUT_TEX_DIR` no `env` (slice de prova r002). | NOVO |
| `tools/flat_white_gate.py` | **NOVO** — `flat_white_check(png_path, style) -> {result, fails, warns, metrics}` usando `render_fingerprint.fingerprint`. CLI `python -m tools.flat_white_gate <png>`. | NOVO (STUB->REAL) |
| `tools/gen_textures.py` | (se faltar PNG pra algum kind do mapa) adicionar a textura procedural correspondente. So se um kind do `texture_map_for` nao tiver png. | EDIT condicional |
| `assets/textures/procedural/*.png` | novos PNGs so se gerados por `gen_textures.py` (auto-contido). | possivel NOVO |
| `references/materials/*.md` | leitura-fonte do `kind_finish` (RGB+roughness+metalness ja documentados). Sem mudanca de conteudo, so consumo. | REAL (read-only) |

## Algorithm

```
# --- 1. style_spec.py: finish token (destilado dos .md, sem inventar) ---
@dataclass StyleSpec:
    ... kind_rgb, kind_texture (REAL) ...
    kind_finish: dict   # kind -> {finish:str, roughness:float, metalness:float, tile_in:int}
# ex. (citando metal.md): "foot"/"frame" grafite fosco -> {matte, 0.7, 0.4, 40}
#     (citando metal.md): inox escovado -> {brushed, 0.4, 0.9, 40}
#     (citando lacquer.md): laca fosca off-white -> {matte, 0.6, 0.0, 40}
def finish_map_for(style): return STYLE_TOKENS[style].kind_finish  # espelha texture_map_for

# --- 2. place_layout_skp.rb: aplicar textura no path interativo ---
def pl_material(model, name, rgb, tex_path=nil, tile=40):
    m = existing or model.materials.add(name)
    m.color = Color(rgb); m.alpha = 1.0
    if tex_path && File.exist?(tex_path):
        m.texture = tex_path            # <-- A CORRECAO DO BUG
        m.texture.size = [tile, tile]
    return m
# pl_run:
tex_map = JSON.parse(ENV['LAYOUT_TEX_MAP'] || '{}')   # kind -> png (de texture_map_for)
tex_dir = ENV['LAYOUT_TEX_DIR']
for each box b:
    kind = b['kind']
    png  = tex_map[kind]                               # kind = FONTE UNICA; sem entrada -> nil
    tex_path = (png && tex_dir) ? File.join(tex_dir, png) : nil
    mat = pl_material(model, "ph_#{kind}", b['rgb'], tex_path)
    g.material = mat
# INVARIANTE: material ph_<kind> recebe SO a textura do seu kind. Nunca a 1a peca em tudo.

# --- 3. furnish_apartment.py / place_layout_skp.py: injetar o mapa ---
if FURNISH_STYLE:
    env['LAYOUT_TEX_MAP'] = json(texture_map_for(FURNISH_STYLE))
    env['LAYOUT_TEX_DIR'] = str(ROOT/'assets/textures/procedural')
# ... gera .skp + after_top.png ...
res = flat_white_check(after_iso_png, FURNISH_STYLE)
if res['result']=='FAIL': print + nao promover (evidencia de regressao)

# --- 4. flat_white_gate.py (DETERMINISTICO, sem LLM) ---
def flat_white_check(png, style):
    fp = fingerprint(png)                      # render_fingerprint.py (REAL)
    white_frac = fp['clipped_white_px'] / total  # ou palette: peso de buckets ~[>=235]^3
    # variancia local nas zonas centrais (zone_colors) = proxy de "tem textura"
    texless_zones = zonas com contrast_std < TEX_STD_MIN
    fails=[]; warns=[]
    if white_frac > WHITE_FRAC_FAIL: fails += "flat_white: {white_frac:.0%} quase-branco"
    elif white_frac > WHITE_FRAC_WARN: warns += ...
    if len(texless_zones) >= TEXLESS_ZONES_FAIL: fails += "sem variacao (provavel sem textura)"
    result = FAIL if fails else (WARN if warns else PASS)
    return {result, fails, warns, metrics:{white_frac, texless_zones, ...}}
# thresholds calibrados contra: (a) baseline ATUAL chapado (deve FAIL/WARN) vs
#                               (b) .skp texturizado novo (deve PASS). micro-fixture primeiro.
```

## Acceptance

| Cenario | PASS | WARN | FAIL |
|---|---|---|---|
| `.skp` interativo de r002 com `FURNISH_STYLE=industrial` | sofa/rack/tapete/parede saem com `m.texture` setada (trama/veio/concreto), nao cor chapada | textura aplicada so num subconjunto dos kinds com mapa | nenhum `m.texture` setado (continua chapado) ou textura da 1a peca pintada em todos |
| Invariante kind = fonte unica | cada `ph_<kind>` recebe png do SEU kind (verificavel no log: `tex ph_<kind> <- <png>`) | — | um png aplicado a kinds diferentes / paint-all |
| `flat_white_check` no baseline ATUAL (pre-fix, chapado) | — | — | FAIL ou WARN (gate PEGA o problema que o Felipe viu) |
| `flat_white_check` no `.skp` texturizado novo | PASS | WARN tolerado | FAIL (gate falso-positivo -> recalibrar) |
| Render V-Ray default (sofa-sala/quarto) | byte-equivalente ou visualmente igual ao baseline PASS | diff trivial documentado | qualquer regressao visivel no PASS existente |
| `kind_finish` | toda entrada cita faixa de `references/materials/*.md`; nenhum valor inventado | entrada sem citacao mas plausivel | valor fora da faixa do `.md` / fabricado |
| Veredito estetico FINAL | (fora do gate) so o Felipe: IMPROVED/SAME/WORSE | — | maquina auto-declarar IMPROVED |

## Required tests

| Teste | Tipo | O que prova |
|---|---|---|
| `test_texture_map_for_industrial_covers_must_style` | unit | `texture_map_for('industrial')` tem png pra todo kind em `must_style` (sofa/tapete) |
| `test_finish_map_values_within_reference_bands` | unit | cada `kind_finish[k].roughness/metalness` cai na faixa citada do `.md` (tabela de bandas no teste) |
| `test_apply_style_does_not_paint_all_with_first` | unit | dois kinds com texturas distintas -> mapa distinto por kind; nenhum kind herda textura de outro |
| `test_flat_white_fails_on_synthetic_white_png` | unit (micro-fixture) | PNG sinteticamente quase-branco/chapado -> `flat_white_check` FAIL |
| `test_flat_white_passes_on_textured_png` | unit (micro-fixture) | PNG com trama/veio sintetico -> PASS |
| `test_pl_material_sets_texture_when_png_present` (contrato TEXTO) | contract | o `.rb` nao e executavel headless aqui -> teste-contrato em Python checa que o ENV/JSON gerado tem `LAYOUT_TEX_MAP` correto e que o `.rb` referencia `m.texture`; FLAG "confirmar em build SU real" |
| `test_furnish_injects_tex_map_when_style_set` | unit | com `FURNISH_STYLE` setado, `env['LAYOUT_TEX_MAP']` != '{}' e `LAYOUT_TEX_DIR` aponta pra pasta existente |
| smoke planta_74 (manual) | e2e | gerar `.skp` real texturizado + render + `flat_white_check` PASS; Felipe da o veredito |

## Done means

- [ ] `pl_material` (place_layout_skp.rb) aplica `m.texture` por kind quando ha png; fallback chapado preservado.
- [ ] `place_layout_skp.py` e `furnish_apartment.py` injetam `LAYOUT_TEX_MAP` (de `texture_map_for(style)`) + `LAYOUT_TEX_DIR` no ENV.
- [ ] `style_spec.py` ganha `kind_finish` + `finish_map_for`, cada valor citando `references/materials/*.md`.
- [ ] `tools/flat_white_gate.py` real (nao stub), usando `render_fingerprint.py`, com CLI; thresholds calibrados (baseline chapado -> FAIL/WARN; texturizado -> PASS) via micro-fixture ANTES da planta real.
- [ ] Todos os testes da tabela verdes (incl. o contrato-texto do `.rb` com FLAG de confirmacao SU).
- [ ] Render V-Ray default (sofa-sala/quarto) sem regressao (byte-equivalente OU diff documentado).
- [ ] `.skp` texturizado da planta_74 gerado, promovido pra `artifacts/planta_74/furnished/`, e ENTREGUE pro Felipe pro veredito visual (IMPROVED/SAME/WORSE e dele).
- [ ] PR contra `develop` landada ou descartada explicitamente — nada de PR aberta.

## Reference

- BUG (path humano chapado): `tools/place_layout_skp.rb` `pl_material` linhas 43-50 (`m.color` so, sem `m.texture`).
- REAL (path V-Ray que ja texturiza): `tools/vray_export.rb` linhas 14-143 (`tex_map`, `m.texture`, gated `VRAY_TEX_DIR`).
- Mapa de textura por estilo (ja existe, subconsumido): `tools/style_spec.py` `_INDUSTRIAL_TEX`/`_MODERN_WARM_TEX` (40-73) + `texture_map_for` (109-112).
- Fonte unica da cor: `apply_style` (`style_spec.py` 93-106) — `kind` -> `ph_<kind>`.
- PNGs versionados + gerador: `assets/textures/procedural/*.png` (17 arquivos) via `tools/gen_textures.py` (procedural + override PBR CC0 de `assets/textures/pbr/`).
- Finish/roughness/metalness (linguagem-fonte do `kind_finish`): `references/materials/{metal,wood,lacquer,stone}.md` (ex. grafite fosco roughness 0.6-0.8 metalness medio; inox escovado roughness 0.3-0.5 metalness alto; laca gloss roughness baixa).
- Molde de gate deterministico a espelhar: `tools/style_coherence_gate.py` (PASS/WARN/FAIL + metrics; nao auto-julga aparencia).
- Extrator pro flat-white gate: `tools/interior_studio/render_fingerprint.py` (`fingerprint`, `clipped_white_px`, `palette`, `zone_colors`, `contrast_std`).
- Caller da planta inteira: `tools/furnish_apartment.py` `main()` (456-501) -> `place_layout_skp.rb` via ENV.
- Regras: `apps/sketchup-mcp/.claude/CLAUDE.md` (kind=verdade, develop-first, headless proibido em dev, promover runs/->artifacts/); veredito visual = humano (memoria `feedback_visual_review_chrome_only` / VISUAL_REVIEW gate).
