# Pedra — bancada, tampo, backsplash, ilha

> Knowledge base de marcenaria planejada. Referência = LINGUAGEM de material;
> a POSIÇÃO (pia, parede, hidráulica) vem do PDF. Estes RGB são alvos de
> material SketchUp/V-Ray (cor base difusa aproximada), não medições.

**Golden sample (cozinha planta_74):** tampo + backsplash em PEDRA CLARA
`rgb[222,219,212]` (quartzo branco-neutro / off-white levemente quente). É a
régua: pedra clara coordena com inferiores carvalho claro `[191,167,137]` e
aéreos fendi `[224,215,199]` sem competir. Qualquer escolha abaixo é julgada
contra essa coerência.

Onde a pedra entra no sistema planejado: tampo de bancada, frontão/backsplash
(de preferência a mesma chapa subindo — "tampo que vira parede"), tampo de
ilha, nicho molhado, soleira. Princípio do programa: `loose_object →
planned_niche_system` — a pedra deixa de ser "uma peça" e vira a superfície
contínua do sistema.

---

## Quartzo (engineered / silestone, caesarstone, tipo)

- **Aparência:** branco neutro a cinza, granulado fino e MUITO uniforme.
  Branco puro `rgb[236,236,234]`; off-white quente (golden-sample) `[222,219,212]`;
  cinza concreto `[176,176,178]`; veio fino discreto. Acabamento fosco (mate)
  lê mais sofisticado que polido espelhado em render.
- **Custo:** `$$$` (médio-alto; o default "seguro" de planejado contemporâneo).
- **Prós:** não-poroso → não mancha com ácido/vinho/café como mármore; cor
  consistente lote a lote (some o risco de "veio que não bate"); ampla gama de
  brancos/cinzas; o material que melhor casa com a paleta clara do golden sample.
- **Contras:** veios artificiais podem parecer repetitivos/plásticos em chapa
  grande; menos "alma" que pedra natural.
- **ONDE FALHA:**
  - **Calor:** marca/amarela com panela quente direta (resina). Trinca com
    choque térmico perto do cooktop — no modelo, é o argumento pra cooktop com
    folga e nunca encostar a chapa direto na boca.
  - **UV:** branco puro próximo a janela ensolarada AMARELA com o tempo. Em
    render: não cravar branco-papel `[245,245,245]` num tampo — lê irreal e
    "clínico". Ficar em `[222,219,212]`–`[230,228,222]`.
  - **Render:** quartzo branco fosco com specular alto vira plástico. Manter
    roughness alta, reflexo baixo.

## Granito

- **Aparência:** preto absoluto `rgb[28,28,30]` (o clássico de cozinha BR),
  cinza Corumbá `[120,120,124]`, branco Itaúnas com pintas pretas. Granulação
  visível, pontos minerais — leitura "pétrea" honesta.
- **Custo:** `$$`–`$$$` (preto absoluto é acessível e onipresente; exóticos sobem).
- **Prós:** duríssimo, resiste a risco e calor melhor que quartzo; preto faz
  contraste forte com madeira clara (oposto do golden sample, mas válido pra
  cozinha "pesada"/escura).
- **Contras:** preto domina visualmente e PUXA o ambiente pra escuro — briga
  com a paleta clara/fendi do golden sample. Pontilhado pode datar (cara de
  cozinha 2005).
- **ONDE FALHA:**
  - **Preto polido MARCA digital e poeira** — em render fica "sujo"/borrado;
    preferir leathered/acetinado `[34,34,36]` com roughness média.
  - Granito branco/claro é POROSO de verdade (mais que quartzo) → mancha de
    óleo/café se não selado. Anti-padrão: usar como "quartzo barato".
  - Pingado de cor (azul/verde exótico) data rápido e briga com qualquer
    paleta neutra.

## Mármore

- **Aparência:** branco Carrara `rgb[228,228,224]` com veio cinza-azulado
  fluido; Calacatta `[232,229,222]` veio dourado/cinza largo e dramático. O
  veio é o produto — é o material mais "caro de olhar".
- **Custo:** `$$$$` (natural caro; o "ultra-compacto que imita" é a saída barata).
- **Prós:** topo de luxo visual; veio orgânico que nenhum engineered iguala de
  verdade. Em ilha-herói faz a cozinha inteira subir de nível.
- **Contras:** o material mais frágil da lista pro uso de cozinha.
- **ONDE FALHA (o clássico):**
  - **MANCHA com ácido** (limão, vinho, vinagre) → marca foscas permanentes
    (etching) mesmo selado. Em cozinha de uso real é risco alto — por isso
    planejados sérios usam mármore em ILHA decorativa / lavabo, e quartzo no
    molhado de trabalho.
  - Risca e lasca na quina; absorve óleo (poroso).
  - **Render:** veio mal-mapeado (textura esticada/repetida na chapa) entrega
    "mármore de Photoshop". Veio precisa fluir contínuo na peça e cruzar o
    backsplash coerente.

## Porcelanato / Dekton / Ultracompacto (sinterizado)

- **Aparência:** IMITA mármore/concreto/cimento queimado com chapa grande
  (slab). Concreto `rgb[180,178,174]`; "mármore" `[226,223,216]`; pode replicar
  o golden-sample claro `[222,219,212]` com veio impresso. Acabamento mate é o forte.
- **Custo:** `$$`–`$$$` (Dekton premium `$$$$`; porcelanato slab nacional `$$`).
- **Prós:** quase indestrutível ao calor/risco/UV/mancha; espessura fina
  (6–12 mm) → visual "lâmina" moderno; faz o "tampo que vira parede" sem peso.
  Hoje é o coringa técnico do planejado contemporâneo.
- **Contras:** veio impresso pode repetir; chapa muito fina precisa de apoio.
- **ONDE FALHA:**
  - **LASCA NA QUINA** — porcelanato é o ponto fraco: impacto na aresta viva
    estilhaça (chip). No modelo: nunca quina viva exposta a 90° em canto de
    bater — chanfrar/arredondar levemente a aresta.
  - Borda fina lida de lado mostra "miolo" de cor diferente da face (efeito
    sanduíche) se não for full-body/mitrada.

## Nanoglass / vidro cristalizado

- **Aparência:** branco translúcido leitoso `rgb[238,238,236]`, ultra-uniforme,
  quase sem veio. Brilho de cristal.
- **Custo:** `$$$$`.
- **Prós:** brancura altíssima e estável (não amarela como quartzo/resina sob UV);
  não-poroso.
- **Contras:** nicho, caro, frágil ao impacto pontual.
- **ONDE FALHA:** lasca/trinca com pancada concentrada; o brilho cristalino
  exagera digital em render → vira "plástico branco" se o reflexo não for
  controlado. Usar com parcimônia.

---

## Decisão rápida (para o gerador)

- **Default coerente com golden sample:** quartzo OU porcelanato slab claro
  `[222,219,212]`, acabamento fosco. Casa com madeira clara + fendi.
- **Quer luxo / ilha-herói:** mármore/Calacatta `[232,229,222]` SÓ em superfície
  decorativa; no molhado de trabalho continua quartzo (evita o etching).
- **Quer cozinha escura/pesada:** granito preto leathered `[34,34,36]` — sai do
  golden sample de propósito; conferir contraste com a madeira.
- **Anti-padrões a barrar:** branco-papel `[245,245,245]` (irreal/clínico);
  preto polido espelhado (marca digital, lê sujo); quina viva de porcelanato em
  canto de impacto; veio de mármore esticado/repetido; mármore no molhado de uso
  pesado.
