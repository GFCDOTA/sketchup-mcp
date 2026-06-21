# Learning Report — `modern_dark_gray` (sofá reto baixo, 3 lugares)

Fonte: renders iso/front/top em `references/sofas/audit/modern_dark_gray/`.
Regra: NÃO copiar geometria. Extrair só **proporção / anatomia / softness / material** como benchmark, virando melhoria **reutilizável de classe**.

## Identificação
- **Família**: `straight` (reto). 3 lugares.
- **Tipo**: sofá baixo-e-largo "lounge", low-back, contemporâneo escuro.
- **Escala**: modelo veio em **~meia escala** — bbox medido `1.336 × 0.447 × 0.394 m`, real ≈ **`2.68 × 0.90 × 0.79 m`** (×2). Lição abaixo.
- `single_block=False`, ~17 definições → malha multi-peça (assento/encosto/braço/base separados), não um bloco só. Bate com a nossa direção (`single_block=False`).
- **O que faz parecer real**: 3 almofadas de assento SEPARADAS abauladas + tufting horizontal sutil no encosto + material escuro com variação tonal (não chapado) + base sólida baixa que ancora o volume.

## (1) ASSENTO
- **3 almofadas SEPARADAS** (seat_style `split`), uma por lugar — gaps visíveis no top/front criam ritmo. Confirma nosso default `split`.
- Almofadas **abauladas/macias** (dome contínuo), não rounded box em degrau. **Bate exatamente com o residual conhecido** (topo em degrau → trocar por dome contínuo). Aqui é a prova visual de que `crowned_box` tem que ler como cúpula, sem patamar plano.
- Frente da almofada **rola pra baixo** (não aresta viva na frente). Proporção: assento largo e raso visualmente, altura de assento baixa.

## (2) ENCOSTO
- **LOW BACK** — encosto baixo, mal passa do assento. Altura do encosto pequena vs profundidade. Nosso `back_height_m` range `[0.32, 0.62]` cobre, mas o **default 0.22 de thickness + rake 9°** tende a um encosto mais "ereto/grosso"; a ref pede **low-back fino e quase deitado**.
- **TUFTING HORIZONTAL SUTIL**: canaletas horizontais (channel/biscuit) ao longo do encosto — não é botão, é **vinco horizontal**. É o detalhe que mais "vende" o estofado. **Não temos primitiva pra isso** (só costura de perímetro `thin_seam_line`). Gap claro.
- Encosto também segmentado em almofadas (acompanha os 3 lugares).

## (3) BRAÇO
- Braços **baixos e largos**, no nível (ou pouco acima) do assento — leem como continuação da base, tipo "track/box baixo", NÃO rolled alto. Topo levemente suave, não cilíndrico.
- Lição: a regra `seat_top_below_arm_top_max_m` (0.16) está certa, mas esta ref quer braço **quase rente ao assento** → o gerador deveria suportar braço baixo sem disparar proporção implausível.

## (4) BASE / PÉS
- **Base sólida baixa / plinth recuado** — sem pernas visíveis aparentes; o volume escuro toca quase o chão com leve recuo. `base_style` `plinth`/`recessed`, `leg_style` próximo de `none`/`block` baixo.
- Ancora visual: a base contínua escura dá peso e faz o conjunto "assentar". Não é exposed_legs.

## (5) SOFTNESS
- Softness **alta nas almofadas** (dome generoso, frente rolada) mas **arestas da base/estrutura mais vivas** (a caixa-base é mais reta). Ou seja: **softness não é global** — almofada macia + carcaça firme. Nossa `SOFT` é aplicada por-primitiva, o que é bom, mas o gerador precisa **diferenciar softness de cushion vs softness de base** explicitamente.
- Crown deve ler como **cúpula contínua** (residual). `medium`/`high` crown servem; o problema é a topologia (degrau), não o valor.

## (6) DETALHE SEM EXAGERO
- O tufting é **sutil**: vincos rasos, espaçados, horizontais — não esculpe demais. Costura de perímetro quase invisível.
- Lição: detalhe é **subordinado à forma**. Channel horizontal raso > botão fundo. Material escuro **esconde geometria** — então o detalhe tem que vir de **canaleta + variação tonal**, não de relevo agressivo.
- **Essenciais**: 3 almofadas separadas, dome contínuo, low-back, tufting horizontal sutil, base sólida, material escuro com variação. **Dispensáveis**: piping grosso, botões profundos, pernas torneadas, rolled arm alto.

