# Handoff — pro outro Claude (sketchup-mcp): pare a gangorra do soft barrier / grade

> Cole isto na outra sessão. Antes de tudo: `git fetch origin && git checkout
> develop && git pull` — pra pegar `tools/soft_barrier_source_audit.py` e o
> `run_deterministic_gates` com `render_bbox` (já landados).

---

PARE. Você está no **efeito gangorra**: antes "todo peitoril vira grade", agora
"nenhuma grade / tudo bloco cinza". Os dois são **global on/off** — isso não é
correção, é desligar a feature. O alvo é **whitelist POR SEGMENTO**: cada soft
barrier renderiza pela SUA classe e fonte; nada inventado fora disso.

## Estado REAL (confirme você mesmo — render não é prova)
- `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` tem **9
  soft_barriers**. SÓ **`h_sb000`** tem fonte: `barrier_type=peitoril,
  height_m=1.1, geometry_origin=human_annotation`. **`sb000`–`sb007`** são
  polylines NUS: só `{id, polyline_pts}` — sem `barrier_type`, sem fonte.
- O builder `tools/build_plan_shell_skp.rb` (`build_soft_barrier`) renderiza
  TODOS iguais: slab sólido cinza (`PARAPET_RGB=[130,135,140]`) extrudado a
  `PARAPET_HEIGHT_M=1.10`, ligado/desligado por UM flag global
  `SOFT_BARRIERS_MODE` (groups/skip). **Não há render por tipo.** É a raiz da
  gangorra. Os blocos cinza opacos do render = esses 9 slabs; 8 deles (sb000-007)
  são SEM FONTE → **Hard Rule #1 (nunca inventar geometria)**.
- Veja com seus olhos: `.venv/Scripts/python.exe -m tools.soft_barrier_source_audit
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` → `WARN,
  8 unsourced`.

## A REGRA (faça exatamente isso — whitelist, não global)
1. Renderize soft barrier **só se tiver `barrier_type` + fonte** (human_annotation
   ou label PDF validado: PEITORIL/MURETA/H=...).
   - `peitoril`/`mureta` → muro baixo sólido na `height_m` **da própria barreira**.
   - `guardrail`/`railing` → grade (geometria de grade), **só** nos segmentos
     marcados assim.
2. `sb000`–`sb007` (sem fonte) → **NÃO renderize como barreira física.** Não vire
   bloco, não vire grade, não invente. Se achar que são reais, **prove no PDF** e
   adicione `barrier_type`+fonte no consensus — com aprovação (Hard Rule #3).
3. Remover uma grade **NÃO autoriza criar bloco** no lugar. Sem fonte = nada.

## GATE-FIRST (obrigatório — você não decide "pronto", o gate decide)
- **Já existe** `tools/soft_barrier_source_audit.py` (provenance): tem que parar
  de ter unsourced virando física.
- Construa `tools/railing_exact_match_gate.py`: esperado (consensus: barrier_type
  guardrail/railing) **vs** actual no SKP (parseie de `geometry_report.json` /
  grupos SoftBarrier). FAIL se: `missing_expected_railing>0`,
  `extra_unexpected_railing>0`, `railing_on_wrong_host_wall`,
  `|length_delta|>0.10m`.
- Construa `tools/parapet_not_railing_fallback_gate.py`: WARN/FAIL se aparecer
  low-wall/bloco numa fachada **sem fonte** (pega exatamente a troca grade→bloco).
- Cabeie os dois no `tools/run_deterministic_gates.py` + testes (micro-fixture
  sintético primeiro, como os outros detectores).
- **LOOP**: edite → rode os gates → repita **ATÉ TODOS VERDES**. "Parece ok" /
  render bonito **NÃO conta**. Não declare done com gate vermelho.

## DISCIPLINA (não negocie)
- **PDF é a ÚNICA verdade geométrica.** Render não é prova. Verifique contra a
  canônica do **PATH FIXO `artifacts/planta_74/`** — NUNCA snapshots de review com
  timestamp (já enganaram uma revisão: um `visual_loop_current` cortado).
- **Não tweak no escuro**: olhe o PDF + o artefato antes de mexer em parâmetro
  (foi assim que a calibração de tom saiu certa: parede≤72 < vidro 94 < piso 124+).
- **Aparência muda = VISUAL_REVIEW do Felipe.** Não auto-julgue IMPROVED/SAME/WORSE
  (comprovadamente não-confiável).
- Consulte o oráculo **:8765** (`POST /ask`, aceita `prompt`|`question`, modo
  `redteam`) nas decisões de design.
- Não mute fixtures sem aprovação (Hard Rule #3). **develop-first**, commit por
  fatia, teste por fatia.

## ENTREGÁVEL
O consensus renderiza grade **só onde o PDF/consensus autoriza**, **nenhuma grade
fora**, **nenhum bloco substituto inventado**, e os **3 gates verdes**. Aí sim
gera before/after e manda pro Felipe (VISUAL_REVIEW). Enquanto gate vermelho ou
`unsourced→física`, **não está pronto**.
