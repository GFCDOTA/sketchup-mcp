---
name: sketchup-room-knowledge
description: >-
  Consulta a biblioteca segura de modelagem SketchUp por categoria de ambiente (sala, quartos, cozinha, banheiro,
  lavanderia, varanda, home office, closet, circulação), separando o confirmado na documentação e nas aulas das
  adaptações ao projeto, e bloqueia execução não comprovada. Use ao precisar de técnica de modelagem para um cômodo,
  antes de propor builder, ou em "como modelar X no SketchUp" para um ambiente. Consultivo: não autoriza mutação de
  geometria.
---

# FP-041 — conhecimento técnico por ambiente

Leia `references/sketchup/knowledge/environment_recipes.v1.json`. Esse
arquivo é um catálogo **consultivo**; a fonte tem classificação explícita
(`OFFICIAL_DOCUMENTATION_READ` ou `PUBLIC_DESCRIPTION_ONLY`). Não
trate descrição pública como aula assistida nem versão de Ruby API testada.

## Processo obrigatório

1. Localize a categoria em `rooms[].id`, usando os termos de roteamento;
   as nove categorias não equivalem a nove cômodos realmente presentes na planta.
2. Selecione 1–3 receitas pelo campo `rooms`, finalidade, entrada e riscos.
   Consulte `source_refs[].relationship`: `TRANSFER_APPLIED` significa
   **adaptação de uma técnica geral**, não conteúdo explícito daquela aula.
3. Para armários/frentes/gavetas, complemente com
   `references/sketchup/knowledge/video_recipes.v1.json` e a Skill
   `sketchup-video-knowledge`.
4. Confira `parameters_required` na spec arquitetônica/material existente,
   sem preencher com números do vídeo; se faltarem medidas, retorne UNVERIFIED.
5. Consulte `tools/sketchup/knowledge.py` e o builder de cada tipo de cômodo
   apenas para identificar as capacidades presentes e ausentes.
6. Proponha duas rotas se houver modelagem complexa, com ferramentas candidatas,
   geometria isolada, micro-fixture, invariantes e rollback.
7. Finalize como `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`. Nem este catálogo
   nem o catálogo de vídeos autoriza qualquer mutação.

## Proteções

- PDF/consensus e geometria do shell são a fonte de verdade; preservar
  vãos, paredes, hidráulica, elétrica, MEP e circulação.
- Mudanças GEO congeladas exigem aprovação explícita; sem aprovação,
  `BLOCKED_NEEDS_FELIPE_GEO`.
- Reutilizar componentes exige inspecionar definições compartilhadas e
  contexto local/mundo; não editar instância sem confirmar alcance.
- Modelos 3D Warehouse ou vídeo de exemplo não comprovam fit, segurança,
  instalação, ergonomia, ferragens ou licença.
- Não copiar vídeos, screenshots, legendas inteiras ou modelos sem licença.
- Separar L1 sintético, L2 SketchUp real e L3 veredito visual humano.

## Exemplo

"Quero armários planejados na lavanderia": busque
`room.laundry.casework-and-appliances`, complemente com
`cabinet.reusable-components`, consulte hardware real e cotas do projeto.
Se o nicho da lavadora não tiver modelo/folgas do fabricante, não certifique
fit ou fabricação; proponha uma micro-fixture isolada e um gate de envelope.
