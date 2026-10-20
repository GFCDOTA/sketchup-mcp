"""FP-044/F2 — o programa do sofa nao depende mais de configs/, textures/ e renders/ na raiz.

Os .rb nao sao verificaveis sem SketchUp (o L2 da F2 cobre a execucao); aqui o contrato em TEXTO: onde cada um le configs/texturas e onde grava.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOFA = ROOT / "tools/rooms/living/capabilities/ruby/sofa_program"
TEX = ROOT / "assets/textures/sofa_fabric"


def _tracked() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f]


def test_configs_e_texturas_moram_no_dono_e_existem():
    for name in ("sofa_schema.json", "sofa_archetypes.json", "sofa_eval_cases.json", "sofa_vray_material_spec.json"):
        assert (SOFA / "configs" / name).is_file(), name
    assert sorted(p.name for p in TEX.glob("fabric_*")) == sorted(
        f"fabric_{s}_{k}.png" for s in ("dark_charcoal", "light_linen", "mid_gray") for k in ("albedo", "bump"))


def test_spec_vray_aponta_para_texturas_que_existem():
    spec = json.loads((SOFA / "configs/sofa_vray_material_spec.json").read_text("utf-8"))
    maps = re.findall(r'"(?:albedo|bump)_map":\s*"([^"]+)"', json.dumps(spec))
    assert maps and all((ROOT / m).is_file() for m in maps), maps


def test_ruby_le_configs_de_si_mesmo_e_nao_grava_em_pasta_versionada():
    for rb in SOFA.glob("*.rb"):
        text = rb.read_text("utf-8")
        assert not re.search(r"File\.join\(ROOT,\s*'configs'", text), rb.name
        assert not re.search(r"File\.join\((ROOT|REPO),\s*'renders'", text), rb.name
        assert "'textures')" not in text, rb.name


def test_nenhum_codigo_rastreado_usa_os_caminhos_antigos_da_raiz():
    ruins = []
    for f in _tracked():
        if not f.endswith((".py", ".rb", ".ps1", ".cmd", ".sh", ".yml")) or f.startswith(("tests/", "artifacts/", "docs/archive/")):
            continue
        for n, line in enumerate((ROOT / f).read_text("utf-8", errors="replace").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"""['"/\\]configs['"/\\]sofa_|['"]textures['"/\\]+fabric_|\brenders['"/\\](sofa_eval|check|sofa_vray)""", code):
                ruins.append(f"{f}:{n}")
    assert ruins == [], ruins


def test_raiz_sem_as_pastas_do_sofa_e_sem_as_fachadas_de_scripts():
    tracked = _tracked()
    assert not [f for f in tracked if f.split("/")[0] in ("configs", "renders", "textures")]
    assert sorted(f for f in tracked if f.startswith("scripts/")) == ["scripts/set_clipboard_image.ps1"]
