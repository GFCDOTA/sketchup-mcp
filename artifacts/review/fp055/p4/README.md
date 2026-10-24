# FP-055 P4 — construído × ambiente real no SketchUp (2026-10-23/24)

**Estado da fase: CONCLUÍDA como infraestrutura de validação.** As quatro provas no SketchUp real cumprem o esperado num
commit limpo, sem falso PASS conhecido. A planta_74 **não** está aprovada: 34 defeitos físicos reais ficam registrados e
bloqueiam a aprovação funcional (ver "Defeitos reais"). Aparência: `PENDING_HUMAN`.

| Item | Valor |
|---|---|
| Commit sob prova | `ac3c1c96…` (`git status --porcelain` vazio durante toda a execução) |
| SketchUp | 26.0.429; cada caso abre 3 processos (build, inspect_model, inspect_geometry) e fecha só esses PIDs |
| Reprodução | `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp055/p4/run_p4.py runs/fp055/p4h` |
| Protegidos (consensus, `.skp` canônicos, PDF) | SHA-256 idênticos antes e depois (`summary.json: protected_unchanged = true`) |
| Resultado | `summary.json: result = PASS`; expectativas A/B/C/D = true |

## Arquitetura validada
1. **Contrato de referencial** (`core/plan_frame.py`): um único `pt_to_m` resolvido pela mesma regra do shell builder;
   cadeia consensus → plano (m) → caixas (in) → mundo do SketchUp (in) → inspeção (m), mesma origem e sem espelhamento.
   `check_chain` bloqueia divergência antes de construir. `verify_against_built` confere as paredes esperadas contra as
   construídas: IoU global (filtro, 0,95) e, decisivo, **por parede**: cobertura ≥ 0,99, excesso ≤ 1%, contorno
   (Hausdorff) ≤ 1 cm e comprimento/espessura ≤ 1 cm.
2. **Geometria bruta** (`tools/sketchup/ruby/inspect_geometry.rb`):
   - toda face não vertical (horizontal e inclinada), percorrendo grupos e componentes aninhados com a transformação
     composta;
   - partes (container com faces próprias) com a faixa de Z;
   - bbox do próprio SketchUp. Extração que não cobre esse bbox = `BLOCKED`.
3. **Construído × ambiente** (`tools/validation/built_geometry.py` v2, `tools/validation/penetration.py`). Área, contato e
   profundidade direcional são medidos separados; o círculo inscrito é só complementar. Contato ≠ penetração por
   `EPS_DEPTH` = 0,5 mm, derivado do arredondamento da exportação: ±0,05 mm por coordenada, ≤ 0,1 mm de sobreposição
   espúria; 300 contatos com ruído deram no máximo 0,095 mm.
   | Cheque | Como mede |
   |---|---|
   | Contenção | profundidade para fora do **polígono efetivo** = laje construída − massa de parede construída |
   | Parede | MTD por região de contato contra a peça de parede local |
   | Porta | a folha construída gira de 0 a 90°, na faixa de Z da folha do modelo |
   | Objetos | por parte, com sobreposição em planta **e** em altura |
4. **Três veredictos independentes**: geométrico, funcional (motor F2 sobre as caixas provadas iguais ao construído, com as
   interfaces movidas) e visual (`PENDING_HUMAN`). Válido só com geométrico e funcional `PASS`.
5. **Normalização** só nas métricas de contorno e dimensão de parede: abertura de 2 mm, registrada por parede (área e
   extensão removidas). Contenção, colisão, porta e funcional usam sempre a geometria bruta.
6. **Não regressão** (`tools/validation/defect_baseline.py`, `defect_baseline.json`): defeito novo, ou mais profundo que o
   registrado do apartamento original, reprova a geração.

## Resultado por caso (gates efetivos)
| Caso | Contrato | Paredes | Extração | Contenção | Parede | Porta | Objetos | Geométrico | Funcional | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A — fixture válida (solver desloca o vaso) | OK | 4/4, IoU 0,9998 | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **BUILT, válido** |
| B — L com armário no quadrante vazio (injetado) | OK | 6/6 | PASS | **FAIL** (1,095 m fora) | PASS | PASS | PASS | FAIL | NOT_EXECUTED | rejeitado; o cheque antigo por bbox **passaria** |
| C — escala divergente (0,0259 × 0,0352) | **BLOCKED_SCALE_MISMATCH** antes de construir | — | — | — | — | — | — | — | — | rejeitado |
| C forçado (só prova) | BLOCKED | 4/4 (o shell está certo) | PASS | **FAIL** (0,95 m) | **FAIL** (0,42 m) | PASS | PASS | BLOCKED | NOT_EXECUTED | rejeitado; proposta = construído (0 mm) não salva |
| D — Banho 02 real, proposta INFEASIBLE construída em diagnóstico | OK | **20/20**, IoU 0,9996 | PASS | FAIL | FAIL | PASS | FAIL | FAIL | NOT_EXECUTED | rejeitado; não regressão **FAIL** (1 defeito novo, 2 piores) |

Os casos negativos comprovadamente rejeitados no SketchUp real são três:
- peça dentro do bbox e fora do polígono (B);
- escala divergente, tanto bloqueada antes de construir quanto forçada e construída (C);
- proposta real que cria colisão nova (D: papeleira × vaso 11 cm; bancada 1,9 → 2,8 cm e box 2,2 → 3,4 cm fora do cômodo).

