# FP-054 F1C — folga funcional e alcance com interfaces semânticas (REPORT_ONLY)

> Gerado por `PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1c --compare docs/reports/fp054/f1b/functional_clearance.json`. Retrato datado: regenere, não edite. Nenhum layout foi alterado.

Resumo: INVALID 8 · VALID_BELOW_TARGET 0 · VALID 5 · PREFERRED 7 · BLOCKED_MISSING_INPUT 0 · NOT_APPLICABLE 3 — 23 avaliações; base da interface: SEMANTIC_BUILDER 18, SEMANTIC_PDF_ANCHOR 2

| Cômodo | Peça | Regra | Medido (m) | Mín. ref. | Alvo | Pref. | Veredito | Base da interface | Proveniência (mín/alvo/pref) |
|---|---|---|---|---|---|---|---|---|---|
| r004 | countertop | kitchen_counter.front_clearance | 1.088 | 0.9 | 0.9 | 1.0 | **PREFERRED** | SEMANTIC_PDF_ANCHOR | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r004 | countertop | kitchen_counter.reach_path | 1.343 | 0.9 | 0.9 | 1.0 | **PREFERRED** | SEMANTIC_PDF_ANCHOR | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r005 | Bancada | lavatory.front_clearance | 0.843 | 0.55 | 0.6 | 0.8 | **PREFERRED** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r005 | Bancada | lavatory.reach_path | 0.941 | 0.6 | 0.6 | 0.8 | **PREFERRED** | SEMANTIC_BUILDER | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r005 | Box | shower.entry_front_clearance | 1.677 | 0.6 | 0.6 | 0.8 | **PREFERRED** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r005 | Box | shower.entry_width | 0.327 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r005 | Box | shower.reach_path | 0.627 | 0.6 | 0.6 | 0.8 | **VALID** | SEMANTIC_BUILDER | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r005 | Vaso | toilet.front_clearance | 0.675 | 0.6 | 0.6 | 0.8 | **VALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r005 | Vaso | toilet.reach_path | 0.831 | 0.6 | 0.6 | 0.8 | **PREFERRED** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r006 | Bancada | lavatory.front_clearance | 0.714 | 0.55 | 0.6 | 0.8 | **VALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r006 | Bancada | lavatory.reach_path | 0.86 | 0.6 | 0.6 | 0.8 | **PREFERRED** | SEMANTIC_BUILDER | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r006 | Box | shower.entry_front_clearance | 0.0 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r006 | Box | shower.entry_width | 0.0 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r006 | Box | shower.reach_path | 0.0 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r006 | Vaso | toilet.front_clearance | 0.523 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r006 | Vaso | toilet.reach_path | 0.703 | 0.6 | 0.6 | 0.8 | **VALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r007 | Bancada | lavatory.front_clearance | 0.044 | 0.55 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r007 | Bancada | lavatory.reach_path | 0.79 | 0.6 | 0.6 | 0.8 | **VALID** | SEMANTIC_BUILDER | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r007 | Box | shower.entry_front_clearance |  | 0.6 | 0.6 | 0.8 | **NOT_APPLICABLE** |  | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r007 | Box | shower.entry_width |  | 0.6 | 0.6 | 0.8 | **NOT_APPLICABLE** |  | COMFORT_GUIDE / PROJECT_POLICY / HEURISTIC |
| r007 | Box | shower.reach_path |  | 0.6 | 0.6 | 0.8 | **NOT_APPLICABLE** |  | HEURISTIC / PROJECT_POLICY / HEURISTIC |
| r007 | Vaso | toilet.front_clearance | 0.032 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |
| r007 | Vaso | toilet.reach_path | 0.0 | 0.6 | 0.6 | 0.8 | **INVALID** | SEMANTIC_BUILDER | COMFORT_GUIDE / PROJECT_POLICY / COMFORT_GUIDE |

## F1B heurística × F1C semântica

