# Lessons learned — sketchup-mcp

Aprendizados permanentes. Cada item já custou tempo / PR / rework.

## 1. Não criar demo paralela quando existe artefato canônico

Pra adicionar porta/janela/móvel, **abrir o `.skp` que funciona e
editar in-place** via `push_pull` + `add_face`. NUNCA rebuild via
`entities.clear!` em `consume_consensus.rb`-style. Validado em
quadrado_demo: V1 rebuild fechava SU rápido; V2 in-place edit
abre 27+s.

## 2. Micro-test → planta real, fluxo disciplinado

Antes de tocar `planta_74`, provar o paradigma na fixture
`quadrado/`. Fluxo de 5 etapas:

1. Micro-fixture canônica
2. Prova isolada (teste verde)
3. Teste regressivo no contrato
4. Aplicação na planta real
5. Comparação com baseline

Micro-test é PERMITIDO mas DEVE terminar em decisão explícita:
**aplicado / rejeitado / bloqueado**. Sem caminho de volta pra
planta = demo bonita = proibido.

Critério mental: *"isso aproxima o pipeline real ou é só demo
bonita?"*

## 3. PNG/render ajuda, mas o `.skp` precisa ser entregue

Render é evidência auxiliar. Critério canônico exige
`.skp` versionado, não só PNG. Ver `memory/artifact_policy.md`
e `skills/skp-artifact-management/SKILL.md`.

## 4. Room fidelity pode falhar por rooms semanticamente fundidos

Quando o PDF não tem parede real entre dois ambientes (open-plan,
ex.: sala de jantar + estar), o polygonize fecha 1 cell, não 2.
`room_fidelity = WARN`, NÃO FAIL — é honesto. Inventar parede pra
hit a "11 rooms" violaria Hard Rule #1.

Backlog: overlay `semantic_zones` separado pode dividir cells
fundidos sem forjar geometria de parede.

## 5. Soft barriers / peitoril não viram parede cheia

Peitoril (sill) e grade não são walls estruturais. Window
aperture (3D carve) preserva mass abaixo do sill e acima da
verga. Door/porta-vidro vão pelo path 2D full-height carve.
Ver `kind_v5` routing em `project_context.md`.

## 6. PDF → metros precisa de âncora física

`PT_TO_M` sai de `wall_thickness_pts / 0.19` (ou outra dimensão
real conhecida). NUNCA `0.0254 / 72` default. PDF não vem com
escala universal — depende do plotter de origem.

## 7. Não fabricar sem medidas no PDF

Extraction deve ser HONESTA: sem inferência procedural nem
injeção de GT externo. Se a parede não aparece no PDF, ela não
existe na consensus. Anchor: Hard Rule #1.

## 8. Olhar artefato ANTES de tweakar parâmetro

Se output errado, parar e LER o artefato + checar fonte (vetor
vs raster), NÃO iterar threshold/kernel no escuro.

## 9. Não rodar cleanup em loop

Repo hygiene precisa de trigger real (gate quebrando, ref
duplicada, root script fora da allowlist). Não fazer 3 audits
seguidos convergindo no mesmo "preserve" — virou bikeshed.

## 10. SU runner mode default = interactive

`--mode headless` é APENAS pra CI. Em dev local SU fecha sozinho
após build e parece bug. Default `interactive` deixa janela
aberta pra inspeção visual. (PR #186 cravou regra.)

## 11. Não confundir gate visual com gate de contrato

Visual fidelity (PNG comparativo) é informativo. Gate de
contrato é teste Python (`tests/`). Os dois precisam passar — um
não substitui o outro.

## 12. No SKP, no progress (LL-021)

Toda PR que promete melhorar fidelidade arquitetônica deve gerar
`.skp` novo em pasta human-facing (`artifacts/review/<plant>/<cycle>/`)
com renders + comparação antes/depois + `regression_summary.md`.

Por quê: já tivemos casos (2026-05-27, pós PR #194) onde o gate
machine-readable (`gates_self_check = true`) passava mas o humano
levantou suspeita visual de regressão de openings. Só rodando
build fresh e comparando contagens deu pra dismissar a hipótese
(invariantes pinados em PR #195).

`gates_self_check = true` sozinho não prova fidelidade.
`.skp` em `/runs/` (scratch) não serve pra revisão.

Constituição #8 cravou. Operacional em
[`specs/skp_proof_of_progress_gate.md`](../specs/skp_proof_of_progress_gate.md).
Skill `generate-and-compare-skp-after-change` implementa.
