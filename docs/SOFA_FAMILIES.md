# Famílias mínimas de sofá

Este documento define as **famílias canônicas de sofá** organizadas por eixo. Cada
família descreve, sempre nas mesmas 4 dimensões:

- **(a) O que MUDA** — o que distingue esta família das irmãs no mesmo eixo.
- **(b) O que PERMANECE** — o que é invariante (vale pra TODA a classe, não muda).
- **(c) PARÂMETROS do schema** — campos de `configs/sofa_schema.json` que controlam.
- **(d) FALHAS comuns** — erros típicos a evitar nesta família.

> **Regra raiz**: as regras vivem na **classe**, não num exemplar. Nada de hardcode
> de um único sofá. Forma antes de detalhe. Detalhe nunca esconde forma ruim.

---

## Schema paramétrico (referência)

Campos de `configs/sofa_schema.json`:

| Campo | Valores / Tipo |
|---|---|
| `id` | string (identificador do exemplar) |
| `family` | `straight` \| `loveseat` \| `chaise` \| `modular` \| `armchair` |
| `seat_count` | int |
| `seat_style` | `bench` \| `split` |
| `back_style` | `cushion` \| `tight` \| `pillow` |
| `arm_style` | `none` \| `slim` \| `track` \| `box` \| `wide` \| `rolled_soft` |
| `base_style` | `plinth` \| `recessed` \| `exposed_legs` |
| `leg_style` | `none` \| `tapered_wood` \| `block` \| `metal_stub` |
| `softness_level` | `low` \| `medium` \| `high` |
| `edge_radius_level` | `low` \| `medium` \| `high` |
| `seam_style` | `none` \| `simple` \| `piping_subtle` |
| `overall_width_m` | float (m) |
| `overall_depth_m` | float (m) |
| `overall_height_m` | float (m) |
| `seat_height_m` | float (m) |
| `seat_depth_m` | float (m) |
| `seat_cushion_thickness_m` | float (m) |
| `arm_width_m` | float (m) |
| `arm_height_m` | float (m) |
| `back_height_m` | float (m) |
| `back_thickness_m` | float (m) |
| `back_rake_deg` | float (graus) |
| `leg_height_m` | float (m) |
| `leg_inset_m` | float (m) |

### Faixas dimensionais realistas (m) — NÃO inventar fora disto

| Dimensão | Faixa |
|---|---|
| `seat_height_m` | 0.42 – 0.45 |
| `seat_depth_m` | 0.55 – 0.62 |
| `overall_height_m` | 0.78 – 0.90 |
| `overall_depth_m` | 0.88 – 1.00 |
| largura por assento (`overall_width_m` / `seat_count`) | 0.55 – 0.70 |
| `arm_width_m` (slim) | 0.10 – 0.16 |
| `arm_width_m` (track / box) | 0.18 – 0.26 |
| `arm_width_m` (wide) | 0.24 – 0.32 |
| `arm_height_m` | 0.55 – 0.68 |
| `back_thickness_m` | 0.16 – 0.24 (pillow até 0.28) |
| `back_rake_deg` | 6 – 12 |
| `leg_height_m` | 0.06 – 0.16 |
| `leg_inset_m` | 0.04 – 0.08 |
| `seat_cushion_thickness_m` | 0.12 – 0.18 |

---

## Princípios (valem pra todas as famílias)

1. **NÃO overfit** — regras vivem na classe, não num exemplar. Generalização é obrigatória.
2. **Forma antes de detalhe** — ordem de prioridade:
   silhueta > proporção > anatomia > maciez > composição > detalhe > material.
3. **Parecer estofado** — o sofá precisa ter: volume, topo coroado (não plano),
   bordas suaves, encosto com espessura + rake, braço com massa, base recuada,
   costura sutil.
4. **Generalização obrigatória** — uma regra só vale se vale pra família inteira.
5. **Detalhe nunca esconde forma ruim** — costura/piping não salva caixotão.

### Erros PROIBIDOS (qualquer família)

