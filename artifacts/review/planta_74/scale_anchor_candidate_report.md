# Scale-anchor candidate report — planta_74 (REPORT ONLY, no patch)

Method: extract PDF dimension cotas (text) + their isolated dimension line (vector path bbox) via pypdfium2; scale = cota_m / line_length_pts. Hatching filtered (no parallel sibling). DETERMINISTIC. NOT applied to the builder.

## Candidate anchors (clean, isolated lines)

| cota (m) | line bbox pts [l,b,r,t] | len pts | orient | implied m/pt |
|---|---|---|---|---|
| 5.45 | (335.8, 667.2, 548.4, 668.2) | 212.54 | H | 0.02564 |
| 2.60 | (388.3, 535.2, 490.2, 536.2) | 101.91 | H | 0.02551 |
| 2.40 | (236.8, 576.0, 335.4, 577.0) | 98.55 | H | 0.02435 |

## Candidate scale

- **mean PT_TO_M ≈ 0.02517 m/pt** (anchors: 5.45→0.02564, 2.60→0.02551, 2.40→0.02435)
- residual: range [0.02435, 0.02564] = ±2.6% around mean
- tightest pair 5.45 & 2.60 agree to ~0.5%% (0.02564 vs 0.02551); 2.40 looser (~5%% low)

## vs current builder

- current PT_TO_M = 0.19/5.4 = **0.03519** (assumes wall=0.19 m)
- candidate/current ratio = 0.715  => current is ~1.40x too BIG
- at candidate scale: wall 5.4 pt → 0.136 m (a normal interior wall)
- apartment bbox 17.744×10.508 m (current) → **12.69×7.52 m** (candidate); bbox area 186→95 m²

## Confounded (NOT used — could not isolate clean dimension line)

- 5.14, 4.37, 4.20, 3.20, 3.82, 2.90, 1.79: nearest thin lines were hatching or ambiguous (implied scales scattered 0.034–0.12). Not fabricated into anchors.

## Decision

- DO NOT apply scale yet (user rule). This is prep evidence only.
- Apply only AFTER: (a) GPT visual review via Chrome on the door patch, and (b) ideally a 2nd independent confirmation. The 5.45+2.60 agreement (~0.0256) is the strongest signal that the current 0.0352 scale is ~1.4x too large.
