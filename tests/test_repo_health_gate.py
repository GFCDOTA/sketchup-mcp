"""FP-043 P3a-05 / D-006 — `tools/validation/repo_health_gate.py` passa a rodar no CI (pytest coleta `tests/`).

Antes: o gate tinha um `test_repo_health` dentro de `tools/` (nao coletado) e reprovava 4 itens sem ninguem ver.
Agora: os 4 foram resolvidos (3 READMEs de proveniencia + escala da planta_74 vinda de `core.scale`) e as regras
passam a ser verificadas; as contraprovas abaixo garantem que o gate ainda reprova de verdade.
"""
from __future__ import annotations

from tools.validation import repo_health_gate as gate


def test_repo_health_sem_violacoes():
    assert gate.violations() == []


def test_gate_reprova_definicao_de_escala_fora_do_core(tmp_path, monkeypatch):
    f = tmp_path / "x.py"
    f.write_text("PT_TO_M = 0.0259\n", encoding="utf-8")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "_tracked", lambda: ["x.py"])
    assert ("SCALE_DEF_FORA_DO_CORE", "x.py:1") in gate.violations()


def test_gate_reprova_artefato_de_review_sem_report(tmp_path, monkeypatch):
    art = tmp_path / "artifacts/review/planta/a"
    art.mkdir(parents=True)
    (art / "x.png").write_bytes(b"png")
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "_tracked", lambda: [])
    assert ("REVIEW_ARTIFACT_SEM_REPORT", str(art.relative_to(tmp_path))) in gate.violations()
