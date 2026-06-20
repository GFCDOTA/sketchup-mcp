# Regras de iluminação — LED quente, discreto, mood noturno + luz natural de dia

> O Felipe quer **mood noturno** (cozinha que brilha de noite, escura/premium) E
> **luz natural de dia** (não virar buraco escuro). A iluminação é o que salva o
> tema BLACK_WOOD_GOLD de virar caverna. Direção aprovada e o que ele recusa:
> ver `FELIPE_KITCHEN_PREFERENCES.md`.
>
> O **porquê funcional do clearance** (LED sob aéreo exige 60 cm bancada→aéreo) e
> o **token** vivem em `references/joinery_rules/premium_details.md` (#5) e
> `references/tokens/under_cabinet_led.json` — **não repetir**. Aqui é a
> **gramática de luz** pro perfil dele.

## Princípio
- **Temperatura: 2700–3000K (quente), SEMPRE.** Quente casa com a paleta
  oak/fendi/nogueira/pedra; **branco-frio 4000K+ mata a madeira** e deixa a
  cozinha "hospitalar". 4000K+ = anti-padrão.
- **Discreta e funcional:** luz que **lava superfície e ilumina tarefa**, nunca a
  fonte aparente. **Sem neon, sem spot bolinha, sem fita visível por baixo**
  (gambiarra). O premium é a *lavagem*, não o ponto de luz.
- **Camadas:** tarefa (bancada) + ambiente/mood (volumes/nichos) + um pouco de
  acento (reflecta/pedra). Não um plafon central chapado iluminando tudo igual.

---

## Onde a luz entra (catálogo)

### 1. LED linear sob o aéreo — luz de tarefa (a principal)
- Fita 2700K **embutida e recuada ~1–2 cm** na frente inferior do aéreo, oculta;
  só a lavagem aparece sobre **bancada + backsplash de pedra**.
- É a "linha de luz" que toda foto de planejado premium tem. Razão funcional do
  clearance de 60 cm bancada→aéreo (ver `premium_details.md` #5).
- **Anti-padrão:** fita visível (não recuada) = gambiarra; intensidade alta
  estoura o branco da pedra.

### 2. Dentro de armário / nicho / vitrine
- LED 2700K interno em **1–2 módulos** com vidro reflecta/champagne ou em nicho
  aberto de destaque → ativa o reflexo e cria pontos de brilho quentes (mood).
- Casa exatamente com a regra de reflecta pontual (`reflecta_control_gate`): o
  módulo de vidro **com LED interno** é o uso aprovado, não vidro em tudo.

### 3. Sóculo / rasgo de piso — luz de piso (mood noturno)
- LED 2700K no **sóculo grafite recuado** lançando luz rasante no piso → faz o
  armário **flutuar** e dá o brilho de baixo que define o mood noturno. Opcional
  mas é assinatura premium barata.
- Mesmo recuo/ocultação: fonte escondida, só a lavagem no piso.

### 4. Rasgo / sanca no teto ou sobre torre — banho indireto
- LED 2700K em rasgo de gesso/sanca **lavando teto/parede** ou descendo pela
  lateral da torre → luz indireta que clareia o ambiente sem ponto de luz duro.
  Ajuda o `cave_check` (compensar o escuro) sem estourar.

### 5. Backsplash / pedra protagonista
- A luz de tarefa (#1) deve **valorizar o veio da pedra** atrás da torneira
  (backsplash protagonista, veio dourado/quente SUTIL). A pedra satin **devolve**
  parte da luz — conta como superfície de daylight_reflection.

---

## Mood noturno + luz natural de dia (as duas cenas)

### Mood noturno
- LED quente em camadas (sob aéreo + nicho/reflecta + sóculo) cria a cozinha que
  **brilha de noite**, escura e premium, com pontos de brilho quentes nas pedras
  e no vidro. É o impacto que ele quer.

### `daylight_reflection` — superfícies que devolvem luz (DE DIA)
- De dia o tema escuro **não pode virar buraco**. Tem que existir superfície que
  **devolve a luz natural** — é o `daylight_reflection_check`:
  - **geladeira satin/reflexiva** (devolve luz),
  - **vidro reflecta/champagne pontual** (1–2 módulos),
  - **pedra satin/polida** (tampo/backsplash que reflete),
  - **champagne/bronze discreto** (rebate quente),
  - parede/teto claro **controlado** (sem virar branco puro).
- **Sem nenhuma superfície refletora → WARN** (vira buraco escuro de dia). A luz
  natural entra pelo PDF (janela = POSIÇÃO, não se move); a marcenaria decide o
  que **rebate** essa luz.

---

## Anti-padrões (recusados pelo Felipe)
- **LED frio 4000K+** → cozinha "hospitalar"; mata madeira/pedra quente. **NÃO.**
- **Spot bolinha** (mini-spots pontuais) → ele recusou; usar **linear/lavagem**.
- **Neon / fita colorida** → fora do tema premium.
- **Fita LED visível por baixo** (não recuada) → lê gambiarra.
- **Intensidade alta** estourando o branco da pedra → suave, realça não estoura
  (em V-Ray = emissive quente **baixo**).
- **Plafon central único chapado** iluminando tudo igual → mata o mood em camadas.
- **Só luz noturna sem nenhuma superfície refletora** → buraco escuro de dia
  (WARN `daylight_reflection_check`).

## Como o gate usa isto
1. Toda fonte de LED = **2700–3000K**; qualquer 4000K+ = FAIL.
2. Fonte **sempre oculta/recuada**; fita aparente = FAIL.
3. Cena noturna (mood em camadas) **e** cena diurna (≥1 superfície de
   daylight_reflection) ambas válidas → senão WARN (`cave_check` /
   `daylight_reflection_check`).
4. Reflecta com LED interno conta como mood + reflexo, mas respeita o limite de
   1–2 módulos (`reflecta_control_gate`).
