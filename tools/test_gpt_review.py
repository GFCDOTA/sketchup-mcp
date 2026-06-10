import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.gpt_review import parse_verdict, gate_decision, DEFAULT_DIMS

# Caso 1: veredito REAL do eyefill3 (esperado GATE=PASS, promote=True)
t1 = ("VERDICT: PASS // LIGHTING: PASS - resolveu: sofa virou heroi // PREMIUM_REALISM: WARN - "
      "falta composicao final // MATERIALS: PASS - madeira e tecido legiveis // CAMERA: WARN - "
      "faixa cinza inferior // FURNITURE_DETAIL: PASS - leitura clara // TOP_3_ISSUES: 1) faixa "
      "cinza 2) parede escura 3) almofada macia // NEXT_ACTION: corrigir o enquadramento")

# Caso 2: veredito REAL do eye-level sem luz (esperado GATE=WARN: VERDICT WARN, sem dim FAIL)
t2 = ("VERDICT: WARN // CAMERA: PASS - eye-level melhor // LIGHTING: WARN - paredes escuras // "
      "BEST_SHOT: eyelevel // NEXT_ACTION: adicionar luz interna")

# Caso 3: sintetico FAIL numa dimensao (esperado GATE=FAIL, promote=False mesmo com VERDICT WARN)
t3 = ("VERDICT: WARN // LIGHTING: FAIL - janela estourada // MATERIALS: PASS // NEXT_ACTION: segurar janela")

for name, t, exp_gate, exp_promote in [("eyefill3", t1, "PASS", True),
                                       ("eye-nolight", t2, "WARN", True),
                                       ("synthetic-fail", t3, "FAIL", False)]:
    p = parse_verdict(t, DEFAULT_DIMS)
    g = gate_decision(p)
    ok = (g["gate"] == exp_gate and g["promote"] == exp_promote)
    print(f"[{'OK' if ok else 'XX'}] {name}: verdict={p['verdict']} gate={g['gate']} "
          f"promote={g['promote']} dims={ {k:v['status'] for k,v in p['dims'].items()} } "
          f"next={p['next_action'][:30]!r}")
    assert ok, f"FALHOU {name}: esperava gate={exp_gate} promote={exp_promote}, veio {g}"
print("\nMICRO-TEST OK: parser + gate corretos nos 3 casos (PASS / WARN / FAIL-block).")
