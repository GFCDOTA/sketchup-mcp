# ADR-0002: Porta Shaker usa plano próprio (`shaker_door_plan.v1`), sem estender `cabinet_assembly_plan.v1`

- **Status**: Aceito (FP-046/P1, resolve a ADR-046-01 proposta na SPEC)
- **Data**: 2026-10-21
- **Contexto do projeto**: `sketchup-mcp`, gabinete paramétrico compartilhado (`tools/rooms/shared/cabinet/`)

## Contexto

O plano atual do gabinete (`cabinet_assembly_plan.v1`) descreve caixaria retangular + frentes lisas separadas. O
materializador Ruby (`cabinet_build.rb`) só aceita `capability.id == shared.cabinet.parametric`, e `require_valid`
recusa qualquer outro plano. A porta Shaker precisa de papéis novos (`frame`, `panel`), 5 peças por frente e um
recuo real do painel — e as frentes lisas aprovadas não podem mudar de saída nem de assinatura (FP-046 R-19/RNF-03).

## Decisão

1. **Esquema separado.** A Shaker tem `shaker_door_request.v1` e `shaker_door_plan.v1`, capability
   `shared.cabinet.front.shaker`, no pacote `tools/rooms/shared/cabinet/shaker/`. O plano antigo não ganha campos nem
   um modo "estilo": a rota legada fica byte a byte igual (assinaturas das fixtures `valid_a`/`valid_b` travadas em teste).
2. **O plano Shaker é filho de um plano de gabinete.** Cita `parent_cabinet_request_id`, a frente substituída
   (`replaces_part`) e a `parent_plan_signature`. O pai é revalidado por `require_valid` (o código legado) e, se mudar
   depois, `require_valid_shaker` recusa com `PARENT_PLAN_CHANGED`.
3. **Porta única própria.** `require_valid_shaker` revalida a geometria (não confia na assinatura) e recusa plano
   adulterado, reassinado-mas-inválido, com `execution_authorized` alterado ou capability de outro esquema. O
   `require_valid` legado recusa o plano Shaker (capability diferente) — teste explícito.
4. **O materializador Ruby é decisão da P3**, também separado (`shaker_build.rb`); `cabinet_build.rb` segue protegido.
5. **Dentro do módulo `shared`:** sem importar nenhum pacote de cômodo; o adapter da cozinha (P4) consome, não o contrário.

## Consequências

- Duplicação mínima e controlada: `shaker/plan.py` reutiliza `quantity`, `GRAINS`, `definitions`, `_canonical` e a
  assinatura do pai; só a geometria da submontagem é nova.
- Duas portas de materialização (`require_valid` e `require_valid_shaker`): cada uma recusa o esquema da outra.
- Se um dia houver mais estilos de frente (veneziana, almofadada), o padrão "plano filho de um pai assinado" se repete;
  unificar num esquema único exigirá nova ADR e migração de assinaturas.
- Nada aqui autoriza execução, altera canônico ou declara aparência: `execution_authorized=false`, `visual=NOT_REVIEWED`.
