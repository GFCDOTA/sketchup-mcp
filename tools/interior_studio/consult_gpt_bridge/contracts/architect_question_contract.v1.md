# ARCHITECT_QUESTION_CONTRACT v1

> Contrato ESTRUTURADO que o Arquiteto (via `consult-liaison`) emite para o **Consult GPT**.
> O `consult-liaison` monta isto; o Felipe copia e cola no ChatGPT (MVP manual). A resposta
> volta no `ARCHITECT_ANSWER_CONTRACT v1`.
>
> **Regra central (não negociável):** referência manda na LINGUAGEM visual · PDF/planta manda na
> GEOMETRIA · gates mandam em segurança/escala/circulação · **Felipe dá o PASS final**. O Consult
> GPT NUNCA recomenda mover parede, janela, porta, shaft, pia fixa ou elemento congelado do PDF.

## Metadata
- question_id: `<auto: <room>_<phase>_<NNN>>`
- created_at: `<iso datetime>`
- agent: `architect`
- mode: `<SPEC | JUDGE | REPAIR | LEARN | COMPARE>`
- project: `<project name, ex.: planta_74>`
- room: `<kitchen | living | bedroom | bathroom | laundry | full_apartment>`
- phase: `<layout | form | skin | lighting | render | final_validation>`
- theme: `<style target, ex.: BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE>`
- priority: `<low | medium | high | blocker>`

### Modos
- **SPEC** — ainda NÃO há imagem. Pergunta para definir direção visual/material/iluminação/composição.
- **JUDGE** — já há render/imagem. O Consult GPT deve julgar PASS/WARN/FAIL.
- **REPAIR** — algo deu errado. O Consult GPT aponta a correção mínima e objetiva.
- **LEARN** — Felipe aprovou/rejeitou algo. O Consult GPT vira o feedback em memória/regra/anti-pattern.
- **COMPARE** — há 2+ versões. O Consult GPT escolhe a melhor e justifica.

## Contexto
> 3–8 linhas: o que está acontecendo.

## Objetivo da decisão
> Exatamente qual decisão o Consult GPT precisa tomar.

## Inputs visuais
- Imagem principal: `<raw github url ou local path>`
- Imagens auxiliares:
  1. `<url/path>`
  2. `<url/path>`
  3. `<url/path>`
- Se for COMPARE:
  - Versão A: `<url/path>`
  - Versão B: `<url/path>`
  - Versão C: `<url/path>`

> Se a imagem for local, o `consult-liaison` deve dar um caminho que o Felipe consiga abrir/subir
> (raw github url preferível — ChatGPT abre via browsing). Se não houver imagem (mode SPEC), declarar
> "sem imagem — decisão de direção".

## Restrições congeladas (NÃO pode mudar)
- Layout linear da cozinha congelado.
- Posição da pia fixa pelo PDF.
- Geladeira fixa na lateral.
- Circulação mínima não pode piorar.
- Não alterar paredes, portas ou janelas.
> (ajustar à room; sempre listar o que é GEOMETRIA congelada do PDF/golden)

## O que pode mudar (espaço de decisão)
- Pele/material · intensidade da madeira · tipo de pedra · metais · iluminação · decoração leve · cor de eletros.
> (a LINGUAGEM visual; nunca a posição)

## Hipótese do Arquiteto
> O que o Arquiteto tentou fazer e por quê.

## Dúvidas específicas (numeradas)
1. cave_check: ficou escuro demais ou se segura?
2. fake_luxury_check: parece elegante ou virou luxo fake?
3. compact_premium_check: tem impacto sem perder uso real?
4. warmth_balance_check: tem madeira/luz suficiente?
5. material_hierarchy_check: os materiais competem entre si?
6. felipe_taste_match: parece o gosto do Felipe?
7. qual é o ajuste número 1 antes do próximo ciclo?
> (pode acrescentar dúvidas específicas do caso; manter os checks canônicos)

## Formato obrigatório da resposta
Responder usando **`ARCHITECT_ANSWER_CONTRACT v1`**. Obrigatório:
- **VEREDITO:** PASS / WARN / FAIL
- respostas para CADA dúvida (com PASS/WARN/FAIL + explicação curta)
- correção prioritária número 1
- regras novas para o **Felipe Style DNA**
- anti-patterns detectados
- próxima microtarefa executável
