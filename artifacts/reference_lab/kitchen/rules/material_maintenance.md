# Material × manutenção — veredito por material pro perfil do Felipe

> Regra-mãe do Felipe: **beleza SEM dor de cabeça. Manutenção viável > material
> delicado.** Sonhar alto no conceito, mas durar e limpar fácil na vida real
> (apto ~74 m², ele + namorada, uso de cozinha moderado, robô aspirador rodando).
>
> Esta tabela é o **maintenance_gate** virado decisão. Não duplica a química do
> material — isso vive em `references/materials/{stone,wood,lacquer,metal}.md`
> (ONDE FALHA por material). Aqui é só: **vale pro Felipe? sim / com cuidado /
> não.** Direção aprovada: BLACK_WOOD_GOLD industrial boutique premium
> (ver `FELIPE_KITCHEN_PREFERENCES.md`).

## Eixos de avaliação (o que importa pra ele)

- **Durabilidade** — aguenta uso diário sem lascar/empenar/descascar?
- **Risco de mancha** — café/óleo/ácido/água deixam marca?
- **Risco de dedo** — marca digital aparente? (ele ACEITA reflecta marcar SE
  for bonito — mas isso vira WARN, não free pass.)
- **Risco de risco** — risca com atrito/panela/faca?
- **Limpeza** — pano passa fácil? junta sujeira em ressalto/rejunte/sulco?
- **Veredito Felipe** — `SIM` (default seguro) · `CUIDADO` (usar com critério /
  zona certa / WARN no gate) · `NÃO` (anti-padrão pro perfil dele).

---

## Tabela mestra

| Material | Durabilidade | Mancha | Dedo | Risco | Limpeza | Veredito Felipe |
|---|---|---|---|---|---|---|
| **Madeira** (oak/freijó/nogueira, foil/lâmina) | alta seca, baixa molhada | alta na zona molhada | baixo (fosco) | médio | fácil seca | **CUIDADO** — só backsplash parcial/nicho/painel/detalhe. **NUNCA** área molhada (pia/cooktop) |
| **Quartzo** (engineered) | alta | baixa (não-poroso) | baixo (fosco) | médio (lasca quina) | muito fácil | **SIM** — default seguro de tampo; cuidado com panela quente direta |
| **Porcelanato/Dekton slab** | altíssima | baixíssima | baixo (mate) | alto na quina viva | muito fácil | **SIM** — coringa técnico; chanfrar quina exposta a impacto |
| **Granito escuro** (preto absoluto / leathered) | altíssima (calor+risco) | baixa se selado | **alto se polido** | muito baixo | fácil (leathered) | **SIM** — casa com tema escuro; usar **leathered/acetinado**, não polido |
| **Mármore/Calacatta** | baixa pro uso | **alta (etching ácido)** | médio | lasca/risca | exige cuidado | **NÃO** na zona de trabalho; só superfície decorativa se insistir |
| **Laca preta fosca** (volumes/frentes) | média (retoque pro) | baixa | **alto (marca dedo+gordura)** | risca/lasca | média (perto cooktop pior) | **CUIDADO** — linda no tema, mas **WARN de dedo**; satin alivia |
| **Vidro reflecta / champagne** | média | baixa | **ALTO (marca dedo)** | risca | fácil mas remarca | **CUIDADO** — só 1–2 módulos pontuais + LED interno; **nunca todos os aéreos** |
| **Inox escovado** (eletro) | alta | baixa | médio (escovado disfarça) | médio | fácil | **SIM** — seguro/durável; satin/reflexivo devolve luz de dia |
| **Cuba preta** (granito/quartzo/composto) fosca/satin | alta | baixa | médio-alto (água+dedo) | médio | **marca água/calcário** | **CUIDADO/SIM** — ele quer; satin > fosco; secar evita marca de água |
| **Cuba inox** | alta | baixa | médio | risca leve | muito fácil | **SIM** — a opção segura/durável; trade-off é estética menos "tema" |
| **Piso grafite médio acetinado** | alta | baixa | n/a | esconde risco | fácil; **esconde pó** | **SIM (default)** — melhor equilíbrio: escuro, não pesa, não mostra pó |
| **Piso cimento queimado quente** | alta | média (poroso s/ resina) | n/a | esconde risco | fácil se resinado | **SIM** — combina industrial, mais leve; **resinar/impermeabilizar** |
| **Piso preto** | alta | baixa | n/a | mostra **pó/risco/pegada** | chato (mostra tudo) | **NÃO como default** — só variante "show"; pesa o compacto |
| **Piso claro demais** | alta | mostra sujeira | n/a | mostra risco | mostra tudo | **NÃO** — suja visualmente fácil |