Regressão entre validadores sobre a geometria bruta (`validator_comparison.json`, 8 cômodos + 3 fixtures): 3 mudanças.
- Contenção mais estrita onde o V1 aceitava 1 cm de borda: Painel TV 9,1 mm; base e tampo da cozinha 4,6 mm.
- Lavabo `OBJECTS` FAIL → PASS. Conferido: bandeja (z 0,900–0,915) e sabonete (0,915–0,945) estão **acima** do tampo
  (`bancada_banho`, 0,78–0,88). Sem sobreposição em altura, não há interpenetração. É um defeito de **apoio** (bandeja 2 cm
  acima do tampo), registrado na FP-056.

## Falsos PASS encontrados e corrigidos durante a fase
| # | Falso PASS | Causa | Correção e prova |
|---|---|---|---|
| 1 | proposta = construído e móvel fora do cômodo | conferência só contra os dados enviados ao builder (shell em outra escala) | contrato de referencial + construído × ambiente (casos C) |
| 2 | bounding box do piso | objeto dentro do bbox e fora do polígono | contenção no polígono efetivo (caso B) |
| 3 | área ≤ 4 in² = OK | longo e raso, ou pequeno que bloqueia porta | profundidade direcional + movimento da folha (testes L1) |
| 4 | laje sob a parede tomada como cômodo | `Floor_Group` entra 0,4t sob a parede (D-007) | polígono efetivo = laje − parede (render × overlay conferidos) |

## Defeitos reais da planta_74 (apartamento original; `defect_baseline.json`, `defect_register_original.json`)
34 defeitos, por causa-raiz:
| Causa | Qtd | Exemplos (medida) |
|---|---|---|
| R1 — laje sob a parede usada como área de mobiliar (D-007 / FP-043 P3a-03) | 11 | cozinha: corpo, soco e tampo 4,6 mm na m006; tapetes das suítes 5,6 cm; Box do Banho 01 6,2 cm (m018) |
| R2a — atravessa barreira de varanda (SoftBarrier) | 3 | A.S.: bancada gourmet 20 cm (730 cm² no `SoftBarrier_Group_8`), jardineira 15,6 cm, condensadora 2,9 cm |
| R2b — sobre região sem laje e sem parede | 7 | A.S.: máquina de lavar 21 cm, armário 3,3 cm (área sem laje de 29 × 66 cm); painéis e guarda-roupa 0,8–1,9 cm |
| R2 — fora do cômodo, causa a investigar | 2 | Box do Banho 02 (2,2 cm fora; 1,7 cm na parede) |
| R3 — peça dentro de outra | 9 | cama × painel 3 cm; backsplash × cuba/cooktop 4,6 cm; papeleira, gancho, tapete × vaso/espelho/gabinete |
| R5 — porta não abre 90° (folha construída sem folga inferior × tapete) | 2 | SUÍTE 01 `h_o003` 49°; SUÍTE 02 `h_o004` 16° |
| R6 — funcional F2 | — | Banho 01/02 e lavabo INFEASIBLE no grau de liberdade declarado (FP-054) |

Coordenadas, parede mais próxima, peça, parte, Z e profundidade de cada um: `defect_register_original.json`
(`investigate_defects.py`). A correção é **na origem**, pela FP-056 (`docs/specs/FP-056_usable_space_support_barriers.md`),
começando pela separação entre piso construtivo e área utilizável. O validador **não** ganha exceção.

## Limitações restantes (explícitas)
- **Porta:**
  - só os objetos do próprio cômodo obstruem a folha; os de outro cômodo não são considerados;
  - a folha é um retângulo de 4 cm de espessura;
  - a exigência é 90°, a mesma regra do gate de varredura existente.
- **Embutimento intencional** (pele, nicho, peça hospedada) ainda não é declarado por peça: a pele (`Pele`/`PeleTeto`) vai
  para "finishes" com a protrusão medida, e o resto é tratado como penetração. A declaração por peça é o contrato 1 da FP-056.
- **Apoio físico** (peça flutuando) ainda não é verificado: contrato 2 da FP-056.
- **Verificação de referencial:** confere o shell (paredes); a mobília é conferida pelo construído × ambiente, não pelo
  contrato.
- **Normalização de parede:** a abertura de 2 mm não enxerga desvio de parede com menos de 4 mm de largura. Ela atua só na
  métrica de contorno; cobertura e excesso são medidos no bruto.
- **Fechamento de PID:** um `close` respondeu `PARTIAL` no caso A (PID 3300 ainda vivo no instante do cheque); o
  `tasklist` seguinte mostrou nenhum SketchUp em execução.
- **Escopo:** a planta inteira foi validada no construído só neste caso D e na geração original; os perfis inteligentes
  cobrem banheiro e cozinha (os demais cômodos estão `NOT_INTEGRATED`, P6).
- **O que rodou fora do SketchUp:** o gate de não regressão (`defect_baseline.py`) e o parâmetro `defect_baseline` do
  `build()` entraram **depois** da prova no `ac3c1c96`. Foram exercitados offline, sobre a geometria bruta desta mesma
  execução (D → `FAIL`: 1 novo, 2 piores, 1 resolvido) e nos testes L1. A geometria do apartamento original
  (`raw/baseline_original_*`) foi extraída no mesmo commit, numa inspeção à parte do `.skp` da geração limpa da auditoria
  (snapshot `5426c0087bdfcdc6`, o mesmo do HEAD).

## Evidência (SHA-256 em `SHA256SUMS`)
`raw/*_inspect_geometry.json`: geometria bruta de A, B, C forçado, D e do apartamento original. Também `summary.json`,
`validator_comparison.json`, `defect_baseline.json`, `defect_register_original.json` e
`images/*_overlay_raw.png` × `images/*_sketchup_top.png` (overlay desenhado da geometria bruta ao lado do render do
SketchUp; conferidos: mesmos defeitos, mesma orientação).
