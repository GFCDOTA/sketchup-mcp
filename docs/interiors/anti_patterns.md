# Anti-patterns de layout de interiores

> Catálogo dos erros que **já cometemos** (ou quase) e que viraram regra em
> [`rules_layout.md`](rules_layout.md) / [`tools/layout_rules.py`](../../tools/layout_rules.py).
> Um anti-pattern só "fecha" quando tem uma regra determinística que o pega e um
> teste/artefato que prova. Sem isso, é só lição que vamos repetir.

## Como ler

- **Sintoma**: o que apareceu na tela / no output.
- **Causa técnica**: a raiz no código, não a aparência.
- **Regra**: o ID que previne (ver catálogo).
- **Severidade**: `hard` (reprova) / `soft` (penaliza) / `process`.
- **Status**: `fechado` (regra + prova) / `aberto` (sem regra ainda).

---

### AP-01 — spawner de sofá burro (asset sem layout)
- **Sintoma**: baixava um sofá do 3DW e jogava no centro do cômodo, sem pensar
  em parede focal, circulação ou função.
- **Causa técnica**: pipeline pulava direto pro asset; não existia etapa de
  layout (spatial_model + candidatos).
- **Regra**: RL-01 (layout antes de asset), RL-02 (placeholder antes de 3DW).
- **Severidade**: process. **Status**: fechado — `layout_candidates.py` resolve
  layout com bounding boxes; 3DW só entra depois de um candidato válido.

### AP-04 / AP-03 — sofá flutuante sem função / orientado pra nada
- **Sintoma**: sofá solto no meio da sala, sem encarar TV nem setorizar nada.
- **Causa técnica**: posição derivada do centroide do cômodo (polylabel), sem
  relação com uma parede focal.
- **Regra**: RL-03, RL-04 (e RL-06 pela distância).
- **Severidade**: soft. **Status**: fechado — `soft.orientacao_sofa_tv` exige
  `facing == "tv"`; sem TV candidate o `run()` retorna NO_VALID_LAYOUT.

### AP-05 — TV na maior parede cega, sem profundidade pro sofá
- **Sintoma**: regra ingênua "parede da TV = maior parede cega" escolhia uma
  parede (ex. m014, profundidade **0.67 m**) onde o sofá não cabe.
- **Causa técnica**: decisão por **uma** métrica (comprimento), cravada como
  definitiva.
- **Regra**: RL-05 (escolher por profundidade + qualidade; preferir borda/fundo)
  e RL-11 (marcar AMBIGUOUS quando incerto).
- **Severidade**: soft + process. **Status**: fechado — `spatial_model`
  ranqueia `tv_wall_candidate` com score e `confidence`; o layout penaliza
  parede interna e **explica** a incerteza (`tv_wall_uncertainty`).

### AP-06 — sofá colado na TV ou longe demais
- **Sintoma**: distância sofá↔TV implausível (TV em cima do nariz, ou sala de
  cinema).
- **Causa técnica**: distância era subproduto do template, não um critério.
- **Regra**: RL-06 (ideal 2.6–3.0 m; < 2.3 m vira hard).
- **Severidade**: soft (hard se < 2.3 m). **Status**: fechado —
  `soft.dist_sofa_tv` + flag `RL-06`.

### AP-07 / AP-08 — sofá bloqueando circulação ou porta
- **Sintoma**: o conjunto (sofá+rack) caía em frente a uma porta / sobre a
  rota cozinha→sala→terraço.
- **Causa técnica**: posição fixa no centro da parede, sem fugir da abertura.
- **Regra**: RL-07 (circulação), RL-08 (aberturas), RL-10 (passagem 0.80 m).
- **Severidade**: hard. **Status**: fechado — hard gates + **busca ao longo da
  parede** (offsets ±0.5..±2.0 m) que desliza o conjunto pra uma posição válida.

### AP-12 — NO_VALID_LAYOUT falso (rejeição por toque de 0.03 m²)
- **Sintoma**: todos os candidatos reprovados por sobreposições minúsculas
  (~0.03 m²) e "fora da área útil", mesmo sendo bons.
- **Causa técnica**: gate de parede e gate de circulação compartilhavam a mesma
  tolerância rígida; encostar na parede contava como invadir.
