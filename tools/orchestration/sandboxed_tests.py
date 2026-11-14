"""sandboxed_tests.py — pytest sobre uma arvore NAO confiavel dentro de um AppContainer sem capacidades (FP-060 P2, #606).

Cada execucao e descartavel: perfil AppContainer novo -> workspace novo com DACL protegida (`appcontainer.create_workspace`) ->
copia do interpretador + stdlib + pytest (o Python do coordenador vive no perfil do usuario, que o AppContainer nao le:
medido, o interpretador no lugar morre com STATUS_DLL_NOT_FOUND) -> copia da arvore -> sonda de isolamento -> pytest ->
workspace apagado -> perfil apagado. O processo roda num Job Object kill-on-close (`process_supervisor.WindowsJob`).

O rotulo `ISOLATION` so e devolvido depois de duas provas feitas NAQUELA execucao:
  1. o token do processo criado, lido do kernel, e AppContainer e tem zero capacidades (sem rede, sem bibliotecas do usuario);
  2. uma sonda, no mesmo perfil e workspace, NAO le nem escreve um canario fora do workspace e escreve dentro dele. A sonda
     pega o caso que o token nao mostra: uma raiz cuja ACL de por si liberasse acesso a qualquer AppContainer.
Falha em qualquer etapa levanta `SandboxError` e NENHUM teste roda — nao ha fallback para um processo sem sandbox.

O que isto NAO garante:
  - integridade do resultado: o codigo testado roda no mesmo processo do pytest e controla exit code e saida. O sandbox
    contem o que esse codigo alcanca (arquivos, rede), nao o que ele declara;
  - limpeza se o coordenador morrer no meio: o Job Object mata o processo, mas o perfil e a pasta `sandbox-*` ficam orfaos
    (perfis existentes nunca sao reutilizados nem apagados por nome);
  - limites de CPU, memoria ou disco dentro do workspace."""
from __future__ import annotations

import importlib.metadata as metadata
import json
import os
import re
import shutil
import stat
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from tools.orchestration import process_supervisor as ps
from tools.orchestration.appcontainer import (
    AppContainerError,
    AppContainerProfile,
    create_workspace,
    token_facts,
)

ISOLATION = "appcontainer_no_capabilities"
PROBE_TIMEOUT_S = 30.0
# So `LOCALAPPDATA` e exigido: o Windows o reescreve para a pasta do perfil e, sem ele, CreateProcessW falha com o erro 203
# (medido). `TEMP`/`TMP` tambem sao reescritos. `USERPROFILE` e `APPDATA` nao sao necessarios e ficam de fora.
ENV_NAMES = frozenset({"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LOCALAPPDATA", "TEMP", "TMP"})
RUNTIME_SKIP = ("__pycache__", "site-packages", "test", "tests", "idle_test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3")
_WINDOWS = os.name == "nt"

# `python -I` nao poe nem o cwd nem a pasta do script no sys.path: o bootstrap poe a arvore (cwd) e o pytest copiado.
BOOT_SOURCE = """import os
import sys

sys.path[:0] = [os.getcwd(), sys.argv[1]]
import pytest

sys.exit(pytest.main(sys.argv[2:]))
"""

PROBE_SOURCE = """import json
import sys


def attempt(action, path):
    try:
        with open(path, "rb" if action == "read" else "wb") as handle:
            handle.read() if action == "read" else handle.write(b"x")
    except OSError:
        return "denied"
    return "allowed"


print(json.dumps({"read_outside": attempt("read", sys.argv[1]), "write_outside": attempt("write", sys.argv[2]),
                  "write_inside": attempt("write", sys.argv[3])}))
"""


class SandboxError(RuntimeError):
    """O sandbox nao pode ser montado ou provado. Nenhum teste foi executado fora dele."""


@dataclass(frozen=True)
class SandboxRun:
    exit_code: int | None          # None = estourou o tempo e a arvore de processos foi encerrada
    timed_out: bool
    output: str
    facts: dict


def proves_isolation(facts: object) -> bool:
    """As duas provas de uma execucao: token AppContainer sem capacidades E canario fora do workspace inalcancavel."""
    return (isinstance(facts, dict) and facts.get("is_appcontainer") is True and facts.get("capabilities") == 0
            and facts.get("canary") == {"read_outside": "denied", "write_outside": "denied"})


