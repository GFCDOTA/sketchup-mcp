# Spec de composição de layout — review do ChatGPT (sala r002)

> **Origem**: conversa "Crítica de layout sala" no ChatGPT (Plus, Felipe), via
> extensão do Chrome, sobre os renders before/after/iso da materialização do
> layout vencedor (`sofa_mais_poltrona`) na planta_74. 2026-06-04.
> **Status**: spec de referência pro próximo nível do cérebro de layout. NÃO
> implementado ainda. Veredito visual final é do Felipe.

## Convergência (o que o GPT confirmou que o brain já flagava)

O GPT, vendo só as imagens, chegou nos MESMOS anti-patterns que o
`layout_rules.py` já gera deterministicamente — validação cruzada forte:

| Crítica do GPT | Regra do brain |
|---|---|
| "poltrona jogada no topo, sem função, perto da passagem" | RL-04 |
| "sala = 3 caixas soltas num vazio" | RL-13 |
| "não tratar essa divisória como parede-TV principal; marcar **aceitável/ambígua**" | RL-05 + RL-11 |
| "checar corredores **contínuos** de 0,80 m, não só colisão" | gate circulação |

**Veredito do GPT**: "no caminho certo como 1ª solução determinística, mas ainda
não 'bom de design'. TV/sofá defensável; poltrona ruim; sala vazia; o algoritmo
precisa pontuar **composição**, não só encaixe geométrico."

## Convenção de paredes (sala r002, conforme o GPT leu a planta)

- **cima** = portas / cozinha / circulação
- **baixo** = varanda / janela / terraço
- **esquerda** = divisória interna onde o rack (m013) está hoje
- **direita** = corredor / quartos

## A) Layout ideal concreto (peça → posição → dimensão)

| Peça | Posição | Dimensão (m) | Regras-chave |
|------|---------|--------------|--------------|
| **Rack/TV** | parede esquerda interna, centralizado verticalmente (não colado na passagem de cima), centro alinhado ao sofá | comp 1,80–2,20 · prof 0,35–0,45 | ≥0,30 de porta; tratar como parede-TV "aceitável" |
| **Sofá 3L** | paralelo à parede-TV, frente p/ esquerda, centro alinhado à TV | larg 2,10–2,40 · prof 0,90–1,00 | dist olho-TV 2,60–3,20; não colar na parede de cima |
| **Mesa centro** | entre sofá e rack, mais perto do sofá, eixo paralelo ao sofá | 1,00×0,55 a 1,20×0,70 | 0,40–0,50 da borda do sofá; ≥0,75 do rack |
| **Tapete** | centralizado no eixo TV↔sofá | 2,40–2,80 × 1,80–2,20 | entra 0,30–0,45 sob a frente do sofá; cobre 100% da mesa; alcança a poltrona; 0,15–0,30 antes do rack |
| **Aparador** | atrás do sofá (lado direito), paralelo | comp 1,50–1,90 · prof 0,30–0,35 | **só se** `clearance_atras ≥ prof + 0,80`; respiro 0,05–0,10 do sofá |
| **Poltrona** | quadrante inferior/esquerdo, perto da varanda/janela | — | 0,70–1,00 da parede de baixo; 0,90–1,30 da parede-TV; **rotação 30–45°** p/ mesa/sofá; frente toca o tapete; fora do corredor cozinha→varanda |

## B) Checklist determinístico (codável)

### Hard gates (candidato inválido se qualquer um falhar)
- `min_primary_path_width < 0,80` · `overlap_wall > 0` · `overlap_door_swing > 0`
- `overlap_opening > 0,05 m²` · `sofa_tv_dist < 1,80` ou `> 3,80`
- `rack_depth > 0,50` · `coffee_table_sofa_gap < 0,35` ou `> 0,65`
- `chair_blocks_primary_path`
- **Rotas primárias** (pathfinding em planta livre, `required=0,80`, `ideal=0,90`):
  cozinha/entrada→sala · sala→varanda · sala→corredor/quartos · sofá→saída

