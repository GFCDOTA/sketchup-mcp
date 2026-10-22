# 📐 SPEC de Feature — FP-053: Demo-first, Golden Components e Reuso Antes de Construir
> SDD · GFCDOTA/sketchup-mcp · Micro-fixtures + source of truth + SketchUp 2026 · Planejamento e contrato (sem implementação de builders neste PR)

## 🏷️ BLOCO 1 — Metadata

~~~yaml
spec:
  feature: "FP-053 — Aprendizagem granular orientada por demos e componentes existentes"
  escopo_versao: "Sempre que uma capacidade estiver ausente ou insegura, priorizar reuso autorizado, caso mínimo reproduzível e prova executável antes de generalização e integração ao apartamento."
  versao: "1.0.0"
  status: "RASCUNHO_COM_CRITERIOS_EXECUTAVEIS"
  classificacao:
    contexto_delimitado: "Knowledge / Reference Lab / Shared Geometry / Especialistas"
    dominio: "SketchUp MCP"
    funcionalidade: "gap → procurar/reusar → golden demo → variações → capability → consumidores"
  specs_relacionadas: ["FP-048", "FP-049", "FP-050", "FP-051", "FP-052", "FP-046", "FP-047"]
  baseline_documental: "develop (consultar HEAD antes de cada PR; nenhuma mudança implícita de L2/L3)"
  owner: "tools.rooms.shared (capability) + specialist por cômodo (intenção e regras locais)"
~~~

## 1. Hipótese e objetivo

O caso de referência é `docs/specs/quadrado_demo_spec.md`, com `fixtures/quadrado/consensus_with_window.json`, saída geométrica conhecida, testes e render. Ele provou que uma micro-fixture concreta pode proteger regras difíceis (parede contínua, janela com peitoril e verga, sem recorte integral tipo porta) e permitir reuso na planta maior. **Não significa que seu código ou suas dimensões se aplicam a qualquer objeto.** O método, não a implementação específica, é o padrão.

**Problema:** um agente que recebe "construa bancada com cuba" pode fabricar uma caixa com decalque, ou uma mesa que bloqueia a circulação. A FP-053 garante que a próxima tarefa ausente resulte primeiro em uma prova pequena ou num asset externo **verificado**, nunca numa improvisação silenciosa. A FP-050 continua dona das restrições espaciais; fabricar um objeto válido NÃO prova placement.

**Meta mensurável do piloto:** um recorte de bancada real, com dimensões e resultado-alvo definidos, criado em micro-fixture independente da planta; variações e negativos; resultado salvo/reaberto no SketchUp real; reuso do **mesmo** código na cozinha e no banheiro sem duplicação, respeitando targets próprios. Até L2/L3, registrar estados pendentes, não afirmar móvel concluído.

## 2. Autoridades: quatro verdades distintas

| Item | Verdade autoritativa | Proibido concluir |
|---|---|---|
| **O QUE** construir | FP-052 `reference_target.v1`: anatomia, alvo, referências por peça, medidas/origem e aceites | imagem "bonita" ou sample único autoriza todos os móveis |
| **COMO** construir | recipe por operação com tutorial/revisão/trecho, documentação SketchUp, limitações e decisões derivadas | outro trecho do mesmo vídeo herda `source_verified=true` |
| **O QUE FUNCIONOU** | golden demo versionada: input, expected geométrico, oracle independente, testes/evidência L1/L2/L3 escopada, hash | um render ou asset de terceiros por si só comprova algoritmo próprio |
| **ONDE** instalar | PDF, consensus, restrições do cômodo, FP-050 e gates de circulação | uma peça correta pode ser colocada em corredor ou no meio da cozinha |

**Golden demo é fonte de verdade de REGRESSÃO da capacidade, não substitui o alvo de produto da FP-052.** Alterar o sample esperado requer diff, justificativa e revisão, nunca atualizar snapshots para fazê-los coincidir com uma saída ruim.

## 3. Decisão obrigatória ao encontrar um GAP: buscar antes de inventar

