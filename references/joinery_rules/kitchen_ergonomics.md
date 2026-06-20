# Kitchen ergonomics — as medidas que separam planejado de builder-grade

> Conhecimento reutilizável pro auto-mobiliado (planta_74). Aqui estão **as medidas**,
> o **porquê** de cada uma e o **erro comum** que cada faixa existe pra matar.
> Auditadas por `tools/kitchen_ergonomics.py` (KITCHEN_DIMENSIONAL_AUDIT) contra a
> cozinha CONSTRUÍDA. A referência manda na MEDIDA; o PDF manda na POSIÇÃO
> (pia/parede/porta/hidráulica). Princípio mestre: `loose_object -> planned_niche_system`.

## Tabela mestra (cm)

| Métrica | Faixa | Default do projeto | Constante em `kitchen_layout.py` |
|---|---|---|---|
| Altura da bancada (countertop) | 85–92 | 90 | `COUNTER_H = 0.90` |
| Sóculo / rodapé recuado (toe-kick) | 10–15 | 12 | `TOE_KICK = 0.12` |
| Espessura do tampo | 2–4 | 3 | `TAMPO_THK = 0.03` |
| Profundidade do módulo base | 55–60 | 60 | `COUNTER_DEPTH = 0.60` |
| Profundidade do aéreo | 30–35 | 33 | `AEREO_DEPTH = 0.33` |
| Clearance bancada → base do aéreo | 50–60 | 60 | `AEREO_Z0 - COUNTER_H = 1.50 - 0.90` |
| Cooktop → coifa (under-cabinet) | 45–65 | ~57 | `(AEREO_Z0-0.05) - (COOK_Z0+0.015)` |
| Cooktop → coifa (chaminé/parede) | 70–80 | — | (tipo não usado na planta_74) |
| Largura da geladeira / torre | 55–75 (≈60 ref) | 70 | `GEL_W = 0.70` |
| Respiro lateral da geladeira (total) | 2–6 | — | nicho `GEL_W` − corpo inset |
| Largura de módulo (base e aéreo) | 35–65 (≈40/50/60) | — | porta/gaveta medida |
| Filler / painel de acabamento | 15–18 | 16 | `fb(..., 0.16, ...)` |
| Altura da borda da cuba (flush c/ tampo) | 85–92 | 90 | `PIA_Z0 = 0.90` |

`tools/kitchen_ergonomics.py` classifica cada métrica **PASS** (na faixa),
**WARN** (até 6 cm fora) ou **FAIL** (>6 cm fora, ou não medida = falha de medição).
Métrica zerada = FAIL: o auditor não achou a peça, o que normalmente é bug de layout,
não de medida.

---

## Detalhe métrica a métrica

### Altura da bancada — 85–92 cm (proj. 90)
- **Porquê:** altura de trabalho confortável em pé pra cortar/preparar sem curvar a
  lombar. 90 é o ponto canônico brasileiro; abaixo de 85 castiga as costas, acima de
  92 levanta o ombro pra cortar. Cuba e cooktop herdam essa altura (continuidade do
  plano de trabalho).
- **Erro comum:** mexer SÓ na altura da bancada e esquecer que a cuba (`PIA_Z0`) e o
  cooktop (`COOK_Z0`) precisam acompanhar — degrau no tampo é defeito visível e gera
  FAIL de continuidade.

### Sóculo / toe-kick — 10–15 cm (proj. 12), recuado
- **Porquê:** o recuo do rodapé deixa a ponta do pé entrar embaixo do armário, então
  você chega o corpo na bancada sem bater o dedão. É também onde mora o LED de piso e
  a "sombra" que faz o módulo parecer flutuar (ver `premium_details.md`).
- **Erro comum:** sóculo no nível da porta (sem recuo) = cara de móvel de loja, e o pé
  bate. Sóculo branco igual ao corpo apaga a sombra que dá leveza — use **grafite
  `[40,41,45]`** recuado.

### Espessura do tampo — 2–4 cm (proj. 3)
- **Porquê:** tampo fino lê **caro/contemporâneo**; tampo grosso (>4 cm) lê
  pedra-de-banheiro-anos-90 ou laminado pesado. 3 cm é o sweet spot de pedra (granito
  fino / quartzo / porcelanato).
- **Erro comum:** tampo de 5–8 cm "pra parecer robusto" — efeito inverso, envelhece a
  cozinha. Se precisa de borda gorda, faça **só a frente** engrossada (saia falsa),
  não o tampo inteiro.

### Profundidade do módulo base — 55–60 cm (proj. 60)
- **Porquê:** acomoda eletro embutido (cooktop, forno, cuba grande) e dá superfície de
  trabalho útil. 60 é padrão de bancada; a profundidade do TAMPO pode passar uns 2 cm
  da frente do armário (overhang) pra pingar fora da porta.
