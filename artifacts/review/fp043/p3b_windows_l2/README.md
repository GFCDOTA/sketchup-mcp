# FP-043 / P3b — segurança do executor e L2 real no Windows

Ambiente: SketchUp 26.0.429 (V-Ray instalado), Windows 11, repo em árvore limpa sobre `develop` + as correções desta PR.
Scripts nesta pasta (`tools/`): cada número abaixo sai deles. Todo SketchUp subido foi fechado **pelo PID**; nenhum `taskkill` por nome;
os canônicos (`planta_74.skp`, `geometry_report.json`, `planta_74_furnished.skp`) têm SHA-256 idêntico antes/depois (`reg_summary.json`).

## P3b-01 — processo, janelas e Job Object

### Duas janelas simultâneas ([`two_windows.json`](two_windows.json))
(a) uma janela "do humano" com **trabalho não salvo** (um grupo criado e nunca salvo; heartbeat a cada 1 s) e (b) os jobs do MCP.

| O que se fez em (b) | (a) depois |
|---|---|
| `su_status` (vê (a) na lista de instâncias) | — |
| `su_inspect` pelo MCP: o job abriu **a cópia** `_inspect_target.skp`, PID ≠ (a) | vivo, heartbeat avançando, `modified=true`, grupo e contagem iguais |
| `su_close(all_instances)` sem `confirm` | `CONFIRMATION_REQUIRED`; (a) intacto |
| `su_close(pid=(b), force, confirm)` | só (b) fechou; (a) intacto |
| `su_close` de PID inexistente | `ERROR`; (a) intacto |
| job com **timeout** (1 s, interactive) | `TIMEOUT`; (b) fica aberto de propósito (inspeção) e foi fechado pelo PID; (a) intacto |
| job com `.skp` **corrompido** (erro) | `TIMEOUT` em 45 s, **nenhum resultado positivo**; fechado pelo PID; (a) intacto |
| CLI legada: `launch_owned` + `close_owned` | só o PID próprio fechou; (a) intacto |

Resultado: **6/6** verificações de (a) intacto; **nenhum** `*control*` no `Plugins` antes/depois (sem `autorun_control.txt` global).
A janela (a) só foi fechada no fim, pelo PID, pelo próprio teste.

### Job Object e encerramento do servidor ([`clients.json`](clients.json), [`clients_before_fix.json`](clients_before_fix.json))
Servidor medido com o cliente **Python** (`mcp` 1.28) e com um cliente **Node** (SDK oficial `@modelcontextprotocol/sdk` 1.29, Node 24). **Não** foi o
Claude Code desktop em si (não dá para reconectar o MCP dele daqui): o Node mede o SDK Node sob o mesmo shell/job; o spawn interno do Claude Code
não foi exercitado.

- Os dois enxergam o servidor num job `KILL_ON_JOB_CLOSE`, **sem** `BREAKAWAY_OK`, com `SILENT_BREAKAWAY_OK`; 18 tools.
- **Defeito achado:** com o cliente **Python**, um SketchUp aberto por `su_open` **morria quando o cliente fechava** (`clients_before_fix.json`:
  `alive_4s_after_client_closed=false`), embora o diagnóstico `server_job.sketchup_survives_server_exit` dissesse `true` (o `mcp` Python cria o
  próprio job e o termina; o diagnóstico só vê o job externo). Com o cliente Node sobrevivia.
- **Correção:** `su_open` agora lança o SketchUp **fora do Job Object** (`Win32_Process.Create`, filho do serviço WMI, na sessão do usuário, janela
  visível). Depois: sobrevive nos **dois** clientes (`clients.json`), limpo por PID. Os jobs em lote seguem o job do cliente **de propósito**
  (morrem com ele). O diagnóstico ganhou o limite documentado. Testes novos (L1) cobrem comando WMI, fallback e handle por PID.

### Auditoria das dez entradas do PR #296 e do resto do repo
- Os 10 arquivos do #296 (`bake_theme_skp`, `furnish_apartment`, `furnish_plan`, `kitchen_vray`, `place_bedroom_skp`, `place_layout_skp`,
  `render_banho_vray`, `render_room.ps1`, e os providers `sketchup_basic`/`vray_final`) usam `launch_owned`/`close_owned` ou `Start-Process -PassThru`
  + `CloseMainWindow` (PID próprio); nenhum `/IM`.
- **Mas** `git grep` achou **4 chamadas `taskkill /F /IM SketchUp.exe` fora dessa lista**: `material_review.py` (2), `rooms/bedroom/designer.py` (2) e
  `sofa_premium_harness.py` (1 pré-kill). Depois da P4 os "migrados" viraram fachadas e o teste do #296 passava no vazio. **Corrigido:** removidos os
  pré-kills; o encerramento passou a `terminate_owned(proc.pid)` (só o filho que o script subiu). Novo teste varre **todo** o código rastreado
  (`tests/test_fp043_no_kill_by_name_scan.py`: AST das chamadas + regex nos `.ps1/.cmd/.sh/.rb`).
