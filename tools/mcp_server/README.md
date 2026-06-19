# sketchup-mcp — servidor MCP (fatia 1)

Expõe os **verbos puros/rápidos** do pipeline (sem `SketchUp.exe`) como
ferramentas [MCP](https://modelcontextprotocol.io) estruturadas, pra um agente
(Claude Code) chamar direto. Ganho: JSON minúsculo entra/sai em vez de montar
comando bash + parsear log (corta token), com os **gotchas embutidos** (ex.:
`PT_TO_M=0.0259` default nos gates de mobília).

## Instalar e rodar

```bash
# na venv do repo
pip install -e .[mcp]
python -m tools.mcp_server.server          # sobe via stdio
```

Verificar:

```bash
python -m tools.mcp_server.smoke           # exercita cada tool em processo
python -m tools.mcp_server.stdio_check     # handshake MCP real sobre stdio
```

## Registrar no Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "sketchup": {
      "command": "E:\\Claude\\apps\\sketchup-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "tools.mcp_server.server"],
      "cwd": "E:\\Claude\\apps\\sketchup-mcp"
    }
  }
}
```

Ativa ao **reabrir** o Claude Code (aprovar o server novo). As tools aparecem
como `mcp__sketchup__*`.

## Ferramentas (fatia 1)

| Tool | O que faz | SketchUp? |
|------|-----------|-----------|
| `list_capabilities` | Catálogo + o que está adiado pra fatia 2 | não |
| `run_deterministic_gates` | Gates de consensus/render (PASS/FAIL/INCOMPLETE) | não |
| `furniture_class_derive` | Deriva + valida classe de móvel (sofa/bed/armchair/dining_table/rack/coffee_table) | não |
| `reference_to_grammar` | **Tradutor Pinterest**: sem draft → contrato; com draft → DesignGrammarSpec | não |
| `validate_grammar_spec` | Valida a spec cruzando com a autoridade do PDF | não |
| `room_gates` | Overlap + coerência de estilo de um cômodo | não |
| `kitchen_ergonomics_audit` | Ergonomia da cozinha (12 métricas); degrada se ausente | não |
| `promote_canonical` | Promove build abençoado → `artifacts/<plant>/` | não |
| `skp_inventory` | Inventário categorizado dos `.skp` | não |

**Adiado pra fatia 2** (sobem o SketchUp/V-Ray, ~60–180s): `build_shell`,
`furnish_apartment`, `render_scene_vray`, e `consult_oracle` (proxy do `:8765`).

## Especialista Pinterest (esqueleto)

`reference_to_grammar` + `validate_grammar_spec` implementam o método da skill
[`planned-joinery-translator`](../../.claude/skills/planned-joinery-translator/SKILL.md)
em código:

1. **`reference_to_grammar(room_type)`** → devolve o **contrato**: o que olhar
   na imagem, o vocabulário canônico de tokens (ancorado na cozinha-ouro
   `artifacts/kitchen_research/joinery_tokens.json`) e o formato de resposta.
2. O **Claude é o modelo de visão** — olha a referência e monta o `draft`.
3. **`reference_to_grammar(draft=...)`** → normaliza pra uma `DesignGrammarSpec`
   (colapsa sinônimos de token, injeta os `fixed_anchors` do PDF **por
   construção**).
4. **`validate_grammar_spec(spec, consensus_path, room_id)`** → reprova (FAIL)
   qualquer coisa que fira a autoridade do PDF.

> **Regra-mãe:** a referência manda na **LINGUAGEM** (paleta, tokens,
> assinatura); o PDF/consensus manda na **POSIÇÃO** (pia, parede, porta, janela,
> circulação = imutável). O validador faz cumprir.

Núcleo: [`tools/reference_grammar.py`](../reference_grammar.py) ·
testes: [`tests/test_reference_grammar.py`](../../tests/test_reference_grammar.py).
