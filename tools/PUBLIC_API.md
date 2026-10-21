# API pública estável de `tools/` (FP-044 / F6)

Estes módulos de `tools/*.py` **não** são removidos pela FP-044: há consumidor **fora** deste repositório que importa o
caminho antigo. Cada um é uma fachada que só delega (`sys.modules` aponta para o dono — `tools.X is <dono>`); a lógica
vive só no dono. Teste: `tests/test_fp044_tools_facades.py`.

## Públicos (consumidor: `apps/harness-app`, outro repositório)

| Caminho estável | Dono (implementação única) | Semântica |
|---|---|---|
| `tools.furnish_apartment` | `tools.orchestration.furnish_apartment` | mobiliar a planta (`collect_boxes`, `CONSENSUS`, CLI) |
| `tools.geometry_sanity` | `tools.validation.geometry_sanity` | gate de sanidade geométrica |
| `tools.furniture_overlap_gate` | `tools.validation.furniture_overlap_gate` | gate móvel-sobre-móvel |
| `tools.finding_router` | `tools.orchestration.correction.finding_router` | roteia finding tipado para o dono |
| `tools.circulation_gate` | `tools.validation.circulation_gate` | gate de circulação |
| `tools.correction_loop` | `tools.orchestration.correction.correction_loop` | loop de correção fechado |
| `tools.spatial_model` | `tools.rooms.shared.spatial_model` | modelo espacial (laje/vão por cômodo) |
| `tools.room_type` | `tools.rooms.shared.room_type` | classificação do tipo de cômodo |

Política (D-010): ficam enquanto o harness importar estes caminhos. Aposentar exige primeiro um PR **no harness**
repontando para o dono; só então uma spec futura remove a fachada.

## D-011 — encerrada (FP-045/F2, 2026-10-21)

O Inspector do harness lia `tools/{reference_db,rag_embed_backend,ollama_bridge,run_deterministic_gates}.py` em tempo de
execução. `GFCDOTA/harness-app#17` repontou o catálogo para os donos (`tools/knowledge/*`, `tools/oracle/ollama_bridge.py`,
`tools/validation/run_deterministic_gates.py`) e as 4 fachadas foram removidas. Quem importava `tools.<nome>` deve usar o dono.

## Retidos por decisão do Felipe

`tools/furnish_plan.py` (D-003) e `tools/trace_view.py` (D-004) — não são fachadas; ficam até a decisão.
