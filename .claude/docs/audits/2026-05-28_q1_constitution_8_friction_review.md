# Audit — Constitution #8 friction-tax review (Q1, 2026-05-28)

Review crítica da Constitution #8 / SKP Proof-of-Progress Gate
**antes** de mergear PR #196, conforme tua pergunta Q1
("friction tax após cravar a regra").

## Status do dispatch ao GPT

- Bridge `localhost:8765` testada: **OFFLINE** (sem listener,
  sem `.ai_bridge/` no repo)
- Tentativa de levantar bridge declinada — UI automation
  abriria janela na máquina do user durante o sono
- Q1 resolvida **offline** com a análise técnica fornecida pelo
  próprio user no turno seguinte (transcrita abaixo)

## Pergunta Q1

> "Tenho uma regra recém-cravada num projeto SketchUp que obriga
> toda PR de builder/consensus/renderer a commitar `.skp` binário
> (~140KB) + 2 PNGs (~200KB) + `regression_summary.md` em
> `artifacts/review/<plant>/<branch>/`. Iteração típica de
> feature passa por 3-4 builds. Quais failure modes você vê?
> Especificamente: (a) repo bloat após 50 PRs, (b) template de
> 8 axes virar check-the-box theater, (c) 'in doubt: applies'
> criar over-coverage que mata velocidade, (d) como reduzir
> fricção sem voltar ao problema antigo, (e) o que commitar vs
> CI temporário, (f) quando usar Git LFS, (g) regra escalável."

## Análise canônica (do user)

### Failure mode A — repo bloat

- 50 PRs × ~500-800KB/PR = 25-40MB review artifacts
- GitHub recomenda repos < 1GB, hard < 5GB
- Crescimento histórico via versões antigas amplifica
- **Mitigação**: commitar só FINAL human-facing; intermediários
  em `/runs/` ou CI artifacts (default 90 dias retention)

### Failure mode B — checklist theater

- 8 axes preenchidas com "PASS — ok" viram teatro
- Cada axis precisa de evidência **curta e concreta**
- Permitir `N/A` controlado pra PR que comprovadamente não toca
  aquele eixo

### Failure mode C — over-coverage

- "In doubt: applies" mata velocidade se for cego
- Melhor: **path triggers** + escape hatch com justificativa
- Lista paths SKP-affecting explicitamente, doc/test/CI ficam
  fora por default

### Failure mode D — binário versionado errado

- `.skp` ~140KB é o deliverable principal — manter no repo
- NÃO versionar todos `.skp` intermediários (cada attempt)
- Git LFS tem custo/fricção — NÃO migrar preventivamente; só
  reavaliar se total passar de 200-500MB

### Failure mode E — pixel-perfect instabilidade

- Pixel diff hard gate sofre flakiness (GPU/driver/fontes)
- PNGs são **evidência de review**, não diff bit-exato
- Hard FAIL reservado pra **absurdos categóricos**: missing SKP,
  missing render, window count mismatch, floating door, orphan
  glass sem source, qualquer `gates_self_check = false`

## Refinamentos aplicados em PR #196 (este patch)

### `.claude/constitution.md` §8

- "Toda PR que afete" → "Toda **SKP-affecting PR** (path-triggered)"
- Adicionada cláusula de escape hatch: `SKP-proof: N/A`
- Adicionada cláusula sobre intermediários NÃO commitar por
  default
- Adicionada nota anti pixel-perfect hard gate

### `specs/skp_proof_of_progress_gate.md`

- §"Quando aplica" reescrita com **path triggers explícitos**
  (tabela de paths + condições)
- §"Quando NÃO aplica" reescrita com **escape hatch format**
  (`SKP-proof: N/A\nReason: ...\nJustification: ...`)
- §"Artefatos obrigatórios" reescrita pra política em camadas:
  - "Commitar SEMPRE" = só FINAL (`final/`)
  - "NÃO commitar por default" = intermediários, debug, attempts
  - "Exceção" = intermediário só com decisão-chave documentada
  - Nota explícita sobre **Git LFS — não usar ainda**
  - Nota explícita sobre **pixel-perfect — não fazer hard gate**
- §"Critérios de bloqueio" expandida pra **10 hard gates
  categóricos** (1-7 humano cobra, 8-10 automatizáveis)
- §"Anti-checklist-theater" adicionada com exemplos bom/ruim de
  evidência

### `specs/templates/regression_summary_template.md`

- Tabela de comparação ganhou coluna "Evidência **específica**"
- Adicionado bloco anti-theater com exemplo bom vs ruim
- Permite `N/A — <razão>` por axis

## O que NÃO mudou (intencional)

- Frase-regra "**No SKP, no progress**" — mantida forte
- 10 deliverables do gate — mantidos
- Skill `generate-and-compare-skp-after-change` — mantida
- Encaixe em categoria 5 do operational_rules — mantido

## Encaminhamento

- Refinamentos commitados em mesmo branch PR #196
- Comment no PR explicando a evolução
- Próximo: merge #196, iniciar trabalho do Visual Oracle Gate
  com este refinamento já vigente

## Bridge offline — registro

Q2/Q3 (CI gate design / "reverse-trial" rubric) **não
dispatchadas** — esperando trigger real. Q2 só após autorização
explícita do tool. Q3 vira valuable só se houver bifurcação
visual real na próxima PR de fidelidade.
