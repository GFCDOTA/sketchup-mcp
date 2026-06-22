# Project-Memory RAG (#2) — o "cérebro do arquiteto"

`tools/project_memory_db.py` — memória de longo prazo do PROJETO indexada para
**busca semântica**. Deixa os agentes (arquiteto / PM / lead) consultarem *"o que
já fizemos e aprendemos"* antes de decidir, em vez de depender do relay verbal.

## Dois RAGs distintos (não confundir)

| | RAG #1 — `reference_db.py` | RAG #2 — `project_memory_db.py` (este) |
|---|---|---|
| Sabe | referências visuais de design (cards, temas, renders) | história/decisões/lições do projeto |
| Busca | metadado exato (room/theme/kind) | **semântica** (embeddings + cosseno) |
| Store | `artifacts/reference_lab/reference.db` | `.ai_bridge/project_memory.db` |

## Stack (local-first, zero infra nova)

- **embeddings**: Ollama `nomic-embed-text` (768d) via `urllib` — sem `requests`.
  Requer `ollama pull nomic-embed-text`.
- **store**: SQLite, embedding em BLOB `float32`. Sem `sqlite-vec`, sem Qdrant.
- **busca**: cosseno em `numpy` (corpus pequeno, ~200 chunks). Brute-force é
  instantâneo nessa escala; só vale índice vetorial acima de ~100k chunks.

## Uso

```bash
PY=.venv/Scripts/python.exe
$PY tools/project_memory_db.py index            # ingere o corpus deste checkout
$PY tools/project_memory_db.py index --rebuild  # dropa e reconstrói do zero
$PY tools/project_memory_db.py search "como julgamos a proporção do sofá?" --k 6
$PY tools/project_memory_db.py stats
```

O `.db` é índice **DERIVADO e reconstruível** (gitignored). Idempotente: só
reembeda arquivo que mudou (dedup por hash de conteúdo).

## O que é indexado / o que NÃO é

**Indexa** (alto valor semântico): `HANDOFF*.md`, `fidelity/verdicts/*.md`,
`knowledge/*.md` (axiomas de gosto do Felipe), `lessons/*.md`, planos/backlog,
`interior_consult/cycles.jsonl` + respostas, `research/*.json` (ergonomia),
`learning_patches/*.json`, `interior_cycles/*.json`, `marcos.json`.

**NÃO indexa** (ruído operacional sem sinal): `audit/audit.jsonl` (heartbeat),
`noc/queue+actions.jsonl`, `logs/events.jsonl`, `questions/`+`responses/` legados.

## Invariante de segurança

RAG é **CONSULTIVO**. Os gates determinísticos continuam sendo a verdade. Esta
base responde *"o que já aconteceu?"*, nunca *"está certo?"*.

## Roadmap (próximos passos — não nesta fatia)

- **STEP 4 — write-back curado**: veredito PASS do `:8765` → memória, com gate
  `PENDING → Felipe aprova → APPLIED` (anti lixo-entra-lixo-sai). Detector de
  contradição antes de servir.
- **Endpoint `:8765`**: expor `/api/memory/search` (read-only) no `server.py`
  pra os agentes consultarem por HTTP. Hoje a busca é via CLI.
- **Busca híbrida**: somar BM25 (SQLite FTS5) ao cosseno se a recuperação por
  keyword exata fizer falta.
