# Pedras do tampo + backsplash DARK com VEIO DOURADO sutil — planta_74

> SPEC acionável pro arquiteto/marceneiro. Cozinha LINEAR compacta do apto ~74 m²,
> direção **BLACK_WOOD_GOLD** (preto/grafite fosco + madeira quente + pedra escura
> com veio DOURADO SUTIL + cuba/torneira preta + bronze discreto + LED 2700K).
> Perfil: Felipe + namorada, uso moderado, robô aspirador, **manutenção viável >
> material delicado**, NADA de fake luxury.
>
> Esta spec é o **deep-dive da PEDRA DARK** (o `stone.md` da KB é golden-sample CLARO;
> aqui invertemos pro tema escuro). Tudo em modelos/tipos REAIS do mercado BR, com
> faixa de preço relativo, manutenção e ONDE FALHA. RGB = alvo de material V-Ray/SKP,
> não medição.

```
referência = LINGUAGEM   ·   PDF = POSIÇÃO   ·   gates = SEGURANÇA   ·   Felipe = PASS
```

---

## 0. O que é "veio dourado" e por que isso é delicado de acertar

O veio (em inglês *vein*, *movimento*) é o desenho mineral que corre pela pedra.
No tema escuro o que vende o look premium é uma **base preta/grafite FOSCA com fios
finos cor de ouro/champagne/bronze atravessando** — tipo o mármore Calacatta Gold,
mas em base preta (o chamado "preto-dourado", "Nero gold", "black gold").

A armadilha (a linha entre *premium* e *fake luxury*):
- **SUTIL** = poucos fios finos, dourado dessaturado/quase-bronze, contraste médio.
  Lê caro, "pedra de verdade".
- **EXAGERADO** = veio largo, dourado saturado/brilhante, muito fio, simétrico/repetido.
  Lê "mármore de Photoshop", piso de hall de prédio, mansão fake. **Anti-padrão do Felipe.**

Regra de render/escolha pro nosso caso: **densidade de veio baixa, dourado puxando
pra bronze/champagne (não ouro-amarelo gritante), acabamento MATE/acetinado** (polido
espelhado preto marca dedo e poeira e lê "sujo" em render — ver `material_maintenance.md`).
Backsplash pode ter o veio um pouco mais visível (é zona de "olhar", não de bater);
tampo o veio mais discreto ainda (é zona de trabalho).

---

## 1. QUARTZO escuro (engineered — Silestone / Caesarstone / similar nacional)

Quartzo é pedra de engenharia: ~90% quartzo moído + resina. **Não-poroso.** É o default
"seguro" do planejado contemporâneo. Para base ESCURA + veio dourado, os produtos reais:

- **Silestone Eternal Noir** — base preta com veio branco/dourado discreto (linha
  "Eternal" que imita mármore). É o mais próximo do "preto-dourado" engineered confiável.
- **Silestone Marquina / Negro Tebas** — preto profundo quase liso (pouco ou nenhum veio);
  base pra quem quer preto fechado e bota o dourado só na torneira/bronze.
- **Caesarstone Empira Black / Vanilla Noir** — preto com veio branco/creme dramático
  (mais branco que dourado — pedir amostra do lote pra ver se o veio puxa quente).
- Linhas nacionais (ex. quartzo escuro de fabricante BR) saem mais barato, mas o veio
  dourado fino bem-resolvido costuma ser das marcas importadas.

| Eixo | Veredito |
|---|---|
| Aparência/veio | Base preta uniforme `rgb[30,30,33]`; veio dourado-champagne fino `rgb[150,128,86]` (alvo SUTIL). Granulado finíssimo, muito uniforme. **Mate** lê melhor que polido. |
| Custo | `$$$` (médio-alto). Linha "imita-mármore" (Eternal/Empira) custa mais que preto liso. |
| Mancha | **Excelente** — não-poroso, não absorve café/vinho/óleo/ácido. O grande argumento. |
| Risco | Bom (dureza alta), mas **lasca na quina viva** em impacto — chanfrar aresta de canto. |
| Calor | **Ponto fraco.** A resina **amarela/marca/trinca** com panela quente direta e choque térmico perto do cooktop. Trivet sempre; nunca encostar chapa na boca. |
| Manutenção | Muito fácil — pano úmido. Sem selante, sem ritual. |
| ONDE FALHA | (1) panela quente direta = mancha permanente; (2) veio impresso pode repetir/parecer "plástico" em chapa grande se for produto barato; (3) preto **polido** marca dedo+pó → pedir acabamento **suede/mate**. |

---

