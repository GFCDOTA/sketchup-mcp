"""FP-060-A01 M1 (#606): pytest sobre uma arvore nao confiavel dentro de um AppContainer sem capacidades.

Os testes `windows_only` sobem processos reais num AppContainer real, com arquivos sinteticos. Nenhum deles autoriza executar
agentes ou codigo de PR fora do laboratorio isolado."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tools.orchestration import sandboxed_tests as sb
from tools.orchestration.appcontainer import AppContainerError
from tools.orchestration.sandboxed_tests import SandboxError

windows_only = pytest.mark.skipif(os.name != "nt", reason="requires real Windows AppContainer")

PASSING = "def test_ok():\n    assert 1 + 1 == 2\n"
FAILING = "def test_bad():\n    assert 1 + 1 == 3\n"
DENIED = {"read_outside": "denied", "write_outside": "denied"}


def tree_with(tmp_path, **files) -> Path:
    tree = tmp_path / "tree"
    (tree / "tests").mkdir(parents=True)
    for name, text in files.items():
        (tree / "tests" / f"{name}.py").write_text(text, encoding="utf-8")
    return tree


def sandboxed(tmp_path, tree, tests, timeout=120.0, tag="t"):
    return sb.run_pytest(tree, tests, root=tmp_path / "sandbox", ini_text="[pytest]\n", timeout=timeout,
                         log_dir=tmp_path / "logs", tag=tag)


def _read_all(directory: Path) -> str:
    return "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(directory.iterdir()))


# -- provas reais ----------------------------------------------------------------------------------------------------------
@windows_only
def test_passing_tests_run_inside_an_appcontainer_without_capabilities(tmp_path):
    tree = tree_with(tmp_path, test_ok=PASSING)

    run = sandboxed(tmp_path, tree, ["tests/test_ok.py"])

    assert (run.exit_code, run.timed_out) == (0, False) and "1 passed" in run.output
    assert run.facts["is_appcontainer"] is True and run.facts["capabilities"] == 0 and run.facts["canary"] == DENIED
    assert sb.proves_isolation(run.facts)
    assert any(d.startswith("pytest==") for d in run.facts["runtime"]["distributions"])
    assert run.facts["tree_files"] == 1 and run.facts["workspace_removed"] is True
    assert list((tmp_path / "sandbox").iterdir()) == []                 # nem workspace, nem canario
    assert (tmp_path / "logs" / "sandbox_t_tests.out").read_text(encoding="utf-8").strip().endswith("s")


@windows_only
def test_failing_test_comes_back_as_pytest_exit_code_1(tmp_path):
    run = sandboxed(tmp_path, tree_with(tmp_path, test_bad=FAILING), ["tests/test_bad.py"])
    assert (run.exit_code, run.timed_out) == (1, False) and "1 failed" in run.output


@windows_only
def test_tested_code_imports_modules_from_the_tree_root(tmp_path):
    tree = tree_with(tmp_path, test_uses_root="from thing import VALUE\n\n\ndef test_it():\n    assert VALUE == 7\n")
    (tree / "thing.py").write_text("VALUE = 7\n", encoding="utf-8")
    assert sandboxed(tmp_path, tree, ["tests/test_uses_root.py"]).exit_code == 0


ESCAPE_ATTEMPTS = '''import socket

import pytest

SECRET, INTRUDER, PORT = {secret!r}, {intruder!r}, {port}


def test_cannot_read_a_file_outside_the_workspace():
    with pytest.raises(OSError):
        open(SECRET, encoding="utf-8").read()


def test_cannot_write_outside_the_workspace():
    with pytest.raises(OSError):
        open(INTRUDER, "w", encoding="utf-8").write("x")


def test_cannot_reach_a_loopback_listener():
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", PORT), timeout=3).close()
'''


@windows_only
def test_tested_code_cannot_read_write_outside_or_reach_the_network_and_the_control_can(tmp_path):
    secret, intruder = tmp_path / "secret.txt", tmp_path / "intruder.txt"
    secret.write_text("segredo sintetico", encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        listener.settimeout(0.2)
        tree = tree_with(tmp_path, test_escape=ESCAPE_ATTEMPTS.format(secret=str(secret), intruder=str(intruder),
                                                                     port=listener.getsockname()[1]))

        run = sandboxed(tmp_path, tree, ["tests/test_escape.py"])

        assert run.exit_code == 0 and "3 passed" in run.output           # as tres tentativas foram negadas pelo SO
        assert not intruder.exists()
        with pytest.raises(TimeoutError):
            listener.accept()
        # Controle: a MESMA arvore, sem o AppContainer, consegue os tres acessos — a negacao acima vem do sandbox.
        control = subprocess.run([sys.executable, "-m", "pytest", "tests/test_escape.py", "-q", "-p", "no:cacheprovider"],
                                 cwd=tree, capture_output=True, text=True)
        assert control.returncode == 1 and "3 failed" in control.stdout
        assert intruder.exists()
        listener.settimeout(5)
        listener.accept()[0].close()


@windows_only
def test_timeout_kills_the_test_and_is_reported(tmp_path):
    tree = tree_with(tmp_path, test_slow="import time\n\n\ndef test_slow():\n    time.sleep(120)\n")
    started = time.monotonic()

    run = sandboxed(tmp_path, tree, ["tests/test_slow.py"], timeout=3)

    assert run.timed_out is True and run.exit_code is None
    assert time.monotonic() - started < 60 and run.facts["workspace_removed"] is True


@windows_only
def test_tree_with_a_junction_is_refused_and_nothing_runs(tmp_path, monkeypatch):
    tree = tree_with(tmp_path, test_ok=PASSING)
    outside = tmp_path / "outside"
    outside.mkdir()
    made = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(tree / "tests" / "link"), str(outside)], capture_output=True)
    assert made.returncode == 0
    launched = []
    monkeypatch.setattr(sb.ps, "WindowsJob", lambda *a, **k: launched.append(a) or pytest.fail("processo lancado"))

    with pytest.raises(SandboxError, match="reparse point"):
        sandboxed(tmp_path, tree, ["tests/test_ok.py"])

    assert not launched and list((tmp_path / "sandbox").iterdir()) == []


@windows_only
def test_token_that_is_not_a_bare_appcontainer_stops_the_run_before_it_starts(tmp_path, monkeypatch):
    tree = tree_with(tmp_path, test_ok=PASSING)
    monkeypatch.setattr(sb, "token_facts", lambda pid: {"is_appcontainer": True, "capabilities": 1})

    with pytest.raises(SandboxError, match="token"):
        sandboxed(tmp_path, tree, ["tests/test_ok.py"])

    logs = tmp_path / "logs"
    assert _read_all(logs) == "" and list((tmp_path / "sandbox").iterdir()) == []   # o processo morreu suspenso: nada rodou


@windows_only
def test_probe_that_reaches_the_canary_stops_the_run_before_the_tests(tmp_path, monkeypatch):
    tree = tree_with(tmp_path, test_ok=PASSING)
    monkeypatch.setattr(sb, "PROBE_SOURCE", 'print(\'{"read_outside": "allowed", "write_outside": "denied", "write_inside": "allowed"}\')\n')

    with pytest.raises(SandboxError, match="leu arquivo fora"):
        sandboxed(tmp_path, tree, ["tests/test_ok.py"])

    assert not (tmp_path / "logs" / "sandbox_t_tests.out").exists()     # os testes nem foram lancados


@windows_only
def test_copied_runtime_runs_pytest_without_the_coordinator_environment(tmp_path):
    facts = sb.copy_runtime(tmp_path / "runtime")

    r = subprocess.run([str(tmp_path / "runtime" / "python.exe"), "-I", "-c",
                        "import sys; sys.path.insert(0, sys.argv[1]); import pytest; print(pytest.__file__)",
                        str(tmp_path / "runtime" / "site")],
                       capture_output=True, text=True, env={"SYSTEMROOT": os.environ["SYSTEMROOT"]}, cwd=tmp_path)

    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()).is_relative_to(tmp_path / "runtime")
    assert facts["python"] == sys.version.split()[0] and not (tmp_path / "runtime" / "Lib" / "site-packages").exists()


# -- falha fechada (qualquer plataforma) -----------------------------------------------------------------------------------
def test_outside_windows_nothing_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "_WINDOWS", False)
    with pytest.raises(SandboxError, match="Windows"):
        sandboxed(tmp_path, tree_with(tmp_path, test_ok=PASSING), ["tests/test_ok.py"])
    assert not (tmp_path / "sandbox").exists()


def test_profile_failure_is_a_sandbox_error_and_no_process_is_launched(tmp_path, monkeypatch):
    launched = []

    def no_profile():
        raise AppContainerError("CreateAppContainerProfile failed: 0x80070005")

    monkeypatch.setattr(sb, "_WINDOWS", True)
    monkeypatch.setattr(sb, "AppContainerProfile", no_profile)
    monkeypatch.setattr(sb.ps, "WindowsJob", lambda *a, **k: launched.append(a))

    with pytest.raises(SandboxError, match="CreateAppContainerProfile"):
        sandboxed(tmp_path, tree_with(tmp_path, test_ok=PASSING), ["tests/test_ok.py"])

    assert not launched and list((tmp_path / "sandbox").iterdir()) == []   # o canario tambem e removido


def test_run_without_selected_tests_is_a_caller_error(tmp_path):
    with pytest.raises(ValueError, match="nenhum teste"):
        sandboxed(tmp_path, tree_with(tmp_path, test_ok=PASSING), [])


OK_PROBE = '{"read_outside": "denied", "write_outside": "denied", "write_inside": "allowed"}'


@pytest.mark.parametrize("exit_code, stdout, intruder, expected", [
    (0, OK_PROBE, False, []),
    (0, OK_PROBE.replace('"read_outside": "denied"', '"read_outside": "allowed"'), False, ["leu arquivo fora do workspace"]),
    (0, OK_PROBE.replace('"write_outside": "denied"', '"write_outside": "allowed"'), False, ["escreveu fora do workspace"]),
    (0, OK_PROBE, True, ["escreveu fora do workspace"]),
    (0, OK_PROBE.replace('"write_inside": "allowed"', '"write_inside": "denied"'), False, ["nao escreveu dentro do workspace"]),
    (0, OK_PROBE + "\nSEGREDO", False, ["sonda sem resultado legivel (exit 0)"]),
    (0, "SEGREDO\n" + OK_PROBE, False, ["conteudo do canario apareceu na saida"]),
    (3, OK_PROBE, False, ["sonda saiu com codigo 3"]),
    (3221225781, "", False, ["sonda sem resultado legivel (exit 3221225781)"]),
    (0, "[1, 2]", False, ["sonda sem resultado legivel (exit 0)"]),
])
def test_canary_gaps_name_every_way_the_probe_can_fail(exit_code, stdout, intruder, expected):
    assert sb.canary_gaps(exit_code, stdout, "SEGREDO", intruder) == expected


@pytest.mark.parametrize("facts, expected", [
    ({"is_appcontainer": True, "capabilities": 0, "canary": DENIED}, True),
    ({"is_appcontainer": False, "capabilities": 0, "canary": DENIED}, False),
    ({"is_appcontainer": True, "capabilities": 1, "canary": DENIED}, False),
    ({"is_appcontainer": True, "capabilities": 0, "canary": {**DENIED, "read_outside": "allowed"}}, False),
    ({"is_appcontainer": True, "capabilities": 0}, False),
    ({"is_appcontainer": 1, "capabilities": 0, "canary": DENIED}, False),
    (None, False),
    ("appcontainer", False),
])
def test_isolation_is_proven_only_by_token_and_canary_together(facts, expected):
    assert sb.proves_isolation(facts) is expected


def test_tree_copy_keeps_only_regular_files_and_counts_them(tmp_path):
    src = tmp_path / "src"
    (src / "a" / "b").mkdir(parents=True)
    (src / "top.py").write_text("x = 1\n", encoding="utf-8")
    (src / "a" / "b" / "deep.txt").write_bytes(b"\x00\x01")

    assert sb._copy_tree(src, tmp_path / "dst") == 2
    assert (tmp_path / "dst" / "a" / "b" / "deep.txt").read_bytes() == b"\x00\x01"


def test_workspace_removal_only_touches_a_sandbox_directory_under_the_root(tmp_path):
    victim = tmp_path / "not_a_sandbox"
    victim.mkdir()
    with pytest.raises(SandboxError, match="fora da raiz"):
        sb._remove_workspace(victim, tmp_path)
    with pytest.raises(SandboxError, match="fora da raiz"):
        sb._remove_workspace(tmp_path / "other" / "sandbox-abc", tmp_path)
    assert victim.exists()


def test_workspace_that_cannot_be_removed_is_reported_not_hidden(tmp_path, monkeypatch):
    ws = tmp_path / "sandbox-abc"
    ws.mkdir()

    def locked(path):
        raise PermissionError("em uso")

    monkeypatch.setattr(sb.shutil, "rmtree", locked)
    assert sb._remove_workspace(ws, tmp_path, retry_delays=(0.0, 0.0)) is False
