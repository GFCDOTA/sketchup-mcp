"""FP-060 MT-04: chama o `run_coordinator_tests` REAL do codex_reviewer sobre esta arvore, dois casos. Uso: mt04_real_run.py <diretorio novo de saida>.
O estado do bridge/governanca vai para o diretorio de saida (nunca para runs/governance de producao). Nenhum Codex e nenhum GitHub aqui."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

out = Path(sys.argv[1])
out.mkdir(parents=True)
os.environ["EVENT_BRIDGE_STATE_PATH"] = str(out / "governance" / "bridge.json")

from tools.orchestration import codex_reviewer as cr  # noqa: E402

repo = Path.cwd()
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=repo).stdout.strip()
dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=repo).stdout.strip()
assert not dirty, "arvore suja: a prova precisa de um commit limpo"

CASES = [
    ("diff que toca o publicador de outbox", ["tools/orchestration/outbox_publisher.py"]),
    ("diff que toca o event_store (inclui testes com multiprocessing)", ["tools/orchestration/event_store.py"]),
]
results = []
for name, files in CASES:
    started = time.monotonic()
    ev = cr.run_coordinator_tests(repo, files, timeout=600)
    seconds = round(time.monotonic() - started, 1)
    summary = ev.get("summary") or ""
    failed = sorted(set(re.findall(r"^FAILED (\S+)", summary, re.MULTILINE)))
    last = next((ln for ln in reversed(summary.splitlines()) if re.search(r"\d+ (passed|failed)", ln)), "")
    sandbox = ev.get("sandbox") or {}
    results.append({
        "caso": name, "arquivos_alterados": files, "testes_selecionados": ev["selected"], "sem_teste_correspondente": ev["uncovered"],
        "isolation": ev["isolation"], "tests_passed": ev["tests_passed"], "exit_code": ev.get("exit_code"), "segundos": seconds,
        "ultima_linha_do_pytest": re.sub(r"\s+", " ", last).strip(" =").strip(),
        "falhas": failed,
        "sandbox": {k: sandbox.get(k) for k in ("is_appcontainer", "capabilities", "canary", "tree_files", "workspace_removed")},
        "dependencias_no_runtime": len((sandbox.get("runtime") or {}).get("distributions") or []),
    })
doc = {"commit": head, "casos": results}
(out / "evidence.json").write_text(json.dumps(doc, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(doc, indent=1, ensure_ascii=True))
