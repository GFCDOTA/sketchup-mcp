# Cache Keys — definição precisa por estágio

> Companheiro de [`cache_design.md`](cache_design.md). Define **a
> chave exata** de cada estágio do pipeline pra que dois implementadores
> diferentes cheguem na mesma chave.

## Formato geral

```
key = sha256(  serialize_inputs(stage)  )[:16]
filename = f"<key>.<ext>"
```

`serialize_inputs(stage)` é determinístico: dict com chaves
ordenadas, valores normalizados (floats com 6 casas, paths
relativos ao repo, etc.).

## 1. Raster (PDF page → bitmap)

| Component | Source |
|---|---|
| `pdf_sha256` | `sha256(pdf_bytes)` |
| `dpi` | rendering DPI (int, default depends on caller) |
| `page_idx` | int |
| `pypdfium2_version` | `pypdfium2.__version__` (binding stability) |

```python
key_inputs = {
    "stage": "raster",
    "pdf_sha256": sha256(pdf_bytes).hexdigest(),
    "dpi": dpi,
    "page_idx": page_idx,
    "pypdfium2_version": pypdfium2.__version__,
}
key = sha256(json.dumps(key_inputs, sort_keys=True).encode()).hexdigest()[:16]
path = f"runs/.cache/raster/{key}_dpi{dpi}_p{page_idx}.png"
```

**Output stored:** PNG bytes (raster da página).

## 2. Vector consensus (PDF → walls + soft_barriers)

| Component | Source |
|---|---|
| `pdf_sha256` | hash do PDF |
| `params_dict` | thresholds e configs do `build_vector_consensus.py` |
| `code_sha256` | `sha256(build_vector_consensus.py source bytes)` |

```python
key_inputs = {
    "stage": "vector_consensus",
    "pdf_sha256": sha256(pdf_bytes).hexdigest(),
    "params": serialize_params({
        "wall_thickness_min": ...,
        "wall_thickness_max": ...,
        # outros params expostos pela CLI
    }),
    "code_sha256": sha256(read_file("tools/build_vector_consensus.py")).hexdigest(),
}
```

**Output stored:** consensus_model.json (sem rooms, sem openings ainda).

**Por que `code_sha256`:** se alguém arrumar bug no extractor sem
mudar params, queremos invalidar cache automaticamente.

**Invalidação automática esperada:** qualquer commit em
`tools/build_vector_consensus.py` invalida tudo desse estágio.

## 3. Room labels (PDF → labels.json)

| Component | Source |
|---|---|
| `pdf_sha256` | hash |
| `code_sha256` | `extract_room_labels.py` |

Sem params relevantes hoje (script puro). Cache simples.

```python
key_inputs = {
    "stage": "room_labels",
    "pdf_sha256": sha256(pdf_bytes).hexdigest(),
    "code_sha256": sha256(read_file("tools/extract_room_labels.py")).hexdigest(),
}
```

**Output stored:** labels.json.

## 4. Rooms from seeds (walls + labels → rooms)

| Component | Source |
|---|---|
| `walls_sha256` | hash das walls extraídas (sub-set do consensus_model.json) |
| `labels_sha256` | hash do labels.json |
| `params_dict` | flood-fill params (tolerância, max_iters, etc.) |
| `code_sha256` | `rooms_from_seeds.py` |

```python
key_inputs = {
    "stage": "rooms_from_seeds",
    "walls_sha256": sha256_of_walls_subset(consensus_dict),
    "labels_sha256": sha256(labels_json_bytes).hexdigest(),
    "params": serialize_params(flood_fill_params),
    "code_sha256": sha256(read_file("tools/rooms_from_seeds.py")).hexdigest(),
}
```

**Por que hashear walls** (não o consensus inteiro): rooms depende
só de walls. Se openings mudou (mas walls não), rooms não invalida.

**Output stored:** rooms array (atualizado dentro do consensus_model.json).

## 5. Openings vector (PDF + walls → openings)

| Component | Source |
|---|---|
| `pdf_sha256` | hash |
| `walls_sha256` | hash das walls |
| `params_dict` | confidence threshold, modo (replace/append) |
| `code_sha256` | `extract_openings_vector.py` |

```python
key_inputs = {
    "stage": "openings_vector",
    "pdf_sha256": sha256(pdf_bytes).hexdigest(),
    "walls_sha256": sha256_of_walls_subset(consensus_dict),
    "params": serialize_params({"mode": mode, "min_confidence": ...}),
    "code_sha256": sha256(read_file("tools/extract_openings_vector.py")).hexdigest(),
}
```

**Output stored:** openings array.

## 6. Render axon (consensus → PNG)

| Component | Source |
|---|---|
| `consensus_sha256` | hash do consensus_model.json **inteiro** |
| `view_mode` | "top", "axon", "frontal" |
| `view_params` | dict de elev/azim/zoom/fontsize/color_palette |
| `code_sha256` | `render_axon.py` |

```python
key_inputs = {
    "stage": "render_axon",
    "consensus_sha256": sha256(consensus_json_bytes).hexdigest(),
    "view_mode": view_mode,
    "view_params": serialize_params(view_params),
    "code_sha256": sha256(read_file("tools/render_axon.py")).hexdigest(),
}
```

**Output stored:** PNG bytes.

**Por que consensus inteiro** (não subset): render usa walls + rooms +
openings + soft_barriers. Conservador hashear tudo.

## 7. SketchUp export (consensus → .skp)

