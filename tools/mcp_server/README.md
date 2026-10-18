# sketchup-mcp — servidor MCP (fatias 1 + 2)

Expõe os verbos do pipeline como ferramentas
[MCP](https://modelcontextprotocol.io) estruturadas, pra um agente (Claude
Code, Claude Desktop, harness-app) chamar direto. Fatia 1 = verbos **puros**
(sem `SketchUp.exe`); fatia 2 = o **especialista em SketchUp** (`su_*`). Ganho: JSON minúsculo entra/sai em vez de montar
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
      "cwd": "E:\\Claude\\apps\\sketchup-mcp",
      "env": { "PT_TO_M": "0.0259" }
    }
  }
}
```

Ativa ao **reabrir** o Claude Code (aprovar o server novo). As tools aparecem
como `mcp__sketchup__*`.

**Claude Desktop:** o mesmo bloco `mcpServers` vai em
`%APPDATA%\Claude\claude_desktop_config.json` (Settings → Developer → Edit
Config). Reabra o app.

`PT_TO_M` já é `0.0259` por default dentro do server (planta_74), porque
`core.scale` congela a escala no primeiro import — o `env` acima só deixa isso
explícito. Opcionais: `SKETCHUP_EXE`, `SKETCHUP_PLUGINS`, `VRAY_EXE`,
`RUN_MODE` (`interactive` default local; `headless` fecha o SketchUp que o job
subiu).

## Ferramentas puras (fatia 1)

| Tool | O que faz | SketchUp? |
|------|-----------|-----------|
| `list_capabilities` | Catálogo das tools + gotchas do especialista | não |
| `run_deterministic_gates` | Gates de consensus/render (PASS/FAIL/INCOMPLETE) | não |
| `furniture_class_derive` | Deriva + valida classe de móvel (sofa/bed/armchair/dining_table/rack/coffee_table) | não |
| `reference_to_grammar` | **Tradutor Pinterest**: sem draft → contrato; com draft → DesignGrammarSpec | não |
| `validate_grammar_spec` | Valida a spec cruzando com a autoridade do PDF | não |
| `room_gates` | Overlap + coerência de estilo de um cômodo | não |
| `kitchen_ergonomics_audit` | Ergonomia da cozinha (12 métricas); degrada se ausente | não |
| `promote_canonical` | Promove build abençoado → `artifacts/<plant>/` | não |
| `skp_inventory` | Inventário categorizado dos `.skp` | não |

## Especialista em SketchUp (fatia 2)

Implementação em [`tools/sketchup/`](../sketchup/) — o conhecimento de SketchUp
é **código testável**, não prompt. Sobe o SketchUp (Windows); fora dele as
tools respondem `UNAVAILABLE` com o motivo, nunca sucesso fabricado.

> **Estado de prova: `UNVERIFIED_ON_SKETCHUP`.** As `su_*` foram testadas só
> contra um dublê de Windows+SketchUp (e a lógica pura em Ruby comum). Nenhuma
> rodou num SketchUp real. `su_status` e `list_capabilities` dizem isso em
> `proof_state`. O estado só muda com evidência de um run real commitada em
> `artifacts/review/`.

| Tool | O que faz | Tempo |
|------|-----------|-------|
| `su_status` | SketchUp instalado? Instâncias (PID), plugin de autorun, V-Ray, jobs | instantâneo |
| `su_open` | Abre um `.skp` numa janela nova (desanexada) | instantâneo |
| `su_close` | Fecha por PID / todas — **só com `confirm=true`**; gracioso salvo `force=true` | segundos |
| `su_inspect` | Grupos/componentes (nome, `pid` persistente, tag, material, bbox em m), materiais, tags, cenas | ~30 s |
| `su_render` | PNGs por preset (`top/iso/front/back/left/right`) ou câmera em metros | ~30–60 s |
| `su_apply_edits` | Material/cor/textura, mover, girar, tag, visibilidade, renomear, apagar, inserir componente | ~30–60 s |
| `su_build_shell` | consensus → shell `.skp` + renders + gates determinísticos | ~60–90 s |
| `su_furnish` | Mobilia a planta_74 no shell (brains → `place_layout_skp.rb`) | ~3 min |
| `su_render_vray` | **Recusa hoje, com motivo**: o launcher legado roda `taskkill /F /IM SketchUp.exe`. Volta quando for portado para `tools.sketchup.batch` | — |

Como roda: `SketchUp.exe <cópia.skp> -RubyStartup tools/sketchup/ruby/<job>.rb`.
O job lê `SKMCP_PARAMS` e escreve `SKMCP_RESULT` (JSON, atômico, por último): o
resultado existir é a prova de que **esta** execução terminou. Diferente do
`autorun_consume.rb`, os jobs são versionados e não deixam estado no `Plugins`.

Regras que o código faz cumprir (não o prompt):

- **O original nunca é aberto.** Inspecionar, editar, renderizar e mobiliar
  trabalham numa cópia; em modo `interactive` a janela fica aberta, e um Ctrl+S nela não
  alcança o original (que pode ser o `.skp` canônico).
- **Nada escreve em `fixtures/` ou `artifacts/`.** Saída default:
  `runs/<plant>/mcp/<job>_<stamp>/`. Entregável só via `promote_canonical`.
- **Arquitetura é do PDF.** `PlanShell_*`, `Floor_*`, `Window_*`, `DoorLeaf_*`…
  recusam `move/rotate/delete/rename` (Hard Rule #1); aparência é permitida. A
  recusa vale também quando a arquitetura é o **ancestral** ou um **descendente**
  do alvo, quando casa pelo **nome da definição**, quando o alvo (ou o pai) está
  **`locked`** e quando ele vive numa **definição compartilhada** entre
  instâncias (a edição vazaria para todas — `make_unique` antes).
- **Referencial de mundo.** `move.by_m` e `rotate` são em eixos do mundo; o job
  converte para o local do pai (num grupo girado, um move "cru" andaria nos eixos
  girados). `su_inspect` dá `bbox_local_m` (referencial do pai) e `bbox_world_m`.
- **Nada de transformação dupla.** `move`/`rotate` cujo alvo casa um grupo E
  peças dentro dele é recusado (as peças andariam duas vezes). `rotate` conjuga a
  rotação de mundo inteira para o local do pai, então continua certo sob pai
  espelhado (Flip Along).
- **Destino novo sempre.** `su_apply_edits` recusa `out_path` que já existe.
- **Medida é explícita, em metros.** `move` sem `by_m` é recusado antes de subir
  o SketchUp. Alvo ambíguo (`expect=one` com 2+ casamentos) é recusado — use o
  `pid` do `su_inspect`.
- **Tudo-ou-nada** nas edições: um erro aborta todas as ops.
- **Nunca `taskkill /IM`.** Fechar é por PID e com confirmação; o modo
  `headless` só fecha a instância que o próprio job subiu.
- **Aparência nova pede VISUAL_REVIEW do Felipe** — o resultado lembra.

Exemplo — pintar a cama de preto e conferir (os grupos de móvel se chamam pelo `kind`, ex. `bed`; confira no `su_inspect`):

```json
su_inspect {"skp_path": "artifacts/planta_74/furnished/planta_74_furnished.skp"}
su_apply_edits {
  "skp_path": "artifacts/planta_74/furnished/planta_74_furnished.skp",
  "ops": [{"op": "set_material", "target": {"name_contains": "bed", "expect": "all"},
           "color": [20, 20, 22]}]
}
su_render {"skp_path": "<out_skp do passo anterior>", "views": [{"name": "top", "preset": "top"}]}
```

Testes (sem SketchUp): `tests/test_sketchup_specialist.py` (fiação, regras,
dublê do SketchUp) e `tests/test_sketchup_ruby_jobs.py` (`ruby -c` + lógica pura
em `tests/ruby/test_skmcp_core.rb`). O lado Ruby que usa a API do SketchUp só se
prova numa máquina com SketchUp.

Fora daqui: `consult_oracle` (o `:8765` foi aposentado; o oráculo é o
GPT-Docker `:8899`, via `tools.ask_gpt_gate`).

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