- `CAIXOTAO_FAIL` — sofá vira um cubo/caixa reta sem volume estofado.
- Piping grosso / facetado / "mangueira" / flutuante (descolado da costura).
- Encosto vertical tipo parede (sem rake, sem espessura).
- Assento reto tipo caixa (sem coroamento, sem maciez no topo).
- Braço monolítico (massa única sem leitura de braço estofado).
- Pés colados na borda (sem `leg_inset_m`).
- Ausência de base / sem recuo (`base_style` ignorado).
- Detalhe antes da forma (costura/material antes da silhueta correta).
- Hardcode de um único sofá (regra presa a um exemplar).
- Autoaprovação falsa — escrever "GPT PASS" no render. O agente NUNCA autojulga.

---

# Eixo 1 — Por TAMANHO

Controla principalmente `family`, `seat_count` e `overall_width_m`. A largura por
assento permanece em 0.55–0.70 m em TODAS as famílias deste eixo.

## 1.1 Armchair / poltrona
- **(a) MUDA**: `seat_count = 1`; largura total mínima; uma única posição de assento.
- **(b) PERMANECE**: proporção estofada (altura, profundidade), maciez, base recuada,
  braço com massa; largura por assento 0.55–0.70.
- **(c) PARÂMETROS**: `family=armchair`, `seat_count=1`, `overall_width_m≈0.70–0.95`,
  `overall_depth_m` e `overall_height_m` nas faixas padrão.
- **(d) FALHAS**: virar uma cadeira fina (perde volume estofado); braço sumir; tratar
  como "metade de loveseat" e distorcer proporção.

## 1.2 Loveseat
- **(a) MUDA**: `seat_count = 2` compacto; largura total menor que o "2 lugares" cheio.
- **(b) PERMANECE**: silhueta de sofá completo (dois braços, encosto contínuo),
  proporções e maciez idênticas.
- **(c) PARÂMETROS**: `family=loveseat`, `seat_count=2`,
  `overall_width_m≈1.20–1.45` (≤ 0.70/assento).
- **(d) FALHAS**: ficar largo demais e confundir com 2 lugares; encolher profundidade
  pra "caber" e perder conforto.

## 1.3 Dois (2) lugares
- **(a) MUDA**: `seat_count = 2` em largura plena.
- **(b) PERMANECE**: anatomia de sofá reto; profundidade e altura padrão.
- **(c) PARÂMETROS**: `family=straight`, `seat_count=2`,
  `overall_width_m≈1.40–1.70`.
- **(d) FALHAS**: largura/assento fora de 0.55–0.70; um único cushion gigante quando
  o estilo pede split.

## 1.4 Três (3) lugares
- **(a) MUDA**: `seat_count = 3`; largura total maior.
- **(b) PERMANECE**: mesma seção transversal (corte lateral) do 2 lugares — só o
  comprimento cresce.
- **(c) PARÂMETROS**: `family=straight`, `seat_count=3`,
  `overall_width_m≈1.90–2.20`.
- **(d) FALHAS**: esticar largura sem repetir módulos de assento (assento único
  esticado = caixotão); encosto vira parede longa sem rake.

## 1.5 Quatro (4) lugares
- **(a) MUDA**: `seat_count = 4`; comprimento longo, geralmente com split de assento.
- **(b) PERMANECE**: seção transversal e proporção; maciez constante ao longo do
  comprimento.
- **(c) PARÂMETROS**: `family=straight`, `seat_count=4`,
  `overall_width_m≈2.40–2.80`, normalmente `seat_style=split`.
- **(d) FALHAS**: bench único de 2.6 m (irreal e caixotão); encosto contínuo sem
  divisão visual; sag (afundamento) não modelado.

## 1.6 Modular
- **(a) MUDA**: composição por módulos repetíveis; pode formar L/U; chaise opcional.
- **(b) PERMANECE**: o **módulo** unitário respeita largura/assento, profundidade,
  altura e maciez padrão.
- **(c) PARÂMETROS**: `family=modular`, `seat_count` ≥ 3, dimensões por módulo dentro
  das faixas; `seat_style` tipicamente `split`.
