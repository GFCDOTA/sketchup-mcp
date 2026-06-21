# SPEC DA CLASSE `sofa`

> **Escopo:** esta spec descreve a **classe** sofá — o conjunto de regras, anatomia e proporções que valem para QUALQUER sofá gerado pelo builder paramétrico. Ela **NÃO** descreve um sofá específico.
> **Schema:** os campos referenciados vivem em `configs/sofa_schema.json`. Nenhuma regra deve depender de um exemplar.

## Princípios da classe (lei acima de tudo)

1. **NÃO overfit** — as regras vivem na CLASSE, nunca num exemplar. Proibido hardcode de um único sofá.
2. **Forma antes de detalhe** — ordem inviolável de prioridade:
   `silhueta > proporção > anatomia > maciez > composição > detalhe > material`.
3. **O sofá precisa PARECER estofado** — volume, topo coroado, bordas suaves, encosto com espessura + rake, braço com massa, base recuada, costura sutil.
4. **Generalização obrigatória** — uma regra só entra na classe se valer para todas as `family` (straight, loveseat, chaise, modular, armchair) e todos os estilos.
5. **Detalhe nunca esconde forma ruim** — costura/piping/material não corrigem silhueta de caixote. Se a forma está errada, conserta-se a forma, não o detalhe.

---

## 1. Anatomia universal

Todo sofá da classe é composto pelas zonas abaixo. Cada zona existe sempre — quando ausente (ex.: braço), a ausência é **intencional e justificada**, não um esquecimento.

| Zona | Descrição | Campo(s) do schema |
|------|-----------|--------------------|
| **Base / apoio no chão** | Estrutura que sustenta e levanta o volume do piso. Define se o sofá "flutua" (pés expostos), assenta (plinto) ou recua (recessed). Nunca um bloco maciço sem intenção. | `base_style` (plinth\|recessed\|exposed_legs), `leg_style`, `leg_height_m`, `leg_inset_m` |
| **Assento** | Plano de sentar, estofado, com espessura real de almofada. Pode ser banco único (bench) ou dividido (split). | `seat_style` (bench\|split), `seat_height_m`, `seat_depth_m`, `seat_cushion_thickness_m` |
| **Encosto** | Apoio das costas, com espessura própria e inclinação (rake). Estilos: almofada solta, esticado/firme, travesseiro gordo. | `back_style` (cushion\|tight\|pillow), `back_height_m`, `back_thickness_m`, `back_rake_deg` |
| **Braços** | Massa lateral que delimita o assento. Pode não existir (`none`) — ausência válida em armchair sem braço ou bancos modulares de extremidade aberta. | `arm_style` (none\|slim\|track\|box\|wide\|rolled_soft), `arm_width_m`, `arm_height_m` |
| **Apoio no chão (pés/plinto/base)** | Materializa o contato com o piso: pés afilados de madeira, bloco, pino metálico, ou nenhum (plinto/recessed). Recuado da borda. | `leg_style` (none\|tapered_wood\|block\|metal_stub), `leg_height_m`, `leg_inset_m` |
| **Zonas de folga / recuo** | Espaços de respiro: recuo da base, folga entre almofadas, recuo dos pés. Pequenas, intencionais, dão leitura de estofado (não de bloco). | `leg_inset_m`, folgas derivadas de `softness_level` / `edge_radius_level` |
| **Superfície estofada** | A "pele" macia: faces frontais do assento, topo do encosto e braços levemente coroadas e arredondadas. | `softness_level`, `edge_radius_level` |
| **Costura / piping (opcional)** | Detalhe de acabamento ao longo das arestas estofadas. Sutil ou ausente. NUNCA antes da forma. | `seam_style` (none\|simple\|piping_subtle) |

**Justificativa de ausência de braços:** permitido em `arm_style = none` quando a `family` é `armchair` minimalista, `modular` de extremidade aberta, ou um banco/daybed. A ausência deve ser deliberada e coerente com a silhueta — não um braço esquecido.

---

## 2. Dimensões plausíveis (faixas em metros)

> **NÃO inventar fora destas faixas.** Faixas realistas (m):

| Parâmetro | Campo do schema | Faixa (m) |
|-----------|------------------|-----------|
| Altura do assento | `seat_height_m` | 0.42 – 0.45 |
| Profundidade do assento | `seat_depth_m` | 0.55 – 0.62 |
| Altura total | `overall_height_m` | 0.78 – 0.90 |
| Profundidade total | `overall_depth_m` | 0.88 – 1.00 |
| Largura por lugar | (deriva `overall_width_m` / `seat_count`) | 0.55 – 0.70 |
| Largura do braço — slim | `arm_width_m` (slim) | 0.10 – 0.16 |
| Largura do braço — track/box | `arm_width_m` (track/box) | 0.18 – 0.26 |
| Largura do braço — wide | `arm_width_m` (wide) | 0.24 – 0.32 |
| Altura do braço | `arm_height_m` | 0.55 – 0.68 |
| Espessura do encosto | `back_thickness_m` | 0.16 – 0.24 (pillow até 0.28) |
| Inclinação do encosto | `back_rake_deg` | 6 – 12 graus |
| Altura dos pés | `leg_height_m` | 0.06 – 0.16 |
| Recuo dos pés | `leg_inset_m` | 0.04 – 0.08 |
| Espessura da almofada do assento | `seat_cushion_thickness_m` | 0.12 – 0.18 |

