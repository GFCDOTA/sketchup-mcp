"""FP-057/P8 (#589): protecoes puras do executor — label, paths criticos e teto de arquivos/linhas. Fail-closed em toda entrada estranha."""
from __future__ import annotations

import json

import pytest

from tools.orchestration import execution_guards as g

CFG = g.load_config()


def num(*rows) -> str:
    return "\n".join(f"{a}\t{r}\t{p}" for a, r, p in rows)


# ------------------------------------------------------------------------------------------------------ configuracao
def test_config_unites_review_policy_critical_paths_with_the_executor_extras():
    assert CFG.label == "executor-ok" and CFG.max_files == 8 and CFG.max_lines == 300
    for must in (".github/workflows/", "docs/governance/", "tools/validation/", "tools/orchestration/",
                 "tools/rooms/shared/spatial_solver/",                       # veio da review_policy.json
                 "tools/validation/execution_state.py"):
        assert must in CFG.critical, must


def test_empty_critical_list_refuses_instead_of_allowing_everything(tmp_path):
    guards = tmp_path / "g.json"
    guards.write_text(json.dumps({"label": "executor-ok", "limits": {"max_files": 1, "max_lines": 1}}), encoding="utf-8")
    pol = tmp_path / "p.json"
    pol.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="fail-closed"):
        g.load_config(guards, pol)


# ------------------------------------------------------------------------------------------------------------ label
@pytest.mark.parametrize("labels,ok", [
    (["executor-ok"], True), ([{"name": "executor-ok"}], True), ([{"name": " Executor-OK "}], True),
    (["bug", {"name": "executor-ok"}], True),
    ([], False), (["executor-ok-not"], False), (["executor"], False), (None, False), ("executor-ok", False),
    ([{"nome": "executor-ok"}], False), ([123], False),
])
def test_label_ok_requires_the_exact_label_and_fails_closed_on_odd_shapes(labels, ok):
    assert g.label_ok(labels, CFG) is ok


# --------------------------------------------------------------------------------------------------- paths criticos
@pytest.mark.parametrize("path", [
    ".github/workflows/ci.yml", ".github/workflows/sub/x.yaml", "docs/governance/review_policy.json",
    "docs/governance/executor_guards.json", "tools/validation/anything.py", "tools/orchestration/event_executor.py",
    "tools/rooms/shared/spatial_solver/solver.py",
    ".GitHub/Workflows/ci.yml",                                              # caixa (NTFS)
    ".github\\workflows\\ci.yml",                                            # barras do Windows
    "./tools/validation/x.py",                                               # prefixo ./
    "tools//validation//x.py",                                               # barras duplicadas
    "core/pipeline_contracts.py",                                            # arquivo exato da review_policy
])
def test_critical_paths_are_detected_in_every_spelling(path):
    assert g.is_critical(path, CFG)


@pytest.mark.parametrize("path", ["docs/engineering/x.md", "tests/test_x.py", "tools/rooms/kitchen/x.py", ".github/CODEOWNERS_X",
                                  "tools/validationx/y.py", "tools/orchestration_x/y.py"])
def test_non_critical_paths_pass_and_prefix_matching_is_directory_aware(path):
    assert g.is_critical(path, CFG) is None


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/../../b", "/abs/path", "C:/x/y", "", "   "])
def test_traversal_absolute_and_empty_paths_are_invalid_never_silently_allowed(bad):
    with pytest.raises(ValueError):
        g.is_critical(bad, CFG)


# ------------------------------------------------------------------------------------------------------------ diff
def test_small_noncritical_diff_is_ok_and_measured():
    v = g.evaluate_diff(num((10, 2, "docs/a.md"), (5, 0, "tests/test_a.py")), CFG)
    assert v.ok and v.files == 2 and v.lines == 17 and v.violations == []


def test_limits_are_inclusive_at_the_ceiling_and_fail_one_above():
    at = g.evaluate_diff(num(*[(1, 0, f"docs/f{i}.md") for i in range(8)]), CFG)
    assert at.ok and at.files == 8
    over_files = g.evaluate_diff(num(*[(1, 0, f"docs/f{i}.md") for i in range(9)]), CFG)
    assert not over_files.ok and "max_files" in over_files.reasons()[0]
    assert g.evaluate_diff(num((150, 150, "docs/a.md")), CFG).ok
    over_lines = g.evaluate_diff(num((150, 151, "docs/a.md")), CFG)
    assert not over_lines.ok and "max_lines" in over_lines.reasons()[0]


def test_a_critical_path_blocks_even_a_one_line_change_and_all_violations_are_listed():
    v = g.evaluate_diff(num((1, 0, ".github/workflows/ci.yml"), (400, 0, "docs/big.md"), (1, 1, "tools/validation/x.py")), CFG)
    rules = [x["rule"] for x in v.violations]
    assert not v.ok and rules.count("path_critico") == 2 and "max_lines" in rules


def test_binary_files_are_not_measurable_and_block():
    v = g.evaluate_diff("-\t-\tdocs/img.png", CFG)
    assert not v.ok and v.violations[0]["rule"] == "binario"


@pytest.mark.parametrize("garbage", ["isto nao e numstat", "a\tb\tdocs/x.md", "1\t2", "1\t2\tx\textra"])
def test_unreadable_numstat_blocks_fail_closed(garbage):
    v = g.evaluate_diff(garbage, CFG)
    assert not v.ok and v.violations[0]["rule"] == "numstat_ilegivel"


def test_traversal_path_inside_the_diff_blocks():
    v = g.evaluate_diff(num((1, 0, "../fora/x.py")), CFG)
    assert not v.ok and v.violations[0]["rule"] == "caminho_invalido"


def test_empty_diff_is_ok_with_zero_files_so_the_caller_decides_what_no_change_means():
    v = g.evaluate_diff("", CFG)
    assert v.ok and v.files == 0 and v.lines == 0
