# FP-038 — Room Detail Visual Review Camera

> Segue do [[FP-036]] (Material de Verdade). **Dependência PENDENTE:** o `.skp` texturizado é
> produzido pelo branch `feat/material-de-verdade` (ainda NÃO mergeado em `develop` — checado
> 2026-07-01). Este spec consome esse `.skp`; não reimplementa o texturizador.

## 1. Contexto

No FP-036, o `.skp` interativo passou a texturizar por kind (sofá/tapete/parede/moldura). A **prova
determinística** foi o log per-kind do `.rb` (`tex ph_seat_cushion <- fabric_charcoal.png` …). Mas o
**render de revisão** — o iso da planta INTEIRA (`planta_74_furnished_after_iso.png`) — não mostra a
textura: no FP-036 eu cropei a região da sala e **o sofá saiu pequeno e ATRÁS do vidro da sacada
envidraçada** (grupo `GlazedBalcony`), com a trama lavada/imperceptível. Registro literal do handoff
FP-036: *"o whole-apartment iso não showcaseia a textura (sofa behind glass); as texturas estão no
`.skp` — você as veria orbitando/zoom em SU. Veredito visual final é seu."*

Ou seja: o Felipe hoje só consegue dar veredito **abrindo o `.skp` no SketchUp**. Isso trava o loop
de validação (ele precisa de máquina + tempo). Falta uma **imagem por ambiente, boa o suficiente pra
julgar sem abrir o `.skp`**.

## 2. Problema concreto

O único render de revisão é o iso do apê inteiro, onde:
- o móvel de cada cômodo ocupa uma fração pequena do frame (textura sub-amostrada → invisível);
- há **oclusão real**: a sala fica dentro do `GlazedBalcony` (parede de vidro) → o vidro na frente
  da câmera lava o sofá (confirmado no crop do FP-036);
- não há enquadramento por cômodo nem um close "material proof" perto do sofá/rack.

Evidência de que dá pra resolver com o que já existe:
- `tools/place_layout_skp.rb::pl_top_camera(model, bbox)` e `pl_iso_camera(model, bbox)` **já aceitam
  um bbox** pra enquadrar só uma região (l.10-36); `LAYOUT_ZOOM_GROUP` já enquadra o bbox da mobília
  (`furn_bb`, l.144-150).
- `tools/vray_export.rb` tem `VRAY_ISOLATE` (l.147-159): **esconde** todos os grupos cujo nome não
  contém a substring — o padrão exato de "isola um cômodo, some com o resto".
- No `.rb`, cada móvel é um grupo top-level nomeado **`"#{room} · #{module}"`** (l.82) e o shell é
  travado por grupos nomeados `PlanShell/Floor_Group/DoorLeaf/Window/GlazedBalcony/SoftBarrier/
  PassageMarker` (l.135) — dá pra filtrar por nome.
- Os boxes carregam `b["room"]` (ex. `"SALA DE JANTAR | SALA DE ESTAR"`, `"COZINHA"`, `"SUITE 01"`) →
  bbox por cômodo é computável no Python, antes do SU.

## 3. Escopo

1. **Câmera/enquadramento por AMBIENTE** — sala, cozinha, quarto — que frameia a mobília daquele
   cômodo (bbox do móvel + folga), **escondendo os oclusores** (grupos de outros cômodos + o vidro/
   parede da frente `GlazedBalcony`), pra o material aparecer legível.
2. **Pelo menos uma imagem "material proof"** — close apertado perto do sofá/rack da sala (a
   superfície que mais importa pro veredito de textura).
3. **Saída previsível** em `artifacts/planta_74/furnished/material_review/`:
   - `living_material_proof.png`, `kitchen_material_proof.png`, `bedroom_material_proof.png`
   - `living_sofa_closeup.png` (o material proof apertado).
4. **Uma tool de revisão** (`tools/material_review.py`) que **abre o `.skp` já gerado** (default
   `artifacts/planta_74/furnished/planta_74_furnished.skp`) e produz as imagens — **desacoplada do
   furnish** (dá pra re-render sem regenerar o `.skp`). Uma única sessão SU renderiza todas as câmeras.
