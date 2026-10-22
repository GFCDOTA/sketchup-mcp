# FP-050 — Piloto de posicionamento de gabinete na cozinha (L1)

> SDD · tools/rooms/kitchen/planning · 21/10/2026 · piloto isolado, **não integrado** ao executor SketchUp.

## Problema e resultado mensurável

Um gabinete pode ser modelado corretamente e instalado no lugar errado. O contrato de fabricação compartilhado e os gates existentes não escolhem uma posição semanticamente adequada. Este piloto seleciona posições candidatas **na parede e âncora indicadas**, explica rejeições e verifica espaço de acesso frontal sem abrir ou modificar SKP.

## Entradas explícitas — metros em um único quadro XY

- Polígono do cômodo, **segmento** da parede de instalação pertencente à fronteira, normal cardinal voltada para dentro e ponto âncora **sobre essa parede**.
- Largura total e profundidade total do gabinete **de base**, faixa livre exigida à frente e passo de busca.
- Listas preenchidas explicitamente de móveis existentes, giro de portas e circulação protegida; ausência de dados (None) bloqueia. Lista vazia é afirmação do chamador de que nada foi encontrado, que o adapter real deverá comprovar.
- A âncora precisa ter origem comprovada pelo chamador (PDF/consensus ou pedido do usuário). O piloto nunca inventa âncora ou parede.

## Gates determinísticos

1. Geometrias inválidas, normal invertida, parede interna solta, âncora em outra parede, medidas faltando, negativas ou não finitas: **BLOCKED_INVALID_CONTEXT**.
2. Gerar posições no segmento declarado e incluir a extremidade. Limite de 5.000 posições, sem exploração contínua oculta.
3. Exigir gabinete **e** faixa frontal inteiramente no cômodo.
4. Gabinete não pode invadir móvel, giro de porta nem corredor protegido. Faixa frontal não pode invadir móvel nem giro; ela **pode** coincidir com circulação desimpedida.
5. Classificar posições válidas pela distância entre centro do gabinete e âncora na parede; desempate por ID estável. Retornar OPTIONS_ONLY com geometria e pose em metros; se nada passar, NO_VALID_POSITION + contagem por código de recusa.
6. **execution_authorized=false em toda resposta**. Nenhum passo deste piloto grava o modelo, muda outros cômodos ou autoriza o executor existente.

## Prova e comando

- Testes: python -m pytest tests/test_kitchen_cabinet_placement.py tests/test_kitchen_cabinet_placement_properties.py -q
- Preview sintético: python -m tools.rooms.kitchen.planning.preview --out runs/fp050_placement_demo
- Artefatos: placement_report.json (códigos, alternativas, scores declarados) + placement_plan.png (planta da micro-fixture fictícia, **não** é a cozinha real).
- Os testes determinísticos (11) passaram em ambiente local isolado. A suíte Hypothesis foi preparada para o CI com extra dev; não foi executada localmente porque o pacote não estava disponível. CI ainda deve confirmar. PNG serve a depuração, não aprovação estética.

## Limites explícitos / próximo gate

O piloto usa envelopes 2D, não varredura física de ferragens, colisão 3D, ergonomia completa, requisitos elétricos/hidráulicos, janela ou prova de qualidade do ambiente. Não substitui a seleção de parede da planta nem as regras D-011 e FP-046–FP-049. Não cabe a um solver descobrir intenção ausente.

Para integração futura, a pose e a intenção de parede devem ser validadas no **cabinet_flow** com gate obrigatório antes do job, vinculadas à assinatura do plano: nenhum caminho alternativo de execução pode contornar o gate. Exigir teste L2 SketchUp com salva/reabre/inspeciona e revisão humana L3 para aprovar a aparência e a posição na cozinha real.

Não promover este L1 a “cozinha resolvida” sem essa validação.
