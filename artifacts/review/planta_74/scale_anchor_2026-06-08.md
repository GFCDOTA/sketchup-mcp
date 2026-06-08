# planta_74 — escala TRAVADA vs PDF (cota = verdade)

- **Data:** 2026-06-08 · **Fonte:** planta_74.pdf (PLANTA DE VENDAS R02; "PLANTA SEM ESCALA, MEDIDAS FACE A FACE")
- **Veredito de fidelidade (skill pdf-fidelity-reference): FAIL — scale drift 1.36×.**

## Âncora física (2 dimensões da SUÍTE 01 concordam)
| | consensus (pt) | build @0.0352 | cota PDF (real) | escala implícita |
|---|---|---|---|---|
| SUÍTE 01 largura | 210.7 | 7.41 m | **5.45 m** | 0.0259 |
| SUÍTE 01 altura  | 154.4 | 5.43 m | **4.00 m** | 0.0259 |

→ **PT_TO_M ≈ 0.0259 m/pt** (duas dims independentes, mesmo valor). Build atual `0.19/5.4 = 0.0352` está **1.36× grande**.

## Cross-check de área (reconcilia)
- cômodos-interior @0.0259 ≈ 64 m² + footprint de paredes ≈ **74,93 m² privativos** (PDF). Consistente.
- A âncora de wall_thickness (5.4pt=0.19m → 0.0352) está ERRADA: ou a parede extraída não é 0.19m, ou foi medida torta. A cota da SUÍTE manda.

## Impacto (por que é o alicerce)
- **TODO o apê está 1.36× grande** — afeta proporção de móveis, "tudo parece off", e os renders V-Ray da sessão paralela (estão renderizando um apê 1.36× inflado).
- Nenhum cômodo pode ser "certo" (consolidado) enquanto o build estiver nessa escala → **BLOCKED_BY_GEOMETRY**.

## Fix proposto (alto impacto — precisa coordenação + visual review)
1. `ENV['PT_TO_M']=0.0259` no build_plan_shell_skp (override já existe) → re-build.
2. Re-validar deterministico: SUÍTE 01 → 5.45×4.00; privativa ≈ 74.93. (SU-free, comparando dims vs cotas.)
3. **VISUAL_REVIEW do Felipe** (muda geometria do apê inteiro vs PDF).
4. **Coordenar com a sessão V-Ray** (renders atuais a 0.0352 ficam inválidos).
NÃO aplicar unilateral: re-escala global + colide com a trilha paralela.