- `launch_owned` deixou de usar `-ExecutionPolicy Bypass` (`-Command` não precisa; só fazia o Defender desconfiar).

## P3b-02 — MCP estrito e operações positivas (cliente Python real, 1 sessão; [`reg_summary.json`](reg_summary.json): **19/19 PASS**)

| Operação | Evidência |
|---|---|
| 18 tools listadas; `su_status` com `server_job` e `proof_state` | ok |
| `su_build_shell` planta_74 | `geometry_report` **igual ao aprovado** (só campos de caminho diferem); `run_deterministic_gates --report` PASS (6 gates) |
| `su_inspect` do reconstruído | 77 nós, bbox 13,06×7,74×2,70 m, **idêntico** ao inspect aprovado do L2 FP-042 |
| `su_render` (presets `top`/`iso`) | 2 PNGs 1200×900 com conteúdo (620 e 317 cores) — [`render_planta_top.png`](render_planta_top.png), [`render_planta_iso.png`](render_planta_iso.png); preset inválido → `ERROR` |
| `su_furnish` | 402 caixas; reaberto: 543 nós |
| `su_apply_edits` | `set_tag`+`move`+`set_material` num móvel: reaberto, `dx=0,100 m`, tag e material aplicados, **original intacto**; `delete` do `PlanShell_Group` → recusado ("Hard Rule #1"), cópia não editada marcada `NOT_A_RESULT` |
| `su_open` + `su_close` | janela mantida aberta de propósito (`outside_job=true`); fechada só por PID; `all_instances` sem `confirm` → recusado |
| `su_render_vray` | `OK`, PNG de 635 KB — [`vray_living.png`](vray_living.png) (cena de referência `living_room_black_wood_gold_boutique`; só prova de execução, **sem veredito visual**) |
| stdout limpo / preload | o servidor fala JSON-RPC puro (smoke e stdio_check PASS nesta PR); conectou em ~0,6–0,8 s |
| Retorno só com arquivo válido | `su_apply_edits`/`materialize` conferem o arquivo gravado depois da cópia; jobs interrompidos/falhos não deixam resultado (L1 + P7) |

Observação honesta: numa rodada anterior desta bateria um `su_close(force)` por PID devolveu `PARTIAL` (o processo ainda constava após os 5 s de
graça); não se repetiu em 4 tentativas seguintes (fechamento em ~0,5 s). Registrado, não explicado.

## P3b-03 — modelos regressivos (sem tocar os canônicos)

- **planta_74** (escala `PT_TO_M=0.0259` do ambiente): relatório e inspeção iguais ao aprovado (acima). `su_furnish` + [`reg_compare_furnish.json`](reg_compare_furnish.json):
  **402/402 peças** casadas com o plano, erro máx. 0,05 mm (igual ao L2 FP-042). Os achados de colisão/porta/fora-do-cômodo desse relatório são os já
  conhecidos (matéria-prima da P3a-03) — não foram "corrigidos" nem escondidos.
- **Cada cômodo sozinho × integrado** ([`rooms_isolated_report.json`](rooms_isolated_report.json)): os 8 cômodos materializados isoladamente sobre o shell
  ficam **idênticos** ao integrado (peças e shell), sem módulo estranho.
- **quadrado** (escala padrão do quadrado, não a da planta_74): `su_build_shell` OK; gates PASS (6/6); reaberto: 4,19 m de largura (4,00 m livre + parede),
  **bbox idêntico ao baseline L2 FP-042**. A janela sai ~5,7 cm da face sul (mesma divergência D-001).
- **Controle negativo de escala** (modelo com fator errado, o `S01a` do L2 FP-042): `scale_anchor` **FAIL** independente do builder — o gate de escala pega.
- **Abertura 3D / D-001, às claras** ([`aperture_conditional_tests.txt`](aperture_conditional_tests.txt)): com o shell+relatório REAIS do quadrado no lugar onde os testes
  condicionais olham, 8 passam e **1 falha** (`test_quadrado_window_glass_group_exists`: vidro 1,50–2,10 m do builder × 0,90–2,10 m da referência). É o D-001: segue
  FAIL, sem relaxar limiar, esperando a decisão do Felipe.

## Limites
Cliente Node = SDK, não o Claude Code desktop. Interrupção de job e `su_render_vray` com cena nova não foram exploradas além do descrito. Nada aqui é veredito visual.
