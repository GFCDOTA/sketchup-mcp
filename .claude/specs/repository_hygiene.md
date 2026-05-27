# Repository hygiene — sketchup-mcp

Política de limpeza. Anti-padrão raiz: **cleanup em loop sem
trigger**. Hygiene exige justificativa pontual, não pode virar
bikeshed.

## Triggers reais pra cleanup

Só fazer hygiene pass se um dos abaixo for verdade:

1. **Arquivo quebrando gate** (test falhando por referência
   stale, import quebrado, doc apontando pra path que não existe)
2. **Arquivo duplicado / superseded** com prova: dois arquivos
   cobrem o mesmo escopo, mais novo é melhor
3. **Doc velha errada** referenciada por skill / spec / CLAUDE.md
4. **Root script novo fora da allowlist** (algo apareceu no raiz
   do repo que não pertence)
5. **Artefato solto** que confunde humano / agente (e.g. `.skp`
   em `runs/` que parece deliverable mas não é)

Sem trigger = não fazer hygiene pass. PRs recentes (#73, #108)
convergiram em "preserve" depois de 3 audits seguidos = bikeshed.

## Como identificar arquivo obsoleto (PROVA, não palpite)

```bash
# 1. zero referências em código/teste/doc?
rg -n -- "<arquivo>" --type-add 'docs:*.md' --type docs

# 2. import quebra se remover?
python -c "import <module>"  # ou ruff/mypy

# 3. teste falha se remover?
mv <arquivo> /tmp/ && python -m pytest tests/ -q && mv /tmp/<arquivo> .
```

Sem prova = não tocar.

## Archive antes de delete

Default é **mover pra archive**, não deletar cego. Estrutura:

```
docs/archive/<YYYY-MM-DD>/<original_path>
```

Mantém git history acessível. Delete só depois de archive
sobreviver 1 release ciclo sem ninguém pedir de volta.

**Exceção** (delete direto): arquivos `.tmp_*`, `*.tmp`, `*.bak`,
`*~`, `*.swp`, `*.orig`, `*.rej`. Ver `.gitignore` § enforcement.

## Nunca remover

- Ground truth (`fixtures/`)
- Canonical artifacts (`artifacts/<plant>/` em estado promovido)
- Baselines de regressão (`docs/specs/_assets/`)
- Tests da contract suite (`tests/test_*`)

Mesmo que pareçam não-referenciados, podem ser pinned pelo gate.

## PR de cleanup separada

Hygiene é PR própria, não bundle com feature. Título prefixado
`chore:` ou `docs:`. Body explica trigger + evidência.

Exemplos do repo:

- PR #187: `chore: drop 7 zero-ref fixture orphans + requirements.txt + clean.pdf`
- PR #184: `chore: prune repo to minimal SKP-generation pipeline`
- PR #183, #182, #181, #180: cleanup passes incrementais

## Não fazer cleanup infinito

Stop conditions:

- Se PR de hygiene em sequência (>2) convergiu em "preserve",
  parar e mover pra outro trabalho
- Se reviewer pediu rollback de delete, archive em vez de
  re-deletar
- Se trigger original sumiu durante o trabalho, fechar PR sem merge

## TODO — validar contra repo

- [ ] Confirmar localização do `repo_health_gate.py` mencionado
      em `.gitignore` (`# Enforced by tools/repo_health_gate.py
      E001`) — pode ter sido movido em PR #184
- [ ] Listar allowlist de root scripts (se existir)
- [ ] Listar pasta de archive atual (`docs/archive/`?
      `_archive/`?)
