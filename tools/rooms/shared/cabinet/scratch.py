"""scratch_dir — onde os jobs de INSPECAO do gabinete e da porta Shaker gravam params/resultado/copia (R3 / T0.2, #460).

Regra unica para os dois inspects (antes duplicada no Shaker e ausente no gabinete): o scratch nasce AO LADO do .skp inspecionado so quando o destino
e permitido; se o .skp estiver em `artifacts/` ou `fixtures/` (protegidos), o `output_policy` recusa e o scratch vai para `runs/`. Assim inspecionar
um .skp canonico nunca deixa lixo ao lado dele (achado do L2 da P4 do Shaker, repetido no gabinete)."""
from __future__ import annotations

from pathlib import Path

from tools.sketchup import paths


def scratch_dir(src: Path, label: str, adjacent_suffix: str | None = None) -> Path:
    """`label`: nome do job (pasta em `runs/`); `adjacent_suffix`: sufixo da pasta ao lado quando permitido (padrao = `label`)."""
    side = f"_{src.stem}_{adjacent_suffix or label}"
    try:
        return paths.check_output(src.parent / side / "_probe").parent
    except paths.OutputPathRefused:
        return paths.default_out_dir(label) / src.stem