---

## Notas que mudam o veredito

### Madeira na cozinha do Felipe
- **CUIDADO** é firme: madeira é o acento quente aprovado (nogueira/freijó/
  carvalho mais quente), mas **só seca** — backsplash parcial, nicho, painel,
  lateral de torre, fundo de prateleira. **Pia/cuba com textura de madeira = NÃO**
  (ele disse explícito: "não convence, parece fake"). Gate: `wood_wetzone_gate`.
- Acabamento **fosco/acetinado dessaturado**, nunca verniz brilhante saturado
  (vira builder-grade — ver `references/materials/wood.md`).

### Tampo / bancada (a decisão de "não mancha")
- "Não mancha" é **promessa perigosa** — todo material tem trade-off. Para o
  perfil dele (uso moderado, quer durar): **quartzo OU porcelanato técnico OU
  granito escuro bem tratado**. Cada um com seu risco registrado:
  - **Quartzo** — não-poroso, fácil; **não pôr panela quente direta** (resina
    amarela/trinca).
  - **Porcelanato slab** — quase indestrutível; **só cuidar da quina viva**
    (lasca em impacto → chanfrar).
  - **Granito escuro leathered** — duríssimo e casa com o tema escuro; **fugir do
    polido** (marca dedo/pó, lê sujo).
- **Mármore = NÃO** no molhado de trabalho: mancha com ácido (limão/vinho)
  permanente mesmo selado. Se quiser o veio dourado, é veio **sutil** em
  quartzo/porcelanato impresso, não mármore real na bancada.

### Cuba preta vs inox (a dúvida dele)
- Ele **quer** cuba preta pela estética do tema. Veredito honesto:
  - **Cuba preta** (granito/composto **satin**, não fosco puro) — linda, durável,
    mas **marca água/calcário** e dedo → hábito de **secar depois de usar**.
    Aceitável pro perfil dele SE ele topar o ritual de secagem. Gate: WARN em
    `maintenance_check`.
  - **Cuba inox** — a escolha **segura/durável/sem-drama**; trade-off é parecer
    menos "tema escuro". É o fallback recomendado se "sem dor de cabeça" pesar
    mais que estética.
- **Nunca** resolver com madeira na cuba (anti-padrão dele).

### Dedo / reflecta
- Ele **aceita** que reflecta marca dedo SE for bonito — mas só pontual: **1–2
  módulos** com LED interno, ou faixa vertical perto da torre. **Reflecta em
  todos os aéreos = NÃO** (reflexo demais, marca dedo em tudo, vira showroom).
  Gate: `reflecta_control_gate`.
- **Laca preta fosca** e **preto fosco** marcam dedo/gordura perto do cooktop →
  preferir **satin/acetinado** nessas zonas; mantém o look, sofre menos.

### Piso (robô aspirador + pouco pó visível)
- Robô aspirador roda direto → piso deve **esconder pó e risco** e ser fácil de
  passar. Daí **grafite médio acetinado** ser o default e **preto** e **claro
  demais** caírem fora (mostram tudo). Sem rejunte largo (junta pó/gordura);
  porcelanato grande formato ou cimento queimado resinado.
- Gate: `black_floor_gate` (preto só como teste, nunca default).

---

## Como o gate usa isto
1. Para cada superfície da spec, classificar o veredito (SIM/CUIDADO/NÃO) por
   esta tabela.
2. Qualquer **NÃO** na cozinha real = FAIL do `maintenance_gate` → trocar antes
   de mostrar.
3. Qualquer **CUIDADO** = WARN → registrar o trade-off explícito (ex.: "cuba
   preta marca água, requer secagem") na DECISIONS/spec, não esconder.
4. Química detalhada (ONDE FALHA, RGB, render) → consultar
   `references/materials/*.md`. Esta tabela é só o veredito de uso pro Felipe.
