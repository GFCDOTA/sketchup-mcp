# regression_summary — Fase 2 (Bedroom placement)

## Determinístico (GREEN)

- `validation_report phase2_bedroom` = **GREEN** — 4 gates PASS:
  - SofaPlacementGate (sala) — sem regressão.
  - Sofa anatomy+visual — sem regressão.
  - BedGate (anatomia+visual) — king/queen/casal/solteiro PASS.
  - **BedPlacementGate (NOVO)** — quartos reais r000/r003 = PASS; fixtures de erro = FAIL.
- Artifacts canônicos presentes (planta_74_furnished.skp + renders).
- `base planta_74.skp` INTACTA (hash) em todos os builds.

## BedPlacementGate — detalhe

| quarto | verdict | cabeceira (parede limpa) | wardrobe | nightstands | circulação |
|---|---|---|---|---|---|
| r000 SUITE 01 | PASS | m018 | PASS | PASS | PASS |
| r003 SUITE 02 | PASS | m014 | PASS | PASS | PASS |

Fixtures de erro (r000): cama rotacionada=FAIL, cama flutuando=FAIL, cama bloqueando porta=FAIL.

## Sem regressão

- A sala (SofaPlacementGate) continua PASS — `living_room_planner` intacto.
- O placement do `bedroom_designer` é gate-válido (não foi necessário substituir; o
  FurniturePlacementBrain base fica disponível como fundação genérica/cross-check).

## YELLOW (pendente, não-determinístico)

- **GPT Modo B (visual) BLOQUEADO por infra de anexo-de-imagem ao ChatGPT** (clipboard
  trava persistente; upload_image/file_upload indisponíveis nesta sessão). NÃO autojulgado.
  O placement é deterministicamente PASS (o gate encoda as dimensões do schema GPT). Retry
  no próximo ciclo. Itens visuais pendentes: aparência do quarto (placement) + cama (c0521d3).
