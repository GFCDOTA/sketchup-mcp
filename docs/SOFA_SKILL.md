# SOFA_SKILL — modelagem de sofá low/mid-poly para SketchUp

> **Ensinador**, não asset. Este doc é a regra que `scripts/sofa_primitives.rb`
> e `scripts/build_sofa_3seat_v1.rb` implementam. Objetivo: sair do **blockout
> caixotão** → asset com cara de sofá real, próximo de um bom modelo do
> 3D Warehouse, **sem** depender de asset externo (geometria paramétrica própria).

Fonte das medidas: prática de marcenaria estofada + ergonomia residencial
(`designer_default`); silhueta validada nos ciclos de GPT anteriores
(`project_decision`, ver `artifacts/review/furniture/sofa/`).

---

## 1. Anatomia (peças nomeadas)

```
        ┌───────────── encosto (3 back cushions) ──────────────┐   ← inclinado 8–12°
        │  ╭──────╮  ╭──────╮  ╭──────╮                        │
 braço  │  │ back │  │ back │  │ back │                        │ braço
 (arm)  │  ╰──────╯  ╰──────╯  ╰──────╯                        │ (arm)
 largo ▓│  ╭──────╮  ╭──────╮  ╭──────╮  ← assentos (vinco)    │▓ largo
       ▓│  │ seat │  │ seat │  │ seat │   com VOLUME (coroados) │▓
        └──┴──────┴──┴──────┴──┴──────┴────────────────────────┘
           ▔▔▔▔▔▔▔ base/plinto RECUADO ▔▔▔▔▔▔▔
            ┃                                  ┃   ← pés curtos e RECUADOS
```

Peças obrigatórias (componente/grupo nomeado cada):
- **base** (plinto/estrutura) — recuada da frente; mais escura (contraste).
- **seat_cushion** ×2–3 — separadas (vinco), **com volume** (topo coroado), piping.
- **back_cushion** ×3 — separadas, levemente mais escuras, **inclinadas**.
- **arm** ×2 — **largos**, topo arredondado (track/rolled arm).
- **leg** ×4 (ou 6 com chaise) — **curtos, recuados**, levemente afilados.
- **piping/seam** — vivo fino na borda das almofadas (costura simples).

---

## 2. Proporção (3 lugares — defaults, em metros)

| dim | valor | nota |
|---|---|---|
| largura total `W` | **2.10–2.30** | 3 lugares; default **2.20** |
| profundidade `D` | **0.90–0.98** | default **0.95** |
| altura total `H` | **0.80–0.88** | topo do encosto; default **0.85** |
| altura do assento (sentar) | **0.42–0.45** | topo da almofada de assento |
| espessura almofada assento | **0.14–0.18** | volume — NÃO < 0.12 |
| profundidade de assento (útil) | **0.55–0.60** | da frente à face do encosto |
| altura do braço | **0.58–0.66** | acima do assento ~0.15–0.20 |
| largura do braço | **0.18–0.28** | **largo** (caixotão tem braço fino) |
| espessura do encosto | **0.18–0.22** | almofada cheia |
| inclinação do encosto (rake) | **8–12°** | recline; default **10°** |
| recuo do plinto (frente) | **0.04–0.08** | base não-monolítica |
| altura do pé | **0.06–0.12** | **curto**; recuo do pé ~0.04–0.06 |
| raio de arredondamento (cantos verticais) | **0.03–0.05** | mata o "cubo" |
| raio do topo (almofada) | **0.02–0.04** | borda macia + coroa |
| raio do vivo (piping) | **0.006–0.010** | costura fina |
| vinco entre almofadas (gap) | **0.01–0.02** | separa as peças |

**Por que 2 vs 3 almofadas de assento (escolha justificada):**
- **2 almofadas**: módulos mais largos (~0.90 cada num 2.20) → leitura "lounge/confortável",
  menos linhas, parece sofá de showroom. **Default do v1.**
- **3 almofadas**: 1 por lugar (~0.58 cada) → leitura mais "formal/clássica".
- Regra: assento e encosto **devem ter a mesma contagem** (alinhar os vincos).
  v1 usa **3 encostos + 2 assentos** só se justificado; o default coerente é
  **3+3** OU **2+2**. (v1: **3 encostos / 3 assentos** alinhados — pedido explícito.)

---

## 3. Ordem CORRETA de modelagem (não pular etapas)

