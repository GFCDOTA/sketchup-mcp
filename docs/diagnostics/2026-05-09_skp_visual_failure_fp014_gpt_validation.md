# FP-014 — Validação externa GPT-4o (2026-05-09)

> Resposta integral do GPT-4o validando a interpretação visual do
> Claude e o diagnóstico FP-014. Inputs: 3 imagens raw (PDF limpo +
> Claude interpretation + detector overlay) hospedadas na branch
> `docs/fp014-validation-images`.

## Contexto da validação

**Pergunta enviada (resumo):**
- A) As marcações da imagem (Claude) batem com o que se vê no PDF?
- B) Comparando Claude vs detector, qual está mais próxima do PDF?
- C) Confirma o diagnóstico (peitoris perdidos, widths undershot)?
- D) Prioridade de fix: rooms_from_seeds, F0 gates, ou extract_openings_vector?

**Inputs (URLs raw GitHub):**
- PDF limpo: `2026-05-09_skp_visual_failure_fp014_pdf_clean.png`
- Claude interpretation: `2026-05-09_skp_visual_failure_fp014_claude_interpretation.png`
- Detector overlay: `2026-05-09_skp_visual_failure_fp014_openings_overlay.png`

## Resposta integral do GPT-4o

> Analisei as 3 imagens. Minha leitura é visual/aproximada, então eu
> vou falar em termos de **provável/correto/questionável**, não como
> laudo CAD.

### Resposta curta primeiro

**C) Qual das duas, (2) ou (3), está mais próxima do PDF (1)?**

A imagem **(2), interpretação visual do Claude, está mais próxima do
PDF.**

Acerta melhor a semântica geral:
- distingue porta / janela / balcão / peitoril
- cobre mais aberturas relevantes
- está mais alinhada com o que um humano entende olhando a planta

A imagem (3), do detector atual:
- acerta algumas posições
- em alguns casos parece **estimar melhor o vão real** do que os
  números anotados manualmente
- mas perde tipos importantes e mistura semânticas (janela vs
  peitoril vs porta/balcão)

### A) Portas/janelas visíveis no PDF

**Portas (8):**
- P1. Porta de entrada externa (topo esquerdo, exterior↔sala/cozinha)
- P2. Porta entre cozinha e A.S. (lateral esquerda)
- P3. Porta do lavabo (sala↔lavabo)
- P4. Porta da suíte 01
- P5. Porta do banho 01 (suíte 01↔banho 01)
- P6. Porta do banho 02 (centro, leitura confusa)
- P7. Porta da suíte 02 (perto do banho 02)
- P8. Porta entre A.S. e sala de estar

**Balcões/portas-janelão (2):**
- B1. Sala de estar ↔ terraço social (parede inferior)
- B2. Suíte 02 ↔ terraço social (parede inferior)

**Janelas/peitoris (7):**
- J1. Janela externa cozinha (parede esquerda)
- J2. Janela externa superior A.S.
- J3. Janela externa inferior A.S.
- J4. Abertura horizontal suíte 01 inferior (importante)
- J5. Abertura lateral banho 01
- J6. **PEITORIL H=1,10M no terraço social** (anotado explicitamente)
- J7. Peitoril/abertura terraço técnico

### B) O que está ERRADO ou FALTANDO na interpretação Claude

**O que está bom / próximo:**
- porta de entrada externa ✓
- porta cozinha ↔ A.S. ✓
- porta lavabo ✓
- porta suíte 01 ✓
- porta banho 01 ✓
- porta A.S. ↔ sala ✓
- janelas externas cozinha e A.S. ✓
- peitoril longo do terraço social ✓

**O que está errado ou questionável:**

1. **`J-LAVABO 0.60m` (azul, no topo)** — Parece **errado / não evidente**
   no PDF. Não há janela clara do lavabo; o que existe ali parece mais
   shaft/parede/elemento técnico do que janela explícita.

2. **`J-SU01-TOP 1.40m` (azul, no topo direito)** — A ideia pode estar
   certa, mas **a posição está errada**. Essa medida parece estar mais
   relacionada à abertura do banho 01, no lado direito.

3. **`J-BAN01 0.40m` (azul, à direita)** — **Subestimada ou
   mal classificada.** Existe abertura ali, mas 0.40m parece pequeno
   demais. Leitura visual sugere algo mais próximo de uma abertura
   lateral/janela mais perceptível.

4. **`PV-SALA-TERR 4.20m` (ciano)** — **Muito provavelmente errado**
   como largura do balcão. 4.20 parece ser **cota do ambiente**, não o
   vão real da abertura. O detector marcou ~2.88m, **o que parece mais
   plausível como tamanho do vão**.

5. **`PV-SU02-TERR 3.20m` (ciano)** — Também parece usar **cota do
   ambiente, não o tamanho da abertura**. O vão real parece menor. O
   detector marcou ~1.93m, **que parece bem mais plausível**.

6. **Portas centrais perto de banho 02 / suíte 02:**
   `BAN02-SU01 1.20m`, `BAN02-SU02 0.85m`, `BANE02 1.20m`
   - Há mistura de quem conecta com quem
   - A área central tem duas portas próximas
   - Marcações da região OK, mas nomes/pareamentos confusos

**O que está faltando:**

- **F1. Abertura horizontal da suíte 01 na parede inferior** —
  importante, não ficou claramente representada
- **F2. Semântica exata dos dois balcões** — categoria boa, métrica
  errada

### C) Comparando (2) vs (3)

