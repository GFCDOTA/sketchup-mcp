# Core de construção — mapa de microfases por cômodo e componente

> **O que é:** a fila única e ordenada para melhorar o **detalhe de cada componente** construído no SketchUp, costurando
> as specs que já existem (FP-045 F5–F10, FP-046, FP-047, FP-048, FP-049, FP-050, FP-051, FP-052). **Não substitui
> nenhuma delas** e não cria regra nova: cada microfase aponta para a spec dona.
> **Medido em:** `develop@a87d2ad` (2026-10-22). **Reprodução:** `python -m tools.navigation.builder_detail_audit`
> e `python -m tools.navigation.fp051_baseline`. Retrato datado: atualizar na própria tabela §4 (coluna Estado) por PR.

## 1. Diagnóstico medido

### 1.1 Duas gerações de builder

| Geração | Builders | Medida | Peças | Prova |
|---|---|---|---|---|
| **Gen2 — contrato por pedido** | `shared/cabinet/{model,assembly,plan}`, `shared/cabinet/shaker/*` | toda grandeza `{value, unit, origin}`; **0** literal geométrico embutido | caixaria peça a peça (laterais, base, topo, fundo, prateleira, frentes; moldura + painel Shaker), material e veio por papel | L1 + **L2** no SketchUp real, digests no catálogo |
| **Gen1 — builder de classe** (programa de jun/2026) | guarda-roupa, cama, criado-mudo, sofá, poltrona, decor (`shared/`), rack, mesa de centro, mesa de jantar, poltrona, sofá (`living/`) | constantes no código: **491** literais float dentro de funções + 315 de topo (10–95 por arquivo) | caixas por papel com cor RGB fixa; **guarda-roupa com o corpo inteiro num bloco** (`corpo`) + rodapé + portas + puxador | gate L1 por classe; nenhum L2 próprio |

O número de literais é termômetro, não veredito (inclui proporções de classe legítimas). Ele mede quanto da geometria
**não vem do pedido** e só pode cair: `tests/test_builder_detail_audit.py` trava contra
`docs/reports/construction_core/builder_detail_baseline.v1.json`.

### 1.2 Buraco no R-18 (prova velha passa despercebida)

