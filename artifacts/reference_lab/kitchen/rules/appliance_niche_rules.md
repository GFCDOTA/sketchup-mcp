# Regras de nicho por eletrodoméstico — a lista de obrigatórios do Felipe

> **Anatomia genérica de qualquer nicho** (painel lateral + frente flush + filler
> + respiro + material do conjunto + topo fechado) vive em
> `references/joinery_rules/appliance_niches.md` — **não repetir aqui**. As
> **medidas/clearances** (altura de bancada, profundidade, cooktop→coifa, torre)
> vivem em `references/joinery_rules/kitchen_ergonomics.md`.
>
> Este arquivo é o que falta: **regras por eletro da LISTA DO FELIPE**, com o que
> é OBRIGATÓRIO, o **fluxo** entre eles, **tomada/respiro/abertura** e a regra de
> **não bloquear circulação**. POSIÇÃO da pia/gás/exaustão = PDF (imutável).

## Obrigatórios (não-negociáveis pra cozinha do Felipe)
- **Lava-louças**, **cooktop**, **forno embutido** — presença obrigatória.
- **Micro embutido** em nicho/coluna (nunca na bancada).
- **Airfryer** em nicho próprio (nunca solta no tampo).
- **Filtro/purificador de água** previsto.
- **Torre quente** (forno + micro + airfryer empilhados em coluna) — agrada,
  estudar como arranjo premium.
- Muito armazenamento; **armário até o teto** (anti-pó); **gavetões inferiores**
  pra panela.

---

## Fluxo de trabalho (a regra que organiza os nichos)

O triângulo/linha de trabalho **cooktop → preparo (bancada livre) → pia** rege a
ordem. Na planta_74 a cozinha é **linear compacta** e a **pia é POSIÇÃO do PDF**
(`KITCHEN_SINK_ANCHOR`) — então os eletros se organizam EM TORNO da pia, nunca o
contrário.

- **Zona molhada** (pia + lava-louças): lava-louças **colado à pia** (encanamento
  e mangueira curtos). Abre a porta do DML sem bater na bancada vizinha nem na
  circulação.
- **Zona de preparo**: **manter ≥ 40–60 cm de bancada livre** entre cooktop e pia
  (a área de apoio que o `ergonomics_gate` exige). Não encher de eletro de bancada.
- **Zona quente** (cooktop + coifa + torre quente): cooktop com a coifa alinhada
  por cima; forno/micro/airfryer na **torre quente** perto da zona de preparo,
  **não** no canto longe (anti-padrão do Felipe: "forno longe do preparo").
- **Regra dura:** estética nunca ganha do fluxo. Forno longe / micro inacessível
  reprova no `appliance_workflow_check`.

---

## Regras por eletro

### Lava-louças (OBRIGATÓRIO)
- **Posição:** adjacente à pia (zona molhada). Frente em **painel integrado** do
  material do conjunto (some o eletro) OU inox aparente flush — ambos são nicho,
  nenhum fica solto.
- **Altura/abertura:** módulo base padrão (~60 cm largura, sob bancada de 90 cm).
  A porta **abre pra baixo/frente** — garantir que a abertura não invada
  circulação nem bata em ilha/porta de cômodo.
- **Tomada:** tomada própria **fora do recorte do eletro** (em módulo vizinho ou
  rodapé técnico), nunca atrás onde o corpo encosta; ponto de água/dreno do PDF.
- **Respiro:** vão técnico atrás pro encanamento; não selar.

### Cooktop (OBRIGATÓRIO)
- **Posição:** embutido no tampo, sobre módulo base (gaveteiro ou forno), **nunca
  vão aberto embaixo**. Ramal de gás/elétrica = ponto do PDF.
- **Abertura/folga:** distância de segurança das laterais (não encostar a chapa de
  pedra direto na boca — calor); ver `kitchen_ergonomics.md` (cooktop→coifa
  45–65 cm under-cabinet).
- **Tomada/ligação:** ponto elétrico/gás dedicado; cooktop de indução exige
  tomada de potência própria.
- **Circulação:** quem cozinha fica de frente — **não** posicionar onde a porta de
  outro cômodo abre nas costas de quem está no fogo.

### Forno embutido (OBRIGATÓRIO)
- **Posição:** **em coluna** (torre quente), porta na faixa **80–100 cm** do piso
  (não se abaixar pra abrir) — arranjo premium. Largura útil ~60 cm.
- **Respiro:** forno gera muito calor → **vão de ventilação atrás + grelha de
  exaustão** especificados pelo fabricante; **nunca selar a caixa**.
- **Tomada:** ponto elétrico de potência próprio, **fora da caixa quente**,
  acessível pra manutenção.
