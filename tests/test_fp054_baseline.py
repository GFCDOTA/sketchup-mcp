"""FP-054 F0: o baseline mede sem mudar nada. Trava o inventario reconciliado, a varredura, as cenas semeadas e a
reproducao da busca da mesa (espiao passivo + censo casado 1:1 com as chamadas reais do gate)."""
from __future__ import annotations

import pytest

from tools.navigation import baseline_inventory as bi
from tools.navigation import baseline_probes as bp


# ------------------------------------------------------------------------------------------------- classe
@pytest.mark.parametrize("path,status,expected", [
    ("tests/test_x.py", "TEST", "test"),
    ("projects/planta_74/source/planta_74.pdf", "EVIDENCE_OR_DATA", "source"),
    ("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json", "EVIDENCE_OR_DATA", "fixture"),
    ("docs/archive/old.md", "HISTORICAL", "legacy"),
    ("tools/furnish_apartment.py", "LEGACY_FACADE", "legacy"),
    ("artifacts/planta_74/planta_74.skp", "EVIDENCE_OR_DATA", "artifact"),
    ("core/schemas/specialist_fragment.v1.schema.json", "CONFIG", "contract"),
    ("tools/rooms/kitchen/specialist.v1.json", "CONFIG", "contract"),
    ("tools/rooms/capability_catalog.v1.json", "CONFIG", "contract"),
    ("tools/rooms/kitchen/fragments/cabinetry.fragment.v1.json", "CONFIG", "knowledge"),
    ("references/sketchup/knowledge/x.json", "EVIDENCE_OR_DATA", "knowledge"),
    (".claude/rules/x.md", "AGENT_INSTRUCTION", "agent_instruction"),
    ("tools/validation/circulation_gate.py", "ACTIVE_IMPORTED", "code_active"),
    ("tools/x/cli.py", "CLI_DOC_ONLY", "code_unreached"),
    ("docs/specs/FP-054_kickoff.md", "SPEC", "documentation"),
    ("pyproject.toml", "CONFIG", "config"),
])
def test_every_file_kind_maps_to_one_class(path, status, expected):
    assert bi.artifact_class(path, status) == expected
    assert expected in bi.CLASSES


def test_generated_report_is_recognised_by_its_marker():
    head = "# Handoff\n\n> Gerado por `python -m tools.navigation.file_audit` em `abc`."
    assert bi.artifact_class("docs/reports/file_audit/areas/core.md", "HISTORICAL", head) == "generated"
    assert bi.artifact_class("docs/reports/FP-043_final_validation.md", "HISTORICAL", "# Validacao final") == "documentation"


# ----------------------------------------------------------------------------------------------- varredura
SNIPPET = '''
import os
from functools import lru_cache
M2IN = 39.3700787402
LIMIT_M = 0.90
_CACHE = {}

def a():
    try:
        return 1
    except Exception:
        pass

def b():
    try:
        return 1
    except Exception as e:
        raise RuntimeError(e)

@lru_cache(maxsize=8)
def c(x):
    global LIMIT_M
    return os.environ.get("PT_TO_M")

def d(b):
    return str(b.get("module", "")).startswith("Cadeira")  # noqa: E501
'''


def test_scan_flags_each_hazard_kind_once():
    kinds = sorted(f["kind"] for f in bi.scan_python("tools/x.py", SNIPPET))
    for k in ("silent_except", "broad_except", "scale_constant", "module_constant", "module_cache", "global_stmt",
              "env_read", "name_semantics", "noqa"):
        assert k in kinds, k
    assert kinds.count("module_cache") == 2          # o decorator e o dict de modulo


def test_scan_reads_skip_and_xfail_marks_in_tests():
    text = "import pytest\n@pytest.mark.xfail(reason='x')\ndef test_a(): pass\n\ndef test_b():\n    pytest.skip('ruby nao instalado')\n"
    kinds = sorted(f["kind"] for f in bi.scan_python("tests/test_a.py", text))
    assert kinds == ["skip", "xfail"]


def test_duplicated_constant_reports_divergent_values():
    findings = [{"path": "tools/a.py", "line": 1, "kind": "module_constant", "detail": "CIRC_M=0.85"},
                {"path": "tools/b.py", "line": 1, "kind": "module_constant", "detail": "CIRC_M=0.9"},
                {"path": "tools/c.py", "line": 1, "kind": "module_constant", "detail": "ONLY_HERE=1"}]
    dup = bi.duplicated_constants(findings)
    assert dup == [{"name": "CIRC_M", "modules": ["tools/a.py", "tools/b.py"], "values": ["0.85", "0.9"], "diverges": True}]