- **Erro comum:** base rasa (<50 cm) onde o cooktop não cabe, ou bancada virando sliver
  (`BANCADA_MIN_DEPTH = 0.35` — abaixo disso o código descarta: faixa estreita demais
  é lixo, não bancada).

### Profundidade do aéreo — 30–35 cm (proj. 33)
- **Porquê:** raso o suficiente pra não bater a cabeça/ombro sobre a bancada e ainda
  guardar louça/mantimento. Mais fundo que a faixa avança sobre quem trabalha.
- **Erro comum:** aéreo tão fundo quanto a base (60 cm) — bate a cabeça e escurece a
  bancada. Aéreo SEMPRE mais raso que a base.

### Clearance bancada → base do aéreo — 50–60 cm (proj. 60)
- **Porquê:** espaço de trabalho vertical. Abaixo de 50 cm vira uma "boca" apertada que
  esconde a bancada; acima de 60 cm o aéreo fica alto demais pra alcançar a prateleira
  de baixo.
- **Erro comum:** colar o aéreo na bancada pra "ganhar armário". Sufoca a área de
  trabalho e impede backsplash + LED sob aéreo. 60 cm é o respiro que deixa a luz de
  tarefa caber.

### Cooktop → coifa — 45–65 cm under-cabinet / 70–80 cm chaminé
- **Porquê:** distância de exaustão segura e eficiente. Coifa embutida/slim sob aéreo
  fica em 45–65; chaminé/parede aberta precisa subir pra 70–80 (chama mais exposta).
  Muito perto = risco de calor na coifa; muito longe = não puxa a fumaça.
- **Erro comum:** copiar 70–80 de foto de coifa-chaminé numa cozinha onde a coifa é
  **slim embutida no aéreo** (o tipo aprovado da planta_74) → fica alto e ineficiente.
  Tipo de coifa decide a faixa. Coifa **solta** pendurada longe do nicho é anti-padrão
  (ver `anti_patterns.md`).

### Geladeira / torre — 55–75 cm largura (≈60 ref), respiro 2–6 cm
- **Porquê:** geladeira freestanding padrão tem ~60–70 cm; o nicho precisa do corpo
  **mais** respiro lateral pra dissipar calor do compressor e pra a porta abrir sem
  raspar o painel. Respiro total 2–6 cm (alguns mm por lado).
- **Erro comum:** nicho justo no corpo (0 respiro) → porta raspa, ventilação ruim,
  geladeira "entalada". Ou geladeira **solta** ao lado da bancada sem torre/painel
  lateral = `loose_object` (corrigir → torre integrada, `appliance_niches.md`).

### Largura de módulo — 35–65 cm (base e aéreo)
- **Porquê:** ferragem de dobradiça/corrediça e peso de porta limitam o vão. Módulos
  reais andam em 40/50/60 cm; >65 cm a porta empena e a dobradiça sofre, <35 vira
  porta-frestinha inútil.
- **Erro comum:** uma "porta" única de 1,2 m cobrindo o módulo inteiro — lê fake (não
  existe porta planejada desse tamanho). Reparta em módulos; sobra → vira **filler**,
  não porta gigante.

### Filler / painel de acabamento — 15–18 cm (proj. 16)
- **Porquê:** o vão entre o último módulo e a parede/geladeira/coluna **nunca** fecha
  exato. O filler (painel cego do mesmo material) absorve essa folga e dá acabamento de
  parede-a-parede. Também serve de gable lateral da torre da geladeira.
- **Erro comum:** esticar uma porta pra fechar o vão (porta de medida estranha), ou
  deixar fresta aberta mostrando a parede. Folga >18 cm → repensar modulação, não
  filler gigante.

### Borda da cuba — 85–92 cm, **flush** com o tampo (proj. 90)
- **Porquê:** cuba sob bancada (undermount) ou flush herda a altura do tampo (90).
  Borda no nível do tampo = limpeza com rodo direto pra dentro, sem ressalto que junta
  sujeira.
- **Erro comum:** cuba de sobrepor com borda saliente acima do tampo (degrau que junta
  água/sujeira), ou cuba fora do `KITCHEN_SINK_ANCHOR` (ponto hidráulico do PDF) — ver
  `anti_patterns.md`. Bojo raso também é defeito (cuba rasa).

---

## Como usar isto
1. Construir/ajustar a cozinha em `tools/kitchen_layout.py` mexendo nas constantes
   acima, **não** em números mágicos espalhados.
2. Rodar `PT_TO_M=0.0259 python -m tools.kitchen_ergonomics r004` → ler o
   KITCHEN_DIMENSIONAL_AUDIT.
3. PASS na faixa, WARN tolerável (≤6 cm), FAIL = consertar antes de mostrar. Métrica
   zerada = peça sumiu, é bug de layout.
4. POSIÇÃO (pia/parede/porta) é gate à parte (sink_anchor_pdf + circulation) — medida
   boa com pia no lugar errado ainda reprova.