- **(d) FALHAS**: módulos com proporções diferentes entre si; juntas (seams) que viram
  rachaduras; tratar o conjunto como uma caixa única.

---

# Eixo 2 — Por ASSENTO (`seat_style`, `seat_cushion_thickness_m`)

Em TODAS: o topo do assento é **coroado** (não plano), borda frontal suave, espessura
da almofada 0.12–0.18 m, `seat_height_m` 0.42–0.45, `seat_depth_m` 0.55–0.62.

## 2.1 Bench seat
- **(a) MUDA**: uma única almofada de assento contínua na largura toda.
- **(b) PERMANECE**: coroamento do topo, espessura e profundidade do assento.
- **(c) PARÂMETROS**: `seat_style=bench`, `seat_cushion_thickness_m` 0.12–0.18.
- **(d) FALHAS**: bloco reto sem coroamento (caixotão); borda frontal viva/facetada.

## 2.2 Split 2
- **(a) MUDA**: duas almofadas independentes lado a lado.
- **(b) PERMANECE**: mesma altura, profundidade e maciez por módulo; alinhamento do topo.
- **(c) PARÂMETROS**: `seat_style=split`, `seat_count=2`, espessura 0.12–0.18.
- **(d) FALHAS**: gap entre almofadas virando fenda profunda; almofadas de tamanhos
  diferentes; junta sem volume (parece corte, não estofado).

## 2.3 Split 3
- **(a) MUDA**: três almofadas independentes.
- **(b) PERMANECE**: módulo de assento idêntico ao split 2, repetido.
- **(c) PARÂMETROS**: `seat_style=split`, `seat_count=3`, espessura 0.12–0.18.
- **(d) FALHAS**: almofada central espremida; desalinhamento de topo; seams duros.

## 2.4 Chaise seat
- **(a) MUDA**: um módulo de assento estendido em profundidade (chaise longue).
- **(b) PERMANECE**: altura do assento, coroamento, maciez; conexão suave com o
  restante do sofá.
- **(c) PARÂMETROS**: `family=chaise`, `seat_style` (bench/split), `seat_depth_m`
  estendido apenas no módulo chaise (demais módulos 0.55–0.62).
- **(d) FALHAS**: chaise vira prancha plana sem coroamento; degrau abrupto entre
  chaise e assento normal; profundidade irreal.

---

# Eixo 3 — Por ENCOSTO (`back_style`, `back_height_m`, `back_thickness_m`, `back_rake_deg`)

Em TODAS: o encosto tem **espessura** (0.16–0.24 m, pillow até 0.28) e **rake** de
6–12°. NUNCA vertical tipo parede.

## 3.1 Cushion back
- **(a) MUDA**: encosto formado por almofadas soltas/semissoltas.
- **(b) PERMANECE**: espessura, rake e altura do encosto; topo arredondado.
- **(c) PARÂMETROS**: `back_style=cushion`, `back_thickness_m` 0.16–0.24,
  `back_rake_deg` 6–12, `back_height_m` na faixa.
- **(d) FALHAS**: almofada plana colada na parede (sem rake); espessura insuficiente.

## 3.2 Tight back
- **(a) MUDA**: encosto fixo/esticado, sem almofadas soltas, mas ainda estofado.
- **(b) PERMANECE**: espessura + rake; superfície macia e levemente coroada.
- **(c) PARÂMETROS**: `back_style=tight`, `back_thickness_m` 0.16–0.22,
  `back_rake_deg` 6–12.
- **(d) FALHAS**: virar painel reto/duro (parede); confundir "tight" com "fino demais".

## 3.3 Pillow back
- **(a) MUDA**: almofadas de encosto generosas/fofas, topo mais volumoso.
- **(b) PERMANECE**: rake e altura; integração com o assento.
- **(c) PARÂMETROS**: `back_style=pillow`, `back_thickness_m` até 0.28,
  `softness_level=high` típico, `back_rake_deg` 6–12.
- **(d) FALHAS**: travesseiros flutuando descolados; espessura > 0.28; perda de rake
  por excesso de volume.

