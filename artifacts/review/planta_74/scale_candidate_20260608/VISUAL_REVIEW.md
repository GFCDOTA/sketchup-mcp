# VISUAL_REVIEW — escala planta_74 (candidato PT_TO_M=0.0259)

> **Gate do Felipe.** Mudar a escala muda a geometria absoluta vs PDF → só você aprova.
> Preparado pela trilha V-Ray/mobiliar a pedido seu ("preparo candidato em paralelo").
> **NÃO aplicado** — default segue 0.0352 até seu OK.

## A pergunta
O build está na escala certa vs o PDF? Hoje o default é `PT_TO_M = 0.19/wall_thickness_pts = 0.0352`
(assume parede de 0.19 m). As **cotas impressas no PDF** dizem que isso está **~1.36× grande**.

## Evidência determinística (não é render — render esconde escala por zoom-to-fit)

### 1. Overlay consensus-sobre-PDF — `overlay_consensus_on_pdf.png`
As paredes (azul) e os cômodos (cores) da consensus caem **exatamente** sobre a planta do PDF.
→ **Geometria FIEL em pdf-points.** O erro é puramente o anchor pt→m (quanto vale 1 ponto em metros).

### 2. Cotas impressas do PDF vs build (o teste decisivo)
| cômodo | cota impressa no PDF | @0.0352 (atual) | @0.0259 (candidato) |
|---|---|---|---|
| SUÍTE 01 (r000) | 5.45 × 4.00 | 7.41 × 5.43 ❌ | **5.46 × 4.00** ✅ |
| SUÍTE 02 (r003) | 2.40 × 3.20 | 3.25 × 4.39 ❌ | **2.39 × 3.23** ✅ |
| COZINHA (r004) | ~2.90 | 3.90 ❌ | **2.87** ✅ |
| LAVABO (r007) | 1.55 × 1.20 | 2.04 × 1.61 ❌ | **1.50 × 1.18** ✅ |

**Área total (bbox c/ paredes):** atual **183 m²** (irreal p/ um apê "74") → candidato **~99 m²**. Fator **1.359×**.

### 3. Arcos de porta (prova scale-independent)
7 arcos de porta medidos no vetor do PDF vs largura na consensus: **ratio 0.98–1.09 = FALSE_ALARM(faithful)**
em todos. Como o ratio compara pts-vs-pts, ele independe do anchor → confirma de novo que **a geometria
está certa e só o pt→m está errado**.

## Anchor recomendado: **0.0259**
Bate as cotas de 4 cômodos quase exato (suíte 01 = 5.46 vs 5.45 impressa). O doc anterior
(`visual_regression_20260530T180822Z`) tinha estimado 0.0252 de uma cota só; com o conjunto multi-cômodo,
**0.0259** ajusta melhor. (Variação 0.0252–0.0259 ≈ 2.7%; sua revisão decide o valor final.)

## Como aplicar (se aprovado) — sem mutar fixture
O lever já existe: `build_plan_shell_skp.rb:33` lê `ENV['PT_TO_M']`. Buildar com `PT_TO_M=0.0259`
re-escala tudo (shell + móveis usam a mesma constante via `M(m)=m/PT_TO_M`). Default **não muda**
(quadrado_demo etc. seguem 0.0352). O doc anterior provou: a 0.0252 **todos os gates passam + pytest 223 passed**.

## Decisão (você)
- [ ] **APROVO 0.0259** → re-buildo planta_74 nessa escala, re-renderizo a sala/cozinha/quartos, viro default-por-build da trilha de interiores.
- [ ] **APROVO outro valor** (ex. 0.0252) → buildo no valor que você escolher.
- [ ] **REPROVO / mantém 0.0352** → segue como está; produto continua scale-robusto.

## Impacto no trabalho de PRODUTO já feito
Nenhum desperdício: a lógica de layout (eletro distintos, fluxo, clearances) é **scale-robusta** —
`M(m)=m/PT_TO_M` re-arranja proporcionalmente em qualquer escala. Os renders de validação de produto
(cozinha PASS etc.) julgam composição relativa, que o auto-fit preserva. Só os **números absolutos / m²**
mudam — que é exatamente o que a escala corrige.
