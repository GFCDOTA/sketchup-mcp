# R3 / T0.2 (#460) — L2 refeito: scratch da inspeção nunca ao lado de .skp protegido (2026-10-25)

Prova no SketchUp real das capacidades `shared.cabinet.parametric` e `shared.cabinet.front.shaker` depois de `cabinet.sketchup.inspect` e
`shaker.sketchup.inspect_shaker` passarem a usar o `scratch_dir` único (`tools/rooms/shared/cabinet/scratch.py`). Os símbolos mudaram, então a
evidência anterior foi revogada no mesmo commit da mudança (R-18) e refeita aqui.

| | |
|---|---|
| Código sob prova | commit `53d4711`, árvore **limpa** (`dirty: false` nos dois `summary`) |
| SketchUp | 26.0.429 (Windows 11), modo `interactive`; **27 PIDs** (matriz do gabinete) + **30 PIDs** (matriz Shaker), todos fechados por PID; nenhum SketchUp alheio tocado |
| Base | template padrão do SketchUp (`Temp01a - Simple.skp`), copiada, nunca aberta |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp055/r3_scratch_l2/l2_cabinet.py <saida> <template.skp>` e `.../l2_shaker.py <saida> <template.skp>` (saída em `runs/`) |
| Resultado | gabinete **14/14 PASS** (`cabinet_summary.json`), Shaker **11/11 PASS** (`shaker_summary.json`) |

## O que foi provado
- Mesmas matrizes das provas anteriores (gabinete: 3 dimensões × poses 0/90/30°, reexecução idempotente, `make_unique`, edição local e propagada, material;
  Shaker: 1 e 2 portas, poses, idempotência, `make_unique`, `propagate`, material, 2 negativos no Ruby real), agora sobre o código novo.
- **Caso novo `n1_inspect_protected_skp_leaves_no_trash`** (nos dois scripts): um `.skp` dentro de um `artifacts/` (repo temporário, `paths.REPO_ROOT` trocado só no
  script) é inspecionado no SketchUp real; **nada** novo aparece ao lado dele, o `.skp` mantém o SHA-256 e o scratch do job fica sob `runs/`.

## O que NÃO é
- Não prova a cozinha real nem ferragem/gaveta/veio (`grain = NOT_SUPPORTED`), e **não é veredito visual** (`visual = NOT_REVIEWED`, `PENDING_HUMAN`).
- A matriz do Shaker usa pai sintético (`valid_a_base_600`); os fluxos da cozinha (`kitchen.cabinet.*`) não ficaram velhos com esta mudança (catálogo sem `EVIDENCE_STALE` para eles).
