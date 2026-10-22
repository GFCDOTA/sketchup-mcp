# 📐 SPEC de Feature — FP-052: Alvo de Referência e Aprendizado Técnico de Componentes
> Fluxo de Desenvolvimento Agêntico (SDD) · GFCDOTA/sketchup-mcp · Python/Ruby/SketchUp Windows

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-052 — Reference Target Contract: o que construir + como aprender"
  escopo_versao: "Tornar obrigatória uma referência-alvo rastreável para cada componente e móvel, vinculando fonte geométrica, design aprovado, tutorial verificável e critérios de aceite antes da construção final."
  versao: "1.0.0"
  status: "RASCUNHO_VALIDADO_CONTRA_DEVELOP"
  classificacao:
    contexto_delimitado: "Reference Lab / Aprendizado de marcenaria / Mobiliamento"
    dominio: "SketchUp MCP"
    funcionalidade: "target único, anatomia, aprendizagem granular, comparação e gates"
  baseline_develop: "99a83dde7f72764fc1440eff9dfa871384782f39"
  specs_relacionadas: ["FP-045", "FP-046", "FP-047", "FP-048 (PR #346)", "FP-049 (PR #347)", "FP-050 (PR #355)", "FP-051"]
  destino: "develop por PR; sem tocar SKP/PDF/consensus protegidos"