**Vencedora: imagem (2) — Claude interpretation**

| Aspecto | Claude (2) | Detector (3) |
|---|---|---|
| Semântica humana | ✅ melhor | ❌ pior |
| Cobertura de openings | ✅ mais completa | ❌ mais lacunas |
| Separa porta/janela/balcão/peitoril | ✅ sim | ❌ não |
| Reconhece peitoris | ✅ sim | ❌ ausente |
| Largura PV-SALA-TERR | ❌ 4.20m (cota) | ✅ 2.88m (vão real, plausível) |
| Largura PV-SU02-TERR | ❌ 3.20m (cota) | ✅ 1.93m (vão real, plausível) |
| Confiável para SKP sem supervisão | ❌ não | ❌ não |

> "Para referência de verdade visual: eu confiaria mais em (2),
> corrigindo os pontos listados."

### D) Prioridade de fix para destravar SKP utilizável

**Ordem recomendada (GPT-4o):**

```
1º — (i)  rooms_from_seeds       (root cause principal)
2º — (iii) gates F0              (proteção; precisa andar junto)
3º — (ii)  extract_openings_vector (dívida secundária)
```

**Justificativas:**

> **1º — `rooms_from_seeds`:** Esse é o principal. O SKP ruim **não
> está falhando primeiro por porta/janela**. Ele está falhando porque
> os polígonos dos cômodos/pisos estão errados: vazam, atravessam
> paredes, viram formas diagonais absurdas, materializam no SKP um
> chão que não existe. Se o polígono está errado, o SKP vai sair
> errado mesmo com openings melhores.

> **2º — gates F0:** Mesmo que o algoritmo ainda não esteja perfeito,
> o sistema **não pode deixar sair SKP visivelmente defeituoso.**
> O F0 deveria bloquear: room polygon atravessando parede; floor fora
> do envelope; área absurda; triângulo gigante em cômodo; room com
> vértices demais / shape implausível.

> **3º — `extract_openings_vector`:** Importante mas terceiro. Porque
> o erro que mata o SKP hoje não é "janela 20 cm fora" ou "peitoril
> perdido" — é "o cômodo virou um polígono errado e o piso vazou".
> Openings entram depois que room polygons estiverem estáveis e F0
> bloquear export ruim.

### Resposta final de prioridade

> Em frase simples:
> **Primeiro conserta a geometria dos rooms, depois impede export ruim,
> depois refina portas/janelas.**

### Conclusão prática

- **Root cause principal:** `rooms_from_seeds` / room polygon leakage
- **Gap de proteção:** F0 ainda deixa passar SKP visualmente ruim
- **Dívida secundária:** `extract_openings_vector` ainda perde
  semântica importante (principalmente peitoris/balcões/janelas)

---

## Implicações para o FP-014

### O que confirma (estrutural, sem mudança)

- ✅ 3 famílias de defeitos (A floor polygon / B wall fragments / C openings)
  estão corretamente diagnosticadas
- ✅ Detector perde peitoris e janelas pequenas — **confirmado**
- ✅ Quando wall_gap, mede gap entre fragmentos em vez do vão real —
  **confirmado** (e GPT acrescenta: para PV-SALA-TERR e PV-SU02-TERR
  o detector está MAIS perto do vão real do que minha estimativa
  visual, que confundi com cota do ambiente)
- ✅ Opção A (rooms_from_seeds) + Opção C (gate F0) é a sequência
  correta — **GPT confirma rank 1+2**

### O que ajusta (correção factual)

- ⚠️ **Larguras dos balcões PV-SALA-TERR (4.20m) e PV-SU02-TERR
  (3.20m) na minha interpretação são CORRECT widths do AMBIENTE,
  não do vão.** Detector estava mais correto: 2.88m e 1.93m são
  larguras de vão plausíveis.
- ⚠️ J-LAVABO 0.60m provavelmente não existe (shaft/elemento técnico)
- ⚠️ J-SU01-TOP 1.40m posição errada (medida pertence a banho 01 lateral)
- ⚠️ J-BAN01 0.40m subestimada
- ⚠️ Faltou marcar abertura horizontal SUITE 01 inferior

### O que muda na recomendação de fix

**Antes (Claude solo):** Opção C como menor fix recomendado.

**Depois (GPT validation):** Opção A é o **root cause primário**.
Opção C é proteção necessária em paralelo, mas não substitui A. Opção
B é dívida secundária.

**Sequência recomendada (atualizada):**

1. **Opção A — `rooms_from_seeds` refactor** (prioridade 1)
   - método raster trace + concave-hull → `shapely.polygonize(walls)`
     + matchar seed→cell
   - polygons resultantes: 4–20 vts, perfeitamente colados aos walls
   - **Esse é o fix que destrava o SKP**

2. **Opção C — gates F0 estructurais** (prioridade 2, em paralelo)
   - barreira de proteção contra regression / detector_break
   - bloqueia SKP visivelmente defeituoso mesmo se algoritmo
     ainda imperfeito
   - **NÃO substitui Opção A** — é gate, não fix

3. **Opção B — `extract_openings_vector` improvements** (prioridade 3)
   - melhoria após A + C estabilizarem
   - foco: detectar peitoris + medir vão completo (não fragmento)

## Source

- **Modelo:** GPT-4o via ChatGPT (Felipe transmitiu manualmente)
- **Data:** 2026-05-09
- **Contexto:** Branch `docs/fp014-validation-images`,
  commit `5ff6810`
