"""L2 driver (FP-062): roda furnish_apartment.main() de UMA arvore, sem tocar nada do repositorio.

Uso: python run_furnish.py <tree> <out_dir> <gallery_root> <base_skp> <module_name>
- o corpus de galeria e redirecionado para <gallery_root> (nao escreve no corpus real do workspace);
- o .skp base e uma COPIA (FURNISH_BASE_SKP), nunca o artifacts/ original;
- a saida vai para <out_dir>.
"""
import importlib
import os
import sys
from pathlib import Path

tree, out_dir, gallery_root, base_skp, module_name = (
    Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5],
)
sys.path.insert(0, str(tree))
os.chdir(tree)
os.environ["FURNISH_BASE_SKP"] = str(base_skp)
mod = importlib.import_module(module_name)
assert Path(mod.__file__).resolve().is_relative_to(tree.resolve()), (mod.__file__, tree)
print("[l2] module:", mod.__file__)
print("[l2] ROOT:", mod.ROOT, "BASE_SKP:", mod.BASE_SKP)
mod.GALLERY_CORPUS_ROOT = gallery_root
mod.main(["--out-dir", str(out_dir)])
