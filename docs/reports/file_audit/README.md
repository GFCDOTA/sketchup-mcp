# Auditoria por arquivo e revisão de imports — 2026-10-22

> Retrato datado. **Regenerar, não editar:** `python -m tools.navigation.file_audit --out docs/reports/file_audit`.
> Medido sobre `develop` após a T0.1 (#363) + as correções deste PR. Regras de classificação: docstring de `tools/navigation/file_audit.py`.

## Como ler

- **Um handoff por área** em [`areas/`](areas/): cada cômodo (`kitchen.md`, `living.md`, `bedroom.md`, …), `shared.md`,
  `rooms_core.md` (núcleo `tools/rooms/*.py`), `core.md`, `sketchup_executor.md`, `validation.md`, `tooling.md`,
  `interior.md`, `tests.md`, `docs.md`, `agent.md` e `repo.md`. Cada linha: arquivo, estado, por quê, quantos o importam, quantos o
  citam, último toque e próximo passo. Evidência e histórico (1.397 arquivos) aparecem resumidos por diretório.
- **Dados completos:** [`file_audit.v1.json`](file_audit.v1.json) (todas as linhas de código/doc; evidência e histórico só em contagem).
- **Nada foi apagado.** Arquivar ou remover exige decisão do Felipe (Hard Rule #4 do workspace).

## Números (2.251 arquivos)

| Estado | Arquivos | Leitura |
|---|---|---|
| EVIDENCE_OR_DATA | 1.129 | `artifacts/`, `fixtures/`, `references/`, `assets/`, `projects/` — protegidos por hash FP-042 |
| HISTORICAL | 268 | `docs/archive`, `docs/handoffs`, `docs/reports`, `artifacts/_archive`, logs do `.ai_bridge` |
| ACTIVE_IMPORTED | 227 | módulo importado por outro arquivo |
| TEST | 212 | suíte |
| AGENT_INSTRUCTION | 83 | `.claude/` e `.ai_bridge/` vivos (travados por `tests/test_claude_assets.py`) |
| CONFIG | 79 | JSON/YAML/TOML/perfis de especialista |
| DOC | 62 | documentação viva |
| SPEC | 54 | `docs/specs/` |
| PACKAGE_MARKER | 49 | `__init__.py` sem lógica |
| ACTIVE_ENTRYPOINT | 41 | CLI/script citado por código, CI, config ou skill |
| RUBY_JOB | 34 | `.rb` citado por código Python |
| LEGACY_FACADE | 7 | fachada/API legada (ver abaixo) |
| CLI_DOC_ONLY | 6 | CLI manual citada só em documentação (ver abaixo) |
| ORPHAN_CANDIDATE | **0** | nenhum módulo que ninguém importa nem cita |

## Revisão de imports

| Verificação | Antes | Depois | Trava |
|---|---|---|---|
| ciclos de import de topo (`tools`/`core`/`interior`) | 0 | 0 | `tests/test_file_audit.py` |
| import quebrado em código vivo (alvo `tools.*`/`core.*` inexistente) | 0 | 0 | idem |
| `import *` | 0 | 0 | idem |
| import não usado (ruff F401) em código vivo | **24** em 17 arquivos | **0** | idem (`ruff_checked` + lista vazia) |

23 foram removidos com `ruff --select F401 --fix` **arquivo por arquivo** depois de conferir que nenhum nome era re-export usado
por outro módulo ou teste (`monkeypatch` incluído). O 24º (`_wall_setup` em `tools/rooms/kitchen/layout.py`) é re-export de
contrato conferido por `tests/test_fp042_kitchen_bathroom_builder_ownership.py` via lista parametrizada — a suíte pegou e ele
voltou como import explícito com `noqa: F401` e o motivo no comentário. Erros de lint preexistentes nesses arquivos ficaram idênticos (contados antes e
depois). Imports quebrados restantes vivem só em scripts arquivados/evidência (`docs/archive/2026-07-11/tools/*`,
`artifacts/review/l2_fp042_20261019/tools/*`) — histórico, não se mexe.

## Obsoleto ou sem consumidor — decisão do Felipe

**CLI manual só citada em doc (6):** nenhum teste ou CI as executa, então podem ter apodrecido sem ninguém perceber.
Proposta: dar um teste de fumaça (vira ACTIVE) às que ainda servem e arquivar o resto.

| Arquivo | Citado em | Proposta |
|---|---|---|
| `tools/validation/visual_regression_gate.py` | FP-033, FP-047, handoff de jun | teste de fumaça (o gate PDF×BEFORE×AFTER segue em uso manual) |
| `tools/validation/wall_exact_match_gate.py` | migration guide | teste de fumaça ou arquivar |
| `tools/validation/generalization_gate.py` | migration guide | teste de fumaça ou arquivar |
| `tools/rooms/bathroom/capabilities/estudio_banheiro_scene.py` | migration guide | arquivar se o estúdio do banho (ago) não volta |
| `tools/rooms/bathroom/capabilities/render_banho_auto.py` | migration guide | idem |
| `ops/estudio-front/knowledge_ingest.py` | ADR 0002, spec do Inspector | manter se o painel `:8788` segue vivo |

**Fachadas/APIs legadas (7):** `tools/pdf_knowledge/{export_claude_context,search_pdf_index}.py` (fachadas FP-043/P4 de
`tools.knowledge.pdf.*`), `tools/oracle/{ollama_bridge,make_gpt_review_sheet}.py`, `tools/interior_studio/{interior_quality_scorecard,studio_log}.py`
e `tools/sketchup/disarm_autoruns.py`. Remoção segue a regra da FP-044 (consumidor explícito + data).

**Documentos com sistema removido citado como vigente (4):** receberam nota de histórico no topo neste PR —
`docs/SOFA_VRAY_TRACK.md`, `docs/vision_acl_discrimination_findings.md`, `tools/interior_studio/consult_gpt_bridge/README.md`,
`.claude/specs/generalize_any_plant.md`.

## Cômodos: o que cada módulo tem hoje

| Cômodo | Código vivo | Ruby | Só perfil + conhecimento |
|---|---|---|---|
| cozinha | 13 (fluxos L2: gabinete liso, Shaker; layout galley; placement FP-050) | 2 | — |
| sala | 18 (classes sofá/rack/mesas/poltrona, planner) | 10 | — |
| quarto | 10 (designer, layout, gates de cama/guarda-roupa/criado-mudo) | — | — |
| banheiro | 3 + 2 CLIs só documentadas | — | — |
| serviço | 1 (layout) | — | — |
| varanda, closet, home office, circulação | — | — | sim (correto: sem capacidade provada não se inventa brain) |
| shared | 29 (gabinete paramétrico, Shaker, sofá, cama, guarda-roupa, materiais, geometria) | 4 | — |

## Limites

Análise estática: chamada via `getattr`/string, import dinâmico e uso por ferramenta externa (atalho do Windows, Scheduled Task fora
do repo) não aparecem — por isso "sem consumidor" nunca vira remoção automática. Citação em documentação não conta como uso.
