# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-04) — piso encosta na parede (células)

**VISUAL_REVIEW = IMPROVED** (Felipe, 2026-06-04 — "melhorou bastante; o piso
está encostando nas paredes muito melhor e a sensação de chão comido sumiu").

### Problema
O piso de cada cômodo vinha do `polygon_pts` do consensus, que é **recuado /
desalinhado** da face interna da parede → faixa cinza serrilhada ("formiga
comendo") entre o piso colorido e a parede.

### Fix — preencher a CÉLULA do espaço livre (não o polígono recuado)
`compute_room_floors()` (Python) computa, por cômodo:
- **envelope** do apê = união das paredes + guarda-corpos (soft_barriers),
  buracos preenchidos — fecha a varanda (rail, não parede);
- **célula** = `envelope − (massa_das_paredes ∪ guarda-corpos)` → delimitada
  *exatamente* pela face interna das paredes E dos guarda-corpos; o piso encosta
  sem gap. Subtrair o **guarda-corpo** (não só a parede) foi o 2º fix: sem isso
  a célula da varanda ia até a borda EXTERNA do guarda-corpo de vidro e o piso
  aparecia além do vidro (transparente) — Felipe viu "verde vazando por baixo da
  parede". Com o fix o vazamento do terraço caiu **5089→718pt²** e o piso pra
  fora do apê = **0pt²**;
- **tuck** de `0.4×espessura` sob a parede (esconde a junta). Sweep 0.3–0.6:
  `≤0.45` dá **zero overlap** entre pisos adjacentes (0.6 dava 1354pt²);
- comodos **integrados** que dividem uma célula (SALA+COZINHA, sem parede entre
  eles) são separados pelos polígonos; a cozinha vira um **hole** no piso da
  sala (Ruby `build_floor` recorta o furo como o shell faz).

### Validação (sem chute visual)
- overlap entre pisos = **0.0pt²**; 8 Floor_Groups, todos shapely-válidos;
- **135/135 vértices de piso são estruturais** (caem sobre parede/guarda-corpo
  do consensus) — os recortes contornam pilastras reais, não são artefato;
- render **floors-only** (paredes ocultas) `planta_74_floors_top.png`: sem
  overlap, sem buraco escondido, terraço sem vazamento — as 3 checagens do Felipe;
- deterministic gates **PASS**; heurísticas visuais **0 findings**; pytest **365**.

### Fonte
- `tools/build_plan_shell_skp.py` — `compute_room_floors`, `FLOOR_UNDER_FRAC=0.4`,
  serializa `room_floors` (outer+holes) no `_shell_polygon.json`.
- `tools/build_plan_shell_skp.rb` — `build_floor` usa `room_floors[id]` (sem
  re-snapar) + recorta holes; render extra `*_floors_top.png` (paredes ocultas).
- consensus **intocado**.

---

## Rodada anterior (2026-06-04) — janelas: esquadria + proporção

**VISUAL_REVIEW = IMPROVED** (Felipe, 2026-06-04).

### Esta rodada — proporção das janelas de quarto (1,80 × 1,20m)
Ajuste de altura/peitoril das janelas de dormitório, validado por consulta ao
GPT + foto real (tour Matterport da SUITE 02):
- Peitoril **1,10m** → verga **2,30m** → janela de **1,20m** de altura.
- SUITE 02 (h_o010, largura 1,80m do PDF) = **1,5:1**.
- SUITE 01 (h_o008, largura 2,06m do PDF) = 1,72:1 — mesma altura/peitoril; a
  largura é do PDF (não inventada).
- Verga do BASCULANTE separada (2,10m) → basculantes intocados (0,73 × 0,60m).

> **PREMISSA ARQUITETÔNICA PROVÁVEL** (não dimensão normativa obrigatória): a
> altura não consta no PDF; adotada por consulta ao GPT + prática de apto
> residencial médio-alto + referência visual da foto real. Largura/posição = PDF.

### Mantido das rodadas anteriores
- Esquadria de janela: correr 2 folhas (moldura + montante + vidro verde) +
  caixa de persiana; basculante com folha de vidro inclinada (banheiros).
- Guarda-corpo de vidro na varanda (mureta + vidro + corrimão).
- Notch-removal (toquinhos das junções de parede).

### Fonte
- `tools/build_plan_shell_skp.rb` — `WINDOW_SILL_M=1.10` / `WINDOW_HEAD_M=2.30`
  (correr 1,20m); `BASCULANTE_SILL_IN=1.50` / `BASCULANTE_HEAD_IN=2.10`
  (basculante 0,60m); `build_window_frame_h` / `build_window_basculante_h`.
- `tools/run_skp_visual_review.py` — `_check_window_height` reconhece basculante.
- consensus **intocado**.

### Gates
- deterministic gates: **PASS** (overall).
- pytest: **365 green**.
- canonical sha `301d3361`.

### Evidência
- `artifacts/review/planta_74/bedroom-window-ratio/` + `janelas-esquadria/`.
