# Artifact contract: <artifact name>

> Template para documentar o contrato de um artifact (input,
> output, schema, produtor, consumidor). Salvar em
> `docs/specs/contracts/<artifact>.md` ou inline numa spec FP-NNN
> que introduza o artifact. Apagar este aviso ao usar.

## Identidade

- **Nome**: <e.g. `consensus.json`, `geometry_report.json`,
  `<plant>.skp.metadata.json`>
- **Path canônico**: `<path/to/file>`
- **Schema version**: `<major.minor.patch>`
- **Tracked?**: ✅ versionado / ❌ scratch (gitignored)

## Produtor

- **Quem escreve**: `<tool path>` ou `<manual / humano>`
- **Quando**: <build / promotion / annotation>
- **Função geradora**: `<file:function>` (e.g.
  `tools/build_plan_shell_skp.py:write_metadata`)

## Consumidor(es)

- **Quem lê**: <lista de tools / testes>
- **Para quê**: <cache key / validation / display / handoff>
- **Campos load-bearing**: <quais campos têm semântica
  obrigatória vs informational>

## Schema

```json
{
  "campo_obrigatorio_1": "<tipo, exemplo>",
  "campo_obrigatorio_2": "<tipo, exemplo>",
  "campo_opcional": "<tipo | null>",
  ...
}
```

### Campos

| Campo | Tipo | Obrigatório? | Load-bearing? | Descrição |
|---|---|---|---|---|
| `schema_version` | string | sim | sim | semver do schema |
| `<campo>` | <tipo> | sim/não | sim/não | <descrição curta> |

## Invariantes

<Propriedades que devem sempre valer. Ex.:>

- `schema_version` é semver válido
- `consensus_sha256` bate com SHA256 do `consensus.json`
- `skp_path` aponta pra path **existente** (canonical ou run)
- ...

## Versionamento

- **MAJOR** bump quando: campo load-bearing removido ou renomeado
- **MINOR** bump quando: campo novo opcional adicionado
- **PATCH** bump quando: correção em descrição / tipo sem
  mudança de comportamento

## Migration policy

<Como código existente lida com schema antigo. Ex.:>

- Consumidor faz fallback graceful em campos opcionais ausentes
- Consumidor rejeita schema MAJOR diferente

## Anti-padrões

- Adicionar campo load-bearing sem MAJOR bump
- Mudar significado de campo existente sem renomear
- Schema sem versionamento

## Reference

- Constitution: [`.claude/constitution.md`](../../constitution.md)
- Fidelity gate: [`specs/fidelity_gate.md`](../fidelity_gate.md)
- SKP artifact layout: [`specs/skp_artifact_layout.md`](../skp_artifact_layout.md)
