# Regras de design — dormitórios planejados (auto-mobiliado)

Regras e medidas **destiladas** (não copiadas) de pesquisa com modelos de design
e referências de ergonomia/marcenaria residencial BR. É a fonte-da-verdade
textual do brain `tools/bedroom_layout.py`. Felipe 2026-06-05.

## Dimensões de móvel (m) — largura × profundidade × altura
Cama (largura ao-longo da parede × comprimento × altura do box):
- solteiro `0.88 × 1.88 × 0.55`
- casal `1.38 × 1.88 × 0.55`
- queen `1.58 × 1.98 × 0.55`
- king `1.93 × 2.03 × 0.55`

Guarda-roupa: profundidade `0.60`, altura `2.20`; largura por quarto —
pequeno `1.20` / médio `1.80` / grande-suíte `2.40` / suíte grande `3.00`.

Criado-mudo: `0.40×0.35` (compacto) / `0.50×0.40` (default) / `0.60×0.45` (grande), alt `0.60`.

## Cama por área do cômodo (+ fallback de tamanho)
- `< 10 m²`: solteiro
- `10–14`: casal
- `14–18`: queen → *fallback* casal → solteiro
- `18+`: queen default; **king só se `min_dim ≥ 3.60 m`** (folga com sobra) → *fallback* queen → casal

Fallback = se o tamanho-alvo não passa os hard gates, o brain tenta o próximo
menor automaticamente (registrado em `out.fallback` / `bed_tried`).

## Clearances (m)
- circulação ao redor da cama: **mín 0.60**, alvo `0.75`, nos dois lados úteis
- folga no pé da cama: mín `0.60`, alvo `0.75–0.90`
- frente do guarda-roupa: **`0.75` (correr) / `1.00` (abrir)** — o brain usa correr (`0.75`), padrão de apto compacto
- passagem livre geral: `≥ 0.60`

## Hard gates (reprovam o candidato)
- todos os móveis dentro do polígono do cômodo
- cabeceira da cama encostada em parede
- não bloquear porta nem o arco/caminho de giro (zona de circulação)
- não invadir o vão da abertura (cama em cima da porta = inválido)
- não bloquear janela (móvel alto cobrindo a janela; **cama sob janela é SOFT**, não proíbe)
- guarda-roupa (se presente) com frente livre `≥ 0.75`
- não invadir a massa da parede
- passagem livre `≥ 0.60`

## Soft gates (pontuam o ranking)
- folga lateral da cama → `0.75` | folga no pé → `0.90`
- cama centralizada na parede da cabeceira
- 2 criados-mudos quando couber (1 em quarto pequeno)
- guarda-roupa presente com frente livre
- evitar cabeceira sob janela (penalidade forte `-25`; não proíbe)
- *(TODO)* penalizar guarda-roupa colado na janela; bonus circulação clara porta→cama/armário

## Edge cases (degradação elegante)
- **quarto pequeno**: cortar primeiro o guarda-roupa (omitido se não cabe com folga),
  depois um criado-mudo; cama menor via fallback.
- **suíte grande**: cama maior (king se largo), 2 criados, guarda-roupa folgado.

## Erros comuns a penalizar (pesquisa)
cama bloqueando porta/janela; guarda-roupa perto demais da cama; circulação
insuficiente em volta da cama; móvel grande demais para o cômodo; cabeceira sob janela.

## Fontes consultadas
- **Ollama `interior-designer:latest`** (2026-06-05): guarda-roupa frente correr `0.75` / abrir `1.00`; lista de erros comuns; degradação de quarto pequeno.
- **ChatGPT** "Prioridade Quartos e Layout" (2026-06-05): dimensões de cama/armário/criado, regra de cama por área, hard/soft gates iniciais.
- Implementado/verificado em `tools/bedroom_layout.py` + `tests/test_bedroom_layout.py` (geometria pura, pytest).
