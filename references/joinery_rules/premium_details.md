# Premium details — o que faz a marcenaria "ler caro"

> Os detalhes pequenos que separam planejado de qualidade de móvel-de-loja. Cada um:
> **o que é** + **dimensão** + **por que lê caro**. São acionáveis no
> `tools/kitchen_layout.py` e nos builders de móvel; vários já estão no golden-sample da
> planta_74. O custo está nos detalhes, não no tamanho.

---

## 1. Shadow gap / reveal (junta de sombra)
- **O que é:** frestas finas e propositais entre frentes de armário (e entre armário e
  parede/teto). A sombra dentro da fresta desenha a modulação.
- **Dimensão:** 2–4 mm entre portas; reveal de parede/teto 5–10 mm.
- **Por que lê caro:** prova que cada frente é uma peça independente bem ajustada (não
  uma chapa fake). A sombra dá ritmo e profundidade sem nenhum custo de material. É o
  oposto do "branco chapado" e do "módulo sem junta" (ver `anti_patterns.md`). No código,
  o inset das frentes (`M(0.004)` ≈ 4 mm em volta do backsplash/painéis) é exatamente
  essa fresta.

## 2. Gola / cava — handle-less (sem puxador)
- **O que é:** abertura por **cava** (gola usinada no topo/lateral da porta) ou por
  perfil J/Gola, eliminando o puxador aplicado. Frente totalmente limpa.
- **Dimensão:** cava de ~3–4 cm de recuo na borda superior da porta; perfil Gola
  embutido no reveal entre módulos.
- **Por que lê caro:** linha minimalista contínua, sem ferragem interrompendo a frente.
  Quando há puxador, que seja **slim grafite** (`puxador [44,45,50]`), não maçaneta
  bojuda cromada (builder-grade). Handle-less é o default contemporâneo premium.

## 3. Filler de acabamento (painel de fechamento)
- **O que é:** painel cego do mesmo material que fecha a folga entre o último módulo e a
  parede/coluna/geladeira. Acabamento parede-a-parede.
- **Dimensão:** 15–18 cm (proj. 16). Na planta_74 também é o gable lateral da torre da
  geladeira.
- **Por que lê caro:** elimina a fresta amadora que mostra a parede ou a lateral crua do
  eletro. Diz "feito sob medida pra ESTE vão", não "comprei pronto e sobrou espaço". A
  ausência dele é assinatura de móvel modulado de loja.

## 4. Torre integrada (geladeira/forno piso-teto)
- **O que é:** eletro alto envolto em coluna de marcenaria do piso ao teto — geladeira
  com painel lateral + aéreo de fechamento por cima, ou forno+micro empilhados em coluna.
- **Dimensão:** geladeira `GEL_W=0.70` × `GEL_H=1.80` + módulo `aereo_fridge` fechando
  até `aereo_top ≈ 2.10`. Sem vão morto em cima.
- **Por que lê caro:** verticaliza e ancora a cozinha, some o "buraco" sobre a geladeira
  que acumula pó, e integra o eletro ao conjunto. É o exemplo vivo de
  `loose_object -> planned_niche_system`.

## 5. LED sob aéreo (luz de tarefa)
- **O que é:** fita LED escondida sob o aéreo iluminando a bancada; opcional também no
  sóculo (luz de piso) e dentro de nichos.
- **Dimensão:** perfil embutido na frente inferior do aéreo, recuado ~1–2 cm pra
  esconder a fonte; clearance bancada→aéreo de 60 cm dá o espaço pra a luz cair limpa.
  Temperatura **2700K (quente)** — fria mata a madeira.
- **Por que lê caro:** ilumina a área de trabalho de forma profissional, valoriza o
  backsplash de pedra e cria a "linha de luz" que fotos de cozinha premium sempre têm.
  Razão funcional pra manter o clearance de 60 cm (não colar o aéreo na bancada).

## 6. Backsplash de pedra subindo
- **O que é:** o material do tampo (pedra) **continua na parede** subindo da bancada até
  o aéreo, em vez de azulejo/rejunte.
- **Dimensão:** sobe ~50 cm (da bancada até a base do aéreo); proj. backpanel até o
  aéreo, espessura ~4 cm, mesma cor do tampo (`[222,219,212]`).
- **Por que lê caro:** superfície contínua, **sem rejunte** (que data e acumula gordura),
  veio da pedra emendando tampo↔parede. Monolítico = premium. Azulejo metrô com rejunte
  preto = o oposto.

## 7. Tampo fino
- **O que é:** tampo de pedra esbelto, não a borda gorda anos-90.
- **Dimensão:** 2–4 cm (proj. `TAMPO_THK=0.03`). Se quiser frente robusta, engrossar só
  a saia frontal, mantendo o plano fino.
- **Por que lê caro:** finura = contemporâneo (porcelanato/quartzo de alta resistência).
  Espessura gorda lê laminado pesado ou granito datado. Detalhe de 2 cm que muda a
  época da cozinha inteira.

## 8. Sóculo recuado (rodapé de sombra)
- **O que é:** o sóculo/toe-kick recua em relação à frente do armário, criando uma faixa
  de sombra na base que faz o módulo parecer **flutuar**.
- **Dimensão:** recuo + altura 10–15 cm (proj. `TOE_KICK=0.12`, inset frontal ~4 cm),
  em **grafite** `[40,41,45]` (não na cor do corpo).
- **Por que lê caro:** a sombra na base alivia o peso visual do armário e dá leveza —
  truque clássico de marcenaria fina. Sóculo no nível da frente, na cor do corpo, mata o
  efeito e lê como móvel de loja. É também onde mora o LED de piso opcional.

---

## Tabela-resumo

| Detalhe | Dimensão | Por que lê caro |
|---|---|---|
| Shadow gap / reveal | 2–4 mm portas; 5–10 mm parede/teto | sombra desenha modulação, prova peças ajustadas |
| Gola / handle-less | cava ~3–4 cm / perfil no reveal | frente limpa contínua; puxador slim grafite se houver |
| Filler de acabamento | 15–18 cm | acabamento parede-a-parede, sob medida |
| Torre integrada | geladeira 0.70×1.80 + fechamento até ~2.10 | verticaliza, ancora, some o vão morto |
| LED sob aéreo (2700K) | recuo 1–2 cm; clearance 60 cm | luz de tarefa, valoriza pedra, linha de luz |
| Backsplash de pedra | sobe ~50 cm, mesma cor do tampo | superfície contínua sem rejunte, monolítico |
| Tampo fino | 2–4 cm | finura = contemporâneo; gordo = datado |
| Sóculo recuado grafite | 10–15 cm, inset ~4 cm | sombra faz flutuar; alivia peso visual |

> Regra geral: o premium mora no **reveal, no flush e na continuidade de material**, não
> em adicionar ornamento. Tirar a fresta, alinhar a frente e emendar o material já leva
> 80% do caminho.
