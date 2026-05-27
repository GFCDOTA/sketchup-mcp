# Product goal — sketchup-mcp

## O que é sucesso pro humano

Gerar um `.skp` SketchUp **fiel ao PDF original**, **revisável
visualmente** e **versionado**. Tudo o mais (testes, refactor,
limpeza de repo, ADRs) só conta se destravar esse objetivo.

## "SKP bom" — definição operacional

Um `.skp` é "bom" quando:

1. **Geometria honesta** — todas as paredes / aberturas existem
   no PDF e estão na consensus. Sem inferência procedural.
2. **Aperturas corretas** — windows preservam peitoril + verga
   (3D carve); doors / passages / porta-vidro vão pelo path 2D
   full-height.
3. **Cells fechados onde existe parede** — rooms saem do
   polygonize do shell, não de label de PDF.
4. **Renders auto** — iso + top geradas pelo Ruby builder em
   `write_image`.
5. **Report de geometria** — `geometry_report.json` com gate
   self-check OK ou WARN justificado.
6. **Side-by-side** — PDF underlay sobreposto ao SKP pra
   comparação visual.
7. **Provenance** — README sob `artifacts/<plant>/` com comando
   de regeneração + input + data.

## Artefatos que o humano quer ver

Ordem de prioridade:

1. `artifacts/<plant>/<plant>.skp` — o deliverable
2. `artifacts/<plant>/<plant>_iso.png` + `_top.png` — render
3. `artifacts/<plant>/side_by_side_pdf_vs_skp.png` — diff visual
4. `artifacts/<plant>/geometry_report.json` — gate machine-readable
5. `artifacts/<plant>/README.md` — provenance pra reproduzir

## Diferença engenharia interna vs entrega real

| Engenharia interna | Entrega real |
|---|---|
| `tests/` verde | `.skp` fiel ao PDF |
| Refactor de `build_shell_polygon` | SKP que abre limpo no SketchUp |
| Spec docs em `docs/specs/` | Render side-by-side que o humano consegue revisar |
| Cleanup de fixture orfã | Promotion de `/runs/` pra `artifacts/` |

Engenharia interna habilita entrega. Não é entrega.

## Critérios de avanço real

O projeto avançou quando:

- Um `.skp` novo entra em `artifacts/<plant>/` ou
- Um `.skp` existente em `artifacts/<plant>/` melhora fidelidade
  (rooms fechados que antes não fechavam, openings corretos
  onde estavam errados, stubs eliminados etc.) **com evidência
  visual side-by-side**.

Refactors, ADRs e limpezas só contam se destravarem essa
mudança. Caso contrário é trabalho cosmético.

## Não-objetivos

- Conversão automática end-to-end de qualquer PDF qualquer (PDFs
  podem ser raster, sem escala, sem padrão).
- Reverse engineering do SketchUp file format (usa-se Ruby API).
- Real-time editing (geração é batch).
- Dashboard / UI visual (foi podado em PR #184).
