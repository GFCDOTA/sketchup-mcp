# sketchup-mcp

[![ci](https://github.com/GFCDOTA/sketchup-mcp/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/GFCDOTA/sketchup-mcp/actions/workflows/ci.yml)

**Planta em PDF → modelo SketchUp (`.skp`) fiel à planta.** A partir de um `consensus.json` (paredes, aberturas e
cômodos em pontos de PDF) o projeto gera o shell (paredes extrudadas, portas/passagens em altura cheia, janelas
como aberturas 3D que **preservam peitoril e verga**), renders, relatório de geometria, mobília paramétrica opcional
e uma suíte de gates de fidelidade. O `.skp` é o entregável; o resto existe para provar que ele é fiel ao PDF.

| | |
|---|---|
| Linguagem / plataforma | Python 3.11+ · Ruby (SketchUp 2026 no Windows para qualquer coisa que abra o SketchUp) |
| Servidor MCP | sim: `tools/mcp_server` (FastMCP/stdio, 18 tools: 9 puras + 9 `su_*` que sobem o SketchUp) |
| Testes | Python puro, sem SketchUp; duas invocações por causa da escala (abaixo) |
| Licença | Proprietária |

> **Aprovado ≠ rodou.** Teste verde e CI verde provam o Python. O que o SketchUp real materializou está em
> [`artifacts/review/l2_fp042_20261019/`](artifacts/review/l2_fp042_20261019/README.md), com o que ficou **pendente**
> (aparência é sempre do Felipe: IMPROVED/SAME/WORSE nunca é automático).

---

## Comece por aqui

| Quero… | Vá para |
|---|---|
| entender onde cada coisa mora, e o que existe vs. o que ainda é previsto | [`docs/architecture/repository_map.md`](docs/architecture/repository_map.md) |
| achar um arquivo antigo que sumiu/mudou | [`docs/architecture/migration_guide.md`](docs/architecture/migration_guide.md) |
| ver o que **cada cômodo** tem (capacidades, prova, lacunas, arquivos) | [Módulos de cômodo](#módulos-de-cômodo) · [`tools/rooms/README.md`](tools/rooms/README.md) |
| o estado de **cada arquivo** (ativo, legado, só documentado, histórico) | [`docs/reports/file_audit/`](docs/reports/file_audit/README.md) |
| mexer num cômodo (exemplo completo: cozinha) | [`tools/rooms/kitchen/README.md`](tools/rooms/kitchen/README.md) |
| saber quem usa um arquivo antes de movê-lo | `python -m tools.navigation.consumers <caminho>` |
| ver o plano da reorganização (FP-043) e o estado dela | [relatório P8 (parcial)](docs/reports/FP-043_final_validation.md) · [spec de conclusão P3–P8](docs/specs/FP-043_remaining_execution_P3_P8.md) · [FP-043 original](docs/specs/FP-043_repository_navigation_and_room_specialists.md) · [mapa P0](docs/specs/FP-043_P0_map.md) |
| ver o plano de enxugar a raiz e as fachadas de `tools/` (FP-044) e o estado dela | [relatório final (parcial)](docs/reports/FP-044_final_validation.md) · [spec FP-044](docs/specs/FP-044_root_and_tools_consolidation.md) |
| saber o que ainda mora em `tools/*.py` e por quê | [`tools/PUBLIC_API.md`](tools/PUBLIC_API.md) |
| saber o que o SketchUp real já provou | [`artifacts/review/l2_fp042_20261019/README.md`](artifacts/review/l2_fp042_20261019/README.md) |
| as regras de quem edita (humano ou agente) | [`CLAUDE.md`](CLAUDE.md) → `.claude/` |

---

## O que mora na raiz

<!-- root-layout:begin -->

> Gerado por `python -m tools.navigation.rooms_index --write`; toda entrada versionada da raiz precisa de papel aqui.

| Entrada | Papel |
|---|---|
| `.ai_bridge/` | fio entre sessões (`HANDOFF.md`) e logs históricos de revisão/fidelidade |
| `.claude/` | instruções do agente: CLAUDE.md, rules por caminho, skills, agentes, memória |
| `.github/` | CI (4 checks obrigatórios) |
| `.impeccable/` | config que mantém DESLIGADO o hook de design do plugin impeccable neste projeto (D-008) |
| `artifacts/` | entregáveis canônicos (`artifacts/<planta>/`) e evidência (`artifacts/review/`) — protegidos por hash |
| `assets/` | texturas e recursos reutilizáveis |
| `core/` | domínio sem framework: escala, semântica espacial, schemas (`core/schemas/`), observabilidade |
| `docs/` | specs SDD (`docs/specs/`), mapa e guias (`docs/architecture/`), relatórios e handoffs datados, arquivo morto |
| `fixtures/` | entradas canônicas e sintéticas dos testes — protegidas |
| `interior/` | pacote do estúdio de interiores (planners, renderers, validators, class specs) — importado por várias ferramentas |
| `ops/` | painel do estúdio (`ops/estudio-front/`, :8788) — o Harness App aponta para ele; mover exige repontar (D-009) |
| `projects/` | fonte de cada projeto (`projects/planta_74/source/planta_74.pdf`) |
| `references/` | fontes e recipes de conhecimento (aulas SketchUp, referências de design) |
| `tests/` | suíte de regressão (marker `planta74_scale` separa a escala) |
| `tools/` | código: um módulo por cômodo em `tools/rooms/`, executor SketchUp, gates, navegação, MCP |
| `.dockerignore` | contexto do build do compose do RAG |
| `.gitattributes` | normalização de fim de linha |
| `.gitignore` | o que não versiona (`runs/`, scratch, caches) |
| `.mcp.json` | MCP de DESENVOLVIMENTO dos agentes (Context7, docs de libs externas); nao e runtime — ver `docs/engineering/` |
| `CLAUDE.md` | ponteiro para `.claude/CLAUDE.md` |
| `docker-compose.rag.yml` | Qdrant opcional do RAG (degrada para busca facetada se estiver desligado) |
| `pyproject.toml` | pacote, dependências (`[dev]` inclui ruff/pytest) e config de lint/teste |
| `README.md` | este arquivo |
| `uv.lock` | lock das dependências |

`runs/` existe só localmente (scratch ignorado pelo git).

<!-- root-layout:end -->

---

## Módulos de cômodo

<!-- rooms-index:begin -->

> Gerado por `python -m tools.navigation.rooms_index --write` (não editar à mão; o teste acusa divergência).
> Detalhe por cômodo: [`tools/rooms/README.md`](tools/rooms/README.md) · handoff por arquivo: [`docs/reports/file_audit/`](docs/reports/file_audit/README.md).

| Cômodo | Pasta | Papel | Capacidades (prova) | Lacunas | Fragmentos | Arquivos (py/rb) |
|---|---|---|---|---|---|---|
| Cozinha | [`tools/rooms/kitchen/`](tools/rooms/kitchen/) | planeja e constrói | 5 L2, 1 L1, 1 sem prova | 3 | 5 | 29 (18/2) |
| Sala | [`tools/rooms/living/`](tools/rooms/living/) | planeja e constrói | 3 L1 | — | 3 | 42 (22/10) |
| Quarto | [`tools/rooms/bedroom/`](tools/rooms/bedroom/) | planeja e constrói | 4 L1 | — | 4 | 21 (14/0) |
| Banheiro | [`tools/rooms/bathroom/`](tools/rooms/bathroom/) | planeja e constrói | 2 L1 | — | 3 | 14 (8/0) |
| Serviço | [`tools/rooms/service/`](tools/rooms/service/) | planeja e constrói | 1 L1 | — | 1 | 6 (2/0) |
| Closet | [`tools/rooms/closet/`](tools/rooms/closet/) | reusa outro cômodo (bedroom) | — | 1 | 1 | 5 (1/0) |
| Home office | [`tools/rooms/home_office/`](tools/rooms/home_office/) | reusa outro cômodo (bedroom) | — | 1 | 1 | 5 (1/0) |
| Varanda | [`tools/rooms/balcony/`](tools/rooms/balcony/) | só consultivo | — | 1 | 1 | 5 (1/0) |
| Circulação | [`tools/rooms/circulation/`](tools/rooms/circulation/) | só valida | 1 L1 | — | 1 | 5 (1/0) |
| Compartilhado | [`tools/rooms/shared/`](tools/rooms/shared/) | peças usadas por ≥ 2 cômodos | 2 capacidades | — | — | 42 |

<!-- rooms-index:end -->

---

## Rodar

`uv.lock` é a fonte reproduzível das dependências. Antes de trabalhar numa cópia nova, ou depois de mudança em
`pyproject.toml` / `uv.lock`, sincronize o ambiente canônico:

```bash
uv sync --locked --extra dev --extra mcp

# testes (Python puro). PT_TO_M é lido UMA vez por processo: duas invocações, uma por escala.
uv run --no-sync python -m pytest tests/ -q -m "not planta74_scale"
PT_TO_M=0.0259 uv run --no-sync python -m pytest tests/ -q -m planta74_scale      # PowerShell: $env:PT_TO_M="0.0259"; …

# gates determinísticos (CI / pre-commit)
uv run --no-sync python -m tools.validation.run_deterministic_gates --fixture planta_74
uv run --no-sync python -m tools.validation.run_deterministic_gates --fixture quadrado

# servidor MCP (stdio) e o handshake de prova
uv run --no-sync python -m tools.mcp_server.smoke
uv run --no-sync python -m tools.mcp_server.stdio_check
```

O CI roda `uv lock --check` e instala somente a resolução travada pelo `uv.lock`; um `pyproject.toml`
alterado sem regenerar o lock falha antes das suítes.

Para **gerar `.skp`** use as tools `su_*` do MCP (`su_build_shell`, `su_furnish`, `su_render`, `su_apply_edits`,
`su_inspect`, `su_render_vray`): cada uma sobe uma instância própria do SketchUp, grava em `runs/` e só fecha o PID
que ela mesma abriu. As CLIs equivalentes seguem funcionando (`python -m tools.sketchup.shell.build_plan_shell_skp <consensus> --out runs/…`).

> **Nenhum código rastreado encerra o SketchUp por nome.** As CLIs de materialização (`furnish_apartment`, `place_layout_skp`, `material_review`,
> `bake_theme_skp`, `kitchen_vray`, `render_banho_vray`, `render_room.ps1`, `sofa_premium_harness`, `bedroom_designer`, `interior/renderers/*`) fecham
> **só o PID que elas abriram** (`terminate_owned` / `close_owned`); um teste varre o repositório inteiro
> (`tests/test_fp043_no_kill_by_name_scan.py`). Mesmo assim, uma janela sua com trabalho não salvo continua sua: prefira as tools `su_*`.

`runs/` é scratch (ignorado pelo git). O `.skp` canônico é `artifacts/planta_74/planta_74.skp`; evidências
promovidas ficam em `artifacts/review/<…>/`. Nunca grave sobre `fixtures/` nem `artifacts/` por job automático.

---

## Como o pedido vira `.skp`

```
pedido (humano ou agente)
  → tools/mcp_server/server.py        18 tools registradas (protocolo, sem lógica de domínio)
  → tools/sketchup/jobs.py            verbos su_*: valida entrada, escolhe destino em runs/
  → tools/sketchup/batch.py + process.py   sobe SketchUp próprio (-RubyStartup), lê o resultado em JSON
  → Ruby: tools/sketchup/ruby/*.rb  (jobs MCP)  e  tools/sketchup/{shell,furnish,inspect,vray}/*.rb  (build do shell, mobília, inspeção, vray)
  → .skp + renders em runs/<planta>/mcp/…   → promote_canonical → artifacts/<planta>/

planejamento do cômodo (antes do Ruby):
  consensus.json → tools/room_type.py → tools/rooms/dispatch.py → brain do cômodo (tools/rooms/<room>/)
  → caixas/peças → tools/sketchup/furnish/place_layout_skp.rb
```

Mapa completo, com o estado de cada pasta, em [`docs/architecture/repository_map.md`](docs/architecture/repository_map.md).

---

## Gates de fidelidade

**Determinísticos** (rápidos; `tools/validation/run_deterministic_gates.py`): paredes e posição vs consensus
(`wall_exact_match_gate`, `position_fidelity_gate`), guarda-corpo vs mureta (`railing_exact_match_gate`,
`parapet_not_railing_fallback_gate`), aberturas (`opening_audit`, `opening_aperture_audit`, `opening_host_audit`,
`door_swing_audit`), sobreposição de paredes e enquadramento (`wall_overlap_audit`, `render_bbox_audit`), e os gates
de mobília (`furniture_overlap_gate`, `circulation_gate`, `geometry_sanity`).

**Visual** — a única decisão humana: `run_skp_visual_review`, `visual_regression_gate`, `negative_dogfood`. Um teste
verde, um exit 0 ou um score ajustado **não** são prova visual.

O oráculo GPT-Docker (`:8899`) está **dormente**; o cockpit antigo (`:8765`) foi **removido** em 2026-07-24. O veredito
visual é dado pelo Felipe, direto no chat.

---

## Consensus (informal)

```json
{
  "wall_thickness_pts": 5.4,
  "walls": [{"id": "w_bottom", "start": [100, 100], "end": [213.684, 100], "thickness": 5.4, "orientation": "h"}],
  "rooms": [{"id": "r_main", "name": "QUADRADO", "polygon_pts": [[102.7,102.7],[210.984,102.7],[210.984,210.984],[102.7,210.984]]}],
  "openings": [{"id": "win_south", "wall_id": "w_bottom", "kind_v5": "window", "center": [156.842, 100.0],
                "opening_width_pts": 30.0, "geometry_origin": "svg_segments"}],
  "soft_barriers": []
}
```

`kind_v5` decide **como** carvar: `interior_door` / `interior_passage` / `glazed_balcony` → 2D em altura cheia;
`window` → abertura 3D pós-extrusão (preserva peitoril e verga). `geometry_origin` decide **se**: `svg_arc` /
`svg_segments` / `human_annotation` carvam; `wall_gap` não (o vão já está nos dados da parede).

---

## Regras que não se quebram

1. **Nunca inventar geometria.** Se não está no `consensus.json`, não entra no `.skp`.
2. **Nunca abrir janela em altura cheia.** Janela mantém massa de parede abaixo do peitoril e acima da verga.
3. **Nunca alterar `fixtures/quadrado/` ou `fixtures/planta_74/`** sem aprovação humana explícita (a suíte fixa contra elas).
4. **Nunca `push` direto em `main`.** Branches a partir de `origin/develop`; PR só com CI verde.
5. **`--mode headless` é só CI.** Local usa `interactive` (o SketchUp fica aberto para inspeção).
6. **`runs/` é scratch.** Evidência é promovida; nunca versionada a partir de `runs/`.
7. **Nunca fechar SketchUp por nome** e nunca sobrescrever `.skp`, render ou referência aprovada: edição sai sempre em arquivo novo.

Contexto operacional completo para agentes: `.claude/` (`CLAUDE.md`, `memory/`, `specs/`, `skills/`).
