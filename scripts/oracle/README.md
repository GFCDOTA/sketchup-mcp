# Oráculos do plan-extract-v2

Esta pasta contém **dois oráculos de tempo de desenvolvimento** usados para
diagnosticar runs do pipeline `plan-extract-v2`. Eles produzem segundas
opiniões sobre o que está saindo errado em `observed_model.json` (slivers,
walls fragmentadas, openings mal hospedados, etc.) e nada mais.

> **Invariante (CLAUDE.md §6, vendor README §1):** estes scripts NUNCA são
> importados por `main.py` ou por qualquer service do pipeline. Eles vivem
> em `scripts/oracle/` exatamente porque sua saída é informativa, não
> autoritativa. Use-os para decidir quais patches (`patches/01..09`)
> aplicar; não plug-them no fluxo de produção.

---

## 1. Os dois oráculos

| Aspecto         | `llm_architect.py` (LLM)             | `cubicasa.py` (DL)                          |
|-----------------|--------------------------------------|---------------------------------------------|
| O que faz       | Diagnostica defeitos no overlay      | Re-extrai walls/rooms/openings do PDF       |
| Modelo          | Claude Vision (`claude-opus-4-7`)    | Hourglass `hg_furukawa_original` (CC BY-NC) |
| Entrada         | `<run>/overlay_*.png` + `observed_model.json` | PDF cru                            |
| Saída           | `oracle_diagnosis_llm.json`          | `cubicasa_observed.json` (mesmo schema da pipeline) |
| Custo           | Pago por chamada (Anthropic API)     | Grátis após download                        |
| Latência típica | 10-30 s                              | 5-15 s CPU, 0.2-2 s GPU                     |
| Dependências    | `anthropic`, `jsonschema`, Pillow    | `torch`, `torchvision`, `cv2`, `gdown`, repo+weights vendorizados |
| Offline         | Não                                  | Sim (após bootstrap)                        |
| Licença         | Termos da Anthropic API              | **CC BY-NC 4.0** (não-comercial)            |

Resumo rápido:
- **LLM** = "olha pra figura, me diz o que tá quebrado e por quê".
- **CubiCasa** = "esquece a sua pipeline, eu re-extraio do zero".

---

## 2. Setup

### Fase 1 — LLM architect

```
pip install -r requirements.txt
```

Garanta que `ANTHROPIC_API_KEY` está exportada (ou em `.env` carregado pelo
seu shell). O script falha cedo (`exit 3`) se a variável não estiver no
ambiente.

```
export ANTHROPIC_API_KEY=sk-ant-...
```

PIL é opcional (usado para reduzir overlays > 1024 px no maior lado antes
de mandar). Sem PIL, o script envia o PNG cru.

### Fase 2 — CubiCasa5K

```
python scripts/oracle/cubicasa_download.py
```

Esse comando, idempotente:

1. Clona `https://github.com/CubiCasa/CubiCasa5k` → `vendor/CubiCasa5k/repo/`
2. Baixa `model_best_val_loss_var.pkl` (~96 MB) via `gdown` → `vendor/CubiCasa5k/weights/`
3. Valida tamanho (50-200 MB) e imprime SHA256 (CubiCasa não publica hash
   canônico — o primeiro download bom é seu pin).

Use `--force` para re-clonar/re-baixar do zero.

Custo total em disco: **~600 MB** (5 MB repo + 96 MB weights + ~500 MB
torch/torchvision no seu env Python).

