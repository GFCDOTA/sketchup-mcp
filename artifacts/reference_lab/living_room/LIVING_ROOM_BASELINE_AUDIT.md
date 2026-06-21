# LIVING_ROOM_BASELINE_AUDIT — sala r002 (SALA DE JANTAR | SALA DE ESTAR)

> Diagnóstico do estado ATUAL antes de aplicar black_wood_gold. Sem V-Ray, sem material, sem
> propagar estética. Fonte: `furnish_apartment.py` (PT_TO_M=0.0259) → 18 boxes, LIVING OK.
> Evidência: `kitchen_angles/sala_baseline_montagem.png` (top do apê + crop da sala + iso).

## Estado atual (o que o furnish coloca)
Sala r002 = **estar + jantar integrados**, grande, conectada a terraço (porta de vidro), cozinha
e quartos. Móveis colocados: **Sofá · Mesa de centro · Rack TV · Tapete** (4 itens).
Gates: `geometry_sanity` PASS · `furniture_overlap_gate` PASS (3 móveis, 0 sobreposição).
**→ A geometria é VÁLIDA. O problema é LAYOUT/composição, não erro de forma.**

## ✅ Aproveitável
- **Sofá + tapete** (cluster de estar) — posição no canto esquerdo é ok como ponto de partida.
- **A sala é grande e bem integrada** (estar/jantar/terraço/cozinha) — ótimo potencial de zonas.
- **Geometria limpa** — sem overlap, sem degenerado. A base estrutural está sã.

## ❌ Errado / lixo legado
1. **Rack TV FLUTUANDO no meio da sala** — não está ancorado em parede nenhuma; é um bloco fino
   solto no espaço, só "de frente" pro sofá. **#1 problema** (objeto solto, placement não-humanizado).
2. **Mesa de jantar AUSENTE** — o lado "SALA DE JANTAR" da sala-integrada está **vazio**. O brain
   tem mesa de jantar mas ela não foi colocada (não achou zona livre / sala apertada no lado jantar).
3. **Sala sub-mobiliada** — só o cluster de estar no canto; o resto (centro, lado jantar) vazio,
   sem definição de zonas. Parece grande e oca, não planejada.
4. **"Parede de concreto gigante"** — NÃO aparece na geometria gray. É material de render
   (`VRAY_STYLE` industrial concrete), não parede estrutural. Se dominava, é decisão de RENDER a
   reconsiderar no estilo black_wood_gold — não é problema de forma.

## 🚧 Circulação
- Nada bloqueia geometricamente (gates PASS). Mas o **rack flutuando no meio interrompe o fluxo**
  visual. Eixos de circulação: sala↔terraço (porta de vidro, embaixo) · sala↔cozinha · sala↔quartos.

## 📐 Decisões de layout (pra fase de propagação)
- **Parede-TV:** o rack PRECISA ir pra uma parede REAL. Candidata: parede longa onde o sofá já
  mira (definir uma parede sólida como parede-TV; provavelmente a de cima ou a oposta ao terraço).
- **Sofá:** pode ficar no canto esquerdo, mas **orientado encarando a parede-TV** + tapete
  delimitando a zona de estar (ancorado, não no meio).
- **Jantar:** na zona vazia (lado direito/inferior, **perto da cozinha** — fecha a integração
  sala/jantar/cozinha).
- **Objetos → planned_niche_system:** o rack TV vira **painel de TV planejado na parede** (madeira
  ripada/preto + nicho, linguagem black_wood_gold), não móvel solto. Possível marcenaria de parede.

## Próximo passo (NÃO agora)
Depois deste baseline: corrigir forma/layout (ancorar rack na parede-TV, colocar jantar, definir
zonas) → SÓ DEPOIS aplicar black_wood_gold → flat 5 ângulos → GPT critique → V-Ray hero → Felipe PASS.