- **Abertura:** porta abre pra frente/baixo — deixar **≥ pessoa agachada** de
  folga; não abrir contra a circulação principal.

### Micro embutido (OBRIGATÓRIO em nicho)
- **Posição:** **empilhado com o forno na torre quente** (arranjo premium) ou
  nicho alto no aéreo. **Nunca na bancada** (`loose_object` clássico que come
  área de trabalho).
- **Respiro:** grelhas laterais/traseiras precisam de folga — caixa selada
  superaquece.
- **Tomada:** ponto atrás do nicho, acessível.
- **Altura:** porta em faixa confortável de alcance (não acima da linha dos
  olhos pra uso diário); micro alto demais = inacessível (anti-padrão Felipe).

### Airfryer (em nicho — pedido do Felipe)
- **Posição:** **nicho dedicado** (gaveta/prateleira ventilada ou módulo na torre
  quente), nunca solta no tampo.
- **Respiro:** airfryer **expele ar quente pra cima/trás** → nicho com **folga
  generosa em cima e atrás** e, idealmente, em **bandeja deslizante** pra puxar
  pra fora ao usar (não usar com a fritura dentro de caixa fechada).
- **Tomada:** tomada **dentro/junto** do nicho (uso frequente, não ficar plugando
  e desplugando).
- **Frente:** esconde no fechamento quando guardada (nicho com porta/cava) — fica
  da linha limpa, sai pra usar.

### Filtro / purificador de água (previsto)
- **Posição:** sob a pia (no gabinete da zona molhada) ou ponto dedicado; saída
  por **torneira/bica própria** ou ramal da torneira principal.
- **Acesso:** troca de refil é manutenção rotineira → **acesso fácil pela frente
  do gabinete**, não enterrado atrás do sifão/lava-louças.
- **Ponto:** entrada de água do PDF; não cria ponto hidráulico novo em parede
  sem prumada.

### Torre quente (forno + micro + airfryer — agrada, estudar)
- **Conceito:** **coluna piso-teto** empilhando os eletros quentes numa única
  caixa de marcenaria (frentes flush, reveal entre eles) — o arranjo mais
  planejado e o que ergonomicamente poupa abaixar.
- **Posição:** **perto da zona de preparo/bancada de apoio** (tirou do forno →
  apoia na bancada ao lado), **não** no extremo oposto da pia.
- **Respiro:** **cada** eletro quente com seu vão de ventilação + grelhas; a
  coluna **não** vira caixa selada. Calor sobe → topo com saída.
- **Tomadas:** um ponto elétrico de potência por eletro, dentro da coluna,
  acessível por trás/lateral pra manutenção.
- **Estrutura:** painel lateral (gable) + filler fechando até teto + topo fechado
  (anti-pó). Estudar carga: coluna de eletro quente pesa — fixação na parede.

---

## Regras transversais (valem pra todos)

- **Não bloquear circulação:** **nenhuma porta de eletro** (lava-louças, forno,
  micro, geladeira) pode, **aberta**, invadir a circulação mínima ou bater em
  porta de cômodo / ilha / outro eletro. Simular a porta aberta antes de fechar a
  spec. Largura de passagem livre = restrição do `ergonomics_gate`.
- **Tomada sempre fora da caixa quente/molhada** e **acessível** pra manutenção;
  ponto dedicado por eletro de potência (forno, cooktop indução, lava-louças).
- **Respiro é do fabricante, não chute** — todo eletro embutido/quente exige a
  folga de ventilação dele; selar = superaquece = falha.
- **Frente flush + filler + topo fechado** em todo nicho (anatomia genérica em
  `appliance_niches.md`). Vão morto acima do eletro = anti-pó violado.
- **POSIÇÃO é do PDF:** pia, ramal de gás, exaustão e prumadas não se movem por
  estética. Layout organiza em torno deles.

## Checklist antes de mostrar
- [ ] Lava-louças, cooktop, forno embutido presentes? (obrigatórios)
- [ ] Micro e airfryer **em nicho** (nenhum na bancada)?
- [ ] Filtro previsto com refil acessível pela frente?
- [ ] Torre quente perto do preparo (forno não-longe), cada eletro com respiro?
- [ ] Fluxo cooktop → preparo (≥40–60 cm livre) → pia coerente?
- [ ] Nenhuma porta de eletro aberta bloqueia circulação / outra porta?
- [ ] Tomadas fora da zona quente/molhada, acessíveis, ponto dedicado por potência?
- [ ] Tudo até o teto, sem vão morto acima (anti-pó)?

Falhou obrigatório/fluxo/circulação → FAIL (`appliance_workflow_check`), consertar
antes de mostrar pro Felipe.
