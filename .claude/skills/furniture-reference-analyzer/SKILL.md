---
name: furniture-reference-analyzer
description: >-
  Use ANTES de construir um builder paramétrico de móvel, quando há um .skp de
  REFERÊNCIA (asset baixado, ex. IKEA) pra estudar. Inspeciona o .skp e gera um
  relatório estruturado (unidade, bounding box, materiais, componentes/grupos,
  renders top/front/iso, hipótese semântica: sofá reto / sofá com chaise / cama /
  armário...). Dispara em "analisar referência", "inspecionar .skp", "estudar o
  asset", "Group_60.skp", "que móvel é esse", ou ao receber um .skp de móvel pra
  virar spec/builder. NÃO copia o asset — extrai o aprendizado (dims, anatomia,
  material) pra virar spec + builder + gate. NÃO usar pra gerar móvel (isso é o
  builder) nem pra planta de parede.
---

# Furniture Reference Analyzer

Regra-mãe (Felipe): **não copiar cegamente o asset**. Primeiro **analisar** a
referência e transformar o aprendizado em **spec + builder + gate**. Esta skill é o
passo de análise.

## Pipeline (2 passos)

1. **Inspeção (SketchUp)** — `tools/inspect_skp.rb` abre o `.skp` e escreve
   `<name>_inspect.json` (unidade, bbox in+m, materiais, definições de componentes,
   contagem de entidades, hierarquia com `size_m`/`center_m` até 2 níveis) + renders
   `top/front/iso`. **SU só renderiza com desktop interativo** → lançar via PowerShell
   numa CÓPIA do `.skp` (nunca o original; o autosave do SU mexe no arquivo):

   ```powershell
   $ref="C:\...\Group_60.skp"; $copy="...\.claude\scratch\ref.skp"
   Copy-Item $ref $copy -Force
   $env:INSPECT_OUT="...\group_60_inspect.json"; $env:INSPECT_LOG="...\log.txt"
   $env:RENDER_TOP="...\group_60_top.png"; $env:RENDER_FRONT="..._front.png"; $env:RENDER_ISO="..._iso.png"
   Start-Process "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe" `
     -ArgumentList "`"$copy`"","-RubyStartup","`"...\tools\inspect_skp.rb`""
   # poll do INSPECT_LOG, depois Stop-Process SketchUp
   ```

2. **Interpretação (Python, sem SU)** — `tools/furniture_reference_analyzer.py
   <inspect.json>` lê o JSON e escreve `<name>_analysis.{json,md}`: hipótese de
   objeto + confiança, variante (straight/chaise + lado), `is_single_block`, papéis
   das peças (seat_cushion / back_cushion / seat_base / arm / foot) por assinatura de
   dimensão, anatomia (dims em m), material principal, eixo frontal.

## Saída

Tudo promovido pra `artifacts/review/furniture/<name>/`:
- `<name>_inspect.json` — dados crus da inspeção
- `<name>_analysis.{json,md}` — hipótese semântica + anatomia
- `<name>_{top,front,iso}.png` — renders

## Como ler a hipótese

- **É a verdade?** Não — é **hipótese** (heurística por dimensão). Ex.: um encosto
  baixo e um braço têm assinatura parecida → contagem de braços pode inflar. O valor
  é o **aprendizado** (tipo do objeto, que é composto, dims reais das peças, material),
  não a contagem exata.
- **single block?** Se `True` o asset é uma caixa só (não serve de referência de
  anatomia). Se `False`, as `definitions` dão as dims reais de cada peça → alimenta o
  `furniture-anatomy-spec`.
- **variante chaise**: detectada quando o footprint preenche <80% do bbox (canto
  vazio do L). `chaise_side` por convenção frente=-Y (sentado, +X = esquerda).

## Caso de referência: Group_60.skp (KIVIK L/chaise)

`artifacts/review/furniture/group_60/` — sofá com chaise, 1.66×2.84×0.93 m, 11 peças
(base + 2 assentos + encostos + 2 braços + 4 pés + chaise), tecido escuro (Dansbo).
Confirma a anatomia que o `SofaBuilder` deve reproduzir (NÃO bloco único).

## Hard rules

- Analisar a CÓPIA, nunca o original em Downloads.
- Não importar a geometria do asset pra planta — extrair só dims/anatomia/material.
- Promover os artefatos pra `artifacts/review/furniture/<name>/` (não deixar em runs/).
- A hipótese vira `furniture-anatomy-spec` + `SofaBuilder`; o asset não entra na planta.