### Scores (0–100 cada)
- **parede-TV**: comprimento útil 20 · parede limpa 15 · dist sofá-TV 20 · alinhamento 15 · **glare janela 10** (cone 30° oposto à TV → 0) · circulação 10 · **hierarquia focal 10** (divisória interna ambígua → 5/10)
- **sofá**: orientação p/ TV 25 · dist TV 25 · alinhamento central 20 · clearance atrás 15 · não-barreira 15
- **mesa centro**: dist sofá 30 · centralização 20 · tamanho (40–60% da larg. do sofá) 20 · clearance 20 · entre sofá-TV 10
- **tapete**: sobrepõe sofá (0,30–0,45) 25 · mesa 100% sobre tapete 20 · poltrona ≥25% sobre tapete 20 · passa laterais do sofá 15 · respiro do rack 10 · área 18–32% da sala 10
- **poltrona**: não isolada (0,80–1,40 da mesa) 25 · ângulo de conversa (≤10° → 25) 25 · fora da circulação 20 · perto de apoio visual/janela 15 · conectada ao tapete 15
- **aparador** (só se sofá flutua; `if sofa_back_dist < 1,10 → não coloca`): profundidade 25 · comprimento (60–85% do sofá) 25 · clearance restante 30 · alinhamento 20
- **composição global** (o que faltava): eixo focal TV·mesa·sofá alinhado 25 · grupo unido no tapete 20 · densidade móveis/sala (0,18–0,30) 15 · balanceamento lateral 10 · hierarquia circulação (≥0,90) 15 · peças com função clara 15

### Fórmula final
```
if any_hard_gate_fail: INVALID
else: score = 0.20*tv_wall + 0.20*sofa + 0.15*coffee_table
            + 0.15*rug + 0.15*armchair + 0.05*console + 0.10*global_composition
```

## C) Modelo GENÉRICO (qualquer sala) + pipeline determinístico

O sistema é genérico (mobília qualquer planta). O GPT separou o que é universal
do que adapta:

- **universais** (estáveis p/ qualquer sala): circulação 0,80 (ideal 0,90–1,10;
  secundária 0,60) · mesa↔sofá 0,40–0,50 · poltrona↔mesa 0,80–1,50 · tapete sob
  sofá 0,20–0,45 e excede lateral 0,20–0,40 · rack prof 0,35–0,45 · aparador prof
  0,30–0,35 **só se sobra 0,80 depois**.
- **adaptativas**: dimensões-alvo, densidade e programa variam por tamanho/forma.
- **específicas**: a escolha real (parede X, poltrona aqui) é *derivada*, nunca fixa.

### Classificação da sala (passos 0–1)
- **size**: SMALL `<12 m²` · MEDIUM `12–25` · LARGE `>25`
- **shape** (`aspect = max(W,D)/min(W,D)`): SQUARE `≤1.25` · RECTANGULAR `≤1.80` ·
  LONG_NARROW `>1.80` · L_SHAPED (polígono côncavo → decompor em sub-retângulos,
  escolher o lóbulo de estar) · INTEGRATED (abertura `≥1.20 m` p/ cozinha/varanda)

### Programa de móveis por tamanho
- **SMALL**: req `[rack, sofá, tapete]` · opt `[mesa pequena, lateral]` · sem poltrona/aparador
- **MEDIUM**: req `[rack, sofá, tapete, mesa]` · opt `[poltrona, aparador, lateral]`
- **LARGE**: req idem · opt `[2 poltronas, aparador, laterais, 2ª zona]`
- **densidade** `furniture_area/room_area`: SMALL 0,14–0,24 · MEDIUM 0,16–0,30 ·
  LARGE 0,18–0,34 (abaixo = vazia, acima = apertada)
- **distância sofá-TV** por size: SMALL 1,80–2,60 · MEDIUM 2,30–3,40 · LARGE 2,80–4,20

### Ajustes por formato (penalidades/bônus)
- **LONG_NARROW**: sofá paralelo à parede longa, corredor longitudinal 0,80–0,90;
  −30 se sofá divide a sala e deixa <0,80.
