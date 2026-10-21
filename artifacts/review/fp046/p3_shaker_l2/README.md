# FP-046 / P3 — porta Shaker no SketchUp real (L2)

**Escopo:** a capacidade `shared.cabinet.front.shaker` (`shaker_build.rb` + `shaker_inspect.rb` + `tools/rooms/shared/cabinet/shaker/sketchup.py`)
sobre **gabinetes-pai sintéticos** (`fixtures/synthetic_cabinets/valid_a_base_600.json`, 1 ou 2 frentes). **Não** é a cozinha real da
`planta_74` (adapter e gates da cozinha = P4/P5), **não** inclui gaveta, ferragem, veneziana, recorte nem fabricação, e **não** é veredito
visual: os valores da porta (60/60/18 mm, painel 6 mm, recuo 4 mm) são sintéticos, **não** padrão de fabricante.

| | |
|---|---|
| Código sob prova | commit `2fa85a48ec788e35d77e98b265b8a0778e24efd8`, árvore **limpa** (`dirty: false` no `summary.json`) |
| SketchUp | 26.0.429 (Windows 11), modo `interactive`; **29 PIDs** subidos (build + reabertura), todos fechados por PID via `jobs.close` — nenhum `taskkill` por nome |
| Base | template `Temp01b - Simple.skp` do SketchUp (SHA-256 em [`summary.json`](summary.json)); é copiada, nunca aberta; o pai é construído por `cabinet_build.rb` (intacto) |
| Cada caso | pai materializado → reaberto (baseline) → `shaker_build` numa **cópia** → fecha → **outro SketchUp reabre o salvo** → `shaker_inspect` → `verify_shaker` |
| Tolerância | 1e-5 m (0,01 mm); não é folga de projeto |
| Reprodução | `PYTHONPATH=. python artifacts/review/fp046/p3_shaker_l2/l2_matrix.py <saida> <template.skp>` (saída fora de `fixtures/` e `artifacts/`) |
| Arquivos | `<caso>_verify.json` (todos os checks) + [`summary.json`](summary.json) (commit, versão, PIDs, SHA-256 de cada `.skp` de saída). Os `.skp` ficam em `runs/` (não versionados) |

## Resultado (10 casos, 10 PASS)

| Caso | O que prova | Checks | Erro máx. de vértice |
|---|---|---|---|
| `s1_one_door_r0 / r90 / r30` | 1 porta, pai a 0°/90°/30°: 5 peças, **frente lisa substituída ausente**, vértices de mundo (30° ≠ AABB), recuo **medido no modelo reaberto** = 4,000 mm (medido 3,9999–4,0002 mm), sólidos fechados (6 faces/12 arestas), material, tag `Cabinet_frame/panel`, atributos, definições compartilhadas só entre equivalentes (montantes; travessas), arquitetura/outros objetos intactos, definição órfã da frente removida | 53 cada | 0 / 0 / **4,6e-7 m** |
| `s2_two_doors_r30` | 2 portas no **mesmo** gabinete (duas execuções em sequência): 2 subgrupos, 10 peças sem id duplicado, nenhuma frente lisa sobra, cada porta verificada | 54 | **4,8e-7 m** |
| `s3_idempotent_rebuild` | mesmo `request_id` de novo: substitui (`replaced_previous=1`), 1 grupo, **sem definição órfã** | 51 | 4,6e-7 m |
| `s4_make_unique_local` | `edit_definition` sem `propagate`: `make_unique` — só o montante esquerdo muda; o direito fica e a definição se divide | 52 | 4,6e-7 m |
| `s5_edit_propagate` | `propagate:true`: as duas travessas (definição compartilhada) mudam **porque foi pedido** (`definition_instances_before = 2`) | 50 | 4,6e-7 m |
| `s6_set_material_panel` | material local do painel; as outras 4 peças não mudam | 1 | — |
| `s7_ruby_refuses_stale_parent` | negativo **no Ruby real**: o modelo não tem o pai citado pelo plano ⇒ `FAILED`, sem resultado utilizável | 1 | — |
| `s8_ruby_refuses_changed_parent_signature` | negativo **no Ruby real**: pai com o mesmo `request_id` mas outra assinatura ⇒ `FAILED` | 1 | — |

## O que a prova achou (e foi corrigido antes do commit final)

1. **Sem arquivo-base o SketchUp trava na tela inicial** (`-RubyStartup` sem `.skp` não executa o job). A matriz agora exige um template.
2. **Reexecução deixava definições órfãs** (`replaced=1 groups=1 defs=6` em vez de 3; a nova leva ganhava nome `#1`). O Ruby passou a
   remover as definições órfãs do mesmo `request_id` antes de recriar; teste de texto trava a ordem.
3. Job recusado em Windows: o SketchUp ainda segura a cópia aberta, então o driver deixa o marcador `NOT_A_RESULT` (comportamento já
   existente); a matriz verifica o marcador e apaga o resto depois de fechar o PID.

## Limites que o PASS não cobre

- **Veio: `NOT_SUPPORTED`** (atributo, sem UV). Sem veredito visual: `visual = NOT_REVIEWED` / **`PENDING_HUMAN`** para a aparência.
- Só pai sintético. Âncora da pia, circulação e mobília da cozinha real, regressão dos demais cômodos (FP-047) e o catálogo de
  capacidades **não** foram tocados: o `bind.kitchen.shaker` segue sem capability (D46-09) e `specialists.plan` ainda devolve
  `BLOCKED_CAPABILITY_MISSING`.
- Uma única máquina/versão do SketchUp (26.0.429); a prova é desta árvore/commit (`R-18`: mudou símbolo ⇒ refazer).
