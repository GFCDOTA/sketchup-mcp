# SOFA_GPT_REVIEW_LOOP — harness com o GPT no loop de construção do sofá

> **Por quê (Felipe, 2026-06-10):** o olho do humano não é especialista o bastante pra ser
> o juiz visual. O **GPT é o diretor de qualidade**: ele analisa as fotos (gerado × referência)
> e diz o que mexer. Este harness torna **cada passo da construção do sofá GPT-guiado**,
> repetível e logado — o agente segue o GPT, não o palpite.

## O loop (1 ciclo)

```
1. BUILD    — gerar/ajustar o sistema e rodar a suite (scripts/build_sofa_eval_suite.rb)
2. RENDER   — front / side / top / three_quarter do(s) caso(s) (ja sai da suite)
3. SHEET    — montar a folha REFERENCIA x GERADO:
              python scripts/make_gpt_review_sheet.py <case_id> [modern_dark|kivik]
              -> renders/sofa_eval/gpt_review/<case>_review.png  +  <case>_prompt.txt
4. CONSULT  — o AGENTE manda pro GPT (ChatGPT via extensao Claude no Chrome):
              a) powershell -STA -File scripts/set_clipboard_image.ps1 -Path <review.png>
              b) Chrome MCP: nova aba -> chatgpt.com -> Ctrl+V (cola a imagem) -> cola o PROMPT -> Enter
              c) ler a resposta (get_page_text / screenshot)
5. PARSE    — extrair o formato fixo (abaixo). E a fonte de verdade do veredito visual.
6. APPLY    — aplicar o TOP_FIX em ONDE_NO_SISTEMA (primitive/component/generator/schema/material).
              ANTI-OVERFIT: a correcao e de CLASSE, nunca de 1 exemplar.
7. LOG      — append em references/sofas/gpt_review_log.jsonl (1 linha por ciclo).
8. REPEAT   — volta ao 1 com o proximo TOP_FIX, ate CONVERGIU=sim (ou budget de ciclos).
```

## Formato fixo da resposta do GPT (parseável)

O prompt padrão (`make_gpt_review_sheet.py` emite, igual todo ciclo) força:

```
VEREDITO: PASS|WARN|FAIL
PARTE_PIOR: almofada|encosto|braco|base|perfil|material
TOP_FIX: <a UNICA coisa mais importante pra mexer agora — concreta, geometrica/parametrica>
ONDE_NO_SISTEMA: primitive|component|generator|schema|material
POR_QUE: <1 linha>
PROXIMO_DEPOIS: <2a prioridade>
CONVERGIU: sim|nao
```

Regras embutidas no prompt: **não recomendar textura/V-Ray enquanto a GEOMETRIA do estofado
não estiver boa**; toda correção é de classe.

## Linha do log (`references/sofas/gpt_review_log.jsonl`)

```json
{"cycle": N, "date": "YYYY-MM-DD", "case": "<id>", "ref": "modern_dark|kivik",
 "veredito": "PASS|WARN|FAIL", "parte_pior": "...", "top_fix": "...",
 "onde": "primitive|component|generator|schema|material", "convergiu": "sim|nao",
 "aplicado": "<o que o agente mudou no sistema>", "commit": "<sha curto>"}
```

## Critério de parada

- **CONVERGIU=sim** por 2 ciclos seguidos (na peça em foco) → fecha a peça, passa pra próxima
  na ordem do GPT (almofada → encosto → braço → base/pés → material → V-Ray).
- **Patinagem**: mesmo TOP_FIX repetindo 3x sem o GPT mudar de veredito → parar, registrar
  "BLOCKED" no log e escalar pro Felipe (o GPT pode estar pedindo algo fora do alcance low-poly).
- **Budget**: limite de ciclos por sessão (default sugerido: 6) — depois consolida e reporta.

## Papéis

- **GPT** = diretor/juiz visual (analisa, prioriza, aprova/reprova). Veredito visual nunca é auto
  do agente (regra do projeto — `gpt-review-gate`).
- **Agente (Claude)** = executa build/render, monta a folha, pilota o Chrome, parseia, aplica no
  SISTEMA (não no exemplar), loga, repete.
- **Felipe** = define direção macro e desbloqueia quando o loop patina; não precisa julgar pixel.

## Notas de robustez (Chrome consult)

- `file_upload`/`upload_image` falham p/ paths do repo → usar **clipboard STA + Ctrl+V**
  (`set_clipboard_image.ps1`).
- `navigate` força https; abrir **nova aba por ciclo** (`tabs_create_mcp`) ou reusar a thread de
  review ("Análise de sofá procedural") pra manter contexto.
- `get_page_text` às vezes atrasa a captura da última resposta → fallback `screenshot`.
- **COLISÃO DE CLIPBOARD (bug real do loop, 2026-06-10):** se o agente põe a IMAGEM no
  clipboard e depois o humano **copia o texto do prompt** (Ctrl+C), o texto SOBRESCREVE a
  imagem → o Ctrl+V cola só texto e o GPT responde "anexar a imagem". **FIX:** o AGENTE
  **digita o prompt** no composer via MCP (`type` funciona pra texto), e o humano faz
  **só Ctrl+V (imagem) + Enter**, sem copiar nada. Nunca peça pro humano copiar o prompt.
- O `ctrl+v` SINTÉTICO do MCP NÃO entrega imagem do clipboard (só um Ctrl+V real do teclado
  entrega). Por isso: agente digita texto, humano cola a imagem. `set_clipboard_image.ps1`
  usa `SetDataObject(img, $true)` (persist) pra a imagem sobreviver no clipboard.
- Se o Chrome (extensão Claude) estiver **off** → marcar `BLOCKED_VISUAL_REVIEW_CHROME_OFF`,
  NÃO autoaprovar, salvar a folha e pedir o Chrome ao Felipe.