O especialista deve consultar o `capability_catalog.v1.json`, a base `references/sketchup/knowledge/` e o `reference_lab`, e emitir `gap_report` com o `target_id`, `part_id`, necessidade funcional, evidência faltante e próximo passo. A seguir aplicar a política:

1. **REUSE_CAPABILITY** — capacidade própria existente com geometria/versão/limites suficientes e prova L2 atual; testar contra o novo target e contexto. Sem reescrever builder.
2. **IMPORT_ASSET_VERIFIED** — modelo existente e autorizado (3D Warehouse, componente local, fabricante) atende ao uso pretendido, tem licença/proveniência e é inspecionado no SketchUp; pode ser usado como **instância de asset** sem fingir que geramos sua técnica paramétrica. Se alvo pede edição procedural, reparametrização profunda ou replicação de técnica, importar não satisfaz o requisito de **habilidade aprendida**.
3. **BUILD_MICRO_DEMO** — nenhum candidato adequado, ou requisito exige capacidade paramétrica editável: criar micro-fixture e implementar capacidade shared. Antes de codificar, identificar tutoriais/documentação, suas provas e contrato de sucesso.
4. **BLOCKED_MISSING_EVIDENCE** — não existe fonte/alvo/dimensão/uso seguro. Produzir perguntas técnicas e pedido de curadoria em vez de fabricar geometria ou declarar sucesso.

A escolha deve registrar `decision_reason`, alternativas rejeitadas e custo esperado. Proibido "reuso" de capability cuja prova L2 ficou stale após alterar símbolo, ou cujo escopo não cobre o pedido.

### 3.1 Usar 3D Warehouse sem reinventar a roda

Documentação oficial: https://help.sketchup.com/pt-br/sketchup/inserting-components e https://help.sketchup.com/en/3d-warehouse/downloading-model-file-formats.
Termos/licença oficiais consultados em 2026-10-22: https://3dwarehouse.sketchup.com/tou (inclui General Model License). **Revalidar termos e requisitos quando o agente executar uma tarefa, pois podem mudar.**

- O 3D Warehouse fornece modelos SketchUp, não instruções comprovadas de como reproduzir sua topologia ou construir mobiliário sob demanda; pode ser **produto pronto**, **inspiração/benchmark autorizado** ou **candidato para inspeção técnica**, categorias distintas no registro.
- **Proibido scraper, crawler, download em massa ou automação não autorizada do Warehouse.** Buscar/selecionar/download via fluxos oficiais permitidos, interação do usuário ou mecanismo expressamente autorizado pelo fornecedor. Não criar bot de pesquisa/download ou indexação de assets do catálogo externo.
- Registrar URL/ID estável do asset, título, autor, origem, data de acesso, versão/formato, autorização de uso, termos aplicáveis, SHA-256 do arquivo efetivamente obtido, limites de redistribuição, `role` e `reviewer`. Se o arquivo não estiver disponível, conservar somente metadados/URL, com `asset_unavailable`. Nunca inventar hash nem afirmar licença confirmada sem prova.
- Não commitar `.skp` baixado de terceiros em repositório público sem direitos adequados; manter importação manual/consentida em cache local não rastreado e usar fixtures próprias no CI. Preservar créditos e avisos de autoria, proibir redistribuição como modelo standalone.
- Antes de usar asset em projeto, inspecionar unidades/escala, bounding box, hierarquia de grupos/componentes, faces invertidas, material, origens, eixo, tamanho do arquivo, polígonos extremos, conteúdo oculto e tags. Sanitizar/importar em **modelo isolado** sem executar scripts/plug-ins embutidos ou código externo; rejeitar assets suspeitos e incompatíveis.
- Importação de asset pode ser suficiente quando objetivo é decorar, representar eletro/ferragem ou preencher volume aprovado. Para recortes, parametricidade ou construção ensinada, a *golden demo própria* continua necessária se o requisito for uma capability nossa.
- O asset de terceiros pode ajudar a selecionar anatomia ou estabelecer expectativas qualitativas, mas suas dimensões não se sobrepõem ao PDF, a manuais de produto nem a medidas confirmadas. Fotos ou modelos sem cotas não fornecem medidas de fabricação.
- Não usar scraping, extração em escala ou "treinamento automático" com modelos de terceiros; atividades de aprendizado deste projeto significam conhecimento versionado, receitas e código, com respeito aos direitos de uso.

