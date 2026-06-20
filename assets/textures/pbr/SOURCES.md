# Texturas PBR — fontes

Todas **CC0** (domínio público, uso livre inclusive comercial) do **Poly Haven**
(https://polyhaven.com). Baixadas em 1k JPG (diffuse) via API pública.

| arquivo | asset Poly Haven | uso no pipeline |
|---|---|---|
| `pbr_concrete.jpg` | `concrete` (board-formed) | parede de concreto da TV (`concrete.png`) |
| `pbr_wood_floor.jpg` | `wood_floor` | piso de madeira + móveis (`wood_floor/medium/dark.png`) |
| `pbr_wood_furniture.jpg` | `brown_planks_03` | (reserva — madeira cinza envelhecida) |
| `pbr_fabric.jpg` | `cotton_jersey` | sofá charcoal (escurecido → `fabric_charcoal.png`) |
| `pbr_granite.jpg` | `granite_tile_03` | piso de área molhada (`porcelain.png`) |

Aplicadas via `tools/gen_textures.py::_apply_pbr_overrides` (sobrepõe o procedural quando
o JPG existe; procedural continua sendo o fallback). Licença CC0 permite redistribuir.
