# geometry_sanity — gate de regressão geométrica

> Determinístico, barato, **sem LLM**. Roda ANTES de promover `.skp`/render/artifact/
> ambiente mobiliado. Existe porque já sofremos com geometria **underground, degenerada,
> off-axis, escala explodida, caos voltando depois de "corrigido"**. Impede a regressão.

## O que checa (nas peças/boxes: x0,y0,x1,y1 + z0_in/h_in + corners)
| check | severidade | regra |
|---|---|---|
| `underground` | FAIL | `z0_in < -0.5` (peça embaixo do piso) |
| `degenerate_footprint` | FAIL | footprint < 1 (área ~0) |
| `degenerate_height` | WARN | `0 < h_in < 0.2` (sliver 2D) |
| `off_axis` | FAIL | corners não axis-aligned (eixo torto) |
| `absurd_bbox` | FAIL | qualquer dimensão de UM móvel > 6m (escala explodida) |
| `outside_room` | FAIL | centro da peça fora de todos os polígonos de cômodo (só roda se `rooms` na MESMA unidade) |

Nível-SKP/consensus (parede faltando vs baseline, opening host, wall overlap, render bbox,
wall presence) **já é coberto** por `run_deterministic_gates.py` — `geometry_sanity` é o membro
de **geometria de peças/placement** que faltava; compõe com aqueles, não duplica.

## Veredito
- **PASS** = sem regressão geométrica óbvia. **NÃO** significa bonito/premium.
- **WARN** = borderline; segue com **motivo explícito**.
- **FAIL** = regressão objetiva → **bloqueia promoção** (exit 1).
- Exit codes: `0=PASS · 2=WARN · 1=FAIL`.

NÃO substitui o veredito visual final (estética/premium/fidelidade = visual review/GPT).

## Uso
```bash
python tools/geometry_sanity.py <boxes.json> --to-m 0.0254 [--consensus <c.json>] [--log-dir <dir>]
```
Saída: linha-resumo + JSON; com `--log-dir` grava `geometry_sanity.json` (artifact de auditoria).

## Integração (próximos slices, quando seguro)
- chamar em `run_deterministic_gates.run_all()` quando houver boxes/placement;
- bloquear `promote_artifact`/`promote_canonical` se `overall == FAIL`;
- allowlist do worker local (é determinístico, sem LLM, cwd fixo);
- card "local jobs" no NOC quando existir.

Provado em `apt_boxes.json` (planta_74 mobiliado, 93 peças) = **PASS**; 7 testes herméticos
cobrindo underground/degenerada/off-axis/bbox-absurda/fora-do-cômodo.
