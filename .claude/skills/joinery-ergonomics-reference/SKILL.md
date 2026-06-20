---
name: joinery-ergonomics-reference
description: >
  Especialista em MEDIDAS + REFERÊNCIAS de móvel planejado. Use quando houver REFERENCE_PACK
  de ergonomia (Pinterest/board/foto de cozinha/quarto/banheiro planejado) ou ao validar
  alturas/clearances de marcenaria (bancada, aéreo, sóculo, coifa, geladeira, profundidade).
  Dispara em "referência de medidas", "ergonomia", "clearance", "altura da bancada/aéreo",
  "REFERENCE_PACK", "board do Pinterest", "padrão de planejado". Regra: a referência influencia
  LINGUAGEM e MEDIDA, NUNCA a POSIÇÃO (pia/parede/porta/circulação = PDF). É a metade "medida"
  do método; a metade "gramática visual" é [[planned-joinery-translator]]. Audita com
  `tools/kitchen_ergonomics.py`. NÃO transformar layout linear em U/L por causa de uma foto.
---

# JOINERY_ERGONOMICS_REFERENCE — especialista em medidas

> A referência diz COMO parece e QUANTO mede; o PDF diz ONDE fica. Nunca inverter.

## Regra máxima
```
Referência → LINGUAGEM + MEDIDA (paleta, proporção, clearance, detalhe).
PDF        → POSIÇÃO (pia hidráulica, parede, porta, janela, circulação) = IMUTÁVEL.
NÃO mudar a tipologia (linear/L/U) por causa de uma imagem.
```

## Padrões ergonômicos (cm) — fonte do audit `tools/kitchen_ergonomics.py`

| Medida | Alvo | Token |
|---|---|---|
| Altura da bancada | 88–92 | `countertop_height_88_92cm` |
| Recuo do sóculo (toe-kick) | 8–15 | `toe_kick_10_15cm` |
| Espessura do tampo (borda fina) | 2–4 | — |
| Clearance bancada → aéreo | 50–60 | `upper_cabinet_clearance_50_60cm` |
| Altura do armário aéreo | 50–92 | — |
| Profundidade módulo inferior | 50–60 | `lower_module_depth_50_60cm` |
| Coifa sobre cooktop | 45–65 (under-cabinet) · 70–80 (chaminé) | `hood_clearance_70_80cm_above_cooktop` |
| Clearance da cuba | 60–65 | `sink_clearance_60_65cm` |
| Altura do forno embutido | 140–150 | `oven_height_140_150cm` |

Tokens de linguagem que vêm junto: `tower_appliances_column`, `under_cabinet_led`,
`light_countertop`, `gray_OR_wood_lower_cabinets`, `white/offwhite_upper_cabinets`,
`textured_backsplash`, `gooseneck_faucet`, `slab_doors`, `slim_profile_handle`.

## Protocolo de referência Pinterest/board

1. **Acessar via Chrome** (`mcp__Claude_in_Chrome__*`) — board/pin.
2. ⚠️ **VERIFICAR que o pin/board é do tema certo** — links de pin do Pinterest erram/redirecionam
   (caso real 2026-06-19: pin "979884831441022310" do board de cozinhas abriu como PLACAS SOLARES).
   Se não bate, NÃO inventar gramática; usar os tokens/medidas que o usuário deu no chat (fonte
   autoritativa) e avisar que o link não conferiu.
3. **Extrair** (nunca copiar pixel): paleta, soluções de planejado, proporções/medidas.
4. **Cruzar com o PDF** — medidas entram; posição NÃO muda.
5. **Auditar** o build: `PT_TO_M=0.0259 python -m tools.kitchen_ergonomics` (PASS/WARN por medida).
6. Ajustar só o que estiver fora do alvo; re-render 5 ângulos; veredito humano/GPT.

## Como adicionar uma medida nova
Editar `ERGO` em `tools/kitchen_ergonomics.py` (faixa min,max) e expor a constante
correspondente no builder (ex.: `kitchen_layout.AEREO_Z0`, `TOE_KICK`, `TAMPO_THK`) pra o
audit medir. WARN = guia (não derruba build); a POSIÇÃO continua sob os gates duros
(`kitchen_validation` / `geometry_sanity` / `furniture_overlap_gate`).