`overall_width_m` resulta de `seat_count × width_per_seat (0.55–0.70)` mais a soma dos braços. `id`, `family`, `seat_count` parametrizam a instância; as faixas acima são limites duros da classe.

---

## 3. Regras de proporção

- **Braço não esmaga o assento:** a soma das larguras dos braços nunca rouba a área útil de sentar. Braço `wide` exige `overall_width_m` proporcionalmente maior; senão, rebaixar para `track`/`slim`.
- **Assento não parece tijolo fino:** `seat_cushion_thickness_m` dentro de 0.12–0.18 — almofada com volume, nunca uma lasca.
- **Encosto não parece tábua:** `back_thickness_m` ≥ 0.16 e sempre com rake (`back_rake_deg` 6–12). Espessura + inclinação = leitura de estofado, não de divisória.
- **Base não parece bloco maciço sem intenção:** toda base comunica uma escolha — pés que levantam, plinto que assenta, ou recuo que sombreia. Volume sólido do piso ao assento sem recuo nem pés = proibido.
- **Pés recuados:** `leg_inset_m` 0.04–0.08 — os pés/base recuam da borda externa, criando sombra e leveza. Pé colado na quina = erro.
- **Almofadas respiram:** folgas pequenas e intencionais entre almofadas de assento (split) e encosto. Folga grande = bagunça; folga zero = bloco fundido.
- **Sofá não parece caixas empilhadas:** as zonas (base, assento, encosto, braço) se relacionam por transições suaves e recuos, não como caixotes justapostos. A silhueta lê como um objeto único estofado.

---

## 4. Regras de SOFTNESS (geometria SketchUp)

A maciez é construída na geometria — não no material. Implementar com:

- **Bordas arredondadas** em todas as arestas externas estofadas (assento, encosto, braço, topo).
- **Topo levemente coroado** (crown): faces superiores de assento e braço com leve abaulamento, nunca planas-perfeitas.
- **Transições suaves** entre zonas: chanfros/raios pequenos onde uma zona encontra a outra (assento↔encosto, braço↔assento).
- **Face frontal do assento macia:** a aresta dianteira do assento é arredondada/coroada, dando o "rolinho" de almofada.
- **Encosto com espessura:** volume 3D real (`back_thickness_m`), nunca uma face fina.
- **Braço com quinas menos duras:** arestas do braço com raio; `rolled_soft` recebe o maior arredondamento.
- **Costuras sutis:** quando `seam_style = piping_subtle`, o piping é fino e segue a aresta — acabamento, não estrutura.

### Definição de `softness_level` (em termos de `edge_radius` e `crown`)

| `softness_level` | `edge_radius` (aresta estofada) | `crown` (abaulamento do topo) | Leitura |
|------------------|----------------------------------|-------------------------------|---------|
| **low** | ~0.010–0.015 m | ~0.005 m | firme/estruturado, ainda estofado (nunca caixote) |
| **medium** | ~0.020–0.030 m | ~0.010 m | equilíbrio padrão, macio e definido |
| **high** | ~0.035–0.050 m | ~0.015–0.020 m | pufe/lounge, bem amaciado |

`edge_radius_level` (low\|medium\|high) escala estes raios. Mesmo em `low`, há raio e crown > 0 — **softness nunca é zero**.

---

## 5. Erros PROIBIDOS

Qualquer um destes reprova o sofá (FAIL), independentemente de render bonito:

- **`CAIXOTAO_FAIL`** — silhueta de caixote: zonas como blocos retos empilhados, sem recuo, raio ou crown. O erro-raiz da classe.
- **Piping grosso demais** — costura/piping com seção que vira "salsicha"; deve ser fino e sutil.
- **Piping facetado demais** — piping com poucos segmentos, mostrando arestas poligonais em vez de curva suave.
- **Piping tipo mangueira** — piping com volume tubular excessivo, parecendo uma mangueira aplicada.
- **Piping flutuante** — costura descolada da aresta, "boiando" sobre a superfície.
- **Encosto vertical tipo parede** — `back_rake_deg` ≈ 0 e/ou face fina: encosto que lê como divisória/parede.
- **Assento reto tipo caixa** — assento sem crown, sem face frontal macia, `seat_cushion_thickness` fina: lê como tampo de caixa.
- **Braço monolítico** — braço como bloco sólido sem raio, sem transição, esmagando o assento.
- **Pés colados na borda** — `leg_inset_m` ≈ 0: pés/base na quina externa, sem recuo nem sombra.
- **Ausência de base/recuo** — volume maciço do piso ao assento, sem pés, plinto recuado ou sombra de base.
- **Detalhe antes da forma** — aplicar costura/piping/material sobre uma silhueta ruim, na tentativa de mascará-la.
- **Hardcode de um único sofá** — regras ou dimensões fixadas para um exemplar em vez da classe.
- **Autoaprovação falsa** — declarar sucesso sem validação real (ex.: "GPT PASS" escrito/desenhado no render como se fosse veredito). O veredito visual vem do gate, nunca de texto embutido na imagem.