## 2. GRANITO preto (natural — São Gabriel, Preto Absoluto, Via Láctea, Nero)

Granito é pedra natural, duríssima. O clássico de cozinha BR e o mais **barato e durável**
da família escura. O problema é que o granito preto "puro" é LISO — pra ter veio dourado
você vai pros granitos movimentados:

- **Preto São Gabriel** — preto muito fechado, granulação fina, pouquíssimo veio. Acessível
  e onipresente. (Para o nosso look: serve de base preta, mas o dourado teria que vir do
  bronze/torneira, não da pedra.)
- **Preto Absoluto / Nero Absoluto** — preto chapado uniforme, sem veio. Idem.
- **Via Láctea** — preto com pontos brancos/cristais (pintado de estrelas). NÃO é veio
  dourado — é pontilhado branco. Pode datar ("cozinha 2005"). Evitar pro nosso tema.
- **Granito preto com veio dourado real** existe mas é menos comum em granito que em
  quartzito/porcelanato — peça ao marmorista "granito preto movimentado com veio caramelo/
  dourado" e veja chapas FÍSICAS (cada bloco é único).

| Eixo | Veredito |
|---|---|
| Aparência/veio | Preto `rgb[28,28,30]`; granulação mineral honesta. Veio dourado natural é raro/imprevisível no granito (vem do bloco). **Leathered/acetinado** `rgb[34,34,36]`, NÃO polido. |
| Custo | `$$` (preto absoluto/São Gabriel é o mais barato da lista). Exóticos movimentados sobem. |
| Mancha | Boa **se selado**; o preto é menos poroso que granito claro. Selar 1×/ano. |
| Risco | **Excelente** — dos mais resistentes a risco da lista. |
| Calor | **Excelente** — aguenta panela quente melhor que quartzo (sem resina). Vantagem real perto do cooktop. |
| Manutenção | Fácil se **leathered/acetinado**; selante periódico. **Polido marca digital e poeira** e lê "sujo"/borrado em render. |
| ONDE FALHA | (1) preto **polido** = marca dedo/pó (anti-padrão); (2) achar veio dourado bonito é loteria do bloco — não compre "no catálogo", veja a chapa; (3) Via Láctea/pontilhado data e briga com o tema sofisticado. |

---

## 3. PORCELANATO / LÂMINA porcelânica grande formato (Nero gold, Calacatta black gold)

Slab de porcelanato (lâmina fina 6–12 mm, formato grande ~1,60×3,20 m) que **imprime**
qualquer desenho — é onde o "preto-dourado" mais convence pelo preço, e o coringa técnico
do planejado contemporâneo. Marcas/linhas reais no BR:

- **Portobello / Roca / Eliane / Biancogres / Damme** têm linhas "slab"/"pietra" com
  preto-dourado: nomes de catálogo como *Nero Gold*, *Calacatta Black*, *Marquina Gold*,
  *Patagonia Black*, *Saint Laurent* (mármore preto francês com veio dourado/bordô —
  referência clássica do look).