## 4. Contrato proposto de Golden Demo (fase D0/D1, ainda não implementado)

Um diretório de demo por *capacidade*, com variações sob a mesma implementação; não um diretório por cada móvel do apartamento. Todos os links apontam para fontes canônicas existentes em vez de duplicar tutoriais, imagens ou decisão de design.

~~~text
fixtures/components/<capability_slug>/
  case_001_golden/
    request.json
    expected_geometry.json
    manifest.json
    reference_view.png             # somente se própria/licenciada para repo
  case_002_offset/
    request.json
    expected_geometry.json
  case_003_invalid/
    request.json
    expected_rejection.json

tools/rooms/shared/<domain>/
  model.py
  plan.py
  validation.py
  sketchup.py
  ruby/<capability>_build.rb
  ruby/<capability>_inspect.rb

tests/test_<capability>.py
tests/test_<capability>_properties.py
artifacts/review/<feature>/<attempt>/  # apenas provas promovidas
runs/<feature>/                           # experimentos descartáveis
~~~

`manifest.json` proposto (pseudocontrato, campos não existentes hoje; criar schema em D1, sem inserir no catálogo antes de implementá-lo):

~~~json
{
  "schema_version": "golden_component_demo.v1",
  "demo_id": "shared.countertop.cutout/case_001_golden",
  "capability_id": "shared.countertop.cutout",
  "state": "DRAFT",
  "input_ref": "fixtures/components/countertop_cutout/case_001_golden/request.json",
  "expected_ref": "fixtures/components/countertop_cutout/case_001_golden/expected_geometry.json",
  "target_ref": "artifacts/reference_lab/targets/<project>/<room>/<furniture>.target.v1.json",
  "recipe_ids": ["cabinet.sink-and-wet-channel-cutouts"],
  "source_reviews": [],
  "external_assets": [],
  "parameter_origin": "user_request_or_confirmed_technical_spec",
  "proven_invariants": ["real_through_opening", "valid_solid", "editable_component"],
  "anti_patterns": ["black_rectangle_decal", "solid_block_without_hole"],
  "expected_failures": ["cutout_outside_slab", "insufficient_edge_margin"],
  "evidence": {"l1": "PENDING", "l2": "PENDING", "l3": "PENDING"},
  "execution_authorized": false
}
~~~

**Atenção:** os campos acima são PROPOSTOS, não arquivos já existentes. O `target_ref` deve apontar para o alvo específico **quando conhecido**; uma demo puramente técnica pode ter `target_ref=null` e nunca é prova de que um móvel específico foi aprovado. As dimensões e folgas da demo devem ser valores explicitamente escolhidos como **parâmetros de teste**, não declarados como medidas reais da planta.

### Dependência crítica já identificada pelo handoff do Claude (T0.1)

O handoff integrado em `docs/handoffs/2026-10-22_general_app_handoff.md` e a **fila única** `docs/specs/construction_core_microphases.md` identificaram lacuna histórica de R-18: `capability_catalog.symbol_digest` não cobria todos os helpers transitivos que calculam geometria. **A microfase T0.1 foi concluída no PR #363**: `tools.rooms.evidence_closure` agora usa `closure_digests` e o catálogo bloqueia evidência obsoleta com `EVIDENCE_CLOSURE_STALE`. Nenhum builder ou demo pode contornar esse gate; alterações no fecho exigem revalidar L2 em commit limpo. A FP-053 é o **método de pesquisa/demo/reuso** consumido pelas microfases já ordenadas, não uma segunda fila. A implementação de D0/D1 deve seguir T0.3 (planejador de gaps) e as pré-condições da fila; T0.2 (scratch seguro) continua anterior.

## 5. Ciclo de aprendizado em fatias pequenas

**D0 — Inventário e seleção do próximo gap:** varrer bindings não resolvidos e necessidades reais dos cômodos, incluindo `bind.kitchen.sink-cutout`, `bind.kitchen.countertop`, `bind.kitchen.drawer` e banho; classificar por valor de reuso, pré-requisitos e fonte disponível. Não remodelar o apartamento.