def test_mcp_tools_map_tool_to_repo_modules():
    text = ("from tools.sketchup import jobs as su_jobs\nfrom tools.validation.x import run_all\n"
            "@mcp.tool()\ndef su_status():\n    return su_jobs.status()\n"
            "@mcp.tool()\ndef gates():\n    from core.y import z\n    return run_all()\n")
    modules = {"tools.sketchup.jobs": "tools/sketchup/jobs.py", "tools.validation.x": "tools/validation/x.py",
               "core.y": "core/y.py"}
    assert bi.mcp_tools(text, modules) == {"su_status": ["tools.sketchup.jobs"], "gates": ["core.y", "tools.validation.x"]}


def test_inventory_reconciles_with_git_ls_files():
    result = bi.build()
    s = result["summary"]
    assert s["reconciled"], s
    assert s["rows"] == s["git_ls_files"] == len({r["path"] for r in result["rows"]})
    assert all(r["class"] in bi.CLASSES and r["owner"] for r in result["rows"])


# ------------------------------------------------------------------------------------------------- sondas
def test_synthetic_scene_is_seeded_and_inside_the_room():
    con = bp.synthetic_room(4.0)
    a = bp.synthetic_boxes(con, 50, seed=7, size_m=(0.1, 0.3))
    b = bp.synthetic_boxes(con, 50, seed=7, size_m=(0.1, 0.3))
    c = bp.synthetic_boxes(con, 50, seed=8, size_m=(0.1, 0.3))
    assert bp._sha(a) == bp._sha(b) != bp._sha(c)
    from shapely.geometry import Polygon

    from core.scale import PT_TO_IN
    room = Polygon([(x * PT_TO_IN, y * PT_TO_IN) for x, y in con["rooms"][0]["polygon_pts"]])
    assert all(room.buffer(1e-6).contains(Polygon(box["corners"])) for box in a)


def test_gate_probe_controls_fail_as_expected():
    """As cenas de controle (2 portais partidos; cadeira com nome do vocabulario) TEM que reprovar — senao as sondas de
    falso PASS nao provam nada. O veredito das demais e o retrato do defeito (F1 corrige; nao travado aqui)."""
    probes = {p["id"]: p for p in bp.gate_probes()["probes"]}
    assert probes["P3_two_portals_split_control"]["observed"] == "FAIL"
    assert probes["P4_chair_named_pt"]["observed"] == "FAIL"
    assert probes["P4_chair_named_pt"]["chairs_measured"] == 1


def test_parse_junit_separates_blocked_environment_from_plain_skips():
    xml = """<testsuites><testsuite>
      <testcase classname="t" name="ok" time="0.1"/>
      <testcase classname="t" name="bad" time="0.2"><failure message="boom"/></testcase>
      <testcase classname="t" name="env" time="0"><skipped type="pytest.skip" message="ruby não instalado"/></testcase>
      <testcase classname="t" name="plain" time="0"><skipped type="pytest.skip" message="caso nao aplicavel"/></testcase>
      <testcase classname="t" name="xf" time="0"><skipped type="pytest.xfail" message="bug conhecido"/></testcase>
    </testsuite></testsuites>"""
    res = bp.parse_junit(xml)
    assert res["counts"] == {"blocked_env": 1, "failed": 1, "passed": 1, "skipped": 1, "xfailed": 1}
    assert res["failures"] == [{"test": "t::bad", "message": "boom"}]


@pytest.mark.planta74_scale
def test_dining_search_is_reproduced_with_reasons_for_every_grid_point():
    trace = bp.dining_trace()
    assert trace["proof_spy_is_passive"]["identical"], "o espiao mudou a sala"
    assert trace["census_aligned_with_spy"], "o censo da grade nao casa com as chamadas reais do gate"
    counts = trace["counts"]
    assert counts["gate_calls_total"] == trace["placement_decision"]["n_candidates_tried"]
    assert counts["gate_calls_grid"] == sum(n for r, n in counts["grid_by_reason"].items() if not r.startswith("REJECT"))
    assert all(r["reason"] for r in trace["grid"])
    assert trace["chosen"]["gate"] == "PASS"


def test_critical_flow_map_paths_exist():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/reports/fp054/f0/critical_flow_map.md").read_text(encoding="utf-8")
    paths = {p for p in re.findall(r"`([A-Za-z0-9_./-]+\.(?:py|rb|json|pdf|png|skp))`", text)}
    paths = {p for p in paths if "/" in p}          # nome solto (`x.json`) e desta pasta, nao caminho
    assert len(paths) >= 25
    missing = sorted(p for p in paths if not (root / p).exists())
    assert not missing, missing