- Acabamento **mate/natural** é o que queremos (polido lustra demais e marca).
- A graça: o veio pode **cruzar contínuo** do tampo subindo pro backsplash ("tampo que
  vira parede"), porque é a mesma chapa impressa — efeito de marcenaria cara.

| Eixo | Veredito |
|---|---|
| Aparência/veio | Imita mármore preto-dourado com fidelidade alta. Base `rgb[30,29,32]`, veio dourado `rgb[150,128,86]` impresso e controlável (peça mostruário do veio SUTIL). Espessura fina = visual "lâmina" moderno. |
| Custo | `$$`–`$$$` (slab nacional `$$`; importado/premium `$$$`). Mais barato que quartzo importado e que pedra natural exótica. |
| Mancha | **Baixíssima** — não-poroso, quase indestrutível a café/ácido/óleo. |
| Risco | Altíssima resistência na FACE; **mas LASCA NA QUINA** — é o ponto fraco (ver abaixo). |
| Calor | **Excelente** — aguenta panela quente (cerâmica sinterizada). |
| Manutenção | Muito fácil, sem selante. |
| ONDE FALHA | (1) **LASCA/CHIP na aresta viva** em impacto (panela batendo na quina) → **chanfrar/arredondar/mitrar** a borda, nunca quina 90° viva em canto de bater; (2) borda fina mostra "miolo" de cor diferente (efeito sanduíche) se não for full-body ou mitrada — pedir **borda mitrada (45°)** pra parecer chapa maciça; (3) lâmina muito fina precisa de apoio/substrato. |

---

## 4. DEKTON / NEOLITH / ultracompacto SINTERIZADO

Família "irmã mais cara/forte" do porcelanato slab: superfície sinterizada de partículas
ultracomprimidas. **Dekton** (Cosentino) e **Neolith** são as marcas de referência.
Tecnicamente é o material mais "à prova de tudo" da lista.

- Linhas preto-dourado reais: **Dekton Laurent** (preto com veio dourado/bordô, referência
  do Saint Laurent), **Dekton Kelya/Sirius** (pretos), **Neolith** linha *Calacatta Gold/
  Nero* etc.
- Acabamento **mate (Dekton "X-gloss" é o polido — evitar; pegar o mate/velvet)**.

| Eixo | Veredito |
|---|---|
| Aparência/veio | Igual/superior ao porcelanato em fidelidade; veio dourado controlável e contínuo. `rgb[30,29,32]` base + `rgb[150,128,86]` veio. Visual lâmina premium. |
| Custo | `$$$`–`$$$$` (o mais caro junto com pedra natural exótica). Dekton premium = topo. |
| Mancha | **Praticamente imune** — não-poroso, resiste a ácido/UV/mancha total. |
| Risco | **O melhor da lista** em risco. |
| Calor | **O melhor da lista** em calor (aguenta panela quente direta de verdade). |
| Manutenção | A mais baixa de todas — zero selante, zero ritual. É o "compra e esquece". |
| ONDE FALHA | (1) **quina viva ainda pode lascar** com impacto forte e concentrado (menos que porcelanato comum, mas existe) → chanfrar; (2) **preço** é o real obstáculo — só vale se o orçamento topar o premium; (3) algumas peças polidas marcam micro-risco visível na luz rasante → ficar no mate. |

---

## 5. QUARTZITO escuro com veio dourado (NATURAL — a opção "veio dourado de verdade")

⚠️ **Não confundir QUARTZITO (natural) com QUARTZO (engineered).** Quartzito é pedra
NATURAL, duríssima (mais dura que mármore e granito em vários casos), com veios orgânicos
reais. É aqui que mora o "preto-dourado natural" mais autêntico — e mais caro/imprevisível:

- **Belvedere / Black Belvedere** — fundo escuro/grafite com veios DOURADOS e brancos
  naturais correndo. É o quartzito "preto-dourado" mais citado no BR pro look premium.
- **Titanium / Van Gogh / Nero** quartzitos — fundos escuros movimentados com dourado/cobre.
- Cada CHAPA é única (bookmatch possível: espelhar duas chapas pro veio "abrir simétrico"
  no backsplash — efeito de revista, mas cuidado pra não cair no fake luxury exagerado).

| Eixo | Veredito |
|---|---|
| Aparência/veio | **O veio dourado mais bonito e autêntico** — orgânico, profundidade real que engineered não iguala. Base grafite/preto `rgb[34,32,30]` + veio dourado quente `rgb[160,134,88]`. |
| Custo | `$$$$` (natural premium; importado; bloco exótico). O mais caro da lista junto com Dekton. |
| Mancha | **Boa, MAS é POROSO** (natural) → **precisa selar**; alguns quartzitos "moles"/calcíticos manchsam mais. Pedir **teste de absorção** e selante de qualidade. |
| Risco | **Excelente** — dos mais duros que existem. |
| Calor | **Muito boa** (pedra natural, sem resina). |
| Manutenção | **Exige selante periódico** (1×/ano ou mais) e cuidado com ácido em quartzitos calcíticos. Mais ritual que quartzo/porcelanato/Dekton. |
| ONDE FALHA | (1) **porosidade variável** — alguns quartzitos "fake" no mercado são na verdade mármore dolomítico que mancha; **exigir laudo/teste**; (2) preço + imprevisibilidade do bloco; (3) bookmatch mal-feito ou veio largo vira fake luxury. |

---

## 6. MÁRMORE preto-dourado (Saint Laurent, Nero Portoro) — e por que EVITAR no trabalho

Mármore é o "veio mais caro de olhar", e os mármores preto-dourados são lindíssimos:
- **Saint Laurent** — preto com veio dourado e bordô (a referência estética de todo o look).
- **Nero Portoro** — preto profundo com veio DOURADO dramático (clássico de luxo italiano).
- **Marquina** (preto com veio branco).

**PROBLEMA (decisivo):** mármore é **calcário → reage com ácido**. Limão, vinho, vinagre,
refrigerante, produto de limpeza ácido deixam **manchas foscas PERMANENTES (etching)**
mesmo selado, e ele risca/lasca e absorve óleo (poroso). Numa **zona de trabalho de cozinha
de uso real, isso é risco alto** e bate de frente com a regra do Felipe ("manutenção viável,
nada delicado").

| Eixo | Veredito |
|---|---|
| Aparência/veio | Topo absoluto do veio dourado `rgb[36,34,32]` + `rgb[168,140,92]`. Nenhum engineered iguala de verdade. |
| Custo | `$$$$`. |
| Mancha/Calor/Risco | **O pior da lista pro uso** — etching ácido permanente, poroso, risca, lasca na quina. |
| ONDE FALHA | Zona de trabalho molhada de cozinha = onde ele MAIS falha. |
| Veredito | **EVITAR na bancada/cuba.** Se o Felipe se apaixonar pelo veio do Saint Laurent, a saída é: **reproduzir o LOOK** dele num **porcelanato/Dekton "Laurent"** (impressão fiel, indestrutível) na bancada; mármore real só apareceria em superfície DECORATIVA seca (um nicho, uma prateleira), nunca no molhado. Para o nosso caso prático, **nem isso é necessário** — o porcelanato/Dekton entrega o look. |

---

## 7. RECOMENDAÇÃO pro caso (dark + veio dourado SUTIL + manutenção viável + não fake luxury)

Ranqueado pelo perfil do Felipe (beleza moody premium SEM dor de cabeça):

### 🥇 1ª escolha — PORCELANATO / LÂMINA porcelânica preto-dourado MATE (ex. Nero Gold / Laurent / Calacatta Black)
**Por quê:** entrega o "preto-dourado" com veio SUTIL e controlável, é **não-poroso (não
mancha), aguenta calor, sem selante, custo `$$`–`$$$`** (o melhor custo-benefício premium),
e permite o **veio contínuo subindo do tampo pro backsplash** ("tampo que vira parede") —
exatamente a assinatura do nosso tema. É a escolha que mais respeita "manutenção viável".
**Único cuidado:** chanfrar/mitrar a quina (lasca) e pedir **borda mitrada 45°** pra parecer
chapa maciça. Acabamento **mate**, veio SUTIL no tampo, um pouco mais visível no backsplash.

### 🥈 2ª escolha (se o orçamento topar o topo) — DEKTON/NEOLITH "Laurent" MATE
**Por quê:** mesmo look, porém **indestrutível de verdade** (o melhor em calor+risco+mancha
da lista, zero ritual). É o "compra e esquece" premium. Só perde pro porcelanato no **preço**
(`$$$`–`$$$$`). Se a verba estiver folgada e o Felipe quiser o máximo de durabilidade, sobe pra 1ª.

### 🥉 3ª escolha (quer veio dourado NATURAL e topa o ritual) — QUARTZITO escuro Belvedere
**Por quê:** o veio dourado **mais autêntico/bonito** da lista. Trade-off honesto: **é
poroso, precisa de selante periódico e laudo de absorção** (alguns "quartzitos" são mármore
disfarçado). Recomendado SÓ se o Felipe valorizar muito "pedra natural de verdade" E aceitar
o ritual de selagem. Caso contrário, o porcelanato Laurent entrega 90% do look sem o ritual.

### Coadjuvante — GRANITO preto leathered + dourado nos METAIS (não na pedra)
Se a verba for o fator nº 1: **granito preto São Gabriel/Absoluto leathered** (`$$`,
duríssimo, aguenta calor, barato) como base preta, e o **dourado vem do bronze da torneira/
puxador/luminária**, não da pedra. Fica lindo e econômico, mas **não tem o veio dourado na
pedra** — é "preto + metal dourado", um degrau abaixo do conceito.

### ❌ EVITAR
- **Mármore real** (Saint Laurent/Portoro) na bancada/cuba → etching ácido permanente.
- **Qualquer pedra POLIDA espelhada preta** → marca dedo/pó, lê "sujo" em render e na vida.
- **Veio dourado largo/saturado/simétrico exagerado** → fake luxury (anti-padrão do Felipe).
- **Granito Via Láctea/pontilhado** → data, briga com o tema sofisticado.

---

## 8. Decisão da CUBA esculpida na própria pedra (trade-off)

A "cuba esculpida" (*integrated/seamless sink*) é a cuba feita **na mesma chapa do tampo,
sem rejunte/borda** — sem emenda visível, líquido escorre direto pro tampo. É o ápice do
look planejado premium e do nosso tema (cuba preta integrada, zero quebra visual).

**Viabilidade por material (importa pra decisão):**
- **Porcelanato/Dekton slab** — cuba esculpida na própria chapa é **difícil/cara** (chapa
  fina, miolo frágil ao esculpir). Na prática usa-se **cuba sob medida coladada por baixo
  (undermount) da mesma família/cor** → fica quase tão limpo, mais viável.
- **Quartzo** — dá pra fazer cuba integrada (há cubas de quartzo da mesma cor coladas sem
  emenda aparente). Boa opção pro look "tudo preto contínuo".
- **Quartzito/granito/mármore natural** — esculpir cuba no maciço é caríssimo e some o
  veio na cuba; raríssimo em residencial.

**TRADE-OFF honesto pro Felipe:**
| Opção | Estética | Manutenção | Veredito |
|---|---|---|---|
| **Cuba esculpida/integrada na pedra** (preta contínua) | ⭐⭐⭐ máximo do tema, sem emenda | **marca água/calcário e dedo** (superfície fosca preta) → **exige secar depois de usar**; reparo de avaria é caro (é a chapa toda) | **CUIDADO/SIM** — linda, mas WARN de manutenção. Só se ele topar o ritual de secagem. |
| **Cuba PRETA undermount** (granito/quartzo/composto satin) | ⭐⭐ quase tão limpa, junta mínima embaixo | idem (marca água), mas troca isolada se avariar | **SIM** — o meio-termo recomendado: 90% do look, mais reparável. |
| **Cuba INOX undermount** (escovado escuro/gunmetal) | ⭐ menos "tema", mas existe inox preto/gunmetal | **a mais fácil/durável, sem-drama** | **SIM (fallback seguro)** — se "sem dor de cabeça" pesar mais que estética. |

**Recomendação:** **cuba PRETA undermount em quartzo/composto satin (não fosco puro)** da
mesma cor do tampo — entrega o look "cuba preta integrada" do tema, é mais reparável que a
esculpida na chapa, e o **satin** sofre menos marca de água que o fosco. Registrar o WARN
explícito: **"cuba preta marca água/calcário → hábito de secar"**. Se o Felipe priorizar
zero-manutenção, **inox gunmetal/preto undermount** é o fallback honesto.
**Nunca** cuba com textura de madeira (anti-padrão dele).

---

## 9. Tampo × backsplash: mesma pedra? espessura?

**Mesma pedra (SIM, recomendado).** A assinatura do tema é a **mesma chapa do tampo subindo
e virando o backsplash** ("tampo que vira parede"), com o **veio dourado correndo contínuo**
do horizontal pro vertical. Isso só fica perfeito em material de **chapa grande** (porcelanato/
Dekton/quartzito/quartzo) — outro motivo pra 1ª escolha ser slab. Backsplash pode ser **a
parede inteira atrás da bancada até o aéreo** (frontão protagonista atrás da torneira) ou só
uma faixa — o veio é o herói, então **full-height atrás da pia/cooktop** rende mais.

**Espessuras (faixas reais do mercado BR):**
- **Tampo / bancada:** material slab fino (porcelanato/Dekton **6–12 mm**) ganha **espessura
  aparente** via **borda mitrada (45°)** colando uma tira embaixo → lê **20–40 mm** ("frontão"
  robusto premium sem o peso/custo da chapa grossa). Quartzo/granito naturais vêm em **20 mm
  (3/4") ou 30 mm**; 30 mm lê mais "macição premium". Para o nosso look moody: **borda
  aparente 30–40 mm** no tampo principal passa robustez sem ficar bruto.
- **Backsplash:** **fino (6–12 mm)** colado na parede — não precisa de espessura aparente
  (é vertical, não apoia carga). Slab fino é ideal aqui; o veio manda, a borda não aparece.
- **Coerência:** mesmo acabamento (**mate/acetinado**) no tampo e no backsplash; veio
  **alinhado/contínuo** na quina onde um vira o outro (pedir ao marmorista o **bookmatch/
  veio casado** nessa virada — é o detalhe que separa premium de amador).

**Resumo executável pro marceneiro:**
- Material: **porcelanato/lâmina porcelânica preto-dourado MATE, veio SUTIL** (1ª escolha)
  ou Dekton Laurent (se topar o premium).
- Tampo: borda **mitrada 45°**, espessura aparente **30–40 mm**, quina **chanfrada**.
- Backsplash: **mesma chapa**, fino 6–12 mm, **full-height atrás de pia/cooktop**, veio
  **contínuo/casado** na virada.
- Cuba: **preta undermount satin** mesma cor (WARN: secar p/ não marcar água); fallback inox
  gunmetal.
- Acabamento geral: **MATE/acetinado** (nunca polido espelhado preto).
- RGB-alvo render: base `rgb[30,29,32]`, veio dourado-champagne SUTIL `rgb[150,128,86]`.
