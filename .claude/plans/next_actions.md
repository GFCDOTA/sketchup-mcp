# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-05-28. Decai rápido.

## Fila atual

### 1. Mergear `feat/skp-proof-of-progress-gate`

- **Objetivo:** Constitution #8 + spec + skill + template
  cravados em `develop`
- **Por quê:** Garantir que toda PR futura de fidelidade gere
  evidência human-facing automaticamente, sem o humano cobrar
- **Status:** PR em criação após este commit
- **Critério de parada:** PR mergeada

### 2. (follow-up) Tool `tools/check_skp_proof_of_progress.py`

- **Objetivo:** Implementar o gate sugerido em
  `specs/skp_proof_of_progress_gate.md` § "Testes / gates
  automáticos"
- **Por quê:** O texto sozinho depende de reviewer humano cobrar;
  o gate executável protege automaticamente
- **Arquivos prováveis:** `tools/check_skp_proof_of_progress.py`
  + `.github/workflows/check-skp-proof-of-progress.yml` (se CI
  for adotada) + teste cobrindo a tool
- **Validação esperada:** PR de builder sem artifact review é
  bloqueada automaticamente
- **Critério de parada:** tool + CI verde rodando em PR de teste
- **NÃO INICIAR** sem ok explícito do humano — categoria 5
  pendente

### 3. (follow-up) Aplicar o gate na próxima PR de builder

- **Objetivo:** Exercitar o fluxo em uma PR real de melhoria
  (e.g. próximo fix em wall canonicalisation ou opening routing)
- **Por quê:** Dogfooding da regra antes de virar obrigação cega
- **Critério de parada:** primeiro `artifacts/review/<plant>/<cycle>/`
  com `regression_summary.md` mergeado

### 4. (follow-up) Validar Python install local do user

- **Objetivo:** Confirmar com o humano se Python 3.12 oficial em
  `AppData/Local/Programs/Python/Python312/` foi removido
  intencionalmente, ou se precisa reinstalar
- **Por quê:** Hoje só funciona via `uv`-managed Python. Outros
  agentes/sessões podem encontrar erro 0x80070002
- **Critério de parada:** decisão do humano (reinstalar / aceitar
  uv-only) + memory atualizada

### 5. (follow-up) Adicionar matplotlib ao `pyproject.toml`

- **Objetivo:** `tools/diagnose_wall_stubs.py` (PR #193) importa
  matplotlib mas não está em `pyproject.toml [project.dependencies]`
- **Por quê:** Quebra `pytest --collect` em ambientes sem
  matplotlib pré-instalado
- **Arquivos prováveis:** `pyproject.toml` (1 linha)
- **Validação esperada:** `uv pip install -e ".[dev]"` numa venv
  fresh deixa o pytest verde sem `uv pip install matplotlib`
  manual
- **Critério de parada:** PR mergeada

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor
claro pro produto** (gerar/revisar `.skp` fiel). Não inventar
trabalho cosmético. Ver `specs/product_goal.md` § "Critérios de
avanço real" e `memory/operational_rules.md` § "Continuar
automaticamente vs parar" (5 categorias).