| Component | Source |
|---|---|
| `consensus_sha256` | hash do consensus_model.json |
| `rb_sha256` | `sha256(consume_consensus.rb)` (o consumer Ruby) |
| `su_version` | "2026.0.490" (varia por instalação) |
| `params_dict` | `WALL_HEIGHT_M`, `PARAPET_HEIGHT_M`, `PARAPET_RGB`, `WALL_FILL_RGB`, `ROOM_PALETTE`, tolerância do filtro de parapets |

```python
key_inputs = {
    "stage": "sketchup_export",
    "consensus_sha256": sha256(consensus_json_bytes).hexdigest(),
    "rb_sha256": sha256(read_file("tools/consume_consensus.rb")).hexdigest(),
    "su_version": detected_su_version,
    "params": serialize_params({
        "wall_height_m": WALL_HEIGHT_M,
        "parapet_height_m": PARAPET_HEIGHT_M,
        "parapet_rgb": PARAPET_RGB,
        "wall_fill_rgb": WALL_FILL_RGB,
        "room_palette": ROOM_PALETTE,
        "parapet_tol_in": _segment_overlaps_wall_tol_in,
    }),
}
```

**Output stored:** .skp file (binário, ~250 KB).

**Cuidado:** `rb_sha256` invalida se alguém alterar `consume_consensus.rb`.
Crítico — esse é o consumer; mudança de constante muda o output 3D.

## 8. Validator scoring (PNG + scorer → score)

| Component | Source |
|---|---|
| `png_sha256` | hash do PNG validado |
| `scorer_sha256` | hash do `scorers/<kind>.py` específico |
| `vision_enabled` | bool — se Ollama foi usado |
| `vision_model_version` | string da versão do modelo (e.g. "qwen2.5vl:7b") |

```python
key_inputs = {
    "stage": f"validator_{kind}",
    "png_sha256": sha256(png_bytes).hexdigest(),
    "scorer_sha256": sha256(read_file(f"validator/scorers/{kind}.py")).hexdigest(),
    "vision_enabled": vision_enabled,
    "vision_model_version": vision_model_version if vision_enabled else None,
}
```

**Output stored:** dict com `score, verdict, findings, vision_critique`.

## Helpers compartilhados (não implementar agora — só especificar)

```python
def serialize_params(d: dict) -> str:
    """Determinístico — para floats, 6 casas; ordena chaves recursivamente."""
    def normalize(v):
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, dict):
            return {k: normalize(v[k]) for k in sorted(v)}
        if isinstance(v, list):
            return [normalize(x) for x in v]
        return v
    return json.dumps(normalize(d), sort_keys=True, separators=(",", ":"))


def sha256_of_walls_subset(consensus: dict) -> str:
    """Hash apenas dos walls do consensus, ignorando rooms/openings."""
    walls = sorted(consensus.get("walls", []), key=lambda w: w.get("id", ""))
    return sha256(json.dumps(walls, sort_keys=True).encode()).hexdigest()


def code_sha256(relative_path: str) -> str:
    """Hash do source file relative ao repo root. Inclui no key
    pra invalidar cache quando o estágio muda."""
    full_path = REPO_ROOT / relative_path
    return sha256(full_path.read_bytes()).hexdigest()
```

## Edge cases conhecidos

### Multi-page PDFs
Hoje pipeline assume 1 page. Quando suportar N pages, key precisa
de `page_idx` (já incluído no estágio raster).

### Encoding diferences
JSON serializado deve usar `ensure_ascii=False` ou `ensure_ascii=True`
**consistentemente**. Default Python é True; manter.

### Float precision drift
Floats em consensus_model.json podem ter representação ligeiramente
diferente entre Python builds (extremamente raro, mas possível). Pra
robustez, `serialize_params` arredonda floats em 6 casas. Hash de
JSON inteiro NÃO arredonda — usa bytes literais.

### Compressão dos artefatos
PNGs e .skp já comprimidos. JSONs não. Pra economizar disk, opcional
gzip com `.json.gz` extension (não impacta key — extensão ≠ key).

## Convenções de nomenclatura final

| Stage | Path template | Ext |
|---|---|---|
| raster | `runs/.cache/raster/{key}_dpi{N}_p{idx}.png` | png |
| vector_consensus | `runs/.cache/vector_consensus/{key}.json` | json |
| room_labels | `runs/.cache/room_labels/{key}.json` | json |
| rooms_from_seeds | `runs/.cache/rooms_from_seeds/{key}.json` | json |
| openings_vector | `runs/.cache/openings_vector/{key}.json` | json |
| render_axon | `runs/.cache/render_axon/{key}_{mode}.png` | png |
| sketchup_export | `runs/.cache/sketchup_export/{key}.skp` | skp |
| validator | `runs/.cache/validator/{key}.json` | json |

Sufixos legíveis (`_dpi{N}_p{idx}`, `_{mode}`) ajudam debug humano —
não fazem parte da key, são só anotação no nome do arquivo.

## Cache index

`runs/.cache/_meta/cache_index.jsonl` (append-only):

```jsonl
{"ts":"2026-05-02T19:00:00Z","stage":"raster","key":"abc123def456","status":"miss","compute_s":2.41,"output_bytes":1024000,"caller":"main.py extract"}
```

Permite computar:
- hit rate por estágio
- avg compute time por miss
- avg load time por hit
- top 10 keys por uso
- staleness (last_seen vs now)