1. **Caixa de referência (bbox)** — confirmar `W×D×H` e os planos (assento, braço, encosto).
2. **Pés** — 4 (ou 6) curtos e recuados, afilados; definem a altura do plinto.
3. **Base/plinto** — recuada na frente; é o que segura assentos.
4. **Braços** — rounded box largo; topo arredondado; vão do plinto até `arm_height`.
5. **Almofadas de assento** — rounded box **coroado** (volume), separadas por vinco.
6. **Almofadas de encosto** — rounded box coroado, **cisalhadas em Y** conforme sobem (rake).
7. **Piping/costura** — vivo fino na borda superior das almofadas (followme, guard-railed).
8. **Suavização** — `soft`+`smooth` só nas arestas CURVAS (cantos/coroa), nunca nos 90° reais.
9. **Materiais** — tecido (linho) nas almofadas/braços; estrutura mais escura na base; pés madeira/metal.
10. **Render de check** — front · 3/4 · top · side → `renders/check/`.

> Regra de marcenaria: **componente reutilizável** para peças repetidas (almofada, pé).
> `Make Unique` para variar; espelhar braço com escala −1.

---

## 4. Checklist PASS / WARN / FAIL

**FAIL (reprovam o asset):**
- Parece feito de **caixas** (cantos vivos 90° em tudo, zero arredondamento).
- Almofada **chapada** (sem volume/coroa), espessura < 0.12 m.
- Encosto **vertical** (rake 0°) ou inclinado pra frente.
- Braço **fino** (< 0.15 m) ou inexistente.
- Bloco único (peças fundidas) / peça solta flutuando.
- Pé alto/“perna de mesa”; base sem recuo (monolítica).
- bbox fora de 2.10–2.30 × 0.90–0.98 × 0.80–0.88.

**WARN (passa como asset, mas melhora):**
- Arredondamento tímido (raio < 0.03).
- Sem piping/costura.
- Coroa da almofada fraca.
- Materiais chapados sem variação de tom entre base/assento/encosto.

**PASS (asset):**
- Cantos verticais arredondados + topo das almofadas macio.
- Almofadas com **volume** visível (coroa) e vinco entre elas.
- Encosto inclinado 8–12°.
- Braços largos com topo arredondado.
- Pés curtos recuados; base recuada.
- Piping nas bordas; 3 tons (base escura / assento / encosto).
- Peças nomeadas (grupos/componentes); suavização só nas curvas.

---

## 5. Erros PROIBIDOS

- ❌ Usar caixa única / `add_box` cru sem arredondar nada.
- ❌ `soft`/`smooth` em **todas** as arestas (vira bolha sem definição) — só nas curvas.
- ❌ Inventar dimensão fora da tabela §2 sem justificar.
- ❌ Almofada como placa fina (sem espessura/coroa).
- ❌ Encosto sem rake, ou rake pra frente.
- ❌ Deixar `.skp` em `runs/` (scratch) — asset canônico é versionado.
- ❌ Geometria não-manifold / faces invertidas (normais pra dentro → render preto).
- ❌ Depender de asset baixado (3D Warehouse) — o alvo é referência, não dependência.

---

## 6. Prioridade máxima (ordem de impacto visual)

1. **Bordas arredondadas** (cantos verticais + topo) — maior salto anti-caixote.
2. **Almofadas com volume** (coroa/puff).
3. **Encosto inclinado** (8–12°).
4. **Costuras/piping**.
5. **Proporção realista** (tabela §2).
6. **Pés e base refinados** (curtos, recuados, afilados).

---

## 7. Contrato das primitivas (`scripts/sofa_primitives.rb`)

Unidade da API: **metros** (converte p/ polegadas internas do SU). Cada primitiva
desenha num `entities` passado (normalmente um grupo nomeado) e devolve o grupo.

- `rounded_box(ents, x0,y0,x1,y1,z0,z1, r:, top_bevel:, mat:)` — caixa com cantos
  verticais arredondados (raio `r`) + topo chanfrado/macio (`top_bevel`); suaviza curvas.
- `seat_cushion(ents, x0,y0,x1,y1,z0,z1, r:, crown:, mat:, piping:)` — rounded_box + topo
  **coroado** (volume) + piping opcional.
- `back_cushion(...)` — idem, p/ encosto (chamado já cisalhado pelo build → rake).
- `armrest(ents, x0,y0,x1,y1,z0,z1, r:, mat:)` — rounded box largo, topo bem arredondado.
- `leg(ents, cx,cy, top, z0,z1, taper:, mat:)` — pé curto afilado (frustum).
- `piping(ents, perimeter_pts_in, radius_m, mat:)` — vivo via followme (guard-railed).

Critério de saída do skill: o `build_sofa_3seat_v1.rb` roda no SU, gera os 4 renders,
e o resultado **deixa de parecer caixas** (checklist §4 = PASS), pronto pro veredito visual.
