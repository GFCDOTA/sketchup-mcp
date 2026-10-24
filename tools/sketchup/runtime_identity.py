"""Identidade de runtime (FP-055 P1): QUAL codigo esta gerando a planta, antes de gerar.

O achado que motivou isto (2026-10-23): o checkout usado pelo MCP estava 102 commits atras de `origin/develop`, e um servidor ja
em execucao segue com o codigo antigo na memoria mesmo depois de o disco ser atualizado. Tres identidades, comparadas:

  - `code`: o checkout no disco (HEAD, branch, sujo, a frente/atras de `origin/develop` — sem fetch: so o que o git local sabe);
  - `process`: o HEAD que estava no disco quando ESTE processo importou o modulo (servidor MCP iniciado antes de um pull = velho);
  - `bridge`: SHA-256 dos .rb que o SketchUp executa (o job pode rodar outro Ruby que o Python espera).

`check(profile)` decide. `LEGACY_DIAGNOSTIC` nunca bloqueia (so registra). `INTELLIGENT_DRY_RUN` / `INTELLIGENT_BUILD` bloqueiam com
o motivo quando o codigo nao e o esperado — a nao ser que `allow_dev=True` (execucao de desenvolvimento, marcada como tal no
resultado). Erro de git vira `UNKNOWN`, que bloqueia os perfis inteligentes (fail closed).
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from tools.sketchup.paths import REPO_ROOT

PROFILES = ("LEGACY_DIAGNOSTIC", "INTELLIGENT_DRY_RUN", "INTELLIGENT_BUILD")
BRIDGE_FILES = ("tools/sketchup/furnish/place_layout_skp.rb", "tools/sketchup/furnish/place_layout_geom.rb",
                "tools/sketchup/ruby/render_views.rb", "tools/sketchup/ruby/inspect_model.rb",
                "tools/sketchup/ruby/skmcp_launch.rb", "tools/sketchup/shell/build_plan_shell_skp.rb")
UNKNOWN = "UNKNOWN"


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL,
                                       timeout=20).strip()
    except Exception:  # noqa: BLE001 — sem git / timeout: desconhecido, nunca inventado
        return UNKNOWN


def code_identity(root: Path = REPO_ROOT, base: str = "origin/develop") -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD")
    lr = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{base}").split()
    status = _git(root, "status", "--porcelain")
    return {"root": root.as_posix(), "head": head, "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "base": base, "base_head": _git(root, "rev-parse", base),
            "ahead": int(lr[0]) if len(lr) == 2 else None, "behind": int(lr[1]) if len(lr) == 2 else None,
            "dirty": None if status == UNKNOWN else bool(status), "dirty_entries": [] if status == UNKNOWN else status.splitlines()}


def bridge_identity(root: Path = REPO_ROOT) -> dict[str, str]:
    out = {}
    for rel in BRIDGE_FILES:
        p = root / rel
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "MISSING"
    return out


PROCESS_START_HEAD = _git(REPO_ROOT, "rev-parse", "HEAD")      # congelado no import: o codigo que este processo carregou


def identity(root: Path = REPO_ROOT, process_head: str | None = None) -> dict[str, Any]:
    code = code_identity(root)
    proc = process_head if process_head is not None else PROCESS_START_HEAD
    return {"code": code, "process": {"start_head": proc, "stale": proc != code["head"] or proc == UNKNOWN},
            "bridge": bridge_identity(root)}


def check(profile: str, ident: dict[str, Any] | None = None, *, expected_commit: str | None = None,
          allow_dev: bool = False) -> dict[str, Any]:
    if profile not in PROFILES:
        return {"status": "BLOCKED", "profile": profile, "reasons": [f"perfil desconhecido: {profile}"], "identity": ident}
    ident = ident or identity()
    code, reasons = ident["code"], []
    if UNKNOWN in (code["head"], code["base_head"]) or code["dirty"] is None:
        reasons.append("identidade do codigo desconhecida (git indisponivel)")
    if ident["process"]["stale"]:
        reasons.append(f"processo carregou {ident['process']['start_head'][:10]} mas o disco esta em {code['head'][:10]}: "
                       "reiniciar o servidor")
    if expected_commit and code["head"] != expected_commit:
        reasons.append(f"commit esperado {expected_commit[:10]}, checkout em {code['head'][:10]}")
    elif not expected_commit and code["head"] != code["base_head"]:
        reasons.append(f"checkout {code['head'][:10]} != {code['base']} {code['base_head'][:10]} "
                       f"(a frente {code['ahead']}, atras {code['behind']})")
    if code["dirty"]:
        reasons.append(f"checkout sujo ({len(code['dirty_entries'])} entrada(s))")
    if any(v == "MISSING" for v in ident["bridge"].values()):
        reasons.append("arquivo Ruby da ponte ausente")
    if profile == "LEGACY_DIAGNOSTIC":
        status = "OK" if not reasons else "RECORDED"            # nunca bloqueia; nunca publica como validado
    elif not reasons:
        status = "OK"
    else:
        status = "DEV_OVERRIDE" if allow_dev else "BLOCKED"
    return {"status": status, "profile": profile, "reasons": reasons, "identity": ident}
