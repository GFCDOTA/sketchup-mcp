# FP-043 / P3a-03 — colisões de mobília no apê integrado (L2, SketchUp 26.0.429)

Antes: `planta_check_before.json` (L2 FP-042, P02). Depois: `planta_check_after.json` — `su_build_shell` + `su_furnish` pelo cliente MCP real,
`su_inspect` do `.skp` reaberto, mesmo `planta_check.py` (`artifacts/review/l2_fp042_20261019/tools/`). 402/402 peças casam com o plano (0,05 mm), 0 geometria solta.
Cada SketchUp fechado pelo PID; canônicos intactos (a saída foi para `runs/`).

| Achado (FURNITURE/FIXTURE/decor de piso) | Antes | Depois |
|---|---|---|
| Painel TV na parede | 5,0 cm | 0 |
| Mesa de jantar no giro de `h_o000` | 35,8 cm² | 0 |
| Escova do lavabo no giro de `h_o001` | 65,2 cm² | 0 |
| `kb_ralo` / `box_vidro` do banho 02 | 2,6 / 0,6 cm | ~0 (ruído de arredondamento, 0,0 cm) |
| Criado-mudo 2 da SUITE 01 | 5,3–6,3 cm | **igual — D-008 (decisão de produto)** |

Restam só peças `STRUCTURAL`/`SKIN` (Pele, PeleTeto, piso/teto do box) que entram sob a parede por desenho (laje, D-007) e `kb_folha`/`kb_piso_box` do banho 01
(fora do escopo desta fatia). Muda a aparência: **VISUAL_REVIEW** do Felipe; nenhum veredito visual aqui.
