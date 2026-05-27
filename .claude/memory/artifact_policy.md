# Artifact policy — sketchup-mcp

**O `.skp` é o artefato humano mais importante.** Tudo neste arquivo
existe pra proteger essa propriedade.

## Hierarquia de artefatos

| Tier | Path | Tracked? | Propósito |
|---|---|---|---|
| **Humano / reviewable** | `artifacts/<plant>/` | ✅ | Deliverable canônico. SKP + renders + report + provenance README. Vai pra `develop`/`main` pra revisão. |
| **Humano / review-only** | `artifacts/review/<plant>/` | ✅ | Evidência específica de uma feature (overlay debug, stub review). Não é o deliverable principal. |
| **Canonical inputs** | `fixtures/<plant>/` | ✅ | Consensus JSON pinado. Não mutar sem aprovação humana (Hard Rule #3). |
| **Internal outputs** | `runs/<plant>/` | ❌ (gitignored) | Working build output. Scratch. Default `--out` cai aqui. Safe to delete. |
| **Test assets** | `docs/specs/_assets/` | ✅ | Expected geometry/render dos canonical specs (quadrado). |

## `/runs/` é scratch

`/runs/` está em `.gitignore` (`/runs/`). **Nunca** commitar
`/runs/` inteiro. Se um `.skp` de `/runs/` for evidência
importante de sucesso, **promover** pra `artifacts/<plant>/` antes
de declarar canônico.

## Promotion flow (runs/ → artifacts/)

```bash
# 1. Build cai em runs/
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp

# 2. Validar (gates do repo)
python -m pytest tests/ -q

# 3. Promover (cópia explícita, não move)
mkdir -p artifacts/planta_74
cp runs/planta_74/model.skp artifacts/planta_74/planta_74.skp
cp runs/planta_74/model_iso.png artifacts/planta_74/planta_74_iso.png
cp runs/planta_74/model_top.png artifacts/planta_74/planta_74_top.png
cp runs/planta_74/geometry_report.json artifacts/planta_74/geometry_report.json
# + side-by-side, metadata sidecar, README de provenance

# 4. Commit como artifact tracked
git add artifacts/planta_74/
git commit -m "feat(artifacts): refresh planta_74 SKP + renders + report"
```

Ver `specs/skp_artifact_layout.md` pra paths exatos e metadata
exigida.

## O que cada `.skp` canônico precisa carregar

Sob `artifacts/<plant>/`:

- `<plant>.skp` — o deliverable SketchUp
- `<plant>.skp.metadata.json` — sidecar com consensus SHA256
  (cache key pra invalidação)
- `<plant>_iso.png` + `<plant>_top.png` — renders auto via
  `write_image` no Ruby builder
- `geometry_report.json` — Python stats + SU counts + self-check
  do gate
- `side_by_side_pdf_vs_skp.png` — PDF underlay sobreposto ao SKP
- `README.md` — provenance: comando exato de regeneração + input
  + data + contexto

## Critério pra declarar sucesso

NUNCA basta render PNG. Pra qualquer task que envolva geração
SKP, declarar sucesso exige:

1. `.skp` gravado no path canônico
2. Renders auto (iso + top) presentes
3. `geometry_report.json` com gate self-check OK ou WARN
   justificado
4. Side-by-side PDF vs SKP comparativo quando aplicável
5. Tests verdes (pelo menos a contract suite)

Se faltar 1+ dos 5, status é **incompleto**, não sucesso.

## Sidecar metadata — gotcha de promotion

O builder (`tools/build_plan_shell_skp.py` → `write_metadata`)
escreve o sidecar com `skp_path` apontando pro path do build
(`runs/<plant>/<plant>.skp`). Quando promove pra
`artifacts/<plant>/`, **rewrite obrigatório**:

- `skp_path` ← `artifacts/<plant>/<plant>.skp` (canonical)
- `source_run_path` ← `runs/<plant>/<plant>.skp` (provenance, novo)

Caso contrário o sidecar canônico contradiz a Constitution #1
("SKP é o artefato principal" e mora em `artifacts/`). Schema
detalhado em `specs/skp_artifact_layout.md`.

## TODO — validar contra repo

- [ ] Confirmar que `artifacts/review/<plant>/` é convenção
      estabelecida (vi `artifacts/review/planta_74/` no listing)
      ou foi staging pontual de PR #192
