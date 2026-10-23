# Política de documentação externa (DOC-EXT)

> Normativa. Vale para qualquer agente (Claude Code, Codex, ChatGPT, outros) e para humanos. Ferramenta atual: **Context7**
> (MCP `context7`, configurado em `.mcp.json` na raiz). Ferramenta de **desenvolvimento**, nunca de runtime nem de CI.

## Por que existe

Código que fala com tecnologia externa (SketchUp Ruby API, SDK do MCP, shapely/GEOS, pytest…) quebra de um jeito específico:
assinatura inventada, parâmetro de outra versão, exemplo da versão mais nova adaptado "até o teste passar". A memória do modelo
não é fonte. A fonte é a documentação **da versão que o repositório usa**.

## Duas autoridades, sem sobreposição

| Pergunta | Quem responde |
|---|---|
| Como esta lib/API/CLI/protocolo funciona **na versão usada aqui**? | documentação externa (Context7; fallback abaixo) |
| Como o apartamento é mobiliado, qual circulação vale, qual layout, qual regra geométrica do domínio? | SPECs, código, testes, `core/project_policy.py`, `layout_decisions`, decisões D-xxx, catálogo de capacidades, evidência L2/L3 |

Context7 **nunca** decide domínio, nunca derruba uma SPEC aprovada, um gate, um canônico ou uma decisão do Felipe.

## Autoridade da fonte e vínculo com a afirmação

Encontrar uma página não basta. Toda afirmação externa usada para justificar implementação, threshold, compatibilidade ou
regra técnica deve ser vinculada ao que a fonte **realmente** sustenta. Classifique a autoridade:

| Tier | Fonte típica | Uso permitido |
|---|---|---|
| **A — primária** | norma oficial licenciada/consultável, lei/código oficial, documentação do fornecedor, spec/protocolo oficial, source/changelog da versão | pode sustentar requisito normativo/técnico **dentro da aplicabilidade comprovada** |
| **B — institucional/técnica** | órgão público aplicando a norma, manual técnico institucional, fabricante | referência técnica forte; não substituir texto normativo quando a distinção importar |
| **C — profissional especializada** | publicação técnica/editorial de arquitetura/engenharia, guia profissional reconhecido | orientação técnica/projeto; não promover sozinha para obrigação normativa |
| **D — guia/blog/agregador** | blog comercial, portal de conteúdo, agregador, artigo sem fonte primária | descoberta, conforto, hipótese; nunca hard normative por si só |
| **E — heurística interna** | experiência do projeto, regra aprendida, preferência, hipótese | `PROJECT_POLICY` / `HEURISTIC`; exige decisão explícita se virar hard |

Regras:

- **Fonte só sustenta a afirmação exata que contém.** Não ampliar escopo por analogia.
- Uma fonte secundária que cita uma norma **não transforma a citação em prova normativa**.
- Regra de acessibilidade não vira regra universal de todo ambiente sem comprovar a aplicabilidade.
- Recomendação de conforto não vira mínimo obrigatório.
- Divergência entre fontes deve ser registrada; não escolher silenciosamente a que "cabe melhor".
- Para thresholds externos, registrar ao menos: `source_type`, `source_tier`, `source_ref`, versão/data quando houver,
  `exact_claim_supported`, `applicability` e confiança/limitação.

## Quando consultar

**REQUIRED** — antes de implementar ou alterar código cujo comportamento depende de: SketchUp Ruby API; SDK/protocolo MCP;
pacote Python externo (shapely, numpy, pypdfium2, Pillow, matplotlib, pydantic/jsonschema); pytest e plugins (hypothesis);
SDK de IA/cloud, API HTTP externa, CLI externa (`gh`, V-Ray, Ollama); `subprocess`/processos quando o comportamento depende
da API.

**OPTIONAL** — exploração, comparar alternativas, entender uma lib ainda não adotada, preparar spike.

**NOT AUTHORITATIVE** — layout, constraints do apartamento, circulação, posicionamento, regras geométricas do domínio,
conhecimento de cursos/aulas (`references/sketchup/knowledge/`), `layout_decisions`, SPECs aprovadas, D-xxx, canônicos,
resultado de gate, evidência do SketchUp real.

**RESEARCH REQUIRED FOR DOMAIN THRESHOLDS** — ergonomia, acessibilidade, folgas funcionais, dimensões de uso e qualquer
número externo que possa virar constraint. Context7 pode ajudar a localizar documentação, mas a classificação final segue a
hierarquia de autoridade acima e a regra continua pertencendo ao domínio/projeto, não ao Context7.

## Ordem obrigatória (version awareness)

