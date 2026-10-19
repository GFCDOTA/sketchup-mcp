# FP-043 / P6b — materialização do gabinete no SketchUp real (L2)

**Escopo:** o construtor compartilhado `shared.cabinet.parametric` (`cabinet_build.rb` + `cabinet_inspect.rb` + driver
`tools/rooms/shared/cabinet/sketchup.py`) em **micro-fixtures sintéticos**. **Não** é a cozinha real da `planta_74` (isso é a P7),
**não** inclui ferragem, gaveta, porta Shaker, recorte de bancada/cuba nem fabricação, e **não** é veredito visual.

| | |
|---|---|
| Código sob prova | commit `cdb9dde` (`feat(p6b)`), rodado em árvore limpa |
| SketchUp | 26.0.429 (Windows 11), modo `interactive`, processo próprio por chamada; **26 PIDs** subidos (13 build + 13 reabertura), todos fechados pelo PID — nenhum `taskkill` por nome, nenhum SketchUp alheio tocado |
| Modelo-base | template padrão do SketchUp (1 componente de pessoa), SHA-256 em [`summary.json`](summary.json); a base é copiada, nunca aberta |
| Como cada caso roda | plano L1 → `require_valid` → SketchUp abre a **cópia** → constrói, salva → **fecha** → outro SketchUp **reabre o arquivo salvo** → `cabinet_inspect` lê vértices de mundo/manifold/atributos → `verify` compara com o plano |
| Tolerância | 1e-5 m (0,01 mm). O SketchUp guarda polegadas em ponto flutuante e o job arredonda a 6 casas; não é folga de projeto |
| Reprodução | `l2_matrix.py <saida> <base.skp>` (neste diretório), com o repo no `PYTHONPATH` e `PT_TO_M=0.0259` |

## Resultado (13 casos, 13 PASS)

| Caso | O que prova | Erro máx. de vértice |
|---|---|---|
| `m1_valid_a_base_600_r0/_r90/_r30` | 600×560×720 mm, 0°/90°/30° | 3e-18 / 2e-16 / **5,4e-7 m** |
| `m1_valid_b_tall_900_r90/_r30` | 0,9 m × 350 mm × 210 cm, prateleira + 2 frentes | 5e-16 / **6,0e-7 m** |
| `m1_holdout_c_r30/_r0` | caso **reservado** (437×523×1033 mm; fixado por hash antes do planner), 30° e 0° | **4,8e-7 m** / 3e-16 |
| `m2_idempotent_rebuild` | mesmo `request_id` sobre o arquivo anterior: substitui (`replaced_previous=1`), 1 grupo, mesmas definições — **sem duplicar** | 3e-18 |
| `m3_repeat_x` / `m3_repeat_y` | dois gabinetes iguais no **mesmo modelo** (repetição), cada um íntegro | 5e-16 |
| `m3_edit_local` | `edit_definition` sem `propagate`: `make_unique` — **só** a lateral esquerda de X muda; a direita de X e o Y inteiro ficam | 5e-16 |
| `m3_edit_propagate` | `propagate:true`: as duas frentes (definição compartilhada) mudam **porque foi pedido**; Y intacto | 5e-16 |
| `m3_set_material` | atualização local de material em uma peça; as demais peças não mudam | — |

Cada caso confere, **por peça**: os 8 vértices de mundo (geometria real, não AABB — nos 30° a diferença para o AABB é grande),
sólido fechado (`manifold`, 6 faces, 12 arestas), material, tag (`Cabinet_<papel>`), nome = id estável do plano, atributos
(`skmcp_cabinet`: capacidade, versão, assinatura), definição compartilhada só entre equivalentes, nenhuma geometria solta na raiz
e o **fingerprint do que não é gabinete** igual ao da base (arquitetura/outros objetos intactos).

## Limites que o PASS não cobre

- **Veio da madeira: `NOT_SUPPORTED`.** O material é nome + cor derivada do nome, sem textura; o veio fica só como atributo
  (`grain`), não aplicado nem verificado. Não se declara PASS de veio.
- Só caixaria retangular + frentes lisas separadas (1 ou 2). Nada de ferragem, gaveta, Shaker, recorte, lista de corte.
- Sem revisão visual (`NOT_REVIEWED`); L2 aqui é geometria/estrutura, não beleza nem prontidão de fabricação.
- Modelo-base sintético: a integração com o shell e a cozinha reais (âncora da pia, circulação, mobília planejada) é a P7.
- Interrupção de job (simulação de job morto) e a trilha completa pedido→SKP são da P7.

Arquivos: `<caso>.json` (build + reabertura + verificação) e `<caso>.skp` (o arquivo salvo); [`summary.json`](summary.json) resume
hashes, PIDs e versão.