5. **Config de cômodos declarativa** (nome→substring de match, alvo de close, oclusores a esconder),
   pra crescer pra outros cômodos sem editar o `.rb`.

## 4. Não-escopo

- **Não** render premium/V-Ray — é imagem de REVISÃO (viewport `write_image`), boa o bastante pra
  IMPROVED/SAME/WORSE. Render final continua sendo o pipeline V-Ray existente.
- **Não** julgar a imagem automaticamente (isso é [[FP-039]]/`flat_white_gate`); esta tool só PRODUZ
  as imagens; o veredito é do Felipe.
- **Não** mexer em geometria/material/layout — só câmera + visibilidade (hide/unhide) num `.skp`
  **cópia** (nunca salva por cima do original).
- **Não** depender de crop do render do apê inteiro como entrega (provado insuficiente no FP-036 —
  pequeno + atrás do vidro); crop fica no máximo como fallback documentado, não como aceite.

## 5. Arquivos ancorados

| Arquivo | Papel | Mudança FP-038 |
|---|---|---|
| `tools/material_review.py` | **NOVO** — abre o `.skp` furnished, orquestra as câmeras por cômodo | NOVO |
| `tools/material_review.rb` | **NOVO** — dentro do SU: esconde não-alvo, frameia bbox do cômodo, renderiza cada câmera; NÃO salva o `.skp` | NOVO |
| `tools/place_layout_skp.rb` | `pl_top_camera`/`pl_iso_camera(bbox)`, group naming `"#{room} · #{module}"`, shell lock names | READ-ONLY (reusar helpers/convenções) |
| `tools/vray_export.rb` | `VRAY_ISOLATE` (padrão de esconder grupos) | READ-ONLY (padrão a espelhar) |
| `artifacts/planta_74/furnished/planta_74_furnished.skp` | input (do FP-036) | READ-ONLY |
| `artifacts/planta_74/furnished/material_review/*.png` | saída | NOVO (dir) |

## 6. Estratégia técnica

**Uma sessão SU, N câmeras** (evita N launches). `material_review.py`:
1. Copia o `.skp` furnished pra um temp (nunca renderiza/salva sobre o original).
2. Monta `ROOM_CAMERAS` (JSON no ENV): lista de `{name, room_match, out_png, mode, hide_shell}`, ex.:
   - `{name:"living", room_match:"SALA", out:"living_material_proof.png", mode:"iso", hide:["GlazedBalcony","Window"]}`
   - `{name:"kitchen", room_match:"COZINHA", out:"kitchen_material_proof.png", mode:"iso"}`
   - `{name:"bedroom", room_match:"SUITE 01", out:"bedroom_material_proof.png", mode:"iso"}`
   - `{name:"living_sofa_closeup", room_match:"SALA · Sofa", out:"living_sofa_closeup.png", mode:"closeup"}`
3. Lança `SketchUp.exe <copia.skp> -RubyStartup material_review.rb` (interativo, como furnish; nada de
   `--mode headless` — proibido em dev local).

`material_review.rb`, para cada câmera:
- **Isola**: `entities.grep(Group)` → `g.hidden = true` se o nome do grupo NÃO contém `room_match`
  (móveis de outros cômodos somem); **esconde oclusores** listados em `hide` (ex. `GlazedBalcony`,
  janelas na frente) pra matar o vidro lavando a cena; mantém o piso/paredes de fundo do cômodo.
- **Frameia**: acumula o bbox dos grupos visíveis do cômodo (kbb, como `VRAY_ISOLATE`), com folga
  (~1.2 m); `mode:"iso"` → `pl_iso_camera(model, kbb)`-like; `mode:"closeup"` → câmera interior
  (eye recuado do bbox + target no centro do móvel) pra pegar a trama de perto sem o vidro na frente.
- **Renderiza** `write_image(out_png, 1600×1200)`.
- **Restaura** visibilidade (unhide) antes da próxima câmera (idempotente entre câmeras).
- Escreve um LOG (sinal "done" pro Python, como o `LAYOUT_LOG` do furnish) listando cada câmera +
  quantos grupos escondeu + bbox usado.

**Determinismo:** sem clock/random; mesmo `.skp` → mesmas imagens. Paths via `pathlib.resolve()`.

