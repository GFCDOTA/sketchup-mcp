# Matriz de dependências externas × documentação (DOC-EXT) — 2026-10-23

> Retrato datado (reconciliação de dependências #393). `uv.lock` foi regenerado a partir do `pyproject.toml` e passa a ser
> a fonte reproduzível; o CI executa `uv lock --check` + `uv sync --locked`. Valores antigos do venv abaixo são o snapshot
> pré-sync que revelou o drift e devem desaparecer após `uv sync --locked --extra dev --extra mcp`. Cobertura do Context7 medida
> com `resolve-library-id` no servidor 4.4.3. Política: `external-documentation-policy.md`.

| Módulo | Dependência | Versão (lock / venv) | Context7 | Risco atual | Benefício esperado |
|---|---|---|---|---|---|
| `tools/sketchup/**/*.rb`, `tools/rooms/shared/cabinet/ruby/` | SketchUp Ruby API | 26.0.429 (runtime, `SketchUp.exe`) | `/sketchup/ruby-api-docs` — **sem versão** | alto: API grande, `rescue nil` silencioso no shell (R-07 da F0); só L2 prova | médio: conferir assinatura/semântica (`add_face`, `pushpull`, `start_operation`) antes de escrever Ruby; versão sempre confirmada no L2 |
| `tools/mcp_server/` | `mcp` (FastMCP) | **1.28.1 / 1.28.0 pré-sync** (lock autoritativo) | `/modelcontextprotocol/python-sdk/v1.28.0` — **exata** | médio: 2.0 quebrou o import (pin `<2.0` no pyproject) | alto: doc da tag usada; evidência `evidence/2026-10-23_mcp.json` |
| `tools/validation/`, `tools/rooms/**` (geometria) | `shapely` / GEOS | 2.1.2 / 2.1.2 (GEOS 3.13.1) | `/shapely/shapely` — **sem versão** (main) | médio: `buffer`/`prepare`/vetorizado mudam entre 2.0 e 2.1 | médio: conferir no runtime local; evidência `evidence/2026-10-23_shapely.json` |
| `tools/navigation/baseline_probes.py`, geometria | `numpy` | 2.4.6 / 2.4.6 | `/numpy/numpy` (v2.3.1, v2.1.3) — mais próxima | baixo | baixo |
| `tools/knowledge/pdf/`, extração | `pypdfium2` | 4.30.0 / 4.30.0 | sem versão | médio: API mudou na 4.x | médio |
| renders, PNG | `Pillow` | 11.3.0 / 11.3.0 | `/python-pillow/pillow` (12.x) — versão diferente | baixo | baixo |
| plots de evidência | `matplotlib` | **3.11.0 / 3.10.9 pré-sync** (lock autoritativo) | sem versão | baixo | baixo |
| `tests/` | `pytest` | 8.4.2 / 8.4.2 | `/pytest-dev/pytest` (8.3.4, 9.0.0) — mais próxima | baixo | médio (markers/conftest) |
| `tests/*properties*` | `hypothesis` | **6.170.8 / 6.170.8** | sem versão | baixo: `[dev]` e `uv.lock` agora concordam | médio (`settings`, `derandomize`) |
| `tools/rooms/specialist_fragments.py`, gates de schema | `jsonschema` | 4.26.0 / 4.26.0 | `/python-jsonschema/jsonschema` (v4.25.1) — mais próxima | baixo | baixo |
| lint | `ruff` | **0.15.15 / 0.15.14 pré-sync** (lock autoritativo) | `/astral-sh/ruff` (v0.4.10 — antiga) | baixo | baixo |
| `tools/sketchup/process.py`, `batch.py` | `subprocess`/`tasklist` (stdlib + Windows) | Python 3.12 / Windows 11 | stdlib fora do Context7 → doc oficial Python | médio: fechar só o próprio PID | baixo |
| `tools/sketchup/jobs.py` `render_vray` | V-Ray (`vray.exe`, export Ruby) | runtime local | sem índice útil | alto: só L2 | baixo |
| automação de PR | GitHub CLI `gh` | runtime | `/cli/cli` — sem versão | baixo | baixo |
| oráculo/LLM local | Ollama API | runtime `:11434` | `/ollama/ollama` — sem versão | baixo (fora do caminho P0) | baixo |

## Follow-ups (não feitos nesta PR)

1. **Resolvido em #393:** `uv.lock` regenerado (inclui `hypothesis` 6.170.8), CI passa a validar `uv lock --check` e
   instalar com `uv sync --locked`. Checkouts locais antigos devem rodar `uv sync --locked --extra dev --extra mcp`;
   o venv nunca prevalece sobre o lock.
2. SketchUp Ruby API sem versão no Context7: toda mudança Ruby segue exigindo L2 no 26.0.429; registrar evidência `unversioned`
   com o caso L2 como verificação.
3. `rescue nil` do builder do shell (R-07 da F0): quando for tratado (F4), registrar a evidência da API (`Entities#add_face`).