| Cômodo | Peça | Regra F1B → F1C | F1B | F1C | Medida F1B → F1C (m) | Diverge | Explicação |
|---|---|---|---|---|---|---|---|
| r004 | countertop | kitchen_counter.front_clearance → kitchen_counter.front_clearance | PREFERRED | PREFERRED | 1.088 → 1.088 | não | IGUAL (mesma interface, mesma medida) |
| r004 | countertop | kitchen_counter.reach_path → kitchen_counter.reach_path | PREFERRED | PREFERRED | 1.343 → 1.343 | não | IGUAL (mesma interface, mesma medida) |
| r005 | Bancada | lavatory.front_clearance → lavatory.front_clearance | PREFERRED | PREFERRED | 0.843 → 0.843 | não | IGUAL (mesma interface, mesma medida) |
| r005 | Bancada | lavatory.reach_path → lavatory.reach_path | PREFERRED | PREFERRED | 0.941 → 0.941 | não | PROVENIENCIA: COMFORT_GUIDE -> HEURISTIC |
| r005 | Box | shower.opening_clearance → shower.entry_front_clearance | INVALID | PREFERRED | 0.527 → 1.677 | **sim** | METRICA_REDEFINIDA: disco de 0,60 m (citacao NBR nao conferida) -> profundidade livre na frente da ENTRADA declarada (fonte tier D conferida); INTERFACE_MUDOU: semantica difere da face heuristica em ate 0.62 m; PROVENIENCIA: TECHNICAL_REFERENCE -> COMFORT_GUIDE |
| r005 | Box | shower.reach_path → shower.reach_path | VALID | VALID | 0.65 → 0.627 | **sim** | INTERFACE_MUDOU: semantica difere da face heuristica em ate 0.62 m; PROVENIENCIA: TECHNICAL_REFERENCE -> HEURISTIC |
| r005 | Vaso | toilet.front_clearance → toilet.front_clearance | VALID | VALID | 0.664 → 0.675 | **sim** | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 1.3 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r005 | Vaso | toilet.reach_path → toilet.reach_path | PREFERRED | PREFERRED | 0.831 → 0.831 | não | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 1.3 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r006 | Bancada | lavatory.front_clearance → lavatory.front_clearance | VALID | VALID | 0.714 → 0.714 | não | IGUAL (mesma interface, mesma medida) |
| r006 | Bancada | lavatory.reach_path → lavatory.reach_path | PREFERRED | PREFERRED | 0.86 → 0.86 | não | PROVENIENCIA: COMFORT_GUIDE -> HEURISTIC |
| r006 | Box | shower.opening_clearance → shower.entry_front_clearance | INVALID | INVALID | 0.558 → 0.0 | **sim** | METRICA_REDEFINIDA: disco de 0,60 m (citacao NBR nao conferida) -> profundidade livre na frente da ENTRADA declarada (fonte tier D conferida); INTERFACE_MUDOU: semantica difere da face heuristica em ate 0.79 m; INTERFACE_OBSTRUIDA: a entrada declarada da para parede/obstaculo (nada livre na frente); PROVENIENCIA: TECHNICAL_REFERENCE -> COMFORT_GUIDE |
| r006 | Box | shower.reach_path → shower.reach_path | INVALID | INVALID | 0.499 → 0.0 | **sim** | INTERFACE_MUDOU: semantica difere da face heuristica em ate 0.79 m; INTERFACE_OBSTRUIDA: a entrada declarada da para parede/obstaculo (nada livre na frente); PROVENIENCIA: TECHNICAL_REFERENCE -> HEURISTIC |
| r006 | Vaso | toilet.front_clearance → toilet.front_clearance | INVALID | INVALID | 0.515 → 0.523 | não | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 1.3 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r006 | Vaso | toilet.reach_path → toilet.reach_path | VALID | VALID | 0.703 → 0.703 | não | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 1.3 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r007 | Bancada | lavatory.front_clearance → lavatory.front_clearance | INVALID | INVALID | 0.044 → 0.044 | não | IGUAL (mesma interface, mesma medida) |
| r007 | Bancada | lavatory.reach_path → lavatory.reach_path | VALID | VALID | 0.79 → 0.79 | não | PROVENIENCIA: COMFORT_GUIDE -> HEURISTIC |
| r007 | Box | shower.opening_clearance → shower.entry_front_clearance | NOT_APPLICABLE | NOT_APPLICABLE | None → None | não | METRICA_REDEFINIDA: disco de 0,60 m (citacao NBR nao conferida) -> profundidade livre na frente da ENTRADA declarada (fonte tier D conferida); PROVENIENCIA: TECHNICAL_REFERENCE -> COMFORT_GUIDE |
| r007 | Box | shower.reach_path → shower.reach_path | NOT_APPLICABLE | NOT_APPLICABLE | None → None | não | PROVENIENCIA: TECHNICAL_REFERENCE -> HEURISTIC |
| r007 | Vaso | toilet.front_clearance → toilet.front_clearance | INVALID | INVALID | 0.044 → 0.032 | **sim** | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 2.0 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r007 | Vaso | toilet.reach_path → toilet.reach_path | INVALID | INVALID | 0.0 → 0.0 | não | MESMA_FACE, SEGMENTO AJUSTADO: o segmento do builder difere 2.0 cm do lado heuristico (pegada do builder x retangulo minimo das pecas); a medida acompanha |
| r005 | Box | — → shower.entry_width | — | INVALID | None → 0.327 | **sim** | REGRA_NOVA_F1C (sem equivalente na F1B) |
| r006 | Box | — → shower.entry_width | — | INVALID | None → 0.0 | **sim** | REGRA_NOVA_F1C (sem equivalente na F1B) |
| r007 | Box | — → shower.entry_width | — | NOT_APPLICABLE | None → None | **sim** | REGRA_NOVA_F1C (sem equivalente na F1B) |
