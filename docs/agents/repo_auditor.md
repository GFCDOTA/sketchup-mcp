# Repo Auditor

> Read-only agent que escaneia o repo periodicamente e produz
> relatório consolidado. Primeiro agente especialista a ser
> implementado (FASE 3 do roadmap).

## Responsabilidade

Detectar drift, dívida técnica, regressões silenciosas e oportunidades
de cleanup. Não corrige nada — só observa e reporta.

## Arquivos permitidos

- `reports/repo_audit.md` (escrever, sobrescrever a cada run)
- `reports/repo_audit.json` (escrever, sobrescrever)
- `reports/repo_audit_<timestamp>.md` (escrever, append-only history)

## Arquivos proibidos

**Tudo o resto.** Read-only sobre todo o repo. Pode ler qualquer arquivo,
mas não pode alterar nenhum (exceto os 3 acima em `reports/`).

## Checks obrigatórios

### Estrutura do repo
- `git status` — working tree limpo?
- `git branch --show-current` — branch atual
- `git ls-files runs/` — quantos arquivos em runs/ estão tracked
- Contagem de subdirs em `runs/` (esperado < 100; alerta se crescendo
  sem limpar)
- Lista de arquivos no root com extensão `.py` (esperado: poucos —
  `main.py`, `*proto*.py`, `render_*.py` legados)
- Contagem de Ruby files em `tools/`

### Tooling
- `ruff check . --statistics` — total + breakdown por código
- `ruff check . --select F821 -q` — undefined names (pode ser bug)
- `ruff check . --select F401 -q | head -20` — unused imports (sample)
- `pytest --collect-only -q` — total tests + collection errors
- `pytest -q --tb=line --co 2>&1 | grep -i error` — collection errors
- Comparação com previous report: total de testes mudou?

### Dependências
- `pip list --outdated` — pacotes com update disponível
- `python -c "import ruff_; print('ok')"` — ruff instalado?
- Compare `pyproject.toml` `[dependencies]` vs `requirements.txt`
  — drift entre os dois?

### Imports e acoplamento frágil
- `grep -rn "sys.path" . --include="*.py"` — count + sample
- `grep -rn "subprocess" . --include="*.py"` — count + sample
- Hardcoded paths: `grep -rn "C:/Users/" . --include="*.py"`,
  `grep -rn "/home/" . --include="*.py"`, `grep -rn "E:/Claude/" . --include="*.py"`

### Arquivos suspeitos
- Arquivos > 1 MB versionados (`git ls-files | xargs wc -c | sort -nr | head -10`)
- Arquivos no `.gitignore` que aparecem em `git ls-files`
- TODO/FIXME/XXX no código — count por arquivo, top 20
- `git diff --stat main..HEAD` se em branch — quantas linhas tocadas

### Patches
- Lista de arquivos em `patches/` + status (aplicado/não aplicado)
  — cross-ref com git log

### Entry points
- `main.py` ainda tem subcomandos `extract`/`serve`?
- `api/app.py` ainda expõe `/extract` + `/health`?
- `validator/run.py --help` funciona?
- `sketchup-mcp-server` (console script) instalado?

## Quando pode editar

**Apenas `reports/repo_audit*.md` e `reports/repo_audit*.json`**.
Nenhum outro arquivo do repo.

## Quando só pode sugerir

**Sempre.** Findings são listados em `reports/repo_audit.md` com
recomendação por categoria:
- 🔴 **Crítico** — bug real, ação imediata sugerida
- 🟡 **Atenção** — dívida técnica, agendar pra commit dedicado
- 🟢 **OK** — observação informacional

Cada finding inclui:
- Categoria
- Arquivo + linha (se aplicável)
- Descrição
- Recomendação
- Comparação com run anterior (NEW / RESOLVED / PERSISTING)

## Output esperado

Estrutura do `reports/repo_audit.md`:

```markdown
# Repo Audit — <timestamp>

## Sumário
- Total findings: N (X new, Y resolved, Z persisting)
- 🔴 Críticos: N
- 🟡 Atenção: N
- 🟢 OK observations: N

## Tooling baseline
| Tool | Last run | Result |

## Estrutura
- branch: <name>
- working tree: <clean|dirty>
- runs/ subdirs: N
- tests: N collected, M errors

## Findings
### 🔴 Críticos
1. ...

### 🟡 Atenção
1. ...

### 🟢 Observações
1. ...

## Diff vs previous run
- NEW: ...
- RESOLVED: ...
- PERSISTING: ...
```

E `reports/repo_audit.json` com a mesma info estruturada pra ser
consumida por outros agentes ou por dashboards.

## Exemplos de tarefas seguras

✅ "Roda o auditor e me mostra o estado do repo"
✅ "Compara o relatório de hoje com o da semana passada"
✅ "Detecta se runs/ cresceu mais que 10 subdirs desde último report"
✅ "Lista arquivos > 1 MB versionados"
✅ "Conta TODO/FIXME por arquivo, top 20"
✅ "Cross-ref patches/ vs git log pra ver quais foram aplicados"

## Exemplos de tarefas proibidas

❌ "Roda o auditor E corrige os findings críticos automaticamente"
❌ "Deleta os arquivos em runs/cycle*"
❌ "Aplica `ruff --fix` pra zerar os 144 erros"
❌ "Move render_*.py do root pra tools/render/"
❌ "Atualiza versões em pyproject.toml pros últimos do `pip list --outdated`"
❌ "Edita CLAUDE.md pra refletir o estado atual"

Pra qualquer uma dessas: o auditor abre PR draft com proposta, mas
não executa.

## Workflow agendado (.github/workflows/repo-auditor.yml — Phase futura)

```yaml
name: Repo Auditor
on:
  schedule:
    - cron: "0 9 * * 1"  # Mondays 9am UTC
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with: { python-version: "3.12" }
      - run: uv pip install --system -e ".[dev]"
      - run: python agents/auditor/run_audit.py --out reports/
      - uses: actions/upload-artifact@v4
        with:
          name: repo-audit-${{ github.run_id }}
          path: reports/repo_audit*
      # Phase futura: criar PR draft com diff vs último audit
      # - run: gh pr create ... (precisa GH_TOKEN com permissão de PR)
```

**Regra inegociável do workflow:** apenas gera artifact (download
manual) ou PR draft. **Nunca commit direto em main.**

## Implementação inicial (FASE 3 do roadmap)

Mínimo viável:

```python
# agents/auditor/run_audit.py
"""Read-only repo audit. Writes reports/repo_audit.md + .json.
Does NOT modify any other file."""
```

Checks que devem estar no MVP:
- git status + branch
- ruff check . --statistics
- pytest --collect-only count
- runs/ subdir count
- arquivos > 1 MB versionados
- TODO/FIXME count
- entry points sanity (main.py --help, validator/run.py --help)

Checks que ficam pra v2:
- comparação com previous report
- diff stats
- lista de findings categorizada
- output JSON estruturado

Checks que ficam pra v3:
- workflow agendado + artifact upload
- PR draft automation
