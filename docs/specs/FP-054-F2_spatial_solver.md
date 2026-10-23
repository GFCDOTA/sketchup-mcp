# FP-054-F2 — Solver espacial (contratos → geometria → alternativas → ranking → proposta)

> Fase 2 da FP-054 (depois de F1/F1B/F1C). Responde "qual layout válido é melhor?" **dentro do que o especialista do cômodo
> permite**, sem nunca alterar a planta oficial. Cada fase é um PR.

## Arquitetura (responsabilidades; nomes reais)
```
especialista do cômodo  tools/rooms/<cômodo>/solver_policy.py      âncoras + graus de liberdade (decisão de projeto)
contrato semântico      core/functional_constraints.py (F1C)       interfaces, limiares, fontes (#394)
                        tools/rooms/shared/spatial_solver/contracts.py   problema, objetos, DOF, erros, estados
unidades e frames       core/units.py, core/frames.py              conversão explícita; cômodo <-> planta (rígida)
motor de restrições     tools/validation/functional_clearance.py   folga, alcance, gargalo (F1B/F1C) — reaproveitado
geometria compartilhada tools/rooms/shared/spatial_solver/          (F2B) colisão, dentro do cômodo, arco de porta
candidatos / ranking    tools/rooms/shared/spatial_solver/          (F2C/F2D) enumeração do DOF declarado, ordem lexicográfica
proposta + evidência    tools/rooms/shared/spatial_solver/          (F2E) proposta read-only, overlays dos mesmos dados
```
Ownership: o compartilhado não sabe o que é banheiro; o banheiro não reimplementa geometria.

## Estados
`FEASIBLE` (alternativa sem violação hard, demonstrada) · `INFEASIBLE` (todo o espaço declarado de DOF, na discretização
declarada, viola hard — **não** é prova fora desse espaço) · `UNKNOWN` (limite de exploração sem prova) · `INVALID_INPUT`.

## Regras
- Interface obrigatória ausente ou heurística → `INVALID_INPUT` (o solver nunca adivinha face, porta ou vão).
- Restrição hard nunca é trocada por preferência: ranking lexicográfico (viabilidade primeiro).
- Nenhum valor de guia vira norma; DOF e alvos do projeto são `PROJECT_POLICY` com fonte, `PENDING_FELIPE`.
- Provas L2 protegidas: `kitchen.layout.galley` (`build_boxes` + `place_layout_skp.rb`) e gabinetes — não tocados; a cozinha
  não tem DOF (âncora hidráulica do PDF), só diagnóstico.
- SciPy/OR-Tools não entram: o espaço de busca declarado é pequeno (dezenas de posições por peça) e enumerável exatamente;
  enumeração + verificação geométrica é exata **sobre a discretização** e mais simples de auditar. Reavaliar se o DOF crescer.

## Fases e saídas
F2A contratos (sem mudar layout) · F2B geometria + defeitos reproduzidos · F2C alternativas · F2D ranking + estabilidade ·
F2E proposta read-only + evidência + SketchUp real numa cópia.
