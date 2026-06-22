# Arquiteto-agente: papel, modelo, aprendizado · Claude × GPT (ponte) · 2026-06-22

> Felipe: (1) o inventário do cômodo devia ser o ARQUITETO decidindo (olhar dims + o que existe → propor móveis),
> não Claude hardcodando; (2) qual LLM local pro Arquiteto, rodar contínuo, e como/quando ele aprende.
> Fatos confirmados no código: Arquiteto = `deepseek-r1:14b` (reasoning, text-only); aprende por RAG priming
> (DNA `felipe_style_dna.md` + anti-patterns/erros marcados + textos do GPT alimentados) — NÃO treina pesos, NÃO
> tem loop contínuo. **GPT validou TODAS as posições do Claude.**

## VEREDITO GPT: "concordo com tua posição"
O Arquiteto local tem valor REAL, mas **não como 'designer mágico visual'** — o valor é **raciocínio textual de
programa, coerência e intenção**.

## (1) Inventário por Arquiteto — CONCORDO
Hardcodar `ROOMS = sala tem sofá/mesa/rack` é frágil (cada planta muda). O Arquiteto RECEBE: ambiente · dimensões ·
aberturas/circulação · estilo · assets existentes · restrições · DNA+anti-patterns. E DEVOLVE um **programa de
mobiliário como `proposal`** (Felipe aprova):
```json
{"environment":"sala_jantar","proposal_type":"furniture_program","items":[
  {"asset":"sofa","priority":"core","reason":"define estar e conversa com rack/TV"},
  {"asset":"mesa_centro","priority":"...","reason":"..."}]}
```

## (2) Modelo
- **Arquiteto principal = `deepseek-r1:14b`** (boa escolha pro papel: decidir programa, detectar conflito
  intenção×anti-pattern, raciocinar circulação textual, explicar entra/sai, gerar proposal estruturada).
- **Qwen** se DeepSeek for verboso/lento/ruim em JSON estável → bom pro **Auditor/formatação** ("DeepSeek pensa, Qwen audita/formata").
- **Visão NÃO obrigatória no v1** se as dims+constraints forem bem estruturadas. **Qwen2.5-VL/Qwen3-VL como
  Vision Helper OPCIONAL** é excelente pra ler crop/planta/render → devolve texto estruturado pro Arquiteto.

## (3) Aprendizado — CONCORDO (captura inline + consolidação separada)
- **Captura INLINE** por ciclo (um `learning_event`: cycle/asset/observation/candidate_dna_rule/evidence/
  status="captured_pending_consolidation") → aprende rápido.
- **Consolidação SEPARADA** (passe: deduplica · resolve conflito · junta regras parecidas · remove regra fraca ·
  promove pro DNA · marca anti-pattern), com o **Auditor de Consistência** olhando contradição → memória limpa, DNA não incha.
- **5 coisas pra aprender mais rápido SEM treinar pesos:** memória em CAMADAS → `CANON_DNA` (regras aprovadas,
  curtas, estáveis) · `ANTI_PATTERNS` (erro com gatilho+exemplo) · `CASE_MEMORY` (casos por ciclo: sofá Venezia,
  cozinha black/gold, rack) · `GPT_VERDICTS` (texto externo = EVIDÊNCIA, não regra automática).

## Arquitetura final recomendada (GPT)
- **Arquiteto Local = deepseek-r1:14b:** propor programa de mobiliário · justificativa de design · riscos textuais · proposal estruturada.
- **Vision Helper = Qwen2.5-VL (opcional):** ler crop/planta/render · observações visuais → texto estruturado pro Arquiteto.
- **Auditor = Qwen ou DeepSeek (o mais estável em JSON):** detectar contradição/gap · revisar learning_events · propor limpeza de DNA.
- **Aprendizado:** captura inline por ciclo + consolidação/dedup separada.

## Próximo build (decorre disso)
**`furniture_program` por Arquiteto** = substituir o `ROOMS` hardcodado por uma PROPOSAL do Arquiteto (recebe dims
da planta + estilo + existentes → propõe móveis + porquê → Felipe aprova → vira o inventário do cômodo). É o uso
real, não-firula, do LLM local + responde "deixar o Arquiteto decidir" + "dar trampo contínuo pros caras".
