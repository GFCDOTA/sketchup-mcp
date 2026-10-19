# Projeto `planta_74`

Apartamento de 74 m² que o pipeline modela. Este diretório guarda a **fonte identificada** do projeto e aponta para
as entradas e saídas canônicas; ele não duplica nenhuma delas.

| Papel | Caminho | Observação |
|---|---|---|
| Fonte (verdade geométrica) | [`source/planta_74.pdf`](source/planta_74.pdf) | planta em PDF; o caminho é resolvido só por `core.project_sources.plant_pdf_path` |
| Entrada canônica | [`fixtures/planta_74/`](../../fixtures/planta_74/) | `consensus_with_human_walls_and_soft_barriers.json`; protegida, não se edita sem aprovação humana |
| Entregável canônico | [`artifacts/planta_74/`](../../artifacts/planta_74/) | `.skp`, renders e `geometry_report.json` aprovados |
| Evidência de revisão | [`artifacts/review/planta_74/`](../../artifacts/review/planta_74/) | before/after e auditorias |
| Escala | `core/scale.py` → `PLANT_PT_TO_M["planta_74"] = 0.0259` | âncora de cota verificada (SUITE 01: 5,45 × 4,00 m); processos da planta_74 sobem com `PT_TO_M=0.0259` |

## Regras

- O PDF **ganha** de qualquer inferência: nenhuma medida de tutorial, receita ou render vira cota do apartamento.
- A migração do PDF para cá (FP-043/P2) não mudou o conteúdo: o registro com blob e SHA256 está em
  [`docs/specs/fp043_protected_renames.v1.json`](../../docs/specs/fp043_protected_renames.v1.json).
- O campo `source` do consensus (`"planta_74.pdf"`) é um **nome**, não um caminho, e não muda.
