"""MT-01: o que um AppContainer sem capacidades consegue LER fora do workspace? Mede, nao supoe. Uso: measure_fs_boundary.py <dir novo>.

Cada tentativa de leitura e registrada explicitamente, dentro do sandbox, como uma linha `RESULT {...}` escrita direto no descritor
herdado (`sys.__stdout__`, que o pytest nao captura): NEGADA (PermissionError), PERMITIDA, INEXISTENTE (FileNotFoundError) ou ERRO_<errno>.
O script RECUSA a evidencia se ela estiver incompleta: timeout, erro de coleta, alvo sem RESULT ou duplicado, alvo inexistente ou
com erro diferente de permissao negada, isolamento nao provado, ou arvore suja."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tools.orchestration import sandboxed_tests as sb

out = Path(sys.argv[1])
out.mkdir(parents=True)
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
if subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip():
    sys.exit("arvore suja: a medicao precisa de um commit limpo")

plain = out / "plain_user_file.txt"
plain.write_text("segredo sintetico", encoding="ascii")
shared = out / "ac_readable_file.txt"
shared.write_text("legivel por todo AppContainer", encoding="ascii")
grant = subprocess.run(["icacls", str(shared), "/grant", "*S-1-15-2-1:(R)"], capture_output=True, text=True)   # ALL APPLICATION PACKAGES
if grant.returncode != 0:
    sys.exit("icacls nao concedeu a leitura a ALL APPLICATION PACKAGES")
windir = Path(os.environ["SystemRoot"])
targets = {
    "arquivo_comum_do_usuario": plain,
    "arquivo_do_usuario_com_ACL_ALL_APPLICATION_PACKAGES": shared,
    "windows_system32_cmd": windir / "System32" / "cmd.exe",
    "windows_hosts": windir / "System32" / "drivers" / "etc" / "hosts",
    "program_files_gh": Path(r"C:\Program Files\GitHub CLI\gh.exe"),
}
missing_on_host = [name for name, path in targets.items() if name != "arquivo_comum_do_usuario" and not path.exists()]
if missing_on_host:
    sys.exit(f"alvo inexistente neste host (a medicao seria invalida): {missing_on_host}")

TEMPLATE = '''import json
import sys


def test_{name}_outcome():
    try:
        with open({path!r}, "rb") as handle:
            handle.read(4)
        outcome = "PERMITIDA"
    except PermissionError:
        outcome = "NEGADA"
    except FileNotFoundError:
        outcome = "INEXISTENTE"
    except OSError as exc:
        outcome = "ERRO_%s" % exc.errno
    sys.__stdout__.write("RESULT " + json.dumps({{"alvo": {name!r}, "resultado": outcome}}) + "\\n")
    sys.__stdout__.flush()
'''
tree = out / "tree"
(tree / "tests").mkdir(parents=True)
(tree / "tests" / "test_boundary.py").write_text("\n\n".join(TEMPLATE.format(name=n, path=str(p)) for n, p in targets.items()), encoding="utf-8")

run = sb.run_pytest(tree, ["tests/test_boundary.py"], root=out / "sandbox", ini_text="[pytest]\n", timeout=120.0, log_dir=out / "logs", tag="b")
problems = []
if run.timed_out:
    problems.append("timeout")
if run.exit_code != 0:
    problems.append(f"pytest saiu com {run.exit_code} (erro de coleta ou de execucao)")
if not sb.proves_isolation(run.facts):
    problems.append("isolamento nao provado")
results: dict[str, list[str]] = {}
for found in re.finditer(r"RESULT (\{[^\n]*?\})(?=\s|$)", run.output):          # o pytest imprime pontos no mesmo descritor: sem ancora de linha
    item = json.loads(found.group(1))
    results.setdefault(item["alvo"], []).append(item["resultado"])
for name in targets:
    seen = results.get(name, [])
    if len(seen) != 1:
        problems.append(f"{name}: {len(seen)} resultado(s) em vez de 1")
    elif seen[0] not in ("NEGADA", "PERMITIDA"):
        problems.append(f"{name}: {seen[0]} (nem permitida nem negada por permissao)")
if problems:
    sys.exit("evidencia RECUSADA: " + "; ".join(problems))

report = {"commit": head, "isolamento_provado": True, "exit_code": run.exit_code, "tentativas": len(targets),
          "leitura": {name: results[name][0] for name in targets}}
(out / "evidence.json").write_text(json.dumps(report, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(report, indent=1))