```

## 🎯 BLOCO 2 — Problema e meta observável

Hoje `references/sketchup/knowledge/` explica **como** modelar; `artifacts/reference_lab/` registra preferências visuais, referências e golden samples; o PDF/consensus rege a planta; `capability_catalog` diz o que conseguimos executar. **Não há, porém, vínculo obrigatório e inequívoco de uma instância de móvel com seu alvo aprovado de anatomia, forma, acabamento, escala, função, técnica e critérios de comparação.** O agente consegue gerar algo tecnicamente válido sem entregar a peça desejada.

**Meta de produto:** para `planta_74.r004.kitchen_base_001`, entregar um gabinete cujo corpo, frentes e prateleira tenham referência-alvo **específica**, dimensões com origem, técnica observável e critérios objetivos, montado em cópia do SKP, reinspecionado e comparado ao alvo. Não declarar que o gabinete é um produto aprovado sem aprovação humana de sua aparência e instalação.

**P0 deste PR de contrato:** materializar o schema `core/schemas/reference_target.v1.schema.json` e o **manifesto rascunho bloqueado** `artifacts/reference_lab/targets/planta_74/r004/kitchen_base_001.target.v1.json`; atualizar SPECs e os testes do gate de preflight. Não altera builders nem concede novos PASS L2/L3.

## 2.1 Autoridade por domínio: não existe uma foto que mande em tudo

| Aspecto | Fonte autoritativa na ordem de precedência | O que NÃO se pode inferir |
|---|---|---|
| Estrutura do apartamento | `projects/planta_74/source/planta_74.pdf` + consensus/fixture humana reconciliada | foto de referência não muda parede, abertura ou pia |
| Medidas/instalação | medidas tipadas do projeto + regra estrutural; manual de produto real quando existir | escala de fotografia, vídeo ou render não define cotas reais |
| Resultado visual do cômodo | decisão específica em `artifacts/reference_lab/DECISIONS.md`, `GOLDEN_SAMPLES.md` e imagens correspondentes | aprovação do **tema** não aprova cada peça, nem valida ergonomia |
| Resultado visual/funcional da peça | `reference_target.v1` apontando para referência da peça e aceite específico do usuário | hero de cozinha não comprova interior da gaveta, ferragens ou encaixes |
| Técnica de construção | `references/sketchup/knowledge/video_recipes.v1.json` com source, `recipe_id`, segmento revisado e descrição das operações realmente observadas | um `human_review` de outra recipe **não** se transfere; transcrição não é inspeção visual |
| Método/viabilidade física | código paramétrico, operações SketchUp, materiais, manuais do fabricante e testes L1/L2 | suposição de folga, tolerância, ferragem funcional ou qualidade de marcenaria real |
| Conformidade com o alvo | gates determinísticos + SKP salvo/reaberto + vistas comparativas + decisão humana L3 | `pytest PASS` ou render bonito não basta |

**Regra de precedência em conflitos:** não escolher silenciosamente um documento. Registrar ambos os IDs, o domínio afetado e `OPEN`; consultar arquitetura autoritativa ou decisão explícita e versionada. Ex.: `COMPLETE_KITCHEN_SPEC.md` usa "LINEAR", enquanto `artifacts/planta_74/design_intent/r004.json` declara "Galley em L". O manifesto piloto marca essa divergência como OPEN **sem** afirmar qual layout é correto. Nenhum placement final pode se apoiar nessa divergência não resolvida.

## 2.2 Reutilizar o que existe, sem segundo banco de verdade

- `artifacts/reference_lab/` continua guardando golden samples, imagens, cards, temas e decisões; `references/sketchup/knowledge/` continua guardando tutoriais e recipes; PDF/consensus continuam protegidos.
- `reference_target.v1` é **manifesto de ponteiros imutáveis/versionados para o alvo de uma instância**, não cópia de imagens, texto de aulas ou nova fonte geométrica.
- Cada campo da peça aponta para `source_ref.id`, `recipe_id`, referências de vista e checks de aceitação. O target tem `target_id`, `state`, `source_refs`, `parts`, `conflicts` e `approval`.
- Referências de arquivo usam caminho relativo à raiz + SHA-256 quando verificadas. URL externa deve estar no catálogo de conhecimento com sua proveniência, não ser copiada nem executada do manifesto.
- `state=DRAFT_BLOCKED` permite curadoria e microexperimentos **sem** alegar que a construção final atende ao alvo. `APPROVED_TARGET` exige todas as partes `APPROVED`, referências específicas, anatomia, critérios mensuráveis, resolução de conflitos, integridade das fontes e aprovação humana escopada.
- `style.status=HISTORICALLY_APPROVED` é **somente** o registro de uma decisão histórica sobre estilo. Não muda `approval.decision=PENDING` para um móvel individual.
- Toda alteração de arquivo fonte (SHA), trecho de tutorial, decisão de design, target, símbolo do builder ou SKP invalida as provas vinculadas em seu escopo. Preservar histórico e pedir revalidação, não sobrescrever evidências.
- Jamais armazenar `execution_authorized=true` em `reference_target`. Autorizar execução pertence ao gate/fluxo do job, separado e tipado, após validar alvo/assembly/placement.

## 2.3 Procedimento obrigatório de ensino de cada peça

1. **Target-first:** carregar o manifesto da instância e localizar a peça (frente, lateral, fundo, painel, gaveta, puxador). Identificar requisito funcional, forma visual e status de aprovação.
2. **Anatomia:** decompor em subpeças editáveis, função de cada subpeça, topologia, folgas, material e relações de montagem. Distinguir `required` de `optional`; medidas precisam `value/unit/origin` em contratos executáveis, não serão extraídas por palpite de foto.
3. **Técnica:** vincular cada operação de SketchUp à recipe, trecho exato e fonte; registrar `observed`, `derived` ou `unknown`. Se a técnica não foi vista na fonte, usar documentação oficial quando houver, ou declarar implementação própria, **nunca atribuir o passo ao tutorial**.
4. **Microprova L1:** construir uma peça com Python, testes de topologia, tolerância, transformação, volume, materiais, identidade de componentes e variações de dimensão. Teste negativo obrigatório para a substituição por caixa genérica.
5. **Prova L2:** usar SketchUp Windows em cópia temporária; materializar peças realmente separadas, salvar, fechar PID do job, reabrir, inspecionar e comparar o que foi construído com o `target` aprovado no escopo.
6. **Composição e placement:** integrar a capability compartilhada ao móvel, depois ao especialista de cômodo e às restrições da planta; validação de abertura/uso/circulação independente da geometria do próprio móvel.
7. **L3 e promoção:** comparar vistas frontal/topo/isométrica + vistas de detalhe/aberta quando aplicável com as referências selecionadas; registrar diferenças verificáveis e solicitar veredito humano. `L2_PASS` não significa `TARGET_MATCH` nem `VISUAL_APPROVED`.

## 2.4 Gates, bloqueios e anti-alucinação

| Gate | Bloqueio obrigatório | Resultado permitido |
|---|---|---|
| TG-01 — alvo inexistente | `BLOCKED_TARGET_UNDEFINED` | somente escolha/curadoria de referência |
| TG-02 — peça sem anatomia, referência específica ou aceite | `BLOCKED_TARGET_UNDEFINED` | estudo/protótipo identificados; **não** promover móvel |
| TG-03 — referência inexistente, escapando repo ou hash divergente | `BLOCKED_TARGET_EVIDENCE` | corrigir referência; nenhuma aprovação |
| TG-04 — conflitos entre fontes/versões abertas | `BLOCKED_TARGET_CONFLICT` | decisão explícita; sem posicionamento final |
| TG-05 — tutorial sem recipe/trecho/revisão no escopo | `BLOCKED_KNOWLEDGE_EVIDENCE` | investigar ou escolher outra origem |
| TG-06 — solver/algoritmo de placement sem PDF/âncora | `BLOCKED_INVALID_CONTEXT` | obter origem real; nunca inventar parede |
| TG-07 — L1/L2 sem match do alvo | `PENDING_HUMAN` / `FAILED_TARGET_MATCH` | comparar, corrigir o candidato, não o alvo |
| TG-08 — style aprovado, componente não | `BLOCKED_TARGET_UNDEFINED` para promoção final | continuar a pesquisa de componentes |
| TG-09 — mudança de hashes após prova | `BLOCKED_EVIDENCE_STALE` | refazer o gate do escopo |

O gate `tools/rooms/reference_targets.py` desta fase é read-only e **não está ainda ligado a todos os fluxos executores**. A conexão com `specialists.plan`, `cabinet_flow`, `shaker_flow` e FP-050 é entrega posterior com reexecução L2 quando os símbolos mudarem (R-18/FP-046). Não anunciar proteção E2E antes dessa integração.

## 2.5 Fases pequenas com entrega concreta

| Fase | Entrega | Critério de pronto |
|---|---|---|
| **T0 — inventariar e reconciliar** | referenciar golden 004, PDF/consensus, designs antigos e recipes sem copiá-los; manifesto piloto em DRAFT | gate encontra falta de anatomia, material, ref de detalhe e conflito de layout; **não concede PASS** |
| **T1 — contrato/gate target** | schema e preflight read-only; testes negativos para alvo incompleto, conflito, caminho inexistente, hash stale e aprovação herdada | negativos vermelhos→verdes; CI verde; zero .skp tocados |
| **T2 — curar alvo do primeiro móvel** | vistas concretas de corpo, frente, prateleira, interior/uso, perfil e materiais; estabelecer quantidades, proporções, atributos e anti-exemplos; resolver conflitos de posição pelo PDF/consensus | manifesto completo, links existentes e hashes calculados, registros de decisão no escopo; se não houver referência suficiente, permanece bloqueado |
| **T3 — construir UMA peça** | recipe de trecho observado → operações → builder shared → L1/L2, topologia e inspeção | prova peça versus alvo com imagens, não apenas bounding box; capability reusável com digest válido |
| **T4 — compor e instalar gabinete** | DAG FP-051 + requisitos de FP-049 quando integrados, planner FP-050 quando integrado, gates em `cabinet_flow` e `shaker_flow` | sem bypass por fluxo antigo, .skp salvo/reaberto em cópia; regressão FP-047 |
| **T5 — prova de objetivo e reuso** | comparação target x SKP x tutorial, julgamento L3 humano e consumidor em outro cômodo quando cabível | relatório objetivo `TARGET_MATCH` por peça + móvel; produto entregue só com escopo completo |

**Testes mínimos**: ausência de arquivo; hash incompatível; `APPROVED_TARGET` com `APPROVED_STYLE_ONLY` indevido; peça sem referência de detalhe; fonte do corpo aplicada à frente; tutorial sem revisão da recipe; troca de imagem após aprovar; dimensão deduzida de foto; conflito LINEAR/L não resolvido; box proxy usado como gaveta; alteração de SKP canônico.

## 2.6 Dependências e decisões

- FP-045 permanece dona dos especialistas, recipes e catálogo de capabilities.
- FP-046 permanece dona da porta Shaker; a L2 `L2_PASS` existente permanece uma **prova técnica histórica válida em seu escopo**, **não** prova de correspondência a uma frente-alvo individual FP-052.
- FP-047 compara deltas de SKP; FP-052 adiciona **comparação candidata ↔ referência do objetivo**, distinta de baseline ↔ commit anterior.
- FP-048/049/050 continuam PRs draft e não são pré-condição para **documentar** os targets; a integração operacional exige revisão dos contratos após o merge.
- Não alterar decisões `GOLDEN_SAMPLE_004`; uma mudança estética requer nova variante/decisão, preservando os documentos históricos.
- Não promover `planta_74.r004.kitchen_base_001` antes de referências/anatomia e conflito resolvido. Decisões em aberto exigem curadoria baseada em fontes, não invenção do agente.

## 🔄 BLOCO 3 — Governança / Handoff

**Ordem para agente implementador:** 1) rodar `python -m tools.rooms.reference_targets artifacts/reference_lab/targets/planta_74/r004/kitchen_base_001.target.v1.json`, esperar estado bloqueado **por dados reais ausentes**, não por erro de parsing; 2) obter vista frontal, lateral e interna específica do gabinete escolhido, com licença/locator verificável; 3) extrair anatomia/aceites, propor target atualizado sem alterar fontes protegidas; 4) somente após aprovação estrita da meta da peça iniciar a micro-fixture; 5) executar provas L1/L2; 6) compor, posicionar, comparar e solicitar L3.

**Resultado final exigido:** uma peça não é `DONE` por existir código; um móvel não é `DONE` por possuir geometria; um cômodo não é `DONE` por possuir render. Cada instância deve ser comparável a um alvo versionado, localizado e aprovado, com testes contra falsos positivos.

**Política de PR:** T0/T1 pequeno e separado; não mergear execução do SketchUp nesta fase. CI verde certifica contrato, **não valida aparência**. Falhas devem apresentar o `target_id`, `part_id`, origem, status de revisão, causa e próximo passo.
