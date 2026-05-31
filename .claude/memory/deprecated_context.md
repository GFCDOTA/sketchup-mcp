# Deprecated context — sketchup-mcp

Instruções / preferências / decisões que **NÃO** devem mais
orientar agentes. Mantidas aqui por rastreabilidade, não pra
seguir.

## Formato de entrada

```
## Deprecated: <nome curto>
Status: superseded
Replaced by: <arquivo / regra atual>
Reason: <por quê>
Do not use for future decisions.
```

---

## Deprecated: PR manual via browser como default

Status: superseded
Replaced by: `memory/git_workflow.md` → seção "PR via gh"
Reason: `gh` está instalado e autenticado (account
`fmodesto30`, scope `repo`, keyring). Caminho absoluto
`"/c/Program Files/GitHub CLI/gh.exe"` no Git Bash funciona sem
PATH. Não há mais motivo pra preferir browser manual.
Do not use for future decisions.

---

## Deprecated: pipelines V3 / V4 / V5 / V5.1 / V6.1

Status: superseded
Replaced by: pipeline atual `consensus.json → build_plan_shell_skp`
Reason: Repo foi podado pra "minimal SKP-generation pipeline" em
PR #184 (chore: prune). Algoritmos histórico (V6.2 dois-repos,
V7 vector-first extractor) viviam em `E:/Sketchup/` e
`exp-dedup/`, ambos fora deste repo. Se referência aparecer em
docs/código, é resíduo de cleanup incompleto.
Do not use for future decisions.

---

## Deprecated: `consume_consensus.rb` style (entities.clear! +
rebuild)

Status: superseded
Replaced by: in-place edit do `.skp` canônico (`memory/lessons_learned.md`
#1)
Reason: `entities.clear!` mata o modelo todo e gera SU instável.
Validado em quadrado_demo V2.
Do not use for future decisions.

---

## TODO

- [ ] Auditar `docs/` por referências a V3–V6.x, dashboard
      antigo, `exp-dedup`, CubiCasa5K e adicionar entry aqui se
      ainda houver doc viva apontando pra eles