`capability_catalog.symbol_digest` cobre **só o corpo da função listada**. O fecho estático (funções de `tools.rooms`/`core`
alcançadas por nome) das 5 capacidades L2 tem **7–50 funções**, das quais 3–5 estão listadas. Ex.: `plan_cabinet` chama
`assembly.build_parts` — a geometria do gabinete — que **não** é símbolo provado: mudar `build_parts` mantém o `L2_PASS`
antigo. Medição desta data: nenhum helper de `tools.rooms`/`core` mudou desde as evidências vigentes (o único delta é a
camada de processo `tools.sketchup.process`, do #311, que falha alto e tem bateria L2 própria). **O buraco existia e não
havia sido explorado.** **Fechado na T0.1:** cada evidência L2 guarda `closure_digests` (fecho calculado no commit da prova,
`tools.rooms.evidence_closure`) e o gate do catálogo acusa `EVIDENCE_CLOSURE_STALE`; o backfill confirmou que as 6 evidências
vigentes casam com o HEAD.

### 1.3 Capacidades e cômodos

- 18 capacidades: **5 L2** (cozinha: layout galley, gabinete paramétrico, frente lisa, Shaker ×2), 12 L1, 1 UNTESTED;
  `visual = NOT_REVIEWED` em todas.
- 6 bindings sem capacidade: gaveta, tampo, recorte de cuba (cozinha); pérgola (varanda), porta de correr (closet),
  mesa (home office).
- Modularização por cômodo **feita** (FP-041→045): 9 módulos + `shared`, ownership e imports cruzados travados no CI.
  `balcony`, `closet`, `home_office` e `circulation` têm só perfil + conhecimento — **correto**: não se inventa brain
  para cômodo sem capacidade (FP-045). O que falta não é pasta, é capacidade provada por cômodo (FP-045 F7).

## 2. Definição de pronto de UMA microfase

1. **Um PR, uma intenção**, contra `develop`, com os 4 checks verdes no head exato.
2. **Teste vermelho antes** (comportamento novo ou negativo real); verde depois; nada de mutação que só derruba digest.
3. **Medida vem do pedido** (`{value, unit, origin}`), nunca default; recusa com código estável quando falta.
4. **Técnica nova cita recipe + trecho com `human_review` da mesma recipe**; sem isso a microfase para em L1/`BLOCKED_KNOWLEDGE_EVIDENCE`.
5. **Alvo** (FP-052): peça entregue em móvel real exige `reference_target.v1` aprovado para aquela peça; sem alvo, só microprova `PROPOSED`.
6. **Custo L2 declarado no PR:** quais capacidades ficam velhas; o PR refaz o L2 delas em commit limpo (skill `capability-l2-proof`).
7. **FP-047** antes × depois quando toca a planta (0 delta fora do escopo; preexistentes declarados).
8. **Aparência:** `PENDING_HUMAN` até o Felipe; pacote visual separado quando a aparência muda.
9. **Registro FP-042** (`tools.navigation.register_evidence`) e baseline do builder atualizado se ele mudou.

## 3. Ordem das trilhas

```
T0 core (prova e orquestração) ──► T1 cozinha Gen2 (detalhes) ──► T2 quarto Gen1→Gen2 ──► T3 sala/banho/serviço (reuso)
        │                               ▲  precisa de revisão de trecho + alvo (Felipe)        ▲ precisa de FP-048 frames
        └── FP-048 frames +Y/−Y ────────┴───────────────────────────────────────────────────────┘
```

## 4. Fila

Estado: `PRONTA` (sem bloqueio), `BLOQ-HUMANO` (só o Felipe destrava), `BLOQ-DEP` (espera outra microfase), `FEITA`.

| ID | Cômodo / componente | Entrega (uma coisa) | Prova | Custo L2 | Depende de | Spec dona | Estado |
|---|---|---|---|---|---|---|---|
| **T0.1** | todos / prova | `closure_digests` na evidência L2: fecho estático `tools.rooms`/`core` de cada símbolo, calculado **no commit da evidência**; gate do catálogo acusa fecho velho | testes do fecho (alias, import relativo, aninhada); migração prova igualdade commit×HEAD; teste com helper alterado → stale | nenhum se o fecho casa (medido: casa) | — | R-18 (FP-046/051) | FEITA |
| **T0.2** | cozinha / gabinete | `cabinet.sketchup.inspect` grava scratch em `runs/`, nunca ao lado de `.skp` de `artifacts/`/`fixtures/` (o Shaker já faz) | teste vermelho com caminho protegido; L2 de regressão | frente lisa, se o fecho mudar | T0.1 | FP-043 P6b | PRONTA |
| **T0.3** | todos / orquestração | `plan_furniture_goal()` puro: DAG de componentes → próximo gap; reporta `BLOCKED_TARGET_UNDEFINED` | unitários: reuso, gap, ciclo, prova velha, fonte sem revisão, schema, nunca executa | nenhum | T0.1 | FP-051 P1 | PRONTA |
| **T0.4** | todos / geometria | contrato de quadro `shared_transform.v1` (+Y cozinha × −Y quarto), conversão determinística 0/30/90/180°, ida e volta | propriedades + negativos | nenhum | — | FP-048 F1–F2 | PRONTA |
| **T0.5** | cozinha / posição | placement FP-050 registrado no catálogo (L1) e **gate obrigatório** em `cabinet_flow` e `shaker_flow` (sem bypass) | negativos: normal invertida, giro, corredor; positivo na planta real | frente lisa + Shaker (refazer os 2) | T0.1 | FP-051 P4, FP-052 T4 | PRONTA |
| **K1** | cozinha / tampo | tampo separado do gabinete como peça própria (grupo independente), balanço e espessura do pedido, chanfro/bevel real | L1 + micro-SKP L2 (seção, bbox, normais); FP-047 | novo (capacidade nova) | revisão do trecho 07:09–08:53 + alvo do tampo | FP-051 P2-like, FP-052 T3 | BLOQ-HUMANO |
| **K2** | cozinha / gaveta | **só a caixa** (laterais, traseira, base, fundo com espessuras do pedido); recipe dividida caixa × ferragem antes | L1 com dimensões variadas + L2 micro | novo | revisão do trecho da caixa (mín. possível dentro de 21:20–39:23) | FP-051 P2 | BLOQ-HUMANO |
| **K3** | cozinha / gabinete completo | composição: carcaça + frente (lisa/Shaker) + prateleira + gaveta opcional, uma raiz com partes semânticas | L1/L2 do móvel completo; assinatura e IDs estáveis | gabinete + frentes | K2, T0.3, T0.5 | FP-051 P3, FP-049 F1 | BLOQ-DEP |
| **K4** | cozinha / cuba | recorte passante no tampo (cuba/calha) com espessura remanescente válida | L2 micro + checagem de face residual | tampo | K1 + ficha técnica da cuba + ok hidráulico | recipe `cabinet.sink-and-wet-channel-cutouts` | BLOQ-HUMANO |
| **K5** | cozinha / puxador e giro | envelope de giro da porta e puxador como peça (não decoração) | L1 de colisão com giro; L2 | frentes | fonte + D49-06 | FP-049 D49-06 | BLOQ-HUMANO |
| **K6** | cozinha / rodapé (sóculo) | rodapé recuado da base como peça do pedido | L1 + L2 | gabinete | fonte/alvo a definir (nenhuma recipe cobre hoje) | FP-052 T2 | BLOQ-HUMANO |
| **B1** | quarto / guarda-roupa | corpo em **painéis** reusando a carcaça `shared.cabinet` no quadro −Y (fim do bloco `corpo`) | baseline Gen1 cai; L1 + L2; FP-047 na SUITE | novo (bedroom) | T0.4 | FP-049 F1–F3 | BLOQ-DEP |
| **B2** | quarto / portas do guarda-roupa | portas reusam frente lisa / Shaker (um produtor por tipo) | L2 com duas frentes | Shaker/frente | B1 + veredito L3 da Shaker | FP-049 F4 | BLOQ-DEP |
| **B3** | quarto / criado-mudo | criado-mudo como gabinete paramétrico pequeno (segundo consumidor real do `shared.cabinet`) | mesmo símbolo+versão em 2 cômodos, L2 de ambos | gabinete | T0.4 | FP-051 P7 | BLOQ-DEP |
| **L1** | sala / rack | rack como composição de `shared.cabinet` (portas/nichos), medidas do pedido | baseline do `rack_class` cai; L2 | gabinete | T0.4, K3 | FP-051 P7 | BLOQ-DEP |
| **W1** | banho / gabinete da pia | gabinete de banheiro = `shared.cabinet` + tampo (K1) + recorte (K4) | L2; wet-room guard | tampo/cuba | K1, K4 | FP-045 F7 | BLOQ-DEP |
| **S1** | serviço / armário | armário de lavanderia reusando carcaça + frentes | L2 | gabinete | T0.4 | FP-045 F7 | BLOQ-DEP |
| **C1** | closet / porta de correr | só depois de B1–B2; hoje advisory | — | — | B2 + fonte | FP-045 F7 | BLOQ-DEP |

Cama, sofá, poltrona e mesas (estofado/madeira maciça) **ficam Gen1** até existir alvo FP-052; a única mudança permitida
neles antes disso é mover medida embutida para a spec com origem (baseline cai, aparência igual, prova FP-047).

## 4.1 Trilha R — refatoração SOLID / design patterns e desempenho (pedido de 2026-10-22)

Mesmas regras da §2: um PR por item, saída provada idêntica (ou L2 refeito quando toca símbolo provado), sem padrão por dogma
(`.claude/rules` do workspace: interface só com ≥ 2 implementações reais ou fronteira de teste).

| ID | Onde | Entrega | Prova | Custo L2 | Estado |
|---|---|---|---|---|---|
| R0 | todo o código vivo | revisão de imports: 0 ciclos, 0 quebrados, 0 `import *`, 24 → 0 não usados; trava no CI | `tests/test_file_audit.py` | nenhum | FEITA (#364) |
| R1 | `shared/` | primitivas de peça (`part`, `darker`, `place_parts`, `parts_to_boxes`) saem do módulo do sofá para `shared/parts.py` (DIP/SRP); 14 consumidores | saída byte a byte idêntica; trava de direção | nenhum | FEITA (#367) |
| R2 | gates/planners | caches exatos nos 2 caminhos quentes (erosão do gate de circulação; geometria por consensus) — snapshot 5,25 s → 2,84 s | snapshot idêntico; `tests/test_geometry_hot_paths.py` | nenhum | FEITA (#369) |
| R3 | `shared/cabinet/sketchup.py` + Shaker | `scratch_dir(src, rótulo)` único para os dois inspects (DRY) e fim do scratch ao lado de `.skp` protegido (= T0.2) | teste vermelho com caminho protegido | gabinete + frente lisa (refazer L2) | PRONTA |
| R4 | registro de brains | `RoomBrain` (Protocol) para o registro que já existe (`build_brain_registry`): 5 implementações reais → port com tipo explícito | unitários do registro | nenhum (fora dos fechos L2) | PRONTA |
| R5 | builders Gen1 | medida embutida → spec com origem, um builder por PR, começando pelo guarda-roupa (10 literais) e criado-mudo (22) | baseline cai; aparência igual (FP-047) | nenhum (L1) | PRONTA |
| R6 | `interior/planners/living_room_planner.py`, `interior/class_specs/` | lógica de cômodo fora do módulo do cômodo → `tools/rooms/living/planning/` (modularização por cômodo) | ownership + suíte; consumidores conferidos | nenhum | BLOQ-DEP (mapear consumidores do pacote `interior`) |
| R7 | planners | índice espacial (`STRtree`) nos candidatos — **só se** a planta crescer (hoje ~10–20 obstáculos/cômodo) | igualdade do layout escolhido | — | ADIADA (ganho pequeno, risco de mudar ordem) |

## 5. Pacote de decisão do Felipe (o que destrava a fila)

1. **Veredito L3 da porta Shaker** — `artifacts/review/fp046/l3_package/` (#356): `APPROVED` ou `CHANGES_REQUESTED`. Destrava B2.
2. **Trecho 07:09–08:53 de `yt-cabinet-tips-2021` (tampo)** — confirmar SIM/NÃO:
   (a) o tampo é desenhado como peça própria, separada dos gabinetes (grupo independente);
   (b) o contorno cobre os módulos com **balanço** declarado;
   (c) a espessura é extrudada e o tampo isolado antes do perfil;
   (d) a borda recebe perfil real (arco/bevel que muda a silhueta), não só suavização de aresta.
   Destrava K1 (as medidas continuam vindo do pedido, nunca do vídeo).
3. **Caixa de gaveta em `yt-kitchen-joinery-2024`** — indicar o menor trecho dentro de 21:20–39:23 que mostra **só a caixa**
   (laterais, traseira, base, fundo com espessuras explícitas; frente separada). Ferragem/corrediça fica fora. Destrava K2.
4. **Alvo `planta_74.r004.kitchen_base_001`** (FP-052 T2, hoje `DRAFT_BLOCKED`): curar corpo, frente, prateleira e materiais e
   resolver LINEAR × Galley em L contra a arquitetura. Destrava a entrega de K3 na cozinha real.
5. **D-007** (vão = laje): decidir antes de qualquer mudança que mexa na SUITE 02 (B1).
6. Para K4: ficha técnica da cuba (perímetro de recorte) e ok hidráulico.

## 6. Métricas (só sobem/caem com prova)

| Métrica | 2026-10-22 | Fonte |
|---|---|---|
| capacidades L2 com prova vigente | 5 | `fp051_baseline` |
| literais embutidos Gen1 (dentro de funções) | 491 | `builder_detail_audit` |
| móveis compostos L2 na planta | 2 (gabinete liso, gabinete Shaker) | FP-051 §3.4 |
| móveis posicionados por gate (não pelo pedido) | 0 | FP-051 §3.4 |
| cômodos aprovados em L3 | 0 | catálogo `visual` |

## 7. Limites

Mapa de execução, não spec nova: regras, schemas e critérios de aceite moram nas specs donas. Estados da §4 valem para a data
do cabeçalho; quem conclui uma microfase atualiza a linha no mesmo PR. Nada aqui autoriza executar técnica sem fonte revisada,
aprovar aparência ou escolher medida que o pedido não trouxe.