## 3.4 Low back
- **(a) MUDA**: altura de encosto reduzida (perfil baixo).
- **(b) PERMANECE**: espessura e rake; ainda estofado e coroado.
- **(c) PARÂMETROS**: `back_height_m` reduzido (porém `overall_height_m` ≥ 0.78),
  `back_rake_deg` 6–12.
- **(d) FALHAS**: virar borda fininha tipo banco; rake some; `overall_height_m` cai
  fora da faixa.

## 3.5 High back
- **(a) MUDA**: encosto alto (mais apoio).
- **(b) PERMANECE**: espessura, rake, maciez; proporção geral coerente.
- **(c) PARÂMETROS**: `back_height_m` elevado, `overall_height_m` até 0.90,
  `back_rake_deg` 6–12.
- **(d) FALHAS**: ultrapassar `overall_height_m` 0.90; virar painel vertical alto e
  reto (parede); topo plano.

---

# Eixo 4 — Por BRAÇO (`arm_style`, `arm_width_m`, `arm_height_m`)

Em TODAS (exceto `none`): o braço tem **massa estofada** legível, topo suave,
`arm_height_m` 0.55–0.68. NUNCA monolítico/duro.

## 4.1 No arm
- **(a) MUDA**: ausência de braço (armless).
- **(b) PERMANECE**: silhueta de assento/encosto estofada; laterais acabadas e suaves.
- **(c) PARÂMETROS**: `arm_style=none` (`arm_width_m`/`arm_height_m` ignorados).
- **(d) FALHAS**: lateral viva/cortada sem acabamento; confundir armless com módulo
  modular incompleto.

## 4.2 Slim arm
- **(a) MUDA**: braço fino.
- **(b) PERMANECE**: massa estofada (mesmo fina), topo arredondado, altura na faixa.
- **(c) PARÂMETROS**: `arm_style=slim`, `arm_width_m` 0.10–0.16, `arm_height_m` 0.55–0.68.
- **(d) FALHAS**: braço vira lâmina/parede fina sem volume; largura < 0.10.

## 4.3 Track arm
- **(a) MUDA**: braço reto e baixo-perfil, linha contínua com o encosto.
- **(b) PERMANECE**: massa média, topo levemente suave, altura na faixa.
- **(c) PARÂMETROS**: `arm_style=track`, `arm_width_m` 0.18–0.26, `arm_height_m` 0.55–0.68.
- **(d) FALHAS**: arestas vivas/facetadas (track ≠ caixa dura); largura fora de 0.18–0.26.

## 4.4 Box arm
- **(a) MUDA**: braço de seção mais quadrada/estruturada.
- **(b) PERMANECE**: ainda estofado, bordas com `edge_radius` suavizando os cantos.
- **(c) PARÂMETROS**: `arm_style=box`, `arm_width_m` 0.18–0.26,
  `edge_radius_level` medium/high.
- **(d) FALHAS**: cubo de cantos vivos (caixotão de braço); `edge_radius_level=low`
  deixando duro; braço monolítico.

## 4.5 Wide arm
- **(a) MUDA**: braço largo/robusto.
- **(b) PERMANECE**: topo suave e estofado; proporção com o corpo do sofá.
- **(c) PARÂMETROS**: `arm_style=wide`, `arm_width_m` 0.24–0.32, `arm_height_m` 0.55–0.68.
- **(d) FALHAS**: braço dominar a largura útil do assento; bloco reto largo sem maciez.

## 4.6 Rolled soft arm
- **(a) MUDA**: braço com rolo arredondado para fora (rolled), bem macio.
- **(b) PERMANECE**: altura na faixa; transição suave braço→encosto→assento.
- **(c) PARÂMETROS**: `arm_style=rolled_soft`, `arm_width_m` 0.18–0.32,
  `softness_level=high`, `edge_radius_level=high`.
- **(d) FALHAS**: rolo facetado/poligonal (perde maciez); rolo grande demais virando
  "almofada flutuante"; massa monolítica sem o enrolar.

---

