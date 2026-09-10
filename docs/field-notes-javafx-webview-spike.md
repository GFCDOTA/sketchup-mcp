# Spike — JavaFX WebView aguenta a UI do Inspector?

- **Data:** 2026-09-09 · **Natureza:** spike descartável, risco técnico, NÃO produção
- **Pergunta única:** JavaFX WebView aguenta a UI que o Inspector precisa sem gambiarra?
- **Local (TTL, descartável):** `E:\Claude\data\runs\javafx-webview-spike\`
- **Como rodou:** `javac`/`java` direto com `--module-path`. **Sem build tool**
  (a máquina não tem mvn nem gradle), sem projeto, sem wrapper.

## 1. Resultado

**PASS** — 13/13 critérios atendidos, **zero erro de JS**.

## 2. Critérios, um por um (medido, não olhado)

| # | Critério | Resultado | Evidência |
|---|---|---|---|
| 1 | Java 25 + JavaFX abre janela nativa | **PASS** | `java.version=25.0.2` · `javafx.runtime.version=25.0.4+2` · `window.shown=true` |
| 2 | Carrega página React UMD local | **PASS** | `loadWorker.state=SUCCEEDED` em `file:///…/spike.html` · `reactVersion=18.3.1` · `reactDomPresent=true` |
| 3 | Renderiza SVG | **PASS** | `getBoundingClientRect` do `<rect>` = **200×40** (não-zero, real) |
| 4 | Renderiza `<canvas>` | **PASS** | desenhei `rgb(29,158,117)`; `getImageData` devolveu **[29,158,117,255]** |
| 5 | Atualiza estado React dinamicamente | **PASS** | 2 chamadas Java→JS de `bump()` → DOM virou `"bumps: 2"` |
| 6 | Resize da janela funciona | **PASS** | stage 520→980 ⇒ `innerWidth` 520→**964**, `innerHeight` 700→**721** |
| 7 | Scroll funciona | **PASS** | container `scrollHeight=1464` vs `clientHeight=420`; `scrollTop=400` → leu **400**; reset → **0** |
| 8 | Recebe JSON de trace do Java e atualiza UI | **PASS** | 27 eventos do JSONL **real** empurrados via `JSObject.call` → **27 caixas** no DOM |
| 9 | Sem navegador externo | **PASS** | só a janela JavaFX; nenhum processo de browser |
| 10 | Sem Spring Boot | **PASS** | zero dependência além dos 5 jars do JavaFX |
| 11 | Sem Electron | **PASS** | — |
| 12 | Sem watchdog / Scheduled Task / PowerShell | **PASS** | um `java` em foreground e nada mais |
| 13 | Fechar a janela encerra o processo | **PASS** | `WINDOW_CLOSE_REQUEST` → `Application.stop` → **exit 0**. Não existe `System.exit` no código |

Dado de entrada: o trace real `run_20260827T021348Z_banho.jsonl` (27 eventos).
Não usei dado fake — o real deu menos trabalho e prova mais.

## 3. Versões

- **JDK:** Temurin 25.0.2 (JavaFX não vem no JDK; 5 jars, ~44 MB, no module-path)
- **JavaFX:** 25.0.4+2 (GA; a última GA é 26.0.2, pareei com a major do JDK)
- **WebKit:** `AppleWebKit/623.1 … JavaFX/25 Version/18.4 Safari/623.1`
  → **classe Safari 18.4**, não o WebKit velho da reputação histórica do WebView.
- **JS testado igual ao de produção:** React 18.3.1 UMD + ReactDOM + **Babel standalone 8.0.4**
  transpilando JSX no browser. **Zero erro.** Era o maior risco e ele não se materializou.

## 4. Limitações encontradas

1. **`netscape.javascript.JSObject` está deprecated e marcado pra REMOÇÃO.** É a ponte
   Java→JS que usei no critério 8. Não quebra hoje (4 warnings de compilação), mas é
   dívida com data marcada. Mitigação barata: passar dados como string JSON via
   `executeScript` e não depender de `JSObject`.
2. **Native access vai ser bloqueado em release futura.** Warnings pedem
   `--enable-native-access=javafx.graphics,javafx.web`. Hoje é cosmético, depois é
   obrigatório. Flag trivial.
3. **`WebView` como raiz direta da `Scene` não recorta o conteúdo** — o viewport cresce
   com a página e o scroll interno não existe. Falha da MINHA sonda na 1ª rodada
   (`scrollHeight == clientHeight == 1593`). A UI precisa ser dona do seu container de
   scroll — o que o Inspector faria de qualquer jeito. Disciplina de layout, não defeito.
4. **Sem build tool na máquina** (nem mvn nem gradle, e `~/.m2` sem openjfx). Pro app de
   verdade vai querer o Maven wrapper; pro spike, `javac` direto foi mais limpo.
5. **JavaFX fora do JDK** = 44 MB de jars a distribuir/versionar.

## 5. Recomendação

**`PROCEED_JAVAFX_WEBVIEW`**

O risco que motivou o spike (WebKit velho não aguentar React/Babel/SVG/canvas) **não
existe** nesta versão. Nenhum critério exigiu gambiarra, JNI ou workaround.

Próximo passo conforme combinado: amendar a §7.1 da spec como ADR e seguir com
`Java domain + TraceSource + React visualization`, **começando pelo replay do JSONL**.

## 6. Escopo que eu NÃO fiz (de propósito)

Sem SSE, sem health probe, sem domínio completo, sem layout final. O spike não virou
arquitetura de produção — é `rm -rf` e não sobra nada.