def canary_gaps(exit_code: int | None, stdout: str, secret: str, intruder_exists: bool) -> list[str]:
    """O que impede de confiar no isolamento, lido da saida da sonda. Lista vazia = sonda aprovada."""
    try:
        seen = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        seen = None
    if not isinstance(seen, dict):
        return [f"sonda sem resultado legivel (exit {exit_code})"]
    gaps = []
    if seen.get("read_outside") != "denied":
        gaps.append("leu arquivo fora do workspace")
    if seen.get("write_outside") != "denied" or intruder_exists:
        gaps.append("escreveu fora do workspace")
    if seen.get("write_inside") != "allowed":
        gaps.append("nao escreveu dentro do workspace")
    if secret in stdout:
        gaps.append("conteudo do canario apareceu na saida")
    if exit_code != 0:
        gaps.append(f"sonda saiu com codigo {exit_code}")
    return gaps


def _copy_distributions(site: Path, names: tuple[str, ...]) -> list[str]:
    from packaging.requirements import Requirement  # dependencia obrigatoria do proprio pytest

    pending, done = list(names), {}
    while pending:
        name = pending.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in done:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError as exc:
            raise SandboxError(f"distribuicao {name} ausente do ambiente do coordenador") from exc
        if dist.files is None:
            raise SandboxError(f"distribuicao {name} sem lista de arquivos (RECORD)")
        for item in dist.files:
            source = Path(dist.locate_file(item))
            if item.is_absolute() or ".." in item.parts or "__pycache__" in item.parts or not source.is_file():
                continue                                     # lancadores em Scripts/ e bytecode ficam de fora
            target = site.joinpath(*item.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        done[key] = dist.version
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return sorted(f"{key}=={version}" for key, version in done.items())


def copy_runtime(dst: Path, base: Path | None = None, dists: tuple[str, ...] = ("pytest",)) -> dict:
    """Copia para `dst` (novo) o interpretador base, a stdlib e `dists` com as dependencias obrigatorias em `dst/site`.
    `copyfile` nao leva atributo somente-leitura nem ACL: os arquivos herdam a DACL do diretorio de destino."""
    base = Path(sys.base_prefix if base is None else base)
    if not (base / "python.exe").is_file() or not (base / "Lib" / "os.py").is_file():
        raise SandboxError(f"interpretador base fora do layout esperado no Windows: {base.name}")
    dst.mkdir()
    for item in base.iterdir():
        if item.is_file() and item.suffix.lower() in (".exe", ".dll"):
            shutil.copyfile(item, dst / item.name)
    if (base / "DLLs").is_dir():
        shutil.copytree(base / "DLLs", dst / "DLLs", copy_function=shutil.copyfile)
    shutil.copytree(base / "Lib", dst / "Lib", ignore=shutil.ignore_patterns(*RUNTIME_SKIP), copy_function=shutil.copyfile)
    (dst / "site").mkdir()
    return {"python": sys.version.split()[0], "distributions": _copy_distributions(dst / "site", dists)}


def _copy_tree(src: Path, dst: Path) -> int:
    """Copia so arquivos regulares e devolve quantos. Link simbolico, juncao ou qualquer outro reparse point recusa a arvore
    inteira: copiar seguindo o link traria para dentro do sandbox, pela mao do coordenador, um arquivo de fora."""
    dst.mkdir()
    count = 0
    with os.scandir(src) as entries:
        for entry in entries:
            info = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise SandboxError(f"link ou reparse point na arvore de testes: {entry.name}")
            if entry.is_dir(follow_symlinks=False):
                count += _copy_tree(Path(entry.path), dst / entry.name)
            elif entry.is_file(follow_symlinks=False):
                shutil.copyfile(entry.path, dst / entry.name)
                count += 1
            else:
                raise SandboxError(f"entrada que nao e arquivo nem diretorio na arvore de testes: {entry.name}")
    return count


def _remove_workspace(ws: Path, root: Path, retry_delays: tuple[float, ...] = (0.0, 0.5, 2.0)) -> bool:
    """Apaga o workspace desta execucao. False = ficou para tras (vai para os fatos da execucao, nao e escondido)."""
    if ws.parent != root or not ws.name.startswith("sandbox-"):
        raise SandboxError(f"workspace fora da raiz do sandbox: {ws.name}")
    for delay in retry_delays:
        time.sleep(delay)
        try:
            shutil.rmtree(ws)
            return True
        except OSError:
            continue
    return False


def _env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key.upper() in ENV_NAMES}
    env["PATH"] = str(Path(os.environ["SYSTEMROOT"]) / "System32")
    return env


