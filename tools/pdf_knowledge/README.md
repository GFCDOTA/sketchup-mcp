# sketchup-pdf-knowledge

Mini-projeto para transformar PDFs de SketchUp / móveis planejados em uma base consultável para o `sketchup-mcp`.

## Objetivo

Ajudar o Claude/agentes a usar os PDFs como referência de projeto sem ficar lendo PDF inteiro toda hora.

O fluxo é:

1. Indexar PDFs locais em JSONL por página.
2. Buscar trechos relevantes por tema.
3. Exportar um contexto curto para o Claude.
4. Transformar trechos em `rule_cards` codificáveis.
5. Aplicar as regras no `auto-mobiliado`.

## Não fazer

- Não commitar texto completo extraído dos PDFs.
- Não copiar capítulos inteiros para o repo.
- Não usar os PDFs como desculpa para pesquisa infinita.
- Não afirmar regra de design sem registrar fonte/página ou origem externa.

## Estrutura

```text
config/pdf_manifest.yml        # Lista dos PDFs e papel de cada um
scripts/ingest_pdfs.py         # Extrai texto por página para output/pdf_pages.jsonl
scripts/search_pdf_index.py    # Busca simples local no índice
scripts/export_claude_context.py # Gera contexto curto para colar no Claude
schemas/design_rule.schema.json # Formato de regra codificável
examples/bedroom_rule_cards.json # Exemplos de regras para quartos
prompts/claude_pdf_knowledge_prompt.md # Prompt mestre para o Claude
```

## Instalação

```bash
python -m venv .venv
.venv/Scripts/pip install pypdf pyyaml
```

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install pypdf pyyaml
```

## Uso

Coloque os PDFs em `references/pdfs/` no repo do `sketchup-mcp` e ajuste `config/pdf_manifest.yml`.

Depois rode:

```bash
python scripts/ingest_pdfs.py --manifest config/pdf_manifest.yml --out output/pdf_pages.jsonl
python scripts/search_pdf_index.py --index output/pdf_pages.jsonl --query "guarda roupa criado mudo componente"
python scripts/export_claude_context.py --index output/pdf_pages.jsonl --query "dormitorio cama guarda roupa criado mudo" --out output/claude_context_bedroom.md
```

O arquivo `output/claude_context_bedroom.md` é o que você entrega ao Claude como contexto curto.

## Gate de qualidade

Uma pesquisa só vira útil se gerar pelo menos um destes artefatos:

- constante dimensional em metros;
- hard/soft gate;
- fixture/teste;
- componente planejado;
- relatório de decisão;
- melhoria no `layout_candidates.py` ou novo brain especializado.
