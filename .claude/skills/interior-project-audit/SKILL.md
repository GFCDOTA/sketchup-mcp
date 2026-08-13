---
name: interior-project-audit
description: >-
  Audita um cômodo mobiliado/renderizado (banho, cozinha, quarto, sala) como um
  ARQUITETO/EMPRESA DE MOBILIÁRIO REAL assinaria pra OBRA — não como crítico de imagem.
  Postura de OLHOS DE ÁGUIA (escrutínio agressivo, nada passa batido) + consultoria de
  LOJA DE MOBILIADOS (todo apontamento vem com sugestão de produto/solução concreta,
  não só o diagnóstico). Regra central: render bonito NUNCA aprova projeto tecnicamente
  incompleto. Separa design_score (estética) de execution_status (construtibilidade):
  PASS/WARN/FAIL técnico vence qualquer nota visual alta. Use ANTES de declarar um
  cômodo "fechado"/DESIGN_LOCKED, depois que o hero + auditoria 360° (4 cantos) já
  tiverem veredito visual. Dispara em "fecha o banho/cozinha", "pronto pra obra?",
  "audita como arquiteto", "isso é fabricável?", "empresa de mobiliário aprovaria
  isso?", "olhos de águia", "sugere trocas".
---

# Interior Project Audit — buildability gate

> Origem: consulta ao oráculo GPT-Docker (:8899) em 2026-08-09, pedindo pra vestir o
> papel de arquiteto/designer de interiores REAL, com browsing de referências reais
> (MaxHaus 74m², ReG 75m², Sumarezinho 75m², catálogos Deca/Roca/Ideia Glass/
> Portobello) antes de opinar. Ver memória `project_interior_project_audit_skill.md`.

**Regra-raiz (Felipe, via GPT):** *"render bonito nunca pode transformar projeto
tecnicamente incompleto em aprovado."* Um `execution_status: FAIL` bloqueia
`DESIGN_LOCKED` mesmo com nota visual 9.8.

**Postura obrigatória (Felipe, 2026-08-09): olhos de águia + consultoria de loja de
mobiliados.** Não é auditoria passiva de "aprovar/reprovar" — é escrutínio ATIVO
(procurar defeito que não salta aos olhos, não só reagir ao óbvio) **e** toda
reprovação/WARN vem empacotada com a sugestão de produto/solução que resolveria,
como faria um bom vendedor técnico de loja premium (Tok&Stok/Westwing/marcenaria) —
nunca só "isso está errado", sempre "troca por X / resolve assim, porque Y".

## Quando dispara

Depois que um cômodo já passou por `interior-architect-planner` (DesignIntentSpec) +
render do hero + auditoria 360° (plan + hero + 4 cantos, ver `gpt-review-gate`), ANTES
de declarar o cômodo fechado/pronto pra portfólio. Não substitui o veredito visual —
audita se o que está **por trás** do render é executável.

## Saída (3 sinais separados, nunca uma nota só)

```yaml
design_score: 0..10          # conceito/estética — julgamento humano/GPT
visualization_score: 0..10   # qualidade do render em si
execution_status: PASS | WARN | FAIL   # buildability — determinístico onde der
```

## Pipeline — 12 gates em sequência

**GATE 0 — BENCHMARK.** Antes de criticar, comparar com referência construída da
MESMA escala/tipologia (ex.: apê compacto 70-80m² BR, não penthouse). Registrar
`references: {built_projects_same_typology, built_projects_similar_area,
manufacturer_references}`.

**GATE 1 — GEOMETRY TRUTH.** `room.dimensions_verified`, `ceiling`, `door`,
`windows`, `shafts`, `structure`. Qualquer valor presumido = `UNVERIFIED`, nunca
inventado. (Pega o gotcha real do BANHO 01: vãos de teto abertos vazando background —
isso é bug de geometria, não estética, e é HARD FAIL aqui.)
Antes de julgar aqui: rodar `python -m tools.semantic_geometry_contract_gate <room>`
e `python -m tools.collision_envelope_gate <room>` (determinísticos, 2026-08-12 —
ver `core/spatial_semantics.py`). Este GATE 1 **audita o resultado**, não reimplementa
a checagem — se algum item vier `FAIL_MISSING_SEMANTICS` ou `soft_items_never_solid`,
já é HARD FAIL aqui, sem precisar de julgamento humano/GPT pra essa parte.

**GATE 2 — PRODUCT REALITY.** Cada peça: `manufacturer, model, sku, width, depth,
height, installation_type, technical_source`. Checar `catalog_bbox == model_bbox`.
Nada de objeto genérico tipo `black_rectangle_02` — vira `toilet_paper_holder`,
`robe_hook`, etc., com fonte técnica real.

