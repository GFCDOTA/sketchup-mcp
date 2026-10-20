# FP-044 / F7 — L2 integrado no `develop` final (2026-10-20)

Prova de **saída idêntica** depois das fatias F2, F3 e F6 (movimento + religação). Não é veredito visual, não promove
nada a canônico e não substitui a revisão do Felipe.

- Base: `develop` @ `ce25e8c` (merge do #335, último lote da F6). SketchUp **26.0.429**, modo `interactive`.
- Cliente MCP real por **stdio**, servidor `python -m tools.mcp_server.server` subido do worktree (18 tools),
  `PT_TO_M=0.0259`: `su_status` (0 SketchUp aberto antes) → `su_build_shell` (planta_74, `force`) → `su_furnish`
  (402 caixas) → `su_inspect` (`max_depth=3`, `.skp` reaberto). Cada SketchUp aberto por uma tool foi fechado **só pelo
  PID** que ela devolveu (`su_close pid=… force confirm`); nenhum encerramento por nome. Depois: 0 SketchUp em execução.
- `planta_check.json`: gerado pelo mesmo `artifacts/review/l2_fp042_20261019/tools/planta_check.py` do L2 FP-042/P8,
  cruzando o plano (`collect_boxes`) com o `.skp` reaberto, o `_shell_polygon.json` do build e o consensus.
  **Igual ao `artifacts/review/fp043/p8_l2_20261019/planta_check.json` — mesmo blob git `aed8834f…`**:
  402/402 peças casadas, erro máximo 0,05 mm, mesmas contagens por cômodo.
- Canônicos (SHA-256) iguais aos do relatório P8: `planta_74.skp` `7512d592…`, `geometry_report.json` `dfc431da…`,
  `planta_74_furnished.skp` `d2846ab6…`.
- Programa do sofá (`build_sofa_from_config.rb`, caso `eval_loveseat_slim_arm_tight_back`, sem `SOFA_SCHEMA`):
  `status=OK`, bbox 1,52×0,963×0,818 m, 10 peças, 0 warns; os 5 renders têm **SHA-256 idênticos** aos do código anterior
  à FP-044 (`develop` @ `1beb78e`, rodado na F2). Detalhes, PIDs e hashes em `l2_summary.json`.

Arquivos: `README.md`, `l2_summary.json`, `planta_check.json`. Os `.skp`/renders ficaram em `runs/` (scratch).
