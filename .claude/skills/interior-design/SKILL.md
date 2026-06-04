---
name: interior-design
description: Use when furnishing a SketchUp floor plan with real 3D Warehouse furniture — generating styled, mobiliated apartment variants (planta_74_vN.skp) for the human to compare. Triggers on "mobiliar", "decorar", "design de interiores", "móveis no apê", "sofá/cama/mesa", "3D Warehouse furniture", "estilo industrial/dark/clean", `furnish_plan`, `interior-designer` Ollama model, or creating styled plant variants vN.
---

# interior-design

Mobiliar uma planta SketchUp com **móveis reais do 3D Warehouse**, num **estilo**
escolhido, gerando **variantes** (`planta_74_vN.skp`) pro humano comparar e
escolher. Felipe 2026-06-04.

## Arquitetura — 3 peças

| Peça | Papel | Onde roda |
|---|---|---|
| **`interior-designer`** (Ollama) | *cérebro de design* — recebe cômodo+estilo, devolve plano de mobília em JSON | máquina local (Ollama, base `llama3.1:8b`) |
| **`tools/furnish_plan.{py,rb}`** | *executor* — insere `.skp` na planta-base, posiciona, **auto-escala**, salva `vN` + renders, roda gates | SketchUp via `-RubyStartup` |
| **3D Warehouse** (Chrome MCP) | *fonte* dos componentes | navegador do user |

Build do cérebro: `ollama create interior-designer -f .claude/skills/interior-design/Modelfile`

## Processo (loop por cômodo)

1. **Consultar o cérebro**: POST `localhost:11434/api/generate` model `interior-designer`,
   `format:"json"`, descrevendo o cômodo (função, ~m², portas/janelas/varanda) e o
   estilo → plano de mobília JSON (`moveis[]` com `termo_busca_3dw`, `dimensoes_m`,
   `posicao`, `orientacao`, `cor_material`).
2. **Baixar do 3DW** (Chrome MCP): seção **Models**, busca pelo `termo_busca_3dw` →
   abrir a **página do modelo** → **Download** → **"SketchUp File"**.
3. **Copiar** o `.skp` de `~/Downloads` pra `runs/<plant>/_furniture/<nome>.skp`.
4. **Inserir**: registrar o móvel em `furnish_plan.py` (file/out/room/rot/scale) e
   rodar → insere no centro do cômodo (polylabel), auto-escala, salva `vN.skp` +
   `_iso/_top.png`, roda os gates.
5. **Humano revisa** os `vN.skp` e escolhe. Só então caprichar a posição/orientação
   do vencedor.

## Gates — validação (o user PEDIU pra validar orientação/escala)

- ✅ **Dimensão (determinístico — CONFIÁVEL)**: largura/profundidade/altura dentro de
  faixas plausíveis pro tipo (sofá: larg 1.2-3.6, prof 0.7-1.8, alt 0.55-1.15 m).
  **Pega escala errada** do componente 3DW.
- ✅ **Auto-escala** (`furnish_plan.rb`): normaliza pela ALTURA (Z) → alvo ~0.80 m
  quando fora de [0.55, 1.25] m. Muitos componentes 3DW vêm em miniatura/gigante.
- ⚠️ **Visão (`qwen2.5vl`, AUXILIAR — NÃO confiável)**: olha o render iso e dá
  veredito de orientação. **Alucina** (deu OK pra um sofá em miniatura de 0.39 m).
  Confirma a lição `oracle de visão não julga (PR #209)`. **O olho humano é o juiz.**

## Estilos + paletas (perfil dev/tech/dark do Felipe)

| Estilo | Paleta | Vibe |
|---|---|---|
| **industrial dark** ⭐ | grafite, preto, madeira escura, concreto, metal preto | loft de programador |
| **monocromático dark** ⭐ | grafite→chumbo→preto + off-white | "dark mode IRL" |
| tech/gamer | cinza escuro, preto, vidro, LED | setup gamer |
| nordic noir | cinza escuro, madeira escura, branco gelo | aconchego frio |

"cinza escuro / escurão" → tons `graphite → charcoal → black`.

## 3D Warehouse — seções (qual usar pra quê)

| Seção | Conteúdo | Uso |
|---|---|---|
| **Models** | peças soltas (102k sofás) | móveis individuais — **default** |
| **Catalogs** | catálogos de fabricantes (BR: Officina, Venet, Portal SketchUpBrasil) | conjuntos coerentes, escala real |
| **Collections** | curadorias de usuários (183 sofás numa) | garimpar muito de uma vez |
| **Materials** | texturas (.skm) | **piso/parede** do apê (porcelanato, madeira) |

## Caveats operacionais (aprendidos na marra)

- **Download**: o ícone de download do *card* NÃO baixa direto — abrir a **página**
  do modelo → botão **Download** → item **"SketchUp File"** do dropdown (USDZ/GLB/
  Collada são alternativas). O arquivo cai em `~/Downloads` com nome do componente-raiz
  (ex `Group_60.skp`).
- **Screenshot da extensão Chrome NÃO renderiza os thumbnails** até dar **scroll**
  (lazy-load). Padrão: navigate → wait → scroll down → scroll up → screenshot. O
  `get_page_text` enxerga o DOM mesmo quando o screenshot está em branco.
- **Escala**: SEMPRE auto-escalar — componentes 3DW vêm em unidades/escalas variadas.
- **Posição**: `polylabel` (pole of inaccessibility) dá o ponto mais central do
  cômodo; `representative_point` joga o móvel na borda (sobre parede).
- **Visual review**: veredito é do humano; só via Chrome/olho, nunca auto.

## Arquivos

- `.claude/skills/interior-design/Modelfile` — o cérebro `interior-designer`.
- `tools/furnish_plan.py` — launcher (centro do cômodo, jobs, gates).
- `tools/furnish_plan.rb` — insere/auto-escala/render no SketchUp.
- `runs/<plant>/_furniture/` — componentes baixados.
- `runs/<plant>/planta_<plant>_vN.skp` — variantes mobiliadas.

## Próximo nível (backlog)

- Mapear `posicao`/`orientacao` do cérebro → transform real (hoje vai no centro,
  rot 0; humano ajusta o vencedor).
- Refinar o prompt do `interior-designer` (não pôr guarda-roupa na sala).
- Cômodo a cômodo (quartos, cozinha, banheiros) e múltiplos estilos por planta.
- Texturas de piso (Materials) no chão dos cômodos.
