"""FP-043/P1 — a documentação de navegação é íntegra e não declara o que não existe.

Prova links, o estado `existe`/`previsto` dos caminhos e as cinco rotas de descoberta (README → índice em até
3 cliques, símbolos reais). Não prova que o conteúdo é o melhor: prova que ele aponta para o que há.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.navigation.docs_check import (
    ROUTES_PATH,
    check_links,
    check_routes,
    check_states,
    doc_files,
    links_of,
    state_rows,
)

ROOT = Path(__file__).resolve().parents[1]


def test_documentacao_real_sem_link_quebrado_nem_estado_errado():
    files = doc_files(ROOT)
    assert {f.name for f in files} >= {"README.md", "repository_map.md", "migration_guide.md"}
    assert check_links(files) == []
    assert check_states(files, ROOT) == []


def test_rotas_de_navegacao_passam():
    doc = json.loads((ROOT / ROUTES_PATH).read_text(encoding="utf-8"))
    assert check_routes(doc, ROOT) == []
    ids = {r["id"] for r in doc["routes"]}
    assert ids == {"kitchen-planner-and-sink-rule", "shared-cabinet-builder", "shaker-door-recipe",
                   "kitchen-test-and-l2-evidence", "mcp-to-skp", "kitchen-specialist-and-catalog", "specialists-all-rooms", "kitchen-vertical-trace"}
    assert all(len(r["hops"]) - 1 <= 3 for r in doc["routes"])


def test_shaker_existe_no_codigo_mas_continua_nao_promovida():
    """FP-046/P4: o codigo da Shaker existe (P1-P4), mas a promocao ao catalogo segue bloqueada (D46-09). A rota diz as duas coisas."""
    doc = json.loads((ROOT / ROUTES_PATH).read_text(encoding="utf-8"))
    route = next(r for r in doc["routes"] if r["id"] == "shaker-door-recipe")
    assert not route.get("absent")
    paths = {a["path"] for a in route["answers"]}
    assert {"tools/rooms/kitchen/capabilities/shaker.py", "tools/rooms/shared/cabinet/shaker/plan.py"} <= paths
    assert all((ROOT / p).exists() for p in paths)
    readme = (ROOT / "tools/rooms/kitchen/README.md").read_text(encoding="utf-8")
    assert "BLOCKED_CAPABILITY_MISSING" in readme and "NÃO está promovida" in readme and "D46-09" in readme
    catalog = json.loads((ROOT / "tools/rooms/capability_catalog.v1.json").read_text(encoding="utf-8"))
    assert next(b for b in catalog["bindings"] if b["id"] == "bind.kitchen.shaker")["capability_id"] is None


def test_readme_raiz_nao_repete_afirmacoes_desatualizadas():
    texto = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "85 " not in texto.split("Testes")[1].split("\n")[0]          # contagem fixa de suites
    assert "Servidor MCP | sim" in texto
    assert "removido" in texto and ":8765" in texto                      # cockpit citado só como removido
    assert "not a Model-Context-Protocol" not in texto
    assert "docs/architecture/repository_map.md" in texto


def test_cli_roda_e_passa():
    r = subprocess.run([sys.executable, "-m", "tools.navigation.docs_check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ negativos (árvore sintética)
def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return tmp_path


def test_link_quebrado_e_link_em_codigo_ou_externo(tmp_path):
    root = _tree(tmp_path, {
        "a.md": "[ok](b.md) [x](nao_existe.md) [web](https://x.dev/y) [anc](#ancora) `[c](fantasma.md)`\n"
                "```\n[d](fantasma2.md)\n```\n",
        "b.md": "ok\n",
    })
    assert links_of(root / "a.md") == ["b.md", "nao_existe.md"]
    assert check_links([root / "a.md"]) == ["a.md: nao_existe.md"]


def test_estado_existe_exige_presente_e_previsto_exige_ausente(tmp_path):
    root = _tree(tmp_path, {
        "docs/m.md": "| Caminho | Estado | X |\n|---|---|---|\n"
                     "| `core/` | existe | a |\n| `fantasma/` | existe | b |\n"
                     "| `tools/novo/` | previsto | c |\n| `core/ja_nasceu.py` | previsto | d |\n"
                     "| `texto` | outra coisa | e |\n",
        "core/ja_nasceu.py": "",
    })
    assert state_rows(root / "docs/m.md") == [("core/", "existe"), ("fantasma/", "existe"),
                                              ("tools/novo/", "previsto"), ("core/ja_nasceu.py", "previsto")]
    erros = check_states([root / "docs/m.md"], root)
    assert erros == ["m.md: `fantasma/` declarado 'existe' mas ausente",
                     "m.md: `core/ja_nasceu.py` declarado 'previsto' mas já existe (atualize o estado)"]


def _routes_tree(tmp_path: Path):
    return _tree(tmp_path, {
        "README.md": "[mapa](docs/mapa.md)\n",
        "docs/mapa.md": "[idx](../mod/README.md)\n",
        "mod/README.md": "veja `mod/codigo.py` e [teste](../t/test_x.py); `mod/futuro/` ainda não existe\n",
        "mod/codigo.py": "def planner():\n    pass\n\nSINK = 1\n",
        "t/test_x.py": "def test_x():\n    pass\n",
    })


def _rota(**kw):
    base = {"id": "r", "hops": ["README.md", "docs/mapa.md", "mod/README.md"],
            "answers": [{"path": "mod/codigo.py", "symbol": "planner"}, {"path": "t/test_x.py", "symbol": "test_x"}]}
    base.update(kw)
    return {"schema_version": "fp043_navigation_routes.v1", "start": "README.md", "routes": [base]}


def test_rota_valida_e_cada_falha_e_detectada(tmp_path):
    root = _routes_tree(tmp_path)
    assert check_routes(_rota(), root) == []
    assert check_routes(_rota(answers=[{"path": "mod/codigo.py", "symbol": "SINK"}]), root) == []
    assert any("símbolo nada ausente" in e for e in check_routes(
        _rota(answers=[{"path": "mod/codigo.py", "symbol": "nada"}]), root))
    assert any("inexistente" in e for e in check_routes(_rota(answers=[{"path": "mod/sumiu.py"}]), root))
    assert any("não tem link" in e for e in check_routes(_rota(hops=["README.md", "mod/README.md"]), root))
    assert any("deve partir" in e for e in check_routes(_rota(hops=["docs/mapa.md", "mod/README.md"]), root))
    quatro = ["README.md", "docs/mapa.md", "mod/README.md", "mod/README.md", "mod/README.md"]
    assert any("cliques" in e for e in check_routes(_rota(hops=quatro), root))
    # resposta existe mas o índice não a cita
    (root / "mod/outro.py").write_text("def x():\n    pass\n", encoding="utf-8")
    assert any("não cita" in e for e in check_routes(_rota(answers=[{"path": "mod/outro.py", "symbol": "x"}]), root))


def test_ausencia_declarada_exige_explicacao_e_caminho_continuar_ausente(tmp_path):
    root = _routes_tree(tmp_path)
    ok = _rota(answers=[], absent=[{"path": "mod/futuro", "why": "previsto"}])
    assert check_routes(ok, root) == []
    (root / "mod/futuro").mkdir()
    assert any("existe (atualize a rota)" in e for e in check_routes(ok, root))
    sem_texto = _rota(answers=[], absent=[{"path": "mod/outra", "why": "previsto"}])
    assert any("não explica a ausência" in e for e in check_routes(sem_texto, root))


@pytest.mark.parametrize("doc", [{}, {"schema_version": "x", "routes": []}])
def test_schema_invalido(doc):
    assert check_routes(doc) == ["INVALID_SCHEMA"]
