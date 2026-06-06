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

O deliverable estável `artifacts/<plant>/<plant>.skp` é **um path fixo, sem
timestamp, que sempre aponta pro último build correto**. Não cace pasta
`artifacts/review/<plant>/<ts>/final/` — o canônico mora no path fixo.

**Automático (preferido) — build + promove num comando só.** `--promote` copia
o build pro deliverable estável quando os self-check gates passam:

```bash
python -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out runs/planta_74/model.skp --promote
# -> PROMOTED -> artifacts/planta_74/planta_74.skp (self-check gates green)
git add artifacts/planta_74/ && git commit -m "feat(artifacts): refresh planta_74"
```

Gate-guarded: **gate vermelho / build cached / report ausente NÃO promove** —
nunca empurra build quebrado ou não-verificado pro path fixo.

**Promover um build que já existe** (ex.: um review snapshot aprovado):

```bash
python -m tools.promote_canonical --src artifacts/review/planta_74/<ts>/final
```

`promote_canonical` copia skp + renders + report e reescreve o metadata sidecar
(sha + provenance) — sem cp-dance manual, sem esquecer um arquivo.

⚠️ **VISUAL_REVIEW continua valendo.** `--promote` não substitui o olho do
Felipe: se a mudança altera a APARÊNCIA da planta, mostre o before/after, ele
aprova, e **só aí** você builda com `--promote`. O flag automatiza a *cópia*, não
o *veredito visual*. (Rebuild da mesma aparência aprovada → `--promote` livre.)

Ver `specs/skp_artifact_layout.md` pra paths exatos e metadata exigida.

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

## SKP Proof-of-Progress Gate (Constitution #8)

Toda PR que afete fidelidade arquitetônica adiciona um **6º
requisito**: artefatos de comparação antes/depois em
`artifacts/review/<plant>/<cycle>/` + `regression_summary.md`.

Detalhe completo em
[`specs/skp_proof_of_progress_gate.md`](../specs/skp_proof_of_progress_gate.md).
Skill operacional em
[`skills/generate-and-compare-skp-after-change/SKILL.md`](../skills/generate-and-compare-skp-after-change/SKILL.md).

Resumo: se a mudança toca builder / consensus / renderer / kind
routing / wall canonicalisation, **gerar SKP novo + renders +
comparação não é opcional, é parte da PR**.

## Sidecar metadata — gotcha de promotion (auto-tratada)

O builder (`write_metadata`) escreve o sidecar do build com `skp_path`
apontando pro path do build (`runs/<plant>/<plant>.skp`). Ao promover, o
sidecar canônico precisa de **rewrite**:

- `skp_path` ← `artifacts/<plant>/<plant>.skp` (canonical)
- `source_run_path` ← `runs/<plant>/<plant>.skp` (provenance)
- `consensus_sha256` ← **carregado** do sidecar do build (cache key)

Isto é **feito automaticamente** por `tools/promote_canonical.py` (e portanto
pelo `build_plan_shell_skp --promote`): ele lê o sidecar do build, carrega o
`consensus_sha256` + stats, e reescreve os campos de path pro canônico. Não
precisa editar à mão. Schema detalhado em `specs/skp_artifact_layout.md`.

## TODO — validar contra repo

- [ ] Confirmar que `artifacts/review/<plant>/` é convenção
      estabelecida (vi `artifacts/review/planta_74/` no listing)
      ou foi staging pontual de PR #192
