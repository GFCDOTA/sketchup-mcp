"""MT-01: o que um AppContainer sem capacidades consegue LER fora do workspace? Mede, nao supoe. Uso: measure_fs_boundary.py <dir novo>."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tools.orchestration import sandboxed_tests as sb

out = Path(sys.argv[1])
out.mkdir(parents=True)
plain = out / "plain_user_file.txt"
plain.write_text("segredo sintetico", encoding="ascii")
shared = out / "ac_readable_file.txt"
shared.write_text("legivel por todo AppContainer", encoding="ascii")
grant = subprocess.run(["icacls", str(shared), "/grant", "*S-1-15-2-1:(R)"], capture_output=True, text=True)   # ALL APPLICATION PACKAGES
windir = Path(os.environ["SystemRoot"])
targets = {
    "arquivo_comum_do_usuario": plain,
    "arquivo_do_usuario_com_ACL_ALL_APPLICATION_PACKAGES": shared,
    "windows_system32_cmd": windir / "System32" / "cmd.exe",
    "windows_hosts": windir / "System32" / "drivers" / "etc" / "hosts",
    "program_files_gh": Path(r"C:\Program Files\GitHub CLI\gh.exe"),
}
tree = out / "tree"
(tree / "tests").mkdir(parents=True)
body = "import pytest\n\n\n" + "".join(
    f"def test_{name}_is_readable():\n    with open({str(path)!r}, 'rb') as handle:\n        handle.read(4)\n\n\n" for name, path in targets.items())
(tree / "tests" / "test_boundary.py").write_text(body, encoding="utf-8")

run = sb.run_pytest(tree, ["tests/test_boundary.py"], root=out / "sandbox", ini_text="[pytest]\n", timeout=120.0, log_dir=out / "logs", tag="b")
failed = set(re.findall(r"^FAILED tests/test_boundary.py::test_(\w+?)_is_readable", run.output, re.MULTILINE))
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert not subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip(), "arvore suja"
report = {"commit": head, "icacls_ok": grant.returncode == 0, "isolamento_provado": sb.proves_isolation(run.facts), "exit_code": run.exit_code,
          "leitura": {name: ("NEGADA" if name in failed else "PERMITIDA") for name in targets}}
(out / "evidence.json").write_text(json.dumps(report, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(report, indent=1))
