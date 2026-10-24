# FP-056 P6 — geração completa da planta_74 no SketchUp real × baseline de defeitos (2026-10-24)

**Estado: CONCLUÍDA como medição; a planta NÃO está aprovada.** A geração integral reabre em outro processo, as 8 salas conferem
com o plano (5 mm) e as paredes construídas com o consensus, **nenhum defeito novo ou pior** que o baseline da FP-055 P4, e 5 dos
34 defeitos físicos saíram. Restam 29 (todos já registrados) e a perda de programa da A.S. segue reprovada até a decisão AS-1.
Aparência: `PENDING_HUMAN`.

| Item | Valor |
|---|---|
| Commit sob prova | `a0be0516…` (branch `feat/fp056-p6-apartment-l2`, sobre `origin/develop@716c8fd`; `git status --porcelain` vazio) |
| SketchUp | 26.0.429; 3 processos (build, inspect_model, inspect_geometry), PIDs 7612, 12804, 35864, fechados por PID |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p6/run_p6.py runs/fp056/p6` |
| Protegidos | SHA-256 do shell e do furnished canônicos e do consensus idênticos antes e depois |
| Evidência bruta | geometria extraída com SHA-256 em `summary.json` (`raw_geometry_sha256`); `.skp` `1fbb4266…` |
| Entrega humana | `artifacts/review/planta_74/fp056-p6/final/` (`.skp`, top, iso, `regression_summary.md`) |

## Casos (10 de 11 PASS)
Pré-voo PASS · commit limpo · contrato de escala OK · furnish OK e `.skp` salvo · reaberto e geometria extraída · todo módulo
planejado é grupo no modelo (≤ 5 mm) · paredes construídas = consensus · **sem defeito novo/pior vs baseline** · canônicos
intactos · PIDs fechados. **FAIL (esperado e registrado): `no_program_loss_without_a_recorded_decision`** — `r001|PROGRAM|Bancada gourmet`
e `r001|PROGRAM|Banqueta` (a circulação os omite; decisão AS-1, #442).

## Defeitos × baseline (34 → 29)
Resolvidos (4 por posição, FP-056 P1/P3a): A.S. máquina de lavar, jardineira, armário de serviço, condensadora. Sumiu **com a peça**
(não corrigido): A.S. bancada gourmet. Persistem, idênticos ao baseline (`defects_after.json`):
| Causa | Qtd | O que |
|---|---|---|
| R1 laje sob a parede (D-007) | 11 | cozinha base/tampo/backsplash, tapetes das suítes, box dos banhos |
| R2 / R2b | 2 + 5 | box do Banho 02; guarda-roupa Suíte 01, Painel TV, Painel cabeceira, bancadas dos banhos (hipótese: recorte da laje por traços sem fonte, #484 / #438) |
| R3 vizinhança | 9 | cama × painel, backsplash × cuba/cooktop, enxoval × vaso/espelho/bancada (#437) |
| R5 porta × tapete | 2 | h_o003 e h_o004 (decisão #486) |
Ver também apoio físico (#436, #488) e decisões K-1, AS-1, S2-1, S1-1, B-1, R6, D-007 no Project.

## O que NÃO é
Não aprova função (os banhos e o lavabo seguem INFEASIBLE no grau de liberdade atual, R6) nem aparência. Não prova o caminho
inteligente (`INTELLIGENT_BUILD`): esta é a geração legada com o pré-voo obrigatório, validada pelo construído.
