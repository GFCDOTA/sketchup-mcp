"""FP-043/P0 — o mapa de reorganização cobre exatamente o escopo e o gate é fail-closed.

Não prova que as migrações são seguras (cada PR de movimento revisa seus consumidores); prova que
nada na raiz/tools/scripts/ops/interior fica sem destino ou retenção justificada, e que o mapa
não aponta para o vazio.
"""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path

import pytest

from tools.navigation.consumers import Corpus, scope_items, tracked_files
from tools.navigation.p0_map import check, load, summary

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tracked():
    return tracked_files(ROOT)


@pytest.fixture(scope="module")
def doc():
    return load()


def test_mapa_cobre_exatamente_o_escopo_atual(doc, tracked):
    res = check(doc, tracked)
    assert res["result"] == "PASS", res["errors"]


def test_raiz_e_tools_inteiros_estao_no_escopo(tracked):
    items = set(scope_items(tracked))
    assert {"README.md", "pyproject.toml", "CLAUDE.md", "tools/furnish_apartment.py", "tools/rooms/",
            "scripts/sofa_generator.rb", "interior/validators/", "ops/estudio-front/"} <= items
    assert not any(i.startswith("tests/") or i.startswith("docs/") for i in items)


def test_item_faltando_e_item_inexistente_falham(doc, tracked):
    faltando = copy.deepcopy(doc)
    faltando["items"] = [r for r in faltando["items"] if r["item"] != "tools/furnish_apartment.py"]
    assert check(faltando, tracked)["errors"]["MISSING_ITEMS"] == ["tools/furnish_apartment.py"]

    sobrando = copy.deepcopy(doc)
    fantasma = dict(sobrando["items"][0], item="tools/nao_existe.py")
    sobrando["items"].append(fantasma)
    assert check(sobrando, tracked)["errors"]["STALE_ITEMS"] == ["tools/nao_existe.py"]


@pytest.mark.parametrize("mutacao,codigo", [
    (lambda r: r.update(disposition="talvez"), "INVALID_DISPOSITION"),
    (lambda r: r.update(phase="P99"), "INVALID_PHASE"),
    (lambda r: r.update(risk="enorme"), "INVALID_RISK"),
    (lambda r: r.update(rationale="curto"), "MISSING_RATIONALE"),
])
def test_registro_invalido_falha(doc, tracked, mutacao, codigo):
    ruim = copy.deepcopy(doc)
    mutacao(next(r for r in ruim["items"] if r["item"] == "tools/geometry_sanity.py"))
    assert "tools/geometry_sanity.py" in check(ruim, tracked)["errors"][codigo]


def test_move_exige_destino_e_compat_decisao_exige_pergunta_fachada_exige_canonico(doc, tracked):
    ruim = copy.deepcopy(doc)
    mv = next(r for r in ruim["items"] if r["item"] == "tools/geometry_sanity.py")
    mv["destination"], mv["compat"] = None, None
    dec = next(r for r in ruim["items"] if r["item"] == "tools/trace_view.py")
    dec.pop("open_question")
    fac = next(r for r in ruim["items"] if r["item"] == "tools/sofa_builder.py")
    fac["destination"] = "tools/rooms/shared/nao_existe.py"
    erros = check(ruim, tracked)["errors"]
    assert "tools/geometry_sanity.py" in erros["MISSING_DESTINATION"]
    assert "tools/geometry_sanity.py" in erros["MOVE_WITHOUT_COMPAT"]
    assert "tools/trace_view.py" in erros["DECISION_WITHOUT_QUESTION"]
    assert erros["FACADE_CANONICAL_MISSING"] == ["tools/sofa_builder.py -> tools/rooms/shared/nao_existe.py"]


def _doc_sintetico(compat):
    base = {"phase": "P4", "risk": "low", "rationale": "item sintético de teste do gate"}
    return {"schema_version": "fp043_p0_map.v1", "items": [
        {**base, "item": "tools/x.py", "disposition": "move", "destination": "tools/validation/x.py",
         "compat": compat, "status": "done"},
        {**base, "item": "tools/validation/", "disposition": "retain", "destination": None},
    ]}


def test_movimento_executado_sem_fachada_exige_destino_presente_e_origem_ausente():
    doc = _doc_sintetico("none_needed")
    erros = check(doc, ["tools/x.py"])["errors"]
    assert erros["DONE_DESTINATION_MISSING"] == ["tools/x.py -> tools/validation/x.py"]
    assert erros["DONE_ORIGIN_STILL_PRESENT"] == ["tools/x.py"]
    assert check(doc, ["tools/validation/x.py"])["result"] == "PASS"