- **Regra**: RL-09 (atravessar parede) **separada** de RL-07 (circulação).
- **Severidade**: hard. **Status**: fechado — `TOL_WALL_M2=0.06` (tolera toque)
  vs `TOL_CIRC_M2=0.02` (rígido) + recuo `MARGIN_M=0.03` da face.

### AP-13 — empate artificial em 100
- **Sintoma**: os 3 candidatos válidos pontuavam **100**, sem como rankear.
- **Causa técnica**: score só tinha gates binários; nada contínuo.
- **Regra**: RL-13 (proporção/respiro) + score soft contínuo + tie-break
  determinístico.
- **Severidade**: soft. **Status**: fechado — ranking real
  `sofa_mais_poltrona 84.6 > sofa_contra_parede 83.9 > sofa_flutuante 80.6`.

### AP-VIS — oracle de visão alucina veredito
- **Sintoma**: sofá miniatura (altura **0.39 m**) inserido errado; o gate de
  visão (qwen2.5vl) respondeu `VEREDITO=OK` — idêntico pro modelo certo e pro
  errado.
- **Causa técnica**: confiar num oráculo de visão pra julgar geometria que é
  medível deterministicamente.
- **Regra**: preferir **gate determinístico** (dimensão/escala) sobre o oráculo
  de visão. Alinha com a memória "oracle de visão não julga" (PR #209).
- **Severidade**: process. **Status**: fechado no furnishing (auto-scale por
  altura + dimension gate). *Nota: o brain de layout deste slice é 100%
  determinístico — nenhum oráculo de visão participa do score.*

---

## Feedback humano

Cada linha é um veto real do Felipe → a causa técnica → a regra nova → o
teste/artefato que prova que a regra entrou. É o registro de que o loop
fechou (não ficou só na conversa).

| # | Veto do usuário | Causa técnica | Regra nova | Teste / artefato que prova |
|---|-----------------|---------------|------------|----------------------------|
| 1 | "esse verde está vazando por baixo das paredes" | guard-rail (soft_barrier de vidro) não era subtraído da free-cell do chão → o piso corria até a borda externa do vidro | subtrair `soft_barriers` da massa-barreira (`barrier_mass = union(walls + sb_lines)`) | vazamento 5089→718 pt², past-glass-line 0.0; commit `34a988d` |
| 2 | "não registrar 'parede da TV = maior cega' como decisão definitiva… marcar como AMBIGUOUS" | decisão por uma métrica (comprimento), cravada | RL-05 (score multi-fator) + RL-11 (confidence ambiguous + explicação) | `spatial_model` r002 → `m013` ambiguous; `test_ambiguous_tv_wall_is_explained_not_crammed` |
| 3 | "não aceitar empate artificial em 100" | score só com gates binários | RL-13 + soft contínuo + tie-break determinístico | ranking 84.6 > 83.9 > 80.6; commit `9855bb0` |
| 4 | (implícito) sofá miniatura aceito pelo oráculo | confiar em visão pra medir geometria | gate determinístico de dimensão/escala (furnishing) | auto-scale ×2.03 por altura; `furnish_placements.json` |
| 5 | sofá caindo em frente à porta (m013) | posição fixa no centro da parede | RL-08 + busca ao longo da parede (offsets) | `along_offset_m` no JSON; layout válido sem bloquear porta |

### Protocolo pra novos vetos

Quando o Felipe vetar um layout, antes de mexer no código registrar aqui:

1. **Veto** — a frase exata dele (o que ele apontou na tela).
2. **Causa técnica** — a raiz no código/score, não a aparência.
3. **Regra nova** — ID em `rules_layout.md` + check em `layout_rules.py`
   (`flag_anti_patterns`) e/ou peso no `score`.
4. **Prova** — teste em `tests/test_layout_rules.py` **e/ou** artefato
   (JSON/PNG) que mostra a regra disparando. Sem prova, o anti-pattern fica
   `aberto`.

> Regra-mãe: veredito **visual** (IMPROVED/SAME/WORSE) é sempre do Felipe —
> nunca auto. O que automatizamos é o **determinístico** (medida, gate, regra).
