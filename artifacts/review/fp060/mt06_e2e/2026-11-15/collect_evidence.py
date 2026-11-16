"""FP-060 MT-06: invólucro do coletor da evidencia E2E. A logica e os testes ficam em `tools/validation/fp060_e2e_evidence.py` (o sandbox de testes do revisor
nao copia `artifacts/`). Uso: collect_evidence.py <diretorio novo de saida> <fluxo>=<PR>:<Issue>:<store.db> [...]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))                 # raiz do repositorio
from tools.validation.fp060_e2e_evidence import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
