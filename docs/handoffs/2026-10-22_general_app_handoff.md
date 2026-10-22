# HANDOFF — sketchup-mcp: estado geral da app (2026-10-22)

> Fio da meada para retomar sem arqueologia. Snapshot datado: **não reescrever**; o próximo handoff vai num arquivo novo
> e o topo de `.ai_bridge/HANDOFF.md` passa a apontar para ele. Números medidos em `develop@a87d2ad` (merge do #355).

- **Data / sessão:** 2026-10-22 · sessão Claude Code `1f8cebec`
- **Repo / app:** `apps/sketchup-mcp` (GFCDOTA/sketchup-mcp)
- **Status geral:** **GREEN** para avançar no core de construção · **YELLOW** em aparência (nada aprovado em L3) ·
  bloqueios humanos listados em §6

## 1. Objetivo atual

Gerar a planta_74 em `.skp` fiel ao PDF **e** mobiliá-la com móveis paramétricos de verdade, peça a peça, cada técnica
com fonte revisada e prova no SketchUp real. A arquitetura (shell, aberturas) está estável desde junho; o trabalho de
agora é o **core de construção dos componentes** — hoje só o gabinete da cozinha está no padrão novo.
Plano de execução: [`docs/specs/construction_core_microphases.md`](../specs/construction_core_microphases.md).

## 2. Branch atual

- **Base:** `origin/develop` @ `a87d2ad` (merge do #355). `main` recebe `develop` só via merge de release.
- **PRs desta sessão:** #358 (mergeado), #360 (instruções do agente; CI no momento deste handoff), este PR (handoff +
  estado), e o do mapa de microfases (`docs/specs/construction_core_microphases.md`).
- **Drafts alheios:** nenhum aberto depois de #346/#347/#355/#359 serem mergeados em 2026-10-22.
- **Worktrees em `E:/Claude/worktrees/`:** `w-prov` (esta sessão), `w-fp047` (`feat/fp047-f3-gates`, já mergeada),
  `w-gates` (`docs/fp044-d007-diagnosis`, já mergeada). Conferir `git worktree list` antes de remover — Hard Rule #2 do workspace.

## 3. Arquitetura em uma tela

```
consensus (PDF→humano) ─► tools/sketchup/shell ─► planta_74.skp (canônico, estável)
pedido {value,unit,origin} ─► tools/rooms/specialists.plan()  (perfil do cômodo + allowlist + binding→capability)
        └─► tools/rooms/<cômodo>/capabilities/<x>_flow.run_request ─► gates de domínio ─► job Ruby (cópia em runs/)
                 └─► salvar → fechar PID → reabrir noutro processo → inspecionar → verificar (L2) ─► evidência + digests
conhecimento: references/sketchup/knowledge/*.json (recipe + fonte + trecho + human_review) — nunca autoriza execução
regressão: tools/validation/room_regression*.py (FP-047: contrato, snapshot, diff, gates antes×depois)
```

Módulos por cômodo (`tools/rooms/`): `kitchen` (19 arquivos, único com fluxo L2 completo), `living` (39, builders de
classe), `bedroom` (16), `bathroom` (10), `service` (5) e `balcony`/`closet`/`home_office`/`circulation` (só perfil +
conhecimento). `shared/` (36) concentra o que dois cômodos usam. Ownership e imports cruzados travados no CI (FP-042/043/044).

## 4. Decisões tomadas (e por quê)

| Decisão | Por quê |
|---|---|
| D46-09 opção C: revisão humana do trecho 03:13–04:29 de `yt-cabinet-tips-2021` promove a Shaker | única fonte inspecionada; Felipe confirmou os 4 itens (2026-10-21) |
| `human_review` vale para **uma recipe e um trecho** (#358) | defeito real: outra recipe do mesmo vídeo herdava a revisão |
| Prova velha nunca é reaproveitada (R-18): revogar → L2 em commit limpo → restaurar | digest amarra evidência ao código; ver skill `capability-l2-proof` |
| Veredito visual só do Felipe, no chat; GPT-Docker dormente; NOC `:8765` removido | veredito automático é comprovadamente não confiável (negative_dogfood) |
| CLAUDE.md < 200 linhas, estado vivo fora dele, regras por caminho em `.claude/rules/` (#360) | doc oficial de memória; os 17 imports antigos nunca carregavam |
| FP-052: nenhum móvel vai a montagem/posição final sem `reference_target.v1` aprovado por peça | o golden do ambiente não aprova frente, gaveta ou armário individual |

## 5. Testes rodados + evidências

- **Suíte:** `-m "not planta74_scale"` → 2555 passed, 30 skipped, 1 xfailed · `PT_TO_M=0.0259 -m planta74_scale` → 146 passed
  (medido no branch do #360 sobre `a87d2ad`). Skips = SketchUp/Qdrant/Ollama ausentes ou artefato não gerado — não são prova L2.
- **CI obrigatório:** pytest 3.11, pytest 3.12, deterministic fidelity gates, mcp server smoke+stdio.
- **Capacidades com L2 vigente (5):** `kitchen.layout.galley`, `shared.cabinet.parametric`, `kitchen.cabinet.plain-fronts`,
  `kitchen.cabinet.shaker-door` (refeita no #358, commit `4023b78`, 13/13), `shared.cabinet.front.shaker`. As outras 13 são L1/UNTESTED.
- **Evidência humana pendente:** pacote L3 da Shaker em `artifacts/review/fp046/l3_package/` (#356) — `PENDING_HUMAN`.
- **Veredito visual:** nenhum `APPROVED` no catálogo (18 × `NOT_REVIEWED`).

## 6. Pendências

**Esperando o Felipe (só ele destrava):**
1. Veredito L3 da porta Shaker (`APPROVED` / `CHANGES_REQUESTED`) — pacote do #356.
2. Revisão de trechos de vídeo para as próximas técnicas (checklists prontos no mapa de microfases §5): tampo
   (07:09–08:53 de `yt-cabinet-tips-2021`), caixa de gaveta (dentro de 21:20–39:23 de `yt-kitchen-joinery-2024`), recorte de cuba.
3. Curadoria do alvo `planta_74.r004.kitchen_base_001` (FP-052 T2; hoje `DRAFT_BLOCKED`, inclusive a divergência LINEAR × Galley em L).
4. D-007 (vão de mobiliar = laje): a correção muda a SUITE 02 → precisa de decisão + L3.
5. D-001..D-005 (referência do quadrado, Dockerfile morto, `furnish_plan`, `trace_view`, `set_clipboard_image`), D-008/D-009 (FP-044 F4/F5).

**Falta fazer (técnico, sem bloqueio humano):** ver a fila T0 do mapa de microfases — bug de scratch do
`cabinet.sketchup.inspect`, gap planner (FP-051 P1), gate de posicionamento nos dois fluxos da cozinha (FP-051 P4), contrato de
frames +Y/−Y (FP-048 F1–F2).

## 7. Riscos

- **Duas gerações de builder.** Gabinete/Shaker: peça a peça, 0 constante geométrica embutida, L2. Guarda-roupa, cama,
  criado-mudo, sofá, rack e mesas: 10–95 literais por arquivo, cores RGB fixas, guarda-roupa com corpo em **um bloco**.
  Melhorar "detalhe" nesses sem migrar o contrato só aumenta dívida.
- **Toda mudança em símbolo provado custa um L2** (às vezes de 2–3 capacidades). Planejar microfases para pagar isso uma vez.
- **SketchUp real só nesta máquina Windows** (26.0.429); sessão remota não prova L2.
- `fp042_inventory.v1.json` é editado por quase todo PR → conflito frequente; reaplicar com `tools.navigation.register_evidence`.
- Specs FP-045…FP-052 se referenciam em cadeia; mudar uma regra exige olhar as outras (o mapa de microfases é o índice).

## 8. Próximos 5 passos (menor risco primeiro)

1. Mergear #360 (instruções) e este PR; conferir que a próxima sessão carrega o CLAUDE.md novo (constituição aparece no contexto).
2. M-T0.1: corrigir o `cabinet.sketchup.inspect` que grava scratch ao lado do `.skp` de `artifacts/` (teste vermelho → fix → L2 da frente lisa).
3. M-T0.2: FP-051 P1 — `plan_furniture_goal()` puro, reportando `BLOCKED_TARGET_UNDEFINED` (FP-052) como dependência de produto.
4. M-T0.3: registrar o placement FP-050 no catálogo (L1) e ligá-lo como gate obrigatório em `cabinet_flow` **e** `shaker_flow`
   (FP-051 P4), com L2 dos dois fluxos refeito no mesmo PR.
5. Com o Felipe: veredito L3 da Shaker + revisão do trecho do tampo → abre a trilha K1 (tampo separado + chanfro).

## 9. Comandos úteis

```bash
cd E:/Claude/apps/sketchup-mcp            # ou a worktree da tarefa
PY=E:/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe
git fetch --all --prune && git worktree list
$PY -m pytest tests -q -m "not planta74_scale"
PT_TO_M=0.0259 $PY -m pytest tests -q -m planta74_scale
$PY -m tools.rooms.capability_catalog                                   # errors = {}
$PY -m tools.navigation.fp051_baseline --external docs/reports/fp051/external_snapshot.json --out runs/fp051/baseline.json
$PY -m tools.navigation.register_evidence <arquivos já em git add>      # registro FP-042
"/c/Program Files/GitHub CLI/gh.exe" pr checks <n> --repo GFCDOTA/sketchup-mcp
```

## 10. O que NÃO fazer

- Não declarar aparência aprovada, nem "cozinha concluída", nem `TARGET_MATCH` sem o Felipe.
- Não reaproveitar evidência L2 de outro commit; não editar a pasta de evidência de uma fase já mergeada.
- Não ensinar técnica nova a partir de vídeo sem `human_review` do trecho exato; recipe ≠ permissão.
- Não dar valor default a medida que o pedido não trouxe; não mover âncora/parede do PDF por causa de referência visual.
- Não tocar `fixtures/`, `.skp` canônicos, PDF; SketchUp só em cópia sob `runs/`, fechando só o próprio PID.
- Não reviver NOC `:8765` nem GPT bridge; não `taskkill /IM`; não `ruff --fix` em diretório inteiro.

## 11. Checkpoint para a próxima sessão

Parei com o core do gabinete provado (frente lisa + Shaker, L2 em `4023b78`) e as instruções do agente atualizadas.
**Primeiro movimento:** `git fetch --all --prune`, conferir #360 e este PR mergeados e abrir
`docs/specs/construction_core_microphases.md` §4 (fila T0). **Sinal de que está tudo de pé:** `python -m tools.rooms.capability_catalog`
com `errors: {}`, 5 capacidades `L2_PASS` com digests casando (`tests/test_fp051_baseline.py` verde) e working tree limpa.
