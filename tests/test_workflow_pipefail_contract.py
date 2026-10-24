"""#533: gate ligado por pipe a `tee` so reprova o job com pipefail; sem `shell: bash` o status do pipeline e o do tee (falso PASS)."""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_every_workflow_that_pipes_a_command_into_tee_runs_with_pipefail():
    offenders = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if not re.search(r"\|\s*tee\b", text):
            continue
        default_bash = re.search(r"^defaults:\s*\n\s+run:\s*\n\s+shell:\s*bash\s*$", text, re.MULTILINE)
        if not default_bash and "pipefail" not in text:
            offenders.append(wf.name)
    assert offenders == [], f"workflows com `| tee` sem pipefail (gate reprovado passaria): {offenders}"
