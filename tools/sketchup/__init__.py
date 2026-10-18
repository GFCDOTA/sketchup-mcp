"""tools.sketchup — a camada "especialista em SketchUp" do pipeline.

O que o servidor MCP (`tools/mcp_server`) expõe como `su_*`, e o que o
harness-app pode importar direto. O conhecimento de SketchUp vive AQUI, como
código testável — não em prompt:

- `process`  — achar o SketchUp, listar instâncias, abrir e fechar SEM nunca
               matar a janela do Felipe por nome de imagem (`taskkill /IM`).
- `batch`    — rodar um job Ruby num SketchUp em lote via `-RubyStartup` e
               ler o resultado de um JSON (não de log).
- `paths`    — onde um job pode escrever: nunca em `fixtures/`, nunca em
               `artifacts/` (promoção é só via `promote_canonical`).
- `ops`      — schema das edições de modelo, validado ANTES de subir o SU.
- `jobs`     — os verbos: status/open/close/inspect/render/apply_edits/
               build_shell/furnish/render_vray.

Os jobs Ruby ficam versionados em `tools/sketchup/ruby/` — diferente do
`autorun_consume.rb`, que só existe no `Plugins` da máquina.
"""