**D1 — Alvo e pesquisa de reuso:** inspecionar capability interna, documentação oficial, tutorial curado e modelo externo quando legalmente acessível. Emitir decisão `REUSE_CAPABILITY / IMPORT_ASSET_VERIFIED / BUILD_MICRO_DEMO / BLOCKED_MISSING_EVIDENCE`. Verificar licença e revisão por recipe; **não** promover "TRANSCRIPT_AND_VISUAL_WALKTHROUGH" sem human_review do trecho pedido.

**D2 — Fixture e oracle antes do builder:** formalizar anatomia, dimensões e tolerâncias com origem; escrever testes vermelhos para geometria correta e negativo que falha se trocarmos o objeto por proxy/caixa. O oracle geométrico deve ser derivado de invariantes e dados independentes, não somente snapshot produzido pelo próprio builder.

**D3 — Implementar UM primitivo ou capability em `shared`:** usar Shapely/números para geometria determinística quando adequado; Python produz plano tipado, Ruby materializa SketchUp; separar definition/instance, nomes e IDs estáveis, coordenadas locais e transformação, sem uso de AI para inventar coordenadas. Especialista apenas agrega regras de domínio.

**D4 — Testes L1 e propriedades:** testar golden fixo, edge cases e variações (incluindo escala, rotação, assimetria e limites), topologia, cotas, tolerâncias e desempenho. Hypothesis já está no extra `.[dev]`; seed/caso falho reproduzível. Mudar snapshot esperado requer revisão, não auto-aceite.

**D5 — L2 SketchUp real:** Windows/versão registrada, job com cópia temporária, PID rastreado, reabertura e inspector Ruby independente. Salvar partes editáveis, bbox/topologia real, ausência de perfuração acidental da arquitetura e prova FP-047 de isolamento; rejeitar `FakeSystem` ou render como substituto. Reexecutar L2 ao alterar símbolo protegido por digest (R-18).

**D6 — Promoção escopada:** registrar `capability_catalog`, vínculo com recipe/target, provas e limites. `L2_PASS` da capacidade não concede `L3_APPROVED` de produto. Se asset importado: registrar `ASSET_VERIFIED` em índice de assets, **não** registrar como capability paramétrica própria.

**D7 — Reuso em dois contextos:** testar o mesmo símbolo com parâmetros e transformações diferentes (ex.: recorte da cozinha e bancada do banheiro), sem import de módulo de cozinha por shared. Primeiro provar em duas demos, depois integrar ao projeto real com FP-050 e aprovações necessárias; demonstrar segundo consumidor L2.

**D8 — Retomar tarefa original:** o gap planner deve persistir `blocked_task_id`/`target_id` e dependency DAG; ao promover a capability, reconstruir o plano e avançar a tarefa anterior somente se precondições, versão da evidência, aprovação target e placement ainda forem válidos. **Nunca executar automaticamente só porque a demo ficou verde.**

### Integração com os fragmentos dos especialistas (PR #366)

Cada `tools/rooms/<room>/fragments/<id>.fragment.v1.json` é **índice validado de ponteiros**, não executor independente. Quando D2–D5 criarem uma demo, registrar seu artefato versionado no campo `demos` do fragmento dono (como `tools/rooms/kitchen/fragments/countertop_and_sink.fragment.v1.json`) e relacionar a capacidade compartilhada ao catálogo canônico. O mesmo builder de recorte deve poder ser consumido por cozinha e banheiro (`vanity.fragment.v1.json`), cada um com regras de instalação distintas. `tools.rooms.specialist_fragments.verify()` deve continuar verde. Esses fragmentos atualmente **não contêm as novas demos/capacidades**: são registros das lacunas.

A fila executiva é `docs/specs/construction_core_microphases.md`: T0.1 FEITA; T0.2–T0.5 prontas; K1/K2/K4 bloqueadas por pré-requisitos de evidência, alvo e/ou montagem. **Não converter este backlog ilustrativo em segunda fila, nem promover o recorte antes das pré-condições K1/K4.**

