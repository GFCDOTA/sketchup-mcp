# Learning Report — Group_60.skp (KIVIK com chaise)

**Família:** sofá-seccional de tecido, baixo e horizontal, com chaise longue (canto/L).
Tipo: KIVIK-like (IKEA). 11 peças semânticas, escala real.
**Não** é poltrona compacta nem sofá-cama estruturado — é "sofá macio de estar",
volumetria pesada feita de **panéis encorpados** sobre base baixa.

**O que o faz parecer real (renders iso/front/top):**
1. Almofadas **separadas e legíveis** (assentos e encostos como peças distintas — ver top view: retângulos individuais, não uma massa).
2. **Material escuro com textura de tecido** (Dansbo Dark Gray ~[37,38,33]) — a malha capta sombra/microrrelevo; o olho lê "tecido", não "plástico".
3. **Bordas arredondadas/macias** em tudo — nada de quina viva.
4. Proporção **baixa + longa** (2.84 × 1.66 × 0.93) com braços e encosto encorpados.

---

## (1) ASSENTO
- Construção em **2 camadas**: plataforma de assento (~0.28 m) + almofada solta (~0.15 m) → altura de sentar ~**0.43 m** (ergonomia real de sofá).
- Assentos são **almofadas individuais** (~0.9 × 0.7 × 0.15), não um tampo único.
- **Lição:** assento = `base de assento` + `almofada` (duas primitivas empilhadas), modulado por nº de lugares. Nossa `seat_cushion` sozinha não modela a plataforma.

## (2) ENCOSTO
- Encostos **finos** (~0.15 m de espessura real) mas **lêem encorpados pela maciez** (bordas roladas + textura). Volume aparente ≠ espessura física.
- São **peças separadas** por lugar, ligeiramente reclinadas/macias no topo.
- **Lição:** encosto fino + topo abaulado + canto rolado > encosto grosso de caixa. O residual atual (topo em degrau / rounded box) destrói exatamente esse efeito.

## (3) BRAÇO
- Braços **substanciais e encorpados**, mesma família macia (não um tubo, não uma tábua). Altura ~ topo do encosto, dão a "moldura" do sofá.
- **Lição:** braço é uma primitiva macia própria (crowned box alto e largo), não reaproveitar a almofada. Largura do braço é proporção-chave do volume.

## (4) BASE / PÉS
- Plataforma assenta sobre **4 pés BAIXOS** — quase escondidos; dão um respiro de sombra sob a base sem levantar o móvel.
- **Lição:** pés são **baixos e discretos** (sliver de sombra), não pernas palito. Sem pés a base "derrete" no chão; pés altos descaracterizam o KIVIK.

## (5) SOFTNESS
- A maciez vem de **3 fontes combinadas**: (a) raio de borda generoso em todas as peças, (b) topo **abaulado contínuo** das almofadas (dome, não degrau), (c) textura de tecido que quebra a luz.
- **Lição:** softness é propriedade transversal (raio + dome + textura), não um parâmetro de uma peça. Tem que ser **classe/mixin** aplicável a qualquer primitiva.

## (6) DETALHE SEM EXAGERO
- Detalhe que importa: **separação das almofadas** (linhas de costura/gap) e **arredondamento**. Não há botões, capitonê, pés torneados, costura decorativa.
- **Lição:** o realismo é por **proporção + material + separação modular**, não por micro-geometria. Adicionar enfeite seria ruído.

## (7) O QUE VIRA REGRA SISTÊMICA
Ver bloco final.

---

## Nossas primitivas: forte vs fraco vs esta ref

| Aspecto | Nossa primitiva atual | Gap vs Group_60 |
|---|---|---|
| Almofada assento | `seat_cushion` (rounded box) | topo em **degrau**, falta plataforma de base, falta dome contínuo |
| Almofada encosto | `back_cushion` (rounded box) | mesmo degrau; falta topo abaulado |
| Caixa macia | `crowned_box` | base OK, mas raio/coroamento subdimensionado pra leitura "macia" |
| Braço | (sem primitiva dedicada) | **falta** — braço encorpado é peça própria |
| Base de assento | (ausente) | **falta** — assento real é 2 camadas |
| Pés | (não modelados) | **falta** — 4 pés baixos |
| Material | linho claro **chapado, sem textura** | gap forte: refs reais são **escuros + texturizados**; chapado lê "plástico/maquete" |
| Modularidade | almofada única | refs são **N peças por lugar** |

**Proporções que o gerador deveria aprender (normalizar por nº de lugares, não copiar cotas):**
- altura de sentar ≈ 0.43 m (plataforma ~0.28 + almofada ~0.15)
- profundidade total ≈ 1.6× a profundidade do assento útil
- altura/comprimento baixa (~0.93 alt vs 2.84 comp → razão ~0.33)
- espessura de encosto fina (~0.15) mas com volume aparente maior pelo coroamento
- pés baixos (sliver), não pernas

---

## REGRAS SISTÊMICAS PROPOSTAS
- **softness vira mixin transversal** (`Softness`): raio de borda generoso + **dome contínuo** (não rounded-box) aplicável a qualquer primitiva — mata o residual de "topo em degrau" de uma vez, não por exemplar.
- **Almofada = dome contínuo** no `seat_cushion`/`back_cushion`: trocar rounded box por superfície abaulada (perfil C2), parametrizada por raio e "puffiness".
- **Assento de 2 camadas**: nova primitiva `seat_platform` (base ~0.28) + almofada solta (~0.15) → altura de sentar como parâmetro derivado (~0.43), não hardcode.
- **Braço encorpado vira primitiva própria** (`arm_bolster`, crowned box alto/largo), com largura como proporção do volume — não reusar a almofada.
- **Pés baixos como componente padrão** (`low_feet`, 4×) com sliver de sombra; parâmetro on/off + altura mínima.
- **Modularidade por nº de lugares no schema**: `sofa_schema.json` gera N almofadas de assento + N de encosto separadas (com gap/linha entre elas) em vez de massa única — a separação é o que lê "real".
- **Material: biblioteca de tecidos com TEXTURA**, default escuro (ex. `dansbo_dark_gray` ~[37,38,33] + bitmap de malha). Banir tecido **chapado sem textura** no gate de aparência.
- **Proporções como constantes nomeadas no spec** (seat_height≈0.43, depth_ratio≈1.6, height/length≈0.33, backrest_thin≈0.15, feet=low) — gerador interpola por tamanho, nunca copia geometria.
- **Gate de aparência ganha 3 checagens determinísticas**: (a) almofadas separadas (count ≥ nº lugares), (b) material tem textura (não flat color), (c) presença de pés baixos. Falha → VISUAL_REVIEW.
