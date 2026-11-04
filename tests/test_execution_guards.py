"""FP-057/P8 (#589): protecoes puras do executor — label, paths criticos e teto de arquivos/linhas. Fail-closed em toda entrada estranha.
Contrato do caller: a entrada de evaluate_diff e a saida de `git` com NUMSTAT_ARGS (`--numstat -z --no-renames`)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.orchestration import execution_guards as g

CFG = g.load_config()


def num(*rows) -> str:
    """Formato `git diff --numstat -z --no-renames`: registros `a<TAB>r<TAB>caminho<NUL>`."""
    return "".join(f"{a}\t{r}\t{p}\0" for a, r, p in rows)


# ------------------------------------------------------------------------------------------------------ configuracao
def test_config_unites_baseline_review_policy_and_executor_extras():
    assert CFG.label == "executor-ok" and CFG.max_files == 8 and CFG.max_lines == 300
    for must in (".github/workflows/", "docs/governance/", "tools/validation/", "tools/orchestration/",
                 "tools/rooms/shared/spatial_solver/",                       # veio da review_policy.json
                 "tools/validation/execution_state.py"):
        assert must in CFG.critical, must


def write_cfg(tmp_path: Path, guards: object, policy: object) -> tuple[Path, Path]:
    gp, pp = tmp_path / "g.json", tmp_path / "p.json"
    gp.write_text(json.dumps(guards), encoding="utf-8")
    pp.write_text(json.dumps(policy), encoding="utf-8")
    return gp, pp


GOOD_G = {"label": "executor-ok", "limits": {"max_files": 8, "max_lines": 300}, "extra_critical_paths": ["tools/x/"]}
GOOD_P = {"critical_paths": ["core/a.py"]}


def test_a_minimal_valid_config_still_carries_the_immutable_baseline_in_code(tmp_path):
    cfg = g.load_config(*write_cfg(tmp_path, {**GOOD_G, "extra_critical_paths": []}, GOOD_P))
    assert ".github/workflows/" in cfg.critical and "docs/governance/" in cfg.critical and "core/a.py" in cfg.critical


@pytest.mark.parametrize("policy", [
    {}, {"critical_paths": []}, {"critical_paths": None}, {"critical_paths": "core/a.py"}, {"critical_paths": ["ok", 3]},
    {"critical_paths": ["ok", ""]}, {"critical_paths": ["ok", "   "]}, [], "texto",
])
def test_missing_or_malformed_policy_critical_paths_refuse_the_load_even_if_the_extras_exist(tmp_path, policy):
    with pytest.raises(ValueError, match="fail-closed"):                       # nunca cai num conjunto parcial
        g.load_config(*write_cfg(tmp_path, GOOD_G, policy))


@pytest.mark.parametrize("guards", [
    {k: v for k, v in GOOD_G.items() if k != "extra_critical_paths"},          # chave ausente
    {**GOOD_G, "extra_critical_paths": "tools/x/"}, {**GOOD_G, "extra_critical_paths": [1]},
    {**GOOD_G, "label": ""}, {**GOOD_G, "label": "  "}, {**GOOD_G, "label": 5},
    {k: v for k, v in GOOD_G.items() if k != "label"}, {k: v for k, v in GOOD_G.items() if k != "limits"},
    {**GOOD_G, "limits": []}, {**GOOD_G, "limits": {"max_files": 8}}, {**GOOD_G, "limits": {"max_lines": 300}},
    {**GOOD_G, "limits": {"max_files": 0, "max_lines": 300}}, {**GOOD_G, "limits": {"max_files": -1, "max_lines": 300}},
    {**GOOD_G, "limits": {"max_files": 8, "max_lines": 0}}, {**GOOD_G, "limits": {"max_files": True, "max_lines": 300}},
    {**GOOD_G, "limits": {"max_files": "8", "max_lines": 300}}, {**GOOD_G, "limits": {"max_files": 8.5, "max_lines": 300}},
    [],
])
def test_malformed_guards_config_refuses_the_load(tmp_path, guards):
    with pytest.raises(ValueError, match="fail-closed"):
        g.load_config(*write_cfg(tmp_path, guards, GOOD_P))


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
    ".github/workflows/a\u00e7\u00e3o.yml",                                  # unicode no nome
    ".github/workflows /ci.yml", ".github/workflows./ci.yml", ".github /workflows/ci.yml",  # NTFS ignora espaco/ponto final do componente
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
    v = g.evaluate_diff("-\t-\tdocs/img.png\0", CFG)
    assert not v.ok and v.violations[0]["rule"] == "binario"


def test_paths_with_tab_quote_and_unicode_are_parsed_raw_only_two_tabs_split_fields():
    rows = g.parse_numstat(num((1, 2, 'docs/a\tb.md'), (3, 4, 'docs/"q".md'), (5, 6, "docs/a\u00e7\u00e3o.md")))
    assert rows == [(1, 2, "docs/a\tb.md"), (3, 4, 'docs/"q".md'), (5, 6, "docs/a\u00e7\u00e3o.md")]


@pytest.mark.parametrize("garbage", [
    "isto nao e numstat", "1\t2\tdocs/x.md",                                    # sem NUL final (formato antigo/ambiguo)
    '1\t2\t"docs/a\\303\\247.md"\n',                                            # saida padrao com aspas C e newline
    "a\tb\tdocs/x.md\0", "1\t2\0", "1\t2\t\0", "-1\t2\tdocs/x.md\0", "\u0661\t2\tdocs/x.md\0", " 1\t2\tdocs/x.md\0", "1\t2\tdocs/x.md\0\0",
])
def test_unreadable_or_ambiguous_numstat_blocks_fail_closed(garbage):
    v = g.evaluate_diff(garbage, CFG)
    assert not v.ok and v.violations[0]["rule"] == "numstat_ilegivel"


def test_traversal_path_inside_the_diff_blocks():
    v = g.evaluate_diff(num((1, 0, "../fora/x.py")), CFG)
    assert not v.ok and v.violations[0]["rule"] == "caminho_invalido"


def test_empty_diff_is_ok_with_zero_files_so_the_caller_decides_what_no_change_means():
    v = g.evaluate_diff("", CFG)
    assert v.ok and v.files == 0 and v.lines == 0


# --------------------------------------------- git REAL: o caso do Tech Lead (core.quotePath cita nomes nao-ASCII)
@pytest.mark.skipif(not shutil.which("git"), reason="precisa do git")
def test_real_git_unicode_critical_path_is_caught_with_z_and_the_default_quoted_output_is_refused(tmp_path):
    def git(*a):
        return subprocess.run(["git", "-c", "core.quotePath=true", *a], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("1\n", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-qm", "base")
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "a\u00e7\u00e3o.yml").write_text("x: 1\ny: 2\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "ok.md").write_text("ok\n", encoding="utf-8")
    git("add", "-A")
    raw_default = git("diff", "--cached", "--numstat", "--no-renames")
    assert '"' in raw_default and "\\303" in raw_default                      # o git CITA o nome (prova do problema)
    assert not g.evaluate_diff(raw_default, CFG).ok                           # saida padrao e recusada, nunca "permitida"
    proc = subprocess.run(["git", *g.NUMSTAT_ARGS[:1], "--cached", *g.NUMSTAT_ARGS[1:]], cwd=tmp_path, capture_output=True, check=True)
    v = g.evaluate_diff(proc.stdout.decode("utf-8"), CFG)
    assert not v.ok and any(x["rule"] == "path_critico" and "workflows" in x["detail"] for x in v.violations)
    assert v.files == 2 and v.lines == 3


def test_numstat_args_are_the_contract_with_the_future_caller():
    assert g.NUMSTAT_ARGS == ("diff", "--numstat", "-z", "--no-renames")
