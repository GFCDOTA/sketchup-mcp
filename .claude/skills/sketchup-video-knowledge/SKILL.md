---
name: sketchup-video-knowledge
description: >-
  Consulta receitas técnicas extraídas de aulas públicas de SketchUp para modelagem
  de armários, portas, gavetas, bancadas, componentes e materiais. Use quando
  precisar comparar técnicas de marcenaria, traduzir GUI para Ruby API ou
  orientar o futuro sketchup-tooling-specialist. Conhecimento consultivo, não
  autoriza mutação de geometria.
---

# Conhecimento técnico — aulas SketchUp (FP-041)

## Fonte de verdade

Leia apenas o catálogo `references/sketchup/knowledge/video_recipes.v1.json`.
`sources[]` guarda autoria, URL, idioma, data e grau de inspeção da aula;
`recipes[]` guarda procedimentos **parafraseados**, localização na fonte,
pré-condições, armadilhas, invariantes e chamadas de API candidatas.

**O catálogo não representa APIs testadas no SketchUp real.** O estado
`KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP` não deve ser elevado a PROVEN sem micro-fixture,
revisão estrutural e evidência aprovada. A tradução GUI → API é proposta até teste.
Não reutilize medidas de aulas como cotas universais ou do `planta_74`.

## Quando usar

- Solicitação sobre armários, marcenaria, portas, gavetas, bancadas, frestas,
  grupos/componentes, acabamento, rebaixos, recorte de cuba ou textura.
- Comparação de técnicas manuais com Ruby API/MCP.
- Elaboração de procedimento para o especialista FP-041.

## Procedimento

1. Leia os identificadores `recipes[].id` e escolha no máximo três receitas pertinentes.
2. Confira `when_use`, `avoid_when`, `preconditions` e `sources[].locator`.
3. Encontre a implementação existente no repo (`tools/kitchen_layout.py`,
   `tools/wardrobe_builder.py`, `tools/sketchup/*`) e diferencie fatos verificados
   de capacidades não disponíveis.
4. Compare pelo menos duas estratégias se houver geometria não trivial; explique
   por que a escolhida preserva editabilidade e a fonte de verdade paramétrica.
5. Documente chamadas Ruby `api_candidates` como **candidatas**, nunca como prova
   de existência/compatibilidade sem consultar stubs ou API oficial.
6. Encaminhe a execução ao harness e gates existentes, sem tentar executar Ruby,
   MCP de escrita ou alterar `.skp` por esta Skill.
7. Se faltar capability, retorne proposta + `BLOCKED_CAPABILITY_MISSING` e indique
   micro-fixture necessária. O agente de design e o Felipe mantêm a decisão estética.

## Restrições

- `fixtures/`, planta, aberturas e hidráulica são imutáveis sem autorização.
- Nunca apresentar `Face#offset` como método Ruby nativo.
- Intersect Faces não significa que uma cuba foi recortada corretamente.
- Referências a vídeos são para aprendizagem: não copiar legendas extensas,
  cursos, arquivos, imagens ou modelos sem licença.
- Não criar/alterar nenhuma geometria nesta Skill.

## Exemplo de roteamento

Pedido: "Preciso de portas de armário com frestas e frentes Shaker".

Consultar `cabinet.front-gaps-and-profiles`,
`cabinet.reusable-components` e
`cabinet.recessed-shaker-and-louvers`, comparar perfis explícitos com
uma frente simplificada, anotar `PROFILE_BUILDER_EXTENSION_REQUIRED`
e propor gates estruturais antes de qualquer mudança.