- **L_SHAPED**: TV e sofá no MESMO lóbulo (hard fail se separados pela quina);
  outra perna vira jantar/circulação.
- **INTEGRATED cozinha**: sofá pode ser divisor; −25 se rota cozinha→varanda cruza
  entre sofá e TV. **INTEGRATED varanda**: −30 se TV pega glare frontal ou móvel
  invade a faixa da abertura.

### Pipeline determinístico (15 passos)
`0` preprocessar (segmentos úteis, aberturas, door_swings, rotas primárias com peso)
→ `1` classificar → `2` definir programa → `3` paredes-TV candidatas (hard filter +
score) top-K (K=3/5/8 por size) → `4` rack → `5` sofá (variantes width×dist×offset,
faces TV, ângulo ≤15°) → `6` validar circulação (pathfinding ≥0,80) → `7` tapete
(ancora a zona) → `8` mesa de centro → `9` poltrona (opcional, só se couber +
conversa) → `10` aparador (só se sofá flutua e sobra 0,80) → `11` laterais →
`12` score global → `13` backtracking → `14` degradação por size → `15` escolher
(tie-break determinístico).

### Score global com pesos ADAPTATIVOS por size
`final = w·(tv_wall, sofa, circulação, tapete, mesa, assentos_sec, aparador, densidade)`
- **SMALL**: circulação/sofá/tv 0,25 cada · assentos_sec 0 (prioridade: não entupir)
- **LARGE**: composição/assentos pesam mais (prioridade: não boiar no vazio)

### Backtracking (ordem de degradação quando falha)
ajustar sofá → reduzir sofá → ajustar dist → reduzir mesa → mesa→lateral → remover
poltrona → remover aparador → rack menor → TV suspensa → próxima parede-TV → mínimo.
Tie-break: maior final → maior circulação → maior tv_wall → menos opcionais removidos
→ menor deslocamento do sofá → menor wall_id → menor hash geométrico.

### Regra de ouro
**Core válido > opcional bonito.** O algoritmo não pergunta só "cabe?", e sim, em
ordem: (1) há parede focal boa? (2) o sofá conversa com ela? (3) circulação livre?
(4) tapete une o grupo? (5) mesa funcional? (6) poltrona participa ou está jogada?
(7) sofá flutuante precisa de aparador? (8) sala vazia/equilibrada/apertada?

> Isso valida e expande a arquitetura atual: hoje tenho parte do passo 3 (tv_wall
> score), 5 (sofá along-wall) e 12 (score). Falta: classificação (1-2), tapete (7),
> backtracking estruturado (13-14) e pesos adaptativos.

## Como mapeia no código atual

- **`tools/layout_rules.py`** — vira o lar dos novos thresholds + anti-patterns
  (glare, hierarquia focal, poltrona isolada, falta de tapete/mesa, eixo focal).
- **`score()` em `layout_candidates.py`** — hoje é um score chato (soft 0–100);
  evolui pros 7 sub-scores + composição global, com a fórmula ponderada acima.
- **`FURN` + templates** — adicionar `tapete`, `mesa_centro` (já existe, mas T3
  não usa), `aparador`; novo template "estar ancorado" com tapete+mesa+aparador.
- **`spatial_model.py`** — `tv_wall_candidate` ganha fatores: glare de janela
  (cone vs openings de fachada), visibilidade da entrada, interferência de porta.
- **poltrona** — `template_sofa_poltrona` reposiciona p/ quadrante inferior +
  rotação 30–45° (hoje fica reta ao lado do sofá → exatamente o que o GPT reprovou).

## Vira slice (ordem sugerida pelo ROI)

1. **Composição/ancoragem** — tapete + mesa no T3 + aparador condicional →
   resolve o "sala vazia" (maior queixa).
2. **Poltrona em L** — reposicionar + angular 30–45°.
3. **Score de parede-TV** — glare + hierarquia focal + visibilidade da entrada.
4. **Score de composição global** — a fórmula ponderada + eixo focal.