## (7) MATERIAL (gap forte vs nosso atual)
- Ref = **escuro (charcoal/preto)** com **variação tonal** (várias "DarkGray/myBlack") → não chapado. Lê como tecido/couro escuro com sombreamento por face.
- Nosso atual = **linho claro CHAPADO, sem textura**. Gap duplo: (a) cor clara, (b) flat sem variação. Sob luz, chapado claro "achata" a forma; escuro com variação **realça o dome e o tufting**.

## Nossas primitivas: fracas vs esta ref
| Aspecto | Ref | Nosso atual | Veredito |
|---|---|---|---|
| Almofada (dome) | cúpula contínua | `crowned_box` ainda lê degrau (residual) | **fraco — em correção** |
| Tufting horizontal | canaletas no encosto | inexistente (só `thin_seam_line` de perímetro) | **faltando** |
| Material | escuro c/ variação tonal | linho claro chapado | **fraco** |
| Base | plinth sólido baixo | `block_leg`/`tapered_leg` ok, plinth ok | adequado |
| Low-back fino quase deitado | sim | defaults tendem a ereto/grosso | **ajustar via config, não primitiva** |
| Split 3 lugares | sim | suportado (`split`) | ok |
| Validação de escala | — | schema valida faixas em m | **forte (ver lição escala)** |

## Lição de ESCALA
Modelos 3DW podem vir **fora de escala real** (este veio ~½). Nosso schema valida `overall_*` em **metros com faixas plausíveis** (`overall_width_m [1.10, 3.40]` etc.), o que **rejeitaria** um sofá de 1.34 m de largura travestido de 3 lugares. Isso é uma **proteção que funciona** — manter e reforçar: o gerador opera em metros e o gate de faixa é a defesa contra import fora de escala. Benchmark de proporção deve ser sempre normalizado (×fator) antes de comparar.

---

## REGRAS SISTÊMICAS PROPOSTAS
- **Primitiva nova `channel_tufting` (classe)**: gera N canaletas HORIZONTAIS rasas e suaves numa face de encosto (params: n_channels, depth_m≈0.01–0.02, subtle). Subordinada à forma, guard-railed (degrada se falhar). Reutilizável por qualquer sofá com `back_style=tight/cushion`.
- **`back_style` ganha valor `channel_tufted`** no schema (enum) + spec, mapeando pra `channel_tufting`. Tufting deixa de ser "1 exemplar" e vira opção de classe.
- **Material escuro com variação tonal como CLASSE de material**: helper `mat()` ganha variante que aplica leve jitter tonal por-face (ou 2–3 tons próximos charcoal/black) em vez de cor flat única. Default de tecido escuro disponível; remove o "chapado".
- **Separar `softness` de cushion vs base** no schema: `cushion_softness_level` e `frame_edge_radius_level` distintos (hoje há `softness_level` + `edge_radius_level`, mas o gerador deve aplicar cushion=alto / frame=vivo por padrão). Almofada macia ≠ carcaça macia.
- **Fechar residual do dome contínuo** na `crowned_box` (sem patamar plano no topo) e adicionar **assertiva no gate**: top da almofada não pode ter face horizontal plana > X% da área (detecta regressão "degrau").
- **Perfil low-back lounge como preset de família**: combinação `back_height` baixo + `back_rake` alto (≈14–16°) + braço baixo (`arm_height≈seat_top`) validada como coerente — o gerador não deve penalizar braço quase-rente-ao-assento.
- **Base `plinth` sólida baixa** continua 1ª classe (ancora o volume); manter `legs_must_be_inset` e permitir `leg_style=none` com plinth sem warning.
- **Reforçar gate de ESCALA**: ao importar/benchmarkar referência, normalizar bbox pra metros e exigir faixas do schema ANTES de extrair proporção (proteção já existente — documentar como regra).
- **Benchmark de proporção normalizado**: comparações de fidelidade de sofá usam razões (w:d:h, seat:back:arm) e não medidas absolutas, pra serem imunes a refs em meia-escala.

---
**Resumo (1 linha):** Ref escura low-back 3-lugares ensina dome de almofada CONTÍNUO + tufting HORIZONTAL sutil + material escuro com variação tonal + base plinth sólida e softness separada (cushion macio / carcaça firme) — gaps reais nossos = degrau na almofada, tufting inexistente e linho claro chapado; tudo deve virar primitiva/enum/material de CLASSE, com o gate de escala-em-metros mantido como defesa contra refs fora de escala.
