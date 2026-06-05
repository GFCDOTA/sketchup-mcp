# Auto-Mobiliado (Interior Design) — Visão & Estado Atual

> **STATUS: ROUGH / EXPERIMENTAL — _bem ruim por enquanto_.**
> Isto **não** é um deliverable. É um snapshot do que o auto-mobiliado
> pretende ser + o estado cru de hoje, pra não se perder o fio enquanto
> a feature amadurece. A missão canônica do repo continua sendo o
> **shell** fiel (`consensus.json → .skp`); mobiliar é camada por cima.

---

## 1. O que deveria ser (visão)

Pegar um **shell de planta** já resolvido (walls / openings / rooms do
`consensus.json`) e **mobiliar automaticamente** cada cômodo:

- **Móveis reais** (componentes do 3D Warehouse / catálogo), não caixas.
- **Posicionamento determinístico e explicável** — regras de layout
  (parede-TV, sofá de frente, clearance de circulação, ancoragem por
  tapete) decidem, com **ranking top-K** de candidatos; nada de chute.
- **Generaliza pra qualquer forma de cômodo** (small / medium / large /
  long_narrow / L), não só a `planta_74`.
- **Degradação graciosa**: sem componente real → placeholder; sem âncora
  de escala → `BLOCKED` (nunca inventar).
- **Validável contra referência real** — o arranjo gerado tem que bater
  com como o apê é de verdade (tour / PDF decorado), não só "passar teste".

---

## 2. Estado atual — honesto (_bem ruim por enquanto_)

O que JÁ funciona (núcleo provado):

- Um layout de **sala** fecha de ponta a ponta (`estar_ancorado`): parede-TV
  escolhida, sofá de frente, mesa de centro, tapete ancorando.
- **Gate de circulação determinístico** funciona — removeu a poltrona porque
  ela bloqueava uma porta (~91%). Decisão correta e automática.
- **Generalização sintética 6/6**: o "brain" valida as 5 formas de cômodo
  sintético + harness de regressão trava isso (commit `190f786`).

O que ainda é **ruim / incompleto** (sem maquiar):

- **Placeholders, não móvel real.** O vencedor usa caixas coloridas:
  `azul=sofá`, `roxo=rack/TV`, `laranja=mesa de centro`, `teal=poltrona`
  (removida pelo gate), `bege=tapete`. Móvel real (sofá curvo, rack, etc.)
  só existe em variantes **separadas** (`sofa_compare_v2_v3`), não integradas
  no vencedor.
- **Só a sala é mobiliada.** Quartos, cozinha e banheiros saem **vazios**.
- **Generalização real ≈ zero.** Provado em cômodos **sintéticos** + **1**
  planta real (`planta_74`). Nenhuma 2ª planta real exercita o caminho.
- **Parede-TV resolvida por heurística**, não por dado — o sistema marcou a
  divisória interna como "ambígua" e desempatou via top-K. Funciona aqui,
  mas é frágil fora desta planta.
- **Briga com a própria circulação** — o fato de um móvel ter sido removido
  por bloquear porta mostra que o layout candidato ainda nasce conflitando.

### Comparação com o decorado REAL

Referência canônica: tour **Matterport** do _Living Grand Wish Jardim_ (apê
74 m²) — `https://my.matterport.com/show/?m=rLoqyVDHfzC`.

| | Bate | Diverge |
|---|---|---|
| **Arranjo** | parede-TV = divisória interna; sofá de frente; tapete ancorando; open-plan living→jantar→varanda; varanda na frente; 2 suítes à direita | — |
| **Fidelidade de móvel** | — | real = mobília de verdade (sofá curvo, mármore na TV, estante embutida, camas, mesa de jantar) × nosso = placeholders |
| **Cobertura** | — | real é todo decorado × nosso mobília só a sala |
| **Geometria de comparação** | — | tour = perspectiva × nosso = isométrico (não pixel-alinhado) |

**Veredito honesto:** o **arranjo** corresponde; a **fidelidade de móvel** e a
**cobertura** estão longe. Não é "bate" — é "a lógica de onde pôr as coisas
está certa, o resto é cru".

---

## 3. O que falta pra ficar bom (próximos passos)

1. **Móvel real no vencedor** — trocar placeholder por componente real,
   mantendo o ranking determinístico que já decide a posição.
2. **Mobiliar todos os cômodos** — quartos (cama + guarda-roupa), cozinha,
   banheiros; não só a sala.
3. **2ª+ plantas reais** — generalização de verdade, não só sintética.
4. **Fidelidade visual contra referência real** — gate PDF×BEFORE×AFTER ou
   contra o tour, não só contagem/pytest verde.
5. **Resolver ambiguidades por dado** (parede-TV, orientação) em vez de
   heurística top-K.

---

## 4. Onde olhar (artefatos)

Renders (servíveis pelo cockpit `:8765/artifact?path=<...>`):

- `artifacts/review/planta_74/_preview/` — `estar_ancorado` iso + top,
  `evolucao` before/after, `review_montage`, `sofa_compare_v2_v3`.
- `artifacts/review/synthetic/living_layout_candidates.png` (+ `.json`) —
  snapshot da generalização sintética (candidatos de layout de sala).

Código (em `develop`): `tools/layout_candidates.py` + `tools/layout_rules.py`
(candidatos + regras/ranking), `tools/furnish_plan.{py,rb}` +
`tools/place_layout_skp.{py,rb}` (coloca o móvel no SKP),
`tools/make_synthetic_rooms.py` (cômodos sintéticos), e o harness de
regressão (`190f786`).

Referência real: Matterport acima.

---

_Doc de visão — atualizar conforme o auto-mobiliado evoluir. Quando o
vencedor usar móvel real e cobrir mais de um cômodo, remover o aviso
"bem ruim por enquanto" do topo._
