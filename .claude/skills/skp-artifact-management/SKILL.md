---
name: skp-artifact-management
description: Use whenever a task creates, promotes, validates, or versions a .skp file. Triggers on `artifacts/<plant>/`, `runs/<plant>/`, "promote SKP", "commit SKP", `<plant>.skp.metadata.json`, "build provenance", or any decision about where a generated SKP lands. The .skp is the human-facing deliverable — protect that.
---

# skp-artifact-management

Skill pra gerenciar `.skp` como artefato versionado.

## Princípio raiz

**O `.skp` é o artefato humano mais importante.** Toda decisão
nesta skill protege essa propriedade. PNG / report / overlay são
evidência auxiliar — não substitutos.

## Quando usar

- Task acabou de gerar `.skp` novo em `runs/`
- Decidir se um `.skp` deve virar artifact versionado
- Auditar `artifacts/<plant>/` quanto a completude / staleness
- Atualizar provenance / metadata sidecar
- Cleanup de artifacts duplicados / stale

## Convenção runs/ vs artifacts/

| Path | Tracked? | Status |
|---|---|---|
| `runs/<plant>/` | ❌ (gitignored) | Scratch. Build cai aqui por default. Safe to delete. |
| `artifacts/<plant>/` | ✅ | Deliverable canônico. Vai pra `develop`/`main`. |
| `artifacts/review/<plant>/` | ✅ | Evidência feature-specific (overlay debug, stub review). |

Detalhe completo em `memory/artifact_policy.md` e
`specs/skp_artifact_layout.md`.

## Promotion flow (runs/ → artifacts/)

```bash
# 1. Build em runs/
python -m tools.build_plan_shell_skp \
  fixtures/<plant>/<consensus>.json \
  --out runs/<plant>/<plant>.skp

# 2. Validar gates
python -m pytest tests/ -q

# 3. Copiar pro path canônico
mkdir -p artifacts/<plant>
cp runs/<plant>/<plant>.skp artifacts/<plant>/
cp runs/<plant>/<plant>_iso.png artifacts/<plant>/
cp runs/<plant>/<plant>_top.png artifacts/<plant>/
cp runs/<plant>/geometry_report.json artifacts/<plant>/

# 4. Gerar/atualizar side-by-side comparativo
# (TODO — confirmar comando exato no repo)

# 5. Atualizar metadata sidecar com SHA do consensus
# (ver specs/skp_artifact_layout.md § sidecar)

# 6. Atualizar README de provenance

# 7. Commit
git add artifacts/<plant>/
git commit -m "feat(artifacts): refresh <plant> SKP + renders + report"
```

## Estrutura mínima sob `artifacts/<plant>/`

- `<plant>.skp` ← the deliverable
- `<plant>.skp.metadata.json` ← SHA256 sidecar (cache key)
- `<plant>_iso.png` + `<plant>_top.png` ← renders
- `side_by_side_pdf_vs_skp.png` ← overlay
- `geometry_report.json` ← stats + gate self-check
- `README.md` ← provenance (comando de regeneração, input, data)

Sem QUALQUER um destes 6, artifact é incompleto.

## Critério pra declarar sucesso canônico

Sucesso de geração SKP exige:

1. `.skp` em path canônico ✅
2. Renders auto (iso + top) ✅
3. `geometry_report.json` com gate OK ou WARN justificado ✅
4. Side-by-side PDF vs SKP ✅
5. Contract tests verdes ✅

NUNCA basta PNG. Render bonito sem `.skp` é demo.

## NUNCA fazer

- Commitar `/runs/` inteiro (está em `.gitignore` por boa razão)
- Promover `.skp` sem `geometry_report.json` correspondente
- Sobrescrever `artifacts/<plant>/<plant>.skp` sem atualizar
  metadata sidecar (cache key fica stale → invalidação quebra)
- Deletar `artifacts/<plant>/` que está mergeada em `develop`
  sem PR explícita

## Quando archive

Se um artifact é superseded por nova versão:

- Default: substituir in-place + atualizar README com nota de
  versão anterior
- Se a versão antiga tem valor histórico (e.g. pre-FP-026
  baseline): mover pra `docs/archive/<YYYY-MM-DD>/`

## TODO — validar contra repo

- [ ] Confirmar onde `side_by_side_pdf_vs_skp.png` é gerado
      (tool? manual? Ruby builder?)
- [ ] Confirmar comando exato de geração do sidecar metadata

## Skills relacionadas

- `pdf-to-skp-pipeline/` — quem gera o `.skp`
- `fidelity-review/` — quem aprova o `.skp` pra promotion
- `repo-governance/` — PR + commit do artifact
