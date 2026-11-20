"""Alias de compatibilidade (FP-062). O módulo foi movido para tools.sketchup.pipeline.variant_axes.

Importar este caminho devolve o MESMO objeto de módulo: atributos, monkeypatch e estado valem
nos dois nomes. Remover quando nenhum consumidor usar este caminho antigo.

`python -m tools.orchestration.variant_axes` roda o CLI real. Sem o encaminhamento abaixo o alias não executa nada e a
chamada sairia com código 0 em silêncio.
"""
import sys as _sys

if __name__ == "__main__":
    import runpy as _runpy

    _runpy.run_module("tools.sketchup.pipeline.variant_axes", run_name="__main__", alter_sys=True)
else:
    from tools.sketchup.pipeline import variant_axes as _impl

    _sys.modules[__name__] = _impl