## 6. Pilotos sequenciais e provas que devem falhar

| Prioridade | Golden demo | Prova de sucesso | Regressão negativa crítica |
|---|---|---|---|
| 0 (referência) | Quadrado e janela **já existentes** | parede única + abertura parcial + vidro + invariantes versionadas | janela tratada como recorte de porta / parede quebrada |
| 1 | Placa com recorte de cuba, sem cômodo | furo 3D verdadeiro, geometria válida, cotas e faces editáveis | retângulo preto no tampo / hole falso / recorte fora |
| 2 | Cuba independente | paredes, fundo, profundidade, posicionamento de ralo como modelagem representativa | objeto maciço sem cavidade, bbox suficiente mas topologia errada |
| 3 | Encaixe de cuba + bancada | duas definições, alinhamento, folga parametrizada de fonte real | intersecção impossível / espessura inválida |
| 4 | Espelho de banheiro | plano, espessura, montagem, vidro/material e escala | flat decal não editável, sem orientação/âncora |
| 5 | Box de banheiro | painéis, perfis, dobradiça/porta conforme target; envelope de abertura | vidro atravessa parede, giro invade louça ou área livre |
| 6 | Caixa de gaveta | partes separadas, fundo real, folga, transformações; sem alegar corrediça | uma caixa proxy com face pintada como gaveta |
| Paralelo FP-050 | corredor + mesa + cadeiras (microambiente) | caminho contínuo e espaço de uso da cadeira, porta preservada | mesa/cadeira bloqueando passagem; só validar bbox da mesa |

O plano acima é **backlog sugerido**, não alegação de que já há recipe revisada ou prova para cada item. Se a prioridade do apartamento mudar, selecionar outro demo com justificativa objetiva de dependência e reuso. Não começar G2..G6 antes do sucesso do piloto 1 e do mecanismo de promoção.

## 7. Testes e CI (sem fingir que Linux executa SketchUp)

| Camada | Ambiente | Gate |
|---|---|---|
| Contrato de source, licença/metadata e target | pytest Linux em GitHub Actions | entrada ausente/inconsistente/stale bloqueia, revisão não herdada |
| Lógica geométrica/transformação | pytest + Hypothesis Python 3.11/3.12 | invariantes + negativos + property based |
| Reprodutor de demos | CI Linux headless | input e expected versionados, determinismo, sem baixar Warehouse |
| Integração planners/assembly | CI Linux | consumidor único shared, DAG, tipos, bloqueio por código |
| Inspeção SketchUp | Windows com SketchUp instalado e controle de processo | L2 real: salvar/reabrir/inspecionar objeto e prova sem tocar canônicos |
| Revisão alvo/estética | humano e capturas comparáveis | L3 explícito `APPROVED/PENDING/CHANGES_REQUESTED` |

A infraestrutura atual em `.github/workflows/ci.yml` já usa Linux, dois Pythons, testes de escala separados, gates, MCP smoke e stdio; **reutilizar, não montar pipeline paralela**. L2 Windows fica em execução controlada, com job/pid/log/arquivo de evidência; adicionar runner Windows confiável posteriormente somente com sandbox, secrets restritos, permissão/licença, sessão SketchUp e sem executar código arbitrário de PR público. Downloads externos não entram no CI; usar fixtures próprias/licenciadas.

**Gate de mutação:** substituir o recorte real pelo falso decal/caixa deve derrubar apenas os testes escopados relevantes no L1; mutações que alterem símbolos L2 também tornam a evidência stale, não mascarar isso como falha funcional isolada. Registrar baseline e commit limpos para provas L2.

## 8. Regras para o especialista (R53)

