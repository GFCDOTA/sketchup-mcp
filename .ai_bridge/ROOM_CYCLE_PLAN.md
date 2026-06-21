# ROOM_CYCLE — método referência→render→gates→GPT→aprendizado (2026-06-21)

> Decisão do Felipe (corrigindo o Claude): **gate determinístico pega o que está QUEBRADO; ele NÃO cria
> repertório estético.** Sem referências reais o Claude tende a gerar móvel/interior **genérico/quadrado** —
> um sofá pode passar no gate e continuar feio; uma cozinha pode ser funcional e parecer showroom barato.
> Então o ciclo por cômodo precisa **incluir busca e uso de REFERÊNCIAS REAIS**, não só gate.
>
> **Papel de cada um (importante):** os LLMs locais **não são juiz final de gosto** — são
> **pesquisadores, comparadores e organizadores de referência**. O Claude é a **mão** (constrói), não o
> gosto. O gosto vem de **referência + GPT + Felipe**.

## ROOM_CYCLE = REFERENCES + RENDER + GATES + CONSULT_GPT + LEARNING

1. Selecionar o cômodo atual.
2. Buscar/carregar referências reais (internet via Scout / `reference_db`) para aquele cômodo + tema.
3. Montar um **REFERENCE_PACK**: 5 boas referências do cômodo · 3 detalhes relevantes · 2 anti-exemplos ·
   tags de material, forma, proporção, ergonomia, limpeza/manutenção e coisas a evitar.
4. **Arquiteto extrai uma gramática visual** dessas referências ANTES de gerar.
5. Renderer gera o cômodo.
6. Rodar **gates determinísticos**: `furniture_overlap_gate` · `kitchen_ergonomics` · `geometry_sanity` ·
   circulação/clearance · `visual_regression`/PDF-truth quando aplicável.
7. **Consult Liaison** monta a pergunta estruturada pro Consult GPT: render atual · referências usadas ·
   restrições congeladas · achados dos gates · hipótese do Arquiteto · dúvidas específicas.
8. Felipe cola no GPT (ou, no futuro, OpenAI API).
9. Resposta do GPT é **ingerida** → regra nova · anti-pattern · golden sample · próxima microtarefa ·
   atualização do **Felipe Style DNA**.

### Papéis (sem sobreposição)
| papel | dono | responsabilidade |
|---|---|---|
| Verdade física, escala, circulação, ergonomia | **Gates** (código) | pega o que está QUEBRADO |
| Repertório, exemplos, checklist | **Scout + LLMs locais** | trazem e organizam referência |
| Proposta de design | **Arquiteto** (DeepSeek+DNA+gramática) | propõe a partir da referência |
| Imagem | **Renderer** (Claude/SketchUp/V-Ray) | gera o render |
| Ponte com o crítico | **Consult Liaison** | monta a pergunta estruturada |
| Crítica estética + gosto final | **GPT + Felipe** | juiz do que é BONITO |

### "Rodar ciclo" = SESSÃO RASTREÁVEL (não texto genérico de LLM)
Cada ciclo registra: referências usadas · render gerado · gates executados · problemas encontrados ·
modelos consultados · pergunta gerada pro GPT · resposta ingerida · próxima microtarefa.

### Meta imediata = B+ (não só B)
Render real + gates rodando + reference pack + pergunta estruturada pro GPT. **Critério de pronto:** o ciclo
mostra (referências usadas · gates passa/falha · pergunta gerada pro GPT) · a resposta do GPT pode ser
colada e ingerida · o aprendizado vira regra/anti-pattern · **o Arquiteto não projeta do zero sem referência.**

---

## PRIMEIRA PROVA: `SOFA_CLASS_FROM_REFERENCE` (começar pelo SOFÁ, não pela cozinha)

**Por quê o sofá:** laboratório controlado pra provar que o sistema **para de gerar móvel quadrado**.
Cozinha tem variáveis demais ao mesmo tempo; o sofá é mais isolado e o erro aparece na hora.

**Meta:** parar de gerar sofá-caixa e construir uma **classe de sofá baseada em referência real**, com
proporção, conforto visual e linguagem **industrial boutique premium**.

**Direção visual (gosto Felipe — NÃO "industrial bruto"):** industrial boutique premium · apê dark premium ·
preto/grafite/madeira/couro quente · **volume real de almofada** · **assento profundo** · encosto confortável ·
braço baixo/médio (não bloco gigante) · base leve, pés discretos ou plinto bem resolvido · tecido grafite,
couro caramelo escuro, couro preto fosco ou textura premium. **Proibido:** sofá-caixa quadrado · peça bruta de bar/loft tosco.

**Fluxo da tarefa:**
1. Scout busca **6 referências** de sofá: 3 industrial boutique premium · 2 compactos premium p/ apê · 1 anti-exemplo (caixa) a evitar.
2. Montar `SOFA_REFERENCE_PACK`: imagem/link · por que é boa · forma · proporção · braço · assento · encosto · base/pés · material · o que copiar · o que evitar.
3. **Felipe escolhe 1–2 referências principais.**
4. Gerar `SOFA_BUILD_SPEC`: largura por nº de lugares · profundidade de assento · altura de assento · altura de braço · espessura de almofada · inclinação/volume de encosto · raio/chanfro/softness · tipo de base · tokens de material.
5. Reconstruir a **classe sofá** a partir dessa spec.
6. Render de comparação: sofá antigo quadrado × novo de referência · matriz 2 lugares / 3 lugares / lounge.
7. Rodar gates: escala · footprint · circulação · overlap · compatibilidade com sala compacta.
8. Pergunta pro Consult GPT: referências usadas · render antigo · render novo · dúvidas de forma/conforto/gosto.
9. Ingerir resposta: regras novas · anti-patterns · golden sample · atualização do Felipe Style DNA.

**Critério de pronto do sofá:** não pode parecer caixa · leitura clara de assento/encosto/braço/base ·
parecer confortável · caber em apê compacto · combinar com BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE · **gerar regras
reutilizáveis** pras próximas salas. **Não começar pela cozinha antes de provar o método no sofá.**

---

## Estado do DASHBOARD (pro GPT validar/ajudar a melhorar)
Cockpit `:8782` (Docker), serviço separado do oráculo `:8765`. Tudo no código: `tools/studio_dashboard.py` +
pacote `tools/interior_studio/consult_gpt_bridge/`. Já funciona: Pergunte ao time (com DNA, voz, histórico) ·
Conversa do time (thread única) · Consult GPT Bridge (gera contrato → cola resposta → "✓ aprender" ingere) ·
Ciclo (card solto) · Scout (busca web DuckDuckGo) · layout livre (arrasta/recolhe/redimensiona) · cada agente
com seu modelo local. **Pendência principal:** o ciclo ainda é texto genérico — falta virar o ROOM_CYCLE
rastreável acima (referências + gates + pergunta estruturada). É o que o GPT vai ajudar a desenhar/validar.