**Fallback documentado (não-aceite):** se o SU não puder rodar, um crop PIL do
`planta_74_furnished_after_iso.png` por região — mas o FP-036 já mostrou que isso é pequeno/atrás do
vidro; serve só de degradê, não cumpre o critério de aceite.

## 7. Testes obrigatórios

| Teste | Tipo | Prova |
|---|---|---|
| `test_room_bbox_from_boxes` | unit | dado o `LAYOUT_BOXES` da planta_74, o bbox por `room_match` ("SALA"/"COZINHA"/"SUITE 01") é não-vazio e disjunto o suficiente (o da sala não engloba a cozinha) |
| `test_room_cameras_config_valid` | unit | a config gera nomes de saída previsíveis (`living_material_proof.png` etc.) e todo `room_match` casa ≥1 grupo esperado |
| `test_material_review_rb_contract` (contrato-TEXTO) | contract | o `.rb` esconde grupos por `room_match`, esconde `hide[]`, frameia bbox e **não** chama `model.save`; FLAG "confirmar imagens em build SU real" |
| `test_output_paths_predictable` | unit | os paths caem em `artifacts/planta_74/furnished/material_review/` com os nomes fixos |
| smoke planta_74 (manual) | e2e | rodar a tool → 3 proofs + 1 closeup, sala SEM vidro na frente, sofá grande o suficiente pra ler a trama; Felipe dá IMPROVED/SAME/WORSE só pela imagem |

## 8. Critério de aceite

- Existem `living_material_proof.png`, `kitchen_material_proof.png`, `bedroom_material_proof.png` +
  `living_sofa_closeup.png` em `artifacts/planta_74/furnished/material_review/`.
- Na imagem da sala **não há vidro/parede da frente lavando o sofá** (oclusor escondido), e o
  móvel/textura ocupa parte substancial do frame.
- **O Felipe consegue dar IMPROVED/SAME/WORSE sem abrir o `.skp`** — critério central.
- A tool não altera o `.skp` original (renderiza cópia, não salva).
- Determinística; suíte verde (contratos + bbox por cômodo).

## 9. Riscos

- **Custo/efeito colateral do launch SU** (mata `SketchUp.exe`, abre GUI) — igual ao furnish. Uma só
  sessão pra todas as câmeras. Mitigação: rodar sob demanda, não em toda geração; documentar.
- **Oclusão residual.** Esconder `GlazedBalcony`/janelas pode não bastar (parede interna na frente).
  Mitigação: `mode:"closeup"` com câmera INTERIOR (eye dentro do cômodo) além do iso; config de
  `hide[]` por cômodo ajustável.
- **Match por nome de cômodo frágil** (`"SALA DE JANTAR | SALA DE ESTAR"`). Mitigação: match por
  substring curta ("SALA"/"COZINHA"/"SUITE") + teste que casa contra os nomes reais do `.skp`.
- **Enquadrar cômodo em L / irregular.** Mitigação: bbox da mobília (não do cômodo) + folga fixa;
  iso padrão do `pl_iso_camera` já lida com bbox arbitrário.
- **`.skp` do FP-036 ainda não mergeado.** Mitigação: apontar a tool pro path do artifact (existe no
  branch); tratar FP-036 como dependência (não regenerar aqui).

## 10. Plano de implementação em fatias pequenas

- **Fatia 0 — bbox por cômodo (Python puro)** + `test_room_bbox_from_boxes` + config declarativa +
  `test_room_cameras_config_valid`. Sem SU.
- **Fatia 1 — `material_review.rb` (isola + frameia + render, sem save)** + contrato-TEXTO
  `test_material_review_rb_contract`. Sem rodar SU ainda.
- **Fatia 2 — `material_review.py` (cópia do `.skp` + ENV + launch + coleta do log)** +
  `test_output_paths_predictable`.
- **Fatia 3 — smoke real** na planta_74: gerar os 3 proofs + closeup, conferir que a sala saiu sem
  vidro na frente. **PARA** e entrega as imagens pro veredito do Felipe.
- **Fatia 4 (opcional) — `mode:"closeup"` interior** afinado se o iso não bastar; mais cômodos na config.