**GATE 3 — ASSEMBLY FIT.** Não testar a peça isolada — testar o CONJUNTO:
`WALL + FAUCET + COUNTERTOP + BASIN + TRAP + DRAWER + USER`. Saída:
`front_margin, rear_margin, drill_clearance, trap_collision, drawer_collision,
service_access → PASS|WARN|FAIL`.
Se algum otimizador/busca de posição escolheu onde essa peça vai, rodar
`python -m tools.optimizer_consistency_gate <room>` — otimizador que aprova
uma posição usando heurística diferente do gate real é o mesmo bug de
"testar peça isolada" (achado 2026-08-12: `correction_fixes.py` tinha uma
cópia própria da regra de colisão que divergiu da canônica sem ninguém notar).

**GATE 4 — ERGONOMIA.** Dois envelopes por objeto: `physical_bbox` + `usage_bbox`
(usuário, abertura, alcance, passagem, manutenção). Todo threshold tem
`value` + `source` (`office_rule|manufacturer|standard|client_requirement`).
Sem fonte = `UNVERIFIED`. Nunca hardcode "60cm porque acho".
Isso já é CÓDIGO pra circulação/cadeira (não só julgamento humano): thresholds
com value/source/scope/applicability em `core/project_policy.py`;
`portal_role` (PRIMARY/SECONDARY) declarado por papel arquitetônico da
abertura em `circulation_gate.py`, nunca inferido pela largura medida — a
mesma regra vale aqui: threshold de ergonomia sem `source` fica `UNVERIFIED`,
threshold que É `project_decision` (não norma) tem que dizer isso, não se
disfarçar de norma técnica.

**GATE 5 — MEP** (hidráulica/elétrica). `cold_water, hot_water, sewer, drain,
electricity, ventilation, route_to_shaft` → `VERIFIED|UNVERIFIED|CONFLICT`.
`CONFLICT` = hard fail (ex.: posição do vaso mudou mas ninguém checou a rota até o
shaft).

**GATE 6 — WET AREA.** `waterproofing, floor_slope, drainage, window_return,
sealant, glass, ventilation, maintenance_access`. Janela dentro do box sobe o nível
de auditoria automaticamente.

**GATE 7 — FABRICATION.** Todo item sob medida: `substrate, skin, thickness,
edge_detail, hardware, service_cutout, removable_parts, tolerances, mounting`.
Pergunta-teste: *um fornecedor fabrica isso sem ligar pro arquiteto pra entender
como funciona?* Se não → `SHOP_DRAWING_REQUIRED`.

**GATE 8 — DESIGN INTENT.** Para cada feature especial: `purpose, user_benefit,
maintenance_cost`. Se `purpose == "deixar o render melhor"` → `REJECT`. (Este gate
teria barrado o light slot vertical do BANHO 01 antes de virar rasgo+perfil+driver.)

**GATE 9 — LIGHTING AS FUNCTION.** Separar `general | task | accent`. Espelho é
avaliado primeiro como `task lighting` (função), só depois como composição de foto.

**GATE 10 — 360° AUDIT.** Obrigatório: `PLAN + HERO + NO + NE + SW + SE` (ver
`render_banho_vray`/corner renders). Detectar por canto:
`open_geometry, floating_objects, intersections, unfinished_surfaces,
unknown_objects, missing_material`. **O hero não pode esconder erro** — foi assim
que o BANHO 01 caiu de 8.4 (só hero) pra 7.6 (4 cantos rigorosos).

**GATE 11 — PROJECT CLOSE.** Só escrever `DESIGN_LOCKED` quando `hard_fails == 0`
e todos os gates acima `PASS`/`VERIFIED`. Depois disso: `BEAUTY_PASS_ONLY` — qualquer
mudança de layout exige reabrir com `REOPEN_DESIGN: {reason}`.

## Fluxo recomendado (substitui "render → nota → correção → render")

```
referência construída → geometria → produto real → assembly fit → ergonomia
→ MEP → área molhada → fabricação → auditoria 360° → DESIGN LOCK → V-Ray (beauty pass)
```

## Como consultar (mesmo mecanismo do `gpt-docker-consult`)

Prompt pro GPT-Docker (:8899) deve pedir explicitamente: (1) vestir o papel de
arquiteto/designer que ASSINA o projeto, não crítico de imagem; (2) pesquisar
(browsing) referência construída real da mesma tipologia/escala ANTES de opinar;
(3) responder gate a gate, não só nota geral. Sem isso o oráculo tende a repetir a
crítica estética de imagem que já rodou no `gpt-review-gate`.

## Anti-regras

- NÃO aceitar `DESIGN_LOCKED` com qualquer gate em `FAIL`/`CONFLICT`, mesmo com nota
  visual alta.
- NÃO inventar dimensão/fonte de produto — sem `technical_source`, é `UNVERIFIED`.
- NÃO deixar o hero (1 ângulo) representar o cômodo inteiro — gate 10 é obrigatório.
- NÃO manter feature cujo `purpose` é só "ficar bonito no render" (gate 8).
- NÃO entregar diagnóstico sem sugestão — cada FAIL/WARN carrega o produto/solução
  concreta que resolveria (postura de loja), não só "está errado".