1. **Versão local primeiro**, nesta ordem de fonte: `uv.lock` → `pyproject.toml` → runtime (`importlib.metadata` no venv
   canônico, `SketchUp.exe` FileVersion, `gh --version`). Se lock e venv divergem, registrar a divergência.
2. **Depois** procurar a documentação: `resolve-library-id` (nome da lib) → escolher o ID que lista a versão; consultar
   `query-docs` com o ID **versionado** quando existir (ex.: `/modelcontextprotocol/python-sdk/v1.28.0`).
3. **Só então** escrever código. Nunca: perguntar genericamente → copiar exemplo da última versão → ajustar até passar.

## Quando a documentação não existe

```
Context7 sem a lib ou sem a versão
  -> registrar a lacuna (na evidência e na SPEC)
  -> consultar a documentação oficial por outro meio permitido (site do fornecedor, changelog, código-fonte da tag)
  -> registrar a origem
  -> seguir só com evidência suficiente (de preferência um teste que exercita a API na versão local)
Se nem isso: BLOCKED: documentation unavailable  (não inventar assinatura)
```

## DOC-EXT-01 — gate de evidência (offline)

Mudança que altera comportamento dependente de tecnologia externa precisa de:
versão identificada · documentação compatível consultada · API usada existente nessa versão · comportamento relevante com teste ·
incompatibilidade registrada.

O CI **não** chama o Context7 (build determinístico e offline). O agente consulta durante o desenvolvimento e grava a
evidência em `docs/engineering/evidence/<data>_<dependencia>.json` (schema `core/schemas/external_doc_evidence.v1.schema.json`);
o gate `python -m tools.navigation.external_doc_evidence` valida essas evidências contra `uv.lock`/`pyproject.toml`:

```json
{"schema_version": "external_doc_evidence.v1", "dependency": "mcp", "version": "1.28.0",
 "version_source": "runtime", "documentation_provider": "context7",
 "library_id": "/modelcontextprotocol/python-sdk/v1.28.0", "version_match": "exact",
 "apis_verified": ["mcp.server.fastmcp.FastMCP", "FastMCP.tool"], "checked_on": "2026-10-23",
 "verified": true, "notes": "…"}
```

`version_match`: `exact` (doc da versão), `nearest` (outra versão — dizer qual e por que é compatível), `unversioned`
(doc da branch principal — exige `apis_verified` conferidas no runtime local). Lacuna = `documentation_provider: "none"` +
`verified: false` + motivo — o gate aceita lacuna **declarada**, nunca evidência inventada.

## Na SPEC

Feature que toca tecnologia externa declara o bloco opcional `external_dependencies` (ver
`.claude/specs/templates/feature_spec_template.md`) e aponta as evidências.

Feature de domínio que introduz **threshold externo** (ergonomia, acessibilidade, folga, dimensão funcional) não precisa fingir
que isso é uma dependência de software: usa o bloco `external_sources` do template para registrar fonte, tier, afirmação exata,
aplicabilidade e classificação da regra. Context7 pode participar da pesquisa, mas não é a autoridade do domínio.

Feature de domínio puro sem afirmação externa nova (ex.: reorganização de layout usando política já aprovada) pode omitir ambos.

## Disciplina de retrieval

Antes de consultar qualquer fonte, formular a pergunta de maneira estreita: biblioteca + versão + API/comportamento, ou
threshold + objeto + contexto + aplicabilidade. Preferir poucas fontes de alta autoridade a muitas fontes fracas.

Quando houver uma fonte A suficiente, fontes C/D podem servir como contexto, **não** como voto adicional. Quantidade de links não
aumenta a autoridade da afirmação.

Não despejar documentação inteira no repo. Persistir apenas claim, provenance, versão, aplicabilidade e a evidência mínima
necessária para reprodução/revisão.

### Conhecimento interno do sketchup-mcp

A indexação do próprio repositório/recipes no Context7 é uma possibilidade futura, mas está **adiada enquanto a FP-054 mantém a
expansão de tutoriais/RAG congelada**. Até a liberação formal da F5, não criar uma segunda base concorrente para SPECs,
`project_policy`, `layout_decisions`, recipes ou evidências. O repositório continua sendo a autoridade interna.

## Segurança

Sem chave no git. O servidor responde sem chave (limite menor). Para limite maior, cada pessoa configura a chave **no escopo de
usuário** do seu agente (ex.: `Authorization: Bearer $CONTEXT7_API_KEY`), nunca em `.mcp.json` do repositório.

## Matriz atual

`docs/engineering/external-dependencies-matrix.md` — onde a política rende hoje e as lacunas conhecidas.
