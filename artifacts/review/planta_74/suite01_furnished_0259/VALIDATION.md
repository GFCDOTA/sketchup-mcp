# Suíte 01 (r000) — furnished @ PT_TO_M=0.0259 (prova do fix de escala dos MÓVEIS)

> Plano (b): portar SÓ o fix de escala necessário pro PR feat/mobiliar-bedroom-layout.
> Branch `chore/suite01-scale-gate` (off feat/mobiliar-bedroom-layout). Escopo: Suíte 01 só.
> **NÃO promovido ao canônico/furnished oficial.** Merge coordenado via HANDOFF.

## O que estava errado (root cause — o gate room-aware pegou)
Com `PT_TO_M=0.0259` o SHELL ficava certo (área 15.9 m²) mas os MÓVEIS saíam **1.36× grandes**
(colchão 2.72×2.11 vs queen 1.58×2.03) e o geometry_sanity dava **FAIL** ("CENTRO fora do comodo").
Causa: DOIS sites de escala hardcoded no path do quarto (NÃO o sofa_builder, que já é m→in 39.37):
1. `furnish_apartment.py` `bedroom_designer_boxes`: `pt_m = 0.19/5.4` reconvertia o footprint
   (dimensionado no PT_TO_M novo) de volta a 0.0352 → móvel 1.36× + centro fora do cômodo.
2. `bedroom_designer._items_to_boxes`: `pt_to_in = (0.19/5.4)*39.37` → headboard/rug a 0.0352.
Fix (commit 1d94494): ambos via env, mesmo padrão de `spatial_model`/`geometry_sanity`.

## Prova @ PT_TO_M=0.0259 (determinística)
- **Área Suíte 01**: 15.9 m² (shell correto).
- **Colchão**: 1.99 × 1.54 m ≈ **queen** (1.58×2.03) — era 2.72×2.11 (1.36×). Cama escolhida: queen.
- **geometry_sanity**: **PASS** (zero FAIL, zero WARN). O WARN criado×porta foi limpo: placement
  agora é door-aware (clearance 22in = a do gate) e reduz/afasta só o criado da porta. 2 criados mantidos.
- **Headboard dedup**: 1 cabeceira (era headboard+cabeceira duplicados) → 32 boxes.
- **Default 0.0352 INTACTO** (provado before==after p/ r000+r003); 39 testes + 4 novos (test_suite01_scale_gate) passam; fixtures não mutados.
- **Verificação adversarial** (workflow 9-agent): F1/F2/F4 CONFIRMED; F3 SUSPECT→resolvido (teste + default idêntico).

## Artefatos
- `suite01_furnished_0259.skp` — **SHA256 `0f0c46c87015dad8cbf6fb8150581b736bea799cbac4c2365c51bee9600a997f`**
- `suite01_furnished_top_0259.png` / `suite01_furnished_iso_0259.png` — placement (cama queen + cabeceira + 2 criados + guarda-roupa + tapete dentro do quarto)
- `suite01_furnished_audit_0259.json` — geometry_sanity + medidas

## Reprodução
```bash
# 1) prova determinística (sem SU):
PT_TO_M=0.0259 .venv/Scripts/python.exe -c "import os,json; \
from tools.geometry_sanity import sanity_room; \
from tools.furnish_apartment import CONSENSUS, bedroom_designer_boxes; \
con=json.loads(CONSENSUS.read_text('utf-8')); \
print(sanity_room(con,'r000')); \
bx,_=bedroom_designer_boxes(con,'r000'); \
c=[b for b in bx if b['kind']=='colchao'][0]; \
print('colchao_m', round((c['x1']-c['x0'])*0.0254,2), round((c['y1']-c['y0'])*0.0254,2))"
# 2) .skp: boxes (acima) -> place_layout_skp.rb sobre o shell 0.0259
#    (artifacts/review/planta_74/scale_rebuild_0259_20260608/model.skp). shell_intact=True.
```

## Resposta à pergunta do Felipe (cobre da sessão paralela)
"O furnished de vocês foi gerado com spatial_model.PT_TO_M=0.0259 ou só o shell foi rebuildado?"
→ **Só o shell estava @0.0259; o furnished estava 1.36× grande.** O `spatial_model.PT_TO_M`
deles era 0.0352 hardcoded E havia +2 sites hardcoded (`furnish_apartment.pt_m` +
`bedroom_designer._items_to_boxes`). O patch env conserta os três → furnished real @0.0259.

## V-Ray premium — pipeline OK, hero-cam BLOQUEADO (fallback honesto, regra 10)
Rodei `vray_export.rb` + `tweak_vrscene --materials` + `vray.exe` sobre o .skp @0.0259:
**pipeline funciona** — 19 texturas premium aplicadas (madeira/tecido/linho/piso), GI + denoise
RTX 5080, 0 erros, ~10s. PORÉM o **hero-cam interior** num quarto apertado (4.0×5.46m, móveis
ocupam 2/3, só faixa leste de ~1.5m livre) + GI dim deu shots cramped/escuros em 2 tentativas.
NÃO fiz 3ª (Felipe: "não quero mais tweak de fill/crop por cômodo"). **Follow-ups documentados:**
- estratégia de câmera p/ quarto apertado (doorway/3-4 elevado) + iluminação interior;
- `auto_camera.py` está scale-leaked (0.0352) → precisa do env fix p/ servir cam a 0.0259;
- round-edges (WARN "arestas duras") precisa do plugin V-Ray `texRoundEdges` (não está no pipeline) —
  `tweak_vrscene._set_block` só substitui params existentes, não injeta nó novo.
**Reviewable desta entrega = o SU ISO/top** (mostra cama queen + cabeceira + criados + guarda-roupa
no quarto, escala certa). O V-Ray premium hero é polish gated nos follow-ups acima.

## Próximo (humano)
geometry_sanity sem FAIL → liberado pra **VISUAL_REVIEW do Felipe vs PDF** (gate humano).
NÃO autojulgo IMPROVED/SAME/WORSE. Merge desta branch no PR coordenado via HANDOFF.
