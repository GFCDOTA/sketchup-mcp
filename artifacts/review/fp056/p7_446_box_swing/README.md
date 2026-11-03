# FP-056 R6 — arco de giro da porta do box do Banho 01 (abertura 0,70 m) — 2026-11-02

Evidência para a decisão #446. Fecha a ressalva aberta da recomendação do PR 559: "o solver não modela o arco de giro".

- **Commit sob prova:** `b556ca9f` (`origin/develop`), tracked limpo (`git_dirty_tracked: false` no JSON).
- **O que é:** reproduz o caso do PR 559 (`artifacts/review/fp056/p9_r6_errata_2026-10-25/probe_door_opening.py`):
  FEASIBLE, 6724 candidatos. Em cada um dos **319 candidatos FEASIBLE** modela a folha de abrir (90°, para fora do box,
  dobradiça em cada ponta) com as ferramentas que já existem: `door_swings_pt`/`door_sweeps_pt`, vidro de 8 mm do builder e
  `penetration.door_open_angle`. Mede a interseção com cada peça, com a porta do cômodo e com a parede. Nível **L1**.
- **O que NÃO é:** nada foi aplicado (builder, limiar, layout, fixture e `.skp` intactos; o monkeypatch é desfeito no fim).
  Não houve SketchUp nem veredito visual (`PENDING_HUMAN`). Não escolhe alternativa: a decisão é do proprietário na #446.
- **Reprodução** (~12 min; `--reuse-solve` pula o solver): `PT_TO_M=0.0259 PYTHONPATH=. python
  artifacts/review/fp056/p7_446_box_swing/measure_box_swing.py`. As saídas vão para `runs/fp056_r6_box_swing/`. O resumo
  versionado é `box_swing_r005_opening070_summary.json`; o detalhe por candidato (4,5 MB) foi omitido.

## Resultado
- **Os 0,70 m declarados não são livres:** 5,1 cm ficam sob a parede (laje D-007), 2,0 cm no revestimento de pedra e
  1,3 cm são folga do solver. A folha física tem **0,6165 m**; com ela aberta, a passagem é de 0,6125 m (mínimo 0,60).
  A folha de 0,70 m inteira nasce dentro da parede e não abre.
- **Folha de 0,6165 m:** 0 cm² com o Vaso (folga ≥ 4,4 cm), com a Bancada (≥ 22,5 cm), com o giro da porta h_o002
  (≥ 37,6 cm) e com a parede, nas duas dobradiças e em **319/319** candidatos.
- **Abertura sem enxoval:** 90° em 319/319.
- **O que trava a folha:** o enxoval que o builder põe na frente do box.

| Peça | Interseção (cm²) | Abertura máxima |
|---|---|---|
| Tapete | 1946–2097 | 10–11° |
| Toalheiro, dobradiça do lado da parede | 101 | 80° |
| Toalheiro, dobradiça do lado do vidro fixo | 0,2 | 12° |

- **Arco 100% livre:** 0/319.
- **Não medível:**
  - Porta pivotante: o PR 559 não define o pivô. Limite derivado: um pivô a mais de 1,25 cm da ponta já reprova a entrada
    de 0,60 m.
  - Folga inferior da folha e batente: não há valor para nenhum dos dois.

**Leitura:** do ponto de vista de louça, porta e parede, o box de abrir cabe. Escolhê-lo exige, junto, reposicionar o tapete
e o toalheiro, ou definir uma folga inferior da folha. Essa é uma decisão de projeto.
