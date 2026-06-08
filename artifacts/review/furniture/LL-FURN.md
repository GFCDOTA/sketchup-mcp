# LL-FURN — learning log de mobiliário (memória por objeto)

> Ciclo de aprendizado por móvel: FAIL/WARN visual GPT → regra → fixture/builder →
> SKP → GPT PASS. Cada entrada = uma lição durável de PRODUTO (não de render).
> Anatomia (peças semânticas) vive em `tools/furniture_anatomy_spec.py`.

## LL-BED-001 — cabeceira estofada tira a cama do "look de lajes" (2026-06-08)
- **FAIL/WARN**: cama era estrado+colchão+travesseiros+manta SEM cabeceira → lia como
  "lajes empilhadas", travesseiros encostando no nada (montage v1: FURNITURE_DETAIL ok mas
  PREMIUM WARN "falta bevel").
- **Regra**: cama real tem CABECEIRA. Painel vertical na cabeça (Y alto), X cheio, do chão
  a `headboard_h` (acima dos travesseiros), estofado (linho quente). Travesseiros encostam NELA.
- **Builder**: `bed_builder.py` peça `cabeceira`; `BedSpec.headboard_h/headboard_t/headboard_rgb`;
  `pillow_h` 0.10→0.16 (travesseiro fofo, bevel lê como almofada). `cabeceira` em BED_REQUIRED_PARTS.
- **GPT PASS** (id=bedroom_anatomy_v2): FURNITURE_DETAIL=PASS "cama saiu do look de lajes;
  cabeceira estofada + travesseiros melhoraram MUITO a leitura de cama real". CAMERA/LIGHTING=PASS.
- **Evidência**: `bedroom_anatomy_montage_v2.png`.

## LL-FURN-GOTCHA-001 — bevel/inset quebra em peça FINA ("Duplicate points") (2026-06-08)
- `build_furniture_skp.rb::fz_solid` faz o chanfro insetando o footprint por `bevel` (~4cm).
  Se a peça é fina numa dim (painel/porta/pé: Y<2.4×bevel), o inset zera a face →
  `ArgumentError: Duplicate points in array` → a peça é DROPADA (cabeceira sumiu no 1º build).
- **Fix durável**: guard de footprint em fz_solid — só chanfra se `fw,fd >= bevel*2.4`;
  senão cai pra caixa plana limpa. Peça fina nunca mais quebra; peça grossa ganha chanfro.
- **Regra**: chanfro/inset é pra superfície macia GROSSA (almofada/colchão), não pra painel fino.
  Estofado de painel vem da COR/proporção, não do top-inset.

## Estado da anatomia (2026-06-08)
- **CAMA**: real (cabeceira+colchão+travesseiros+manta+estrado). GPT FURNITURE_DETAIL PASS.
- **GUARDA-ROUPA**: real (corpo+3 portas+puxadores+rodapé). PASS. WARN: laterais/topo rígidos.
- **CRIADO-MUDO**: real (corpo+tampo+gaveta+knob+4 pés). PASS. WARN: o mais blocado dos três.
- **SOFÁ**: base+assentos+encostos+braços+pés (slice anterior).

## Pendente — WARN recorrente "arestas duras / chapado" (PREMIUM_REALISM)
Aparece em TODA review (sofá, cama, trio). NÃO é gap de anatomia (FURNITURE_DETAIL já PASS) —
é **qualidade de RENDER**: estes são ISO flat de showroom (sem textura/GI/round-edges). O premium
real vem da **trilha V-Ray** (texturas + GI + round-edges shader), que está **gated na decisão de
ESCALA do Felipe** (`scale_candidate_20260608/`). Chanfro geométrico em render flat é baixo-ROI;
o caminho certo é V-Ray round-edges (render-time, zero risco de geometria) quando a escala for aprovada.