```
pip install torch torchvision         # CPU. ~500 MB.
# ou para CUDA 12.1:
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> **Atenção licença.** Os pesos e o código clonado estão sob CC BY-NC 4.0.
> Use só em desenvolvimento. NÃO ship a saída deste oráculo dentro de um
> produto comercial sem permissão explícita da CubiCasa.

---

## 3. Uso

### LLM architect

```
python scripts/oracle/llm_architect.py --run runs/openings_refine_final
python scripts/oracle/llm_architect.py --run runs/foo --out diag.json --model claude-sonnet-4-6
```

Procura `overlay_audited.png` primeiro, cai para `overlay_0.png`, lê
`observed_model.json` ao lado. Sai com:
- `2` se faltar arquivo (overlay, observed_model, schema)
- `3` se `ANTHROPIC_API_KEY` não estiver no ambiente
- `0` em sucesso

Saída padrão: `<run>/oracle_diagnosis_llm.json`.

### CubiCasa

```
python scripts/oracle/cubicasa.py --pdf planta_74.pdf --out runs/cubicasa_p74
python scripts/oracle/cubicasa.py --pdf X.pdf --out runs/Y --raster-size 1024
python scripts/oracle/cubicasa.py --pdf X.pdf --out runs/Y --device cuda
```

Defaults: `--raster-size 512`, `--device cpu`. O script rasteriza a
primeira página do PDF via `ingest.ingest_pdf` (mesmo path do pipeline)
para garantir consistência. Sai com:
- `2` se faltar setup (weights, repo) ou input
- `3` se a saída violar o schema (escreve `cubicasa_observed.invalid.json` mesmo assim)
- `0` em sucesso

Saída válida: `<out>/cubicasa_observed.json`.

---

## 4. Formato de saída

### `oracle_diagnosis_llm.json`

Validado contra `scripts/oracle/diagnosis_schema.json` antes de escrever.

```
{
  "run_id": "openings_refine_final",
  "summary": "Model is roughly 1.6x inflated. Most damage is along the left wing where Hough fragmentation produced 3 collinear stubs that polygonize closed into two slivers.",
  "defects": [
    {
      "element_id": "room-12",
      "element_type": "room",
      "defect_kind": "sliver_room",
      "severity": "high",
      "hypothesis": "snap_tolerance left a 30px gap between wall-83 and wall-84; polygonize closed it as a triangle of area ~0.3 m^2.",
      "suggested_fix": "drop rooms with area < 0.4 m^2 OR aspect_ratio > 8 in classify/service.py."
    },
    {
      "element_id": "wall-83",
      "element_type": "wall",
      "defect_kind": "fragmented_wall",
      "severity": "medium",
      "hypothesis": "HoughLinesP(maxLineGap=40) split a single architectural wall into 3 collinear segments.",
      "suggested_fix": "merge collinear walls within 10px gap as part of patch 09 (AFPlan multi-scale)."
    }
  ]
}
```

`defect_kind` enum: `sliver_room`, `thin_strip_room`, `triangle_room`,
`wedge_room`, `fragmented_wall`, `duplicate_wall`, `stub_wall`,
`opening_no_host`, `opening_in_corner`, `opening_on_sliver`,
`global_topology`, `global_inflation`, `other`.

`severity` enum: `high` | `medium` | `low`.

### `cubicasa_observed.json`

Mesmo schema da pipeline (`docs/schema/observed_model.schema.json`,
`schema_version: 2.2.0`), mas com IDs prefixados `cubicasa-` para evitar
colisão.

```
{
  "schema_version": "2.2.0",
  "run_id": "<uuid4-hex>",
  "source": {"filename": "planta_74.pdf", "source_type": "raster", "page_count": 1, "sha256": "..."},
  "walls": [
    {
      "wall_id": "cubicasa-wall-1",
      "parent_wall_id": "cubicasa-wall-1",
      "page_index": 0,
      "start": [120.0, 80.5],
      "end": [120.0, 410.0],
      "thickness": 4.0,
      "orientation": "vertical",
      "source": "cubicasa",
      "confidence": 0.95
    }
  ],
  "junctions": [{"junction_id": "cubicasa-j-1", "point": [120.0, 80.5], "degree": 2, "kind": "pass_through"}],
  "rooms": [{"room_id": "cubicasa-room-1", "polygon": [[...]], "area": 1234.5, "centroid": [200.0, 240.0]}],
  "openings": [
    {
      "opening_id": "cubicasa-opening-1",
      "page_index": 0,
      "orientation": "horizontal",
      "center": [200.0, 215.0],
      "width": 46.0,
      "wall_a": "",
      "wall_b": "",
      "kind": "door"
    }
  ],
  "scores": {"geometry": 1.0, "topology": 0.71, "rooms": 0.83},
  "warnings": ["dl_oracle"]
}
```

`wall_a`/`wall_b` ficam `""` porque a CubiCasa entrega segmentação, não
topologia: não dá para amarrar cada opening a duas walls específicas.

---

## 5. O que fazer com a saída

Os dois oráculos são **pistas, não verdades**. O fluxo de comparação
costuma ser:

1. **LLM diz onde dói**, com vocabulário do projeto:
   *"room-12 é um sliver, hipótese: snap_tolerance deixou um gap que o
   polygonize fechou como triângulo. Fix sugerido: filtrar rooms com area
   < 0.4 m² ou aspect_ratio > 8."*
2. **CubiCasa diz quanta inflação tem**, sem opinião:
   *"Eu vejo 14 rooms aqui; você tem 23 → over-polygonização de ~64%."*
3. **Você decide o que aplicar.** Combine os dois sinais para escolher
   entre os patches existentes:
   - Discrepância grande em rooms + LLM apontando slivers → patch
     `01..04` (higiene de classify) ou patch `09` (topologia).
   - LLM apontando `fragmented_wall` em série → patch `07` (LSD real) ou
     `09` (CCA multi-scale).
   - LLM apontando `opening_no_host` → patch `06` (openings L3).

Nunca aceite a saída cega:
- O LLM pode alucinar IDs que não existem (ele tenta puxar do recap, mas
  erra). O script valida que o JSON bate com o schema; ele não verifica
  que `room-12` realmente existe em `observed_model.json`.
- A CubiCasa foi treinada em plantas residenciais finlandesas e pode
  classificar errado plantas brasileiras com hachura densa ou cotas
  excessivas. Compare visualmente com `debug_walls.svg` antes de tirar
  conclusão.

A regra é a mesma do CLAUDE.md §6: medir baseline antes/depois, inspecionar
visualmente, **não substituir uma observação real por uma do oráculo**.

---

## 6. Limitações

### LLM architect
- Custa por chamada (Anthropic API). Rodar em todos os runs de regressão
  fica caro rapidamente.
- 100% online. Sem internet → sem diagnóstico.
- Qualidade da resposta depende do modelo escolhido. `claude-opus-4-7` é
  o default; `claude-sonnet-4-6` é mais barato e funciona, mas erra mais
  IDs.
- Imagem é redimensionada para 1024 px no maior lado. Detalhes minúsculos
  (slivers de 1-2 px) podem sumir.
- Não é determinístico — a mesma run pode dar diagnósticos diferentes em
  duas chamadas.

### CubiCasa
- **CC BY-NC 4.0.** Uso comercial proibido sem licença explícita.
- ~96 MB de weights + ~500 MB de torch — não é leve.
- Sem `wall_a`/`wall_b` em openings (limitação arquitetural do modelo).
- Treinado em plantas residenciais; performance degrada em comerciais
  grandes, plantas com hachura densa, plantas muito pequenas (<200 px) ou
  muito grandes (>4000 px).
- Não publica SHA256 canônico — o primeiro download é seu pin (gravado
  pelo `cubicasa_download.py`).
- Snap simplificado (segmentos via Hough na máscara de heatmap). Walls
  diagonais reais saem como degraus axis-aligned.

---

## 7. Troubleshooting

### LLM architect

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| `ANTHROPIC_API_KEY is not set` (`exit 3`) | Variável fora do ambiente | `export ANTHROPIC_API_KEY=...` ou carregar `.env` antes |
| `no overlay PNG in <run>` | Run não terminou ou debug artifacts faltando | Rodar `main.py extract` até o fim; conferir invariante 5 |
| `Claude did not return a tool_use block` | Modelo cortou no token limit | Aumentar `max_tokens` em `call_claude` ou trocar para `claude-opus-4-7` |
| `failed to read/resize <path>` | PNG corrompido / Pillow ausente | Re-renderizar overlay; instalar Pillow |
| `tool response failed schema validation` | Modelo divergiu do schema | Conferir `diagnosis_schema.json`; reportar com o JSON inválido |

### CubiCasa

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| `setup error: ... weights not found` | Bootstrap não rodado | `python scripts/oracle/cubicasa_download.py` |
| `gdown failed (exit ...)` | Google Drive rate-limit | Baixar manualmente em https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK e mover para `vendor/CubiCasa5k/weights/` |
| `ImportError: cannot import floortrans.models` | Repo não clonado ou layout mudou | Re-rodar bootstrap com `--force` |
| `MISSING state_dict keys` (verbose) | torch/torchvision incompatível com checkpoint | Pinar `torch==2.2.*` ou similar; reportar lista verbatim |
| `torch.load` falha com pickle error | torch novo com `weights_only=True` default | Já tratado: o script passa `weights_only=False` |
| 0 walls / 0 rooms / 0 openings | Raster pequeno demais ou plant fora-distribuição | Subir `--raster-size` para 1024; conferir `runs/<out>/` |
| `SCHEMA VIOLATION` (`exit 3`) | Saída malformada (bug do oráculo) | Inspecionar `cubicasa_observed.invalid.json`; abrir issue |
| CUDA OOM em GPU | Raster grande + GPU pequena | `--device cpu` ou `--raster-size 512` |

---

## 8. Licença

| Componente | Licença |
|---|---|
| `llm_architect.py`, `diagnosis_schema.json` | Sem restrição além dos termos da Anthropic API |
| `cubicasa.py`, `cubicasa_download.py` | Código deste projeto |
| Weights `model_best_val_loss_var.pkl` + repo `vendor/CubiCasa5k/repo/` | **CC BY-NC 4.0** (https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE) |

A saída do `cubicasa.py` (que deriva dos pesos) **herda** a restrição
não-comercial. A saída do `llm_architect.py` é regida pelos termos da
Anthropic API.

Em caso de dúvida licenciária, leia `vendor/CubiCasa5k/README.md` §2.
