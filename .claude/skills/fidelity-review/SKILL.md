---
name: fidelity-review
description: Use when reviewing whether a generated .skp is faithful to its source PDF. Triggers on phrases like "review SKP", "side-by-side PDF vs SKP", "fidelity check", "room_fidelity", "wall_fidelity", "validar contra planta", "compare with floorplan", "geometry_report", "is the SKP correct". Also fires on visual audits of artifacts/<plant>/.
---

# fidelity-review

Skill pra avaliar se o `.skp` está fiel ao PDF de origem.

## Quando usar

- Review de PR que mexeu em builder ou consensus
- Auditoria de `artifacts/<plant>/` antes de promover
- Investigação de "isso parece errado no SKP"
- Comparação visual PDF underlay vs SKP render

## Spec de referência

Definição completa em `specs/fidelity_gate.md`. Esta skill é o
checklist operacional.

## Checklist de review

### Wall fidelity

- [ ] Todas walls da consensus apareceram como mass extrudada?
- [ ] Sem stubs residuais (PR #192/#193)?
- [ ] Sem notches / slivers no shell polygon?
- [ ] Junction-aware endpoint extension aplicada?

### Room fidelity

- [ ] N closed cells emergiram do polygonize?
- [ ] Cells fundidos têm justificativa (open-plan no PDF)?
- [ ] Labels semânticos preservados com `|` quando fundidos?
- [ ] Cells esperados que NÃO fecharam têm wall geometry
      faltando? (Se sim, é gap real no PDF, não bug do builder)

### Openings

- [ ] Windows preservam peitoril + verga (3D carve)?
- [ ] Doors / passages full-height (2D carve)?
- [ ] Porta-vidro tratada como door (2D), não window?
- [ ] Soft barriers NÃO viraram parede cheia?

### Overlays

- [ ] `side_by_side_pdf_vs_skp.png` gerado e bate visualmente?
- [ ] Render iso + top sob `artifacts/<plant>/`?
- [ ] `geometry_report.json` com gate self-check?

## Evidência exigida

Sem TODAS as 5 abaixo, NÃO declarar sucesso canônico:

1. `.skp` versionado em `artifacts/<plant>/`
2. Render iso + top
3. Side-by-side PDF vs SKP
4. `geometry_report.json` com gate
5. Contract tests verdes

## Quando consultar humano

Pedir PDF / contexto adicional ao humano quando:

- Cell aberto numa região onde "parece" ter parede mas vetor não
  confirma → pode ser peitoril/grade (não-wall) ou PDF
  incompleto. Truth card recomendada.
- Label de ambient ambíguo
- Window que parece deveria ser porta-vidro (e vice-versa)
- Discrepância dimensional > 5% entre PDF measure e consensus

## Quando consultar ChatGPT bridge / LLM local

Em julgamento visual subjetivo (ex.: "parede está no lugar
certo?" comparando renders), seguir `memory/operational_rules.md`
§ Consulta a LLM externo:

1. LLM local (`deepseek-r1:14b` decisão, `qwen2.5-coder:14b`
   código) primeiro
2. ChatGPT bridge `localhost:8765 POST /ask` como fallback
3. Dar contexto: PDF excerpt + render + coords + decisão
   específica

Prompts a LLM devem **forçar criticismo**, não buscar
confirmação ("aponte onde a porta está fora do lugar" > "está
ok?"). Ver memory global `feedback_gpt_critico_imagens.md`.

## Anti-padrões

- Confiar só em render PNG (o `.skp` precisa abrir no SU)
- Tweakar threshold sem ler o artefato (`memory/lessons_learned.md` #8)
- Inventar parede pra fechar cell (Hard Rule #1)
- Aceitar "parece ok" do LLM sem cobrança crítica

## Skills relacionadas

- `pdf-to-skp-pipeline/` — quem gerou o `.skp`
- `skp-artifact-management/` — onde o `.skp` mora
- `multi-agent-handoff/` — se review é shared work
