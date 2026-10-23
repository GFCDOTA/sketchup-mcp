# FP-054 F1B — desenho de conferência da folga funcional e do alcance (planta_74, REPORT_ONLY)

`planta74_functional_clearance.png`: cozinha (`r004`), Banho 01 (`r005`), Banho 02 (`r006`) e lavabo (`r007`) com a face de uso
derivada pelo contrato (magenta), a forma livre medida em frente a cada peça (tracejado), os portais (estrelas) e o veredito.
Serviu para conferir o avaliador antes de aceitar os números (a 1ª versão errava a face da bancada da cozinha e do box do
Banho 02 — corrigido antes do commit).

| | |
|---|---|
| Código | `tools/validation/functional_clearance.py` + `core/functional_constraints.py` |
| Relatório | `docs/reports/fp054/f1b/functional_clearance.{json,md}` |
| Reprodução | `PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1b` |

**O que NÃO é:** não é veredito visual nem decisão de layout; nenhuma caixa nem `.skp` foi alterada (REPORT_ONLY). Os alvos de
projeto estão `PENDING_FELIPE`.