# Eixo 5 — Por BASE (`base_style`, `leg_style`, `leg_height_m`, `leg_inset_m`)

Em TODAS: existe **base com recuo** (`leg_inset_m` 0.04–0.08) — pés/base NUNCA colados
na borda. Quando há pernas, `leg_height_m` 0.06–0.16.

## 5.1 Plinth base
- **(a) MUDA**: base sólida tipo pódio/plinto sob o sofá.
- **(b) PERMANECE**: recuo da base (sombra), corpo estofado por cima.
- **(c) PARÂMETROS**: `base_style=plinth`, `leg_style=none`, `leg_inset_m` 0.04–0.08
  (recuo do plinto), `leg_height_m` baixo/zero.
- **(d) FALHAS**: plinto rente à borda (sem recuo/sombra); plinto = continuação do
  caixotão; ausência de base.

## 5.2 Recessed base
- **(a) MUDA**: base recuada (escondida), sofá "flutua" visualmente.
- **(b) PERMANECE**: recuo pronunciado; corpo estofado com leitura clara.
- **(c) PARÂMETROS**: `base_style=recessed`, `leg_inset_m` no topo da faixa (~0.06–0.08).
- **(d) FALHAS**: base visível quando deveria recuar; recuo zero (`leg_inset_m` baixo).

## 5.3 Exposed legs (genérico)
- **(a) MUDA**: pernas aparentes elevando o corpo.
- **(b) PERMANECE**: recuo dos pés em relação à borda; altura de perna na faixa.
- **(c) PARÂMETROS**: `base_style=exposed_legs`, `leg_style` (ver 5.4–5.6),
  `leg_height_m` 0.06–0.16, `leg_inset_m` 0.04–0.08.
- **(d) FALHAS**: pés colados na borda; pernas altas demais (> 0.16) deixando o sofá
  "em palafitas"; ausência de inset.

## 5.4 Wooden tapered legs
- **(a) MUDA**: pernas de madeira cônicas (estilo mid-century).
- **(b) PERMANECE**: 4 pés recuados, altura na faixa, corpo estofado por cima.
- **(c) PARÂMETROS**: `base_style=exposed_legs`, `leg_style=tapered_wood`,
  `leg_height_m` 0.10–0.16, `leg_inset_m` 0.04–0.08.
- **(d) FALHAS**: cone facetado/grosseiro; pé reto (não cônico); colado na borda.

## 5.5 Block legs
- **(a) MUDA**: pés em bloco (cúbicos/retangulares), baixos.
- **(b) PERMANECE**: recuo e proporção; corpo estofado.
- **(c) PARÂMETROS**: `base_style=exposed_legs`, `leg_style=block`,
  `leg_height_m` 0.06–0.12, `leg_inset_m` 0.04–0.08.
- **(d) FALHAS**: blocos enormes virando segunda base; cantos vivos exagerados; colados
  na borda.

## 5.6 Metal stub legs
- **(a) MUDA**: pés metálicos curtos (stub).
- **(b) PERMANECE**: recuo, baixa altura, corpo estofado.
- **(c) PARÂMETROS**: `base_style=exposed_legs`, `leg_style=metal_stub`,
  `leg_height_m` 0.06–0.10, `leg_inset_m` 0.04–0.08.
- **(d) FALHAS**: stub tão curto que some o vão (vira plinto disfarçado); pé fino tipo
  agulha irreal; colado na borda.

---

## Costura / detalhe (transversal — `seam_style`, `edge_radius_level`, `softness_level`)

Aplicável a TODAS as famílias, sempre por ÚLTIMO (detalhe nunca antes da forma):

- `seam_style=none` — sem costura aparente.
- `seam_style=simple` — costura discreta nas junções.
- `seam_style=piping_subtle` — vivo/piping **sutil**: linha fina, acompanhando a
  costura, NUNCA grosso/facetado/mangueira/flutuante.
- `edge_radius_level` e `softness_level` controlam o quanto o estofado parece macio —
  subir junto com `pillow`/`rolled_soft`; nunca usar detalhe pra disfarçar caixotão.