def test_movimento_executado_com_fachada_mantem_a_origem_no_escopo():
    doc = _doc_sintetico("facade_at_old_path")
    assert check(doc, ["tools/x.py", "tools/validation/x.py"])["result"] == "PASS"
    erros = check(doc, ["tools/validation/x.py"])["errors"]         # a fachada sumiu: o item sobra no mapa
    assert erros["STALE_ITEMS"] == ["tools/x.py"]


def test_pasta_nova_em_tools_exige_entrada_no_mapa():
    doc = _doc_sintetico("none_needed")
    doc["items"] = doc["items"][:1]                                   # sem a entrada da pasta de destino
    erros = check(doc, ["tools/validation/x.py"])["errors"]
    assert erros["MISSING_ITEMS"] == ["tools/validation/"]


def test_nenhuma_decisao_e_fachada_sem_justificativa_e_riscos_consistentes(doc):
    for r in doc["items"]:
        assert len(r["rationale"]) >= 20, r["item"]
        if r["disposition"] == "move" and r["item"].endswith(".rb"):
            assert r.get("dynamic_path_risk"), f"Ruby carregado por caminho precisa de risco marcado: {r['item']}"
        if r.get("dynamic_path_risk"):
            assert r["risk"] == "high", r["item"]
    resumo = summary(doc)
    assert resumo["items"] == len(doc["items"]) and resumo["by_disposition"]["decision"] == len(resumo["open_questions"])


def test_raiz_planejada_so_tem_arquivos_de_papel_explicito(doc):
    assert doc["root_allowlist"] == sorted([
        ".dockerignore", ".gitattributes", ".gitignore", "CLAUDE.md", "README.md", "docker-compose.rag.yml",
        "docker-compose.yml", "pyproject.toml", "uv.lock"])
    movem = {r["item"] for r in doc["items"] if "/" not in r["item"] and r["disposition"] == "move"}
    assert movem == {"CLAUDE_COGNITIVE_ARCHITECTURE.md", "HANDOFF.md", "KICKOFF.md", "HISTORICO_SOFA.json",
                     "planta_74.pdf", "vray_pipeline_proof.png"}


def test_planta_pdf_so_muda_de_caminho_com_resolvedor_unico(doc):
    e = next(r for r in doc["items"] if r["item"] == "planta_74.pdf")
    assert e["compat"] == "resolver_unico" and e["dynamic_path_risk"] and "SHA256" in e["rationale"]


# ---------------------------------------------------------------- consumidores (árvore sintética)
def _repo(tmp_path, arquivos: dict[str, str]):
    for rel, texto in arquivos.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(texto, encoding="utf-8")
    return Corpus(tmp_path, sorted(arquivos))


def test_consumidores_juntam_ast_texto_ci_e_ruby(tmp_path):
    corpus = _repo(tmp_path, {
        "tools/alvo.py": "X = 1\n",
        "tools/alvo.rb": "# job\n",
        "tools/usa_import.py": "from tools import alvo\n",
        "tools/usa_from.py": "from tools.alvo import X\n",
        "tests/test_alvo.py": "import tools.alvo\n",
        ".github/workflows/ci.yml": "run: python -m tools.alvo --check\n",
        "docs/x.md": "veja tools/alvo.py e `-RubyStartup alvo.rb`\n",
        "tools/sem_relacao.py": "print('nada')\n",
    })
    py = corpus.consumers("tools/alvo.py")
    assert py["code"] == ["tools/usa_from.py", "tools/usa_import.py"]
    assert py["tests"] == ["tests/test_alvo.py"] and py["ci"] == [".github/workflows/ci.yml"]
    assert py["docs"] == ["docs/x.md"]
    assert corpus.consumers("tools/alvo.rb")["docs"] == ["docs/x.md"]
    assert corpus.consumers("tools/sem_relacao.py") == {}


def test_modulo_de_um_componente_nao_casa_por_texto(tmp_path):
    corpus = _repo(tmp_path, {
        "interior/__init__.py": "",
        "docs/a.md": "INTERIOR design do interior da casa\n",
        "tools/imp.py": "import interior.coisa\n",
    })
    assert corpus.consumers("interior/__init__.py") == {"code": ["tools/imp.py"]}


def test_diretorio_e_unidade_e_ignora_arquivos_dele_mesmo(tmp_path):
    corpus = _repo(tmp_path, {
        "tools/pkg/__init__.py": "from tools.pkg import mod\n",
        "tools/pkg/mod.py": "",
        "tools/outro.py": "import tools.pkg.mod\n",
        "tests/test_pkg.py": "from tools.pkg import mod\n",
    })
    assert corpus.consumers("tools/pkg/") == {"code": ["tools/outro.py"], "tests": ["tests/test_pkg.py"]}


def test_cli_do_mapa_roda(doc):
    r = subprocess.run([sys.executable, "-m", "tools.navigation.p0_map", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