def _contained(profile: AppContainerProfile, argv: list[str], cwd: Path, env: dict, out: Path, err: Path,
               timeout: float) -> int | None:
    """Sobe suspenso, confere o token no kernel e so entao deixa rodar. None = tempo esgotado (arvore encerrada)."""
    with ps.WindowsJob(argv, cwd=cwd, env=env, suspended=True, profile=profile, stdout=out, stderr=err) as job:
        seen = token_facts(job.pid)
        if seen != {"is_appcontainer": True, "capabilities": 0}:
            raise SandboxError(f"token do processo nao e AppContainer sem capacidades: {seen}")
        job.resume()
        code = job.wait(timeout)
        if code is None:
            job.terminate()
        return code


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def run_pytest(tree: Path, tests: list[str], *, root: Path, ini_text: str, timeout: float, log_dir: Path, tag: str) -> SandboxRun:
    """Roda `tests` (caminhos relativos a `tree`) sobre uma COPIA de `tree` dentro de um AppContainer sem capacidades.

    `root` recebe o workspace temporario e o canario (ambos removidos ao final); `log_dir` recebe stdout/stderr da sonda e
    dos testes, abertos pelo coordenador e herdados pelo processo — ficam fora do workspace. A arvore original nao e tocada.
    """
    if not tests:
        raise ValueError("nenhum teste selecionado para o sandbox")
    if not _WINDOWS:
        raise SandboxError("AppContainer exige Windows; nenhum teste foi executado")
    root, log_dir = Path(root), Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    secret = uuid.uuid4().hex
    canary, intruder = root / f"canary-{secret[:12]}.txt", root / f"canary-{secret[:12]}.written"
    canary.write_text(secret, encoding="ascii")
    try:
        return _run(Path(tree), tests, root, ini_text, timeout, log_dir, tag, secret, canary, intruder)
    except (AppContainerError, ps.ProcessSupervisorError) as exc:
        raise SandboxError(f"{type(exc).__name__}: {exc}") from exc
    except OSError as exc:                                   # sem o caminho: o motivo vai para evento, log e relatorio
        raise SandboxError(f"{type(exc).__name__}: {exc.strerror or 'erro de E/S'} (errno {exc.errno}, winerror "
                           f"{getattr(exc, 'winerror', None)})") from exc
    finally:
        canary.unlink(missing_ok=True)
        intruder.unlink(missing_ok=True)


def _run(tree: Path, tests: list[str], root: Path, ini_text: str, timeout: float, log_dir: Path, tag: str, secret: str,
         canary: Path, intruder: Path) -> SandboxRun:
    facts: dict = {}
    with AppContainerProfile() as profile:
        ws = create_workspace(profile, root)
        try:
            runtime, work, coordinator = ws / "runtime", ws / "work", ws / "coordinator"
            facts["runtime"] = copy_runtime(runtime)
            facts["tree_files"] = _copy_tree(tree, work)
            coordinator.mkdir()
            ini, boot, probe = coordinator / "pytest.ini", coordinator / "boot.py", coordinator / "probe.py"
            ini.write_text(ini_text, encoding="utf-8")
            boot.write_text(BOOT_SOURCE, encoding="utf-8")
            probe.write_text(PROBE_SOURCE, encoding="utf-8")
            python, env = str(runtime / "python.exe"), _env()
            probe_out, probe_err = log_dir / f"sandbox_{tag}_probe.out", log_dir / f"sandbox_{tag}_probe.err"
            code = _contained(profile, [python, "-I", "-B", str(probe), str(canary), str(intruder), str(coordinator / "probe.written")],
                              work, env, probe_out, probe_err, PROBE_TIMEOUT_S)
            gaps = canary_gaps(code, _read(probe_out), secret, intruder.exists())
            if gaps:
                raise SandboxError("sonda de isolamento reprovada: " + "; ".join(gaps))
            facts.update({"is_appcontainer": True, "capabilities": 0, "canary": {"read_outside": "denied", "write_outside": "denied"}})
            tests_out, tests_err = log_dir / f"sandbox_{tag}_tests.out", log_dir / f"sandbox_{tag}_tests.err"
            # `--confcutdir .`: sem ele o pytest faz stat no pai do workspace ao coletar, e o AppContainer nega (medido).
            # No Windows Server 2025 o AppContainer nao pode abrir o dispositivo nulo (medido no runner do CI; no Windows 11
            # pode), e o pytest o abre em dois pontos. `--capture=sys` evita a captura por descritor, que o abre para o stdin
            # (a saida do teste segue capturada); `--log-file` da ao plugin de logging um arquivo do workspace no lugar dele.
            code = _contained(profile, [python, "-I", "-B", str(boot), str(runtime / "site"), *tests, "-q", "-p", "no:cacheprovider",
                                        "--capture=sys", "--log-file", str(coordinator / "pytest.log"), "-c", str(ini),
                                        "--rootdir", ".", "--confcutdir", "."],
                              work, env, tests_out, tests_err, timeout)
            output = (_read(tests_out) + _read(tests_err)).strip()
        finally:
            facts["workspace_removed"] = _remove_workspace(ws, root)
    return SandboxRun(code, code is None, output, facts)
