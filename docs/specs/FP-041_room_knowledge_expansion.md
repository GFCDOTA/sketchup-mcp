# FP-041 — Extensão consultiva da biblioteca para ambientes

## Escopo e estado

Branch independente que parte do head de #252, **não** altera
`develop`, `main`, `*.skp`, builder, fixture canônica nem gates.
Nove **categorias de roteamento**: sala, quarto, cozinha, banheiro,
lavanderia, varanda, home office, closet e circulação.

A principal fonte de geometria de um cômodo continua sendo PDF/consensus
+ parâmetros aprovados do projeto. O catálogo de aulas não autoriza
transformações, importações ou mutações.

## Proveniência

- `OFFICIAL_DOCUMENTATION_READ`: explicações técnicas gerais consultadas
  na documentação do SketchUp sobre grupos, componentes, organização,
  Follow Me, materiais e posicionamento de texturas.
- `PUBLIC_DESCRIPTION_ONLY`: temas identificados por descrições públicas
  de vídeos de lavanderia, pergolado e closet. Nenhum passo desses vídeos
  deve ser atribuído visualmente à aula enquanto não houver inspeção.
- `TRANSFER_APPLIED`: adaptação proposta para o cômodo, não
  transcrição ou afirmação de que a fonte demonstrou aquela aplicação.
- `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`: nenhuma receita foi exercida
  dentro do SketchUp real ou promovida a capability operacional.

A biblioteca inicial `video_recipes.v1.json` preserva oito receitas,
e esta expansão possui onze novas receitas (inclui regras cross-room),
sem duplicar as aulas.

## Contrato

`environment_recipes.v1.json`: fontes identificáveis, roteamento por
cômodo, gui_workflow, parâmetros obrigatórios, validações, pitfalls,
capability proposta, proveniência e bloqueio de execução.

Não há novos thresholds normativos. Exigências de fabricação/MEP,
ferragens e ergonomia são UNKNOWN sem norma/fabricante/projeto.

## Uso

O `sketchup-tooling-specialist` deve ler
`.claude/skills/sketchup-room-knowledge/SKILL.md` para demandas de
qualquer dos nove ambientes, selecionar receitas e explicitar a fonte.
A Skill anterior `sketchup-video-knowledge` é aprofundamento específico
para marcenaria, não substituta da biblioteca de cômodos.

## Validação

Teste focado de schema e roteamento é
`tests/test_sketchup_room_knowledge.py`. Sem execução de Ruby ou
alteração da planta; L1 estrutural apenas, L2 e L3 pendentes. Os testes
devem rodar no checkout/CI antes de merge.
