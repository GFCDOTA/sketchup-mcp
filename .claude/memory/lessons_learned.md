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

## LL-031 (2026-05-30) — consensus do planta_74 tem qualidade de dado SOLTA

Detectores determinísticos (consensus-only) acharam: **9/12 openings com host
errado** (`opening_host_audit`: o007/8/10 janelas, varanda, portas em segmento
curto) + **1 parede duplicada** (`wall_overlap_audit`: h_w001 ≈ w020, x 127.6 vs
129.2, overlap 97pt). Render "passa" mascarando isso (portas/painel não usam o
host; duplicata some no union do shell) → **visual auto-julgado dá falso PASS**.
Regra: rodar os detectores determinísticos ANTES de confiar no render. O FIX de
dado (corrigir extrator + regenerar consensus, dropar duplicata) MUTA fixture →
**NEEDS-HUMAN** (Hard Rule #3), nunca auto-aplicar. Builder já contorna o host
errado (aperture host-filtrado + fallback painel, FP-031).

## LL-032 (2026-05-31) — raiz do FP-031 = FRAGMENTAÇÃO COLINEAR; merge resolve

A raiz dos 9/12 host-errado + da duplicata é **fragmentação**: cada parede
arquitetônica vira vários segmentos colineares curtos com gaps nas aberturas, e o
opening fica num gap sem host válido. `tools/regenerate_consensus.py` (gate :8765
= approach B): **merge colinear (mesma orientação/coord-fixa, gap ≤ bridge_gap) +
re-host openings** → planta_74 walls **35→19**, opening_host **PASS(0/12)**,
wall_overlap **PASS(0)**. Efeito colateral GRANDE no render: a parede contínua faz
`find_wall_face_for_aperture` achar a face sólida → as 4 janelas passam de
**painel-fallback → aperture vazado** (paradigma quadrado). Determinístico
(gates/overlay/detectores PASS). **Regenerar = autônomo; PROMOVER pra canônica =
VISUAL_REVIEW** (render muda → Felipe julga). Câmera top agora determinística (#29,
fit 4:3 explícito, não zoom_extents) → gate cobre 100% das paredes.

## LL-033 (2026-05-31) — promover fixture move a baseline; repinar testes faz parte

Felipe aprovou (IMPROVED) e o regen virou consensus canônico do planta_74. Promover
uma fixture pinada **quebra os testes que afirmavam o estado ANTIGO** — e isso é
ESPERADO, não regressão: 6 testes pinavam o bug (detectores FAIL, wall_shell
junction=27/free=43, n_walls≥30) e foram repinados pro novo estado (PASS,
junction=21/free=17, n_walls≥15). Antes de repinar número geométrico, VERIFICAR que
o novo valor é são (rodei build_shell_polygon: 0 violação de stub LL-017, invariante
junction+free=2*walls vale). A behavior-de-captura dos detectores fica nos testes
SINTÉTICOS (não dependem da fixture), então repinar o teste-real-fixture pra PASS não
perde cobertura. Sempre regenerar o test-data render do build canônico novo.