- R53-01 — Falta de habilidade **não** autoriza improvisar caixa genérica.
- R53-02 — Pesquisar capability e assets válidos antes de implementar outra.
- R53-03 — Sem tutor/technique review no escopo, bloquear promoção da habilidade ensinada; permitir experimentos rotulados como exploratórios.
- R53-04 — Golden demo tem expected independente, referência e checks versionados; preservar versões.
- R53-05 — Golden demo aprovada não decide posição no apartamento, nem substitui FP-052.
- R53-06 — Reuso externo não implica aprendizagem de builder; contratos e estados distintos.
- R53-07 — Shared não importa de kitchen/bathroom/bedroom; cômodos impõem regras locais.
- R53-08 — Nenhum download automatizado massivo/crawler do 3D Warehouse; verificar termos.
- R53-09 — Nunca commitar assets de terceiros sem prova de direitos de redistribuição.
- R53-10 — Não promover falha, ausência ou salto de L1 para L2/L3; não inventar evidência humana.
- R53-11 — Para placement testar volume **e** envelope de uso/circulação, não só interseção de caixas.
- R53-12 — Concluir com demo independente, reuso real e retomada da tarefa original; contar *capabilities usadas*, não quantidade de specs ou renders.

## 9. Critérios de aceite e rollback

**CA-01:** dado um pedido de peça ausente, retorna `gap_report` com caminho decidido, origem e próxima microtarefa; sem SketchUp aberto.  
**CA-02:** dada capability existente atual, reutiliza sem clone de builder.  
**CA-03:** dado asset externo não autorizado, origem desconhecida ou licença não demonstrada, rejeita promoção/importação ao projeto.  
**CA-04:** dado asset verificado que atende objetivo, registra como asset, não como "capability aprendida".  
**CA-05:** dado tutorial revisado para recipe X, pedido Y não passa como `source_verified=true`.  
**CA-06:** dado golden de recorte, caixa com pintura preta falha verificação topológica.  
**CA-07:** dado conjunto de parâmetros válidos variados, operações mantêm cotas, topologia, edição e transformações.  
**CA-08:** dado caso inválido, recebe status determinístico com motivo; sem geometria parcialmente gravada.  
**CA-09:** dado CI Linux verde, não é permitido afirmar L2 real.  
**CA-10:** dado SketchUp Windows, salva/reabre e inspeciona sem alterar canônicos.  
**CA-11:** dado modificação de símbolo/digest, a prova afetada vira stale.  
**CA-12:** dado segundo cômodo, usa mesma capability e adapta frame +Y/-Y conforme contrato FP-048.  
**CA-13:** dada demo concluída, uma tarefa previamente bloqueada é **replanejada**, nunca autoexecutada.  
**CA-14:** dado ambiente com mesa/cadeira, impedir bloqueio de corredor e folga de uso mesmo se bboxes individuais não se sobrepõem.  
**CA-15:** dado target ainda DRAFT/contraditório, demo continua válida no escopo técnico, mas projeto final permanece bloqueado.

Rollback: cada fase em PR pequeno; `git revert` possível; provas históricas mantidas, novas versões não sobrescrevem golden aprovado; gate FP-042 inventário e proveniência para cada arquivo; FP-047 `strict_identity` para refatorações e `scoped_change` para alterações intencionais de objeto.

## 10. Handoff para Claude / ChatGPT

**Primeiro ciclo real** (sem recomeçar o projeto): consultar o `develop` mais recente, a limpeza de `CLAUDE.md`, as FP-048..052, o catálogo e o estado de `quadrado`; reconciliar nomenclatura. Implementar somente D0/D1 (report de gap + política de descoberta e provenance) com testes, **sem downloader de Warehouse**. Depois D2..D5 **somente do recorte de cuba**. Parar a promoção final se a recipe de recorte não possuir revisão humana do segmento, se faltar target válido, se L2 estiver pendente ou se a licença do asset escolhido for inconclusiva.

Para o piloto recorte, pesquisar documentação oficial e tutorial permitido antes de escrever builders; selecionar um caso com input e expected autônomos; registrar source, versão e operação que foi observada em vídeo; implementar Python→Ruby com inspecção; testar variações e negativos; emitir relatório `DEMO_PASS` ou `DEMO_BLOCKED` com causas; só depois adicionar binding/capability ao catálogo e demonstrar um consumidor cozinha e um banheiro.

**Não reinterpretar** esta SPEC documental como implementação concluída. A primeira entrega de runtime precisa ser pequena, reproduzível, com CI verde e relatórios auditáveis. Nenhuma alteração no .skp do apartamento durante o ciclo exploratório.
