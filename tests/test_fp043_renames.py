"""FP-043/P2 — renomeações autorizadas de arquivos protegidos: conteúdo idêntico, manifestos coerentes.

Prova caminho e conteúdo (blob do git + SHA256 do blob) contra o registro `fp043_protected_renames.v1.json`,
medido no commit-base. Não prova que cada consumidor foi atualizado: isso é a revisão do PR de movimento.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.navigation.consumers import tracked_files
from tools.navigation.renames import REGISTRY, check

ROOT = Path(__file__).resolve().parents[1]
VRAY = "artifacts/review/vray_pipeline_proof_2026-06/vray_pipeline_proof.png"
SOFA = "references/sofas/history/HISTORICO_SOFA.json"


@pytest.fixture(scope="module")
def registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tracked():
    return tracked_files(ROOT)


def _rename(reg, old):
    return next(r for r in reg["renames"] if r["old_path"] == old)


def test_renomeacoes_registradas_passam(registry, tracked):
    res = check(registry, tracked, ROOT)
    assert res["result"] == "PASS", res["errors"]
    assert {r["old_path"] for r in registry["renames"]} >= {"HISTORICO_SOFA.json", "vray_pipeline_proof.png"}


def test_conteudo_pre_movimento_e_o_do_commit_base(registry):
    """O SHA256 registrado é o do blob do commit-base: se alguém regravar o arquivo, o registro denuncia."""
    assert registry["baseline_commit"] == "07959bfdd153031de13190e883583c7e8acb5c70"
    vray = _rename(registry, "vray_pipeline_proof.png")
    assert vray["blob_sha"] == "42f50d658683639ac9decb78d373c8463b9dc043"
    assert vray["sha256"] == "aac82e3a638d8a3a6926bb62a51c74a2268b9095e559d807247182cd32ee0532"


def test_destino_com_conteudo_diferente_falha(registry, tracked):
    ruim = copy.deepcopy(registry)
    _rename(ruim, "vray_pipeline_proof.png")["blob_sha"] = "0" * 40
    assert "BLOB_CHANGED" in check(ruim, tracked, ROOT)["errors"]
    ruim = copy.deepcopy(registry)
    _rename(ruim, "vray_pipeline_proof.png")["sha256"] = "f" * 64
    assert "BYTES_CHANGED" in check(ruim, tracked, ROOT)["errors"]


def test_origem_ainda_rastreada_ou_destino_ausente_falha(registry, tracked):
    erros = check(registry, tracked + ["vray_pipeline_proof.png"], ROOT)["errors"]
    assert erros["DONE_ORIGIN_STILL_TRACKED"] == ["vray_pipeline_proof.png -> " + VRAY]
    erros = check(registry, [t for t in tracked if t != SOFA], ROOT)["errors"]
    assert erros["DONE_DESTINATION_MISSING"] == ["HISTORICO_SOFA.json -> " + SOFA]


def test_copia_divergente_com_mesmo_nome_falha(registry, tracked):
    blobs = {t: "a" * 40 for t in tracked}
    blobs[VRAY] = _rename(registry, "vray_pipeline_proof.png")["blob_sha"]
    blobs[SOFA] = _rename(registry, "HISTORICO_SOFA.json")["blob_sha"]
    sobra = tracked + ["copia/vray_pipeline_proof.png"]
    blobs["copia/vray_pipeline_proof.png"] = "b" * 40
    erros = check(registry, sobra, ROOT, blobs=blobs)["errors"]
    assert list(erros["DIVERGENT_COPY"]) == ["copia/vray_pipeline_proof.png (mesmo nome de " + VRAY + ", conteúdo diferente)"]


def test_manifestos_precisam_refletir_o_movimento(registry, tracked):
    ruim = copy.deepcopy(registry)
    _rename(ruim, "vray_pipeline_proof.png")["in_assets"] = False
    assert "ASSETS_UNEXPECTED_DESTINATION" in check(ruim, tracked, ROOT)["errors"]
    ruim = copy.deepcopy(registry)
    _rename(ruim, "HISTORICO_SOFA.json")["in_assets"] = True       # .json não é binário: não está em assets
    assert "ASSETS_DESTINATION_BLOB_MISMATCH" in check(ruim, tracked, ROOT)["errors"]


def test_planned_exige_origem_presente_e_destino_ausente(registry, tracked):
    plan = copy.deepcopy(registry)
    _rename(plan, "vray_pipeline_proof.png")["status"] = "planned"
    erros = check(plan, tracked, ROOT)["errors"]
    assert "PLANNED_ORIGIN_MISSING" in erros and "PLANNED_DESTINATION_EXISTS" in erros


@pytest.mark.parametrize("campo", ["sha256", "blob_sha", "owner_group", "justification", "consumers_reviewed"])
def test_campo_obrigatorio_ausente_falha(registry, tracked, campo):
    ruim = copy.deepcopy(registry)
    _rename(ruim, "HISTORICO_SOFA.json").pop(campo)
    assert any(campo in x for x in check(ruim, tracked, ROOT)["errors"]["MISSING_FIELD"])


def test_registro_invalido_e_rejeitado(tracked):
    assert check({}, tracked, ROOT)["errors"] == {"INVALID_SCHEMA": [""]}


def test_raiz_so_tem_o_que_a_allowlist_permite_mais_os_movimentos_pendentes(tracked):
    mapa = json.loads((ROOT / "docs/specs/fp043_p0_map.v1.json").read_text(encoding="utf-8"))
    pendentes = {r["item"] for r in mapa["items"]
                 if "/" not in r["item"] and r["disposition"] == "move" and r.get("status", "planned") != "done"}
    esperado = set(mapa["root_allowlist"]) | pendentes
    assert {t for t in tracked if "/" not in t} == esperado
    movidos = {"CLAUDE_COGNITIVE_ARCHITECTURE.md", "HANDOFF.md", "KICKOFF.md", "HISTORICO_SOFA.json", "vray_pipeline_proof.png"}
    assert not esperado & movidos
    assert pendentes <= {"planta_74.pdf"}        # o PDF migra em PR próprio, com resolvedor único
