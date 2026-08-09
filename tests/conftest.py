"""conftest.py — roda ANTES de qualquer coleta/import de teste.

planta_74 tem escala verificada por cota (PT_TO_M=0.0259), diferente do
default de `core.scale` (ancoragem por wall-thickness, ~0.0352). Setar aqui,
no ponto mais cedo possível do processo pytest, garante que NENHUM módulo de
teste consiga importar `core.scale` (direto ou em cascata via
tools.spatial_model/bathroom_layout/bedroom_layout/kitchen_layout/
layout_candidates) antes do env estar correto — independe da ordem de coleta
dos arquivos. Ver core/scale.py::assert_pt_to_m_for_source (guard fail-fast
que pega exatamente este footgun).
"""
import os

os.environ.setdefault("PT_TO_M", "0.0259")
